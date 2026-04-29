"""ziniao CLI — command-line interface for Ziniao stores and Chrome browsers.

Entry point registered as ``ziniao`` in pyproject.toml ``[project.scripts]``.
"""

from __future__ import annotations

import os
import sys
from typing import Optional

import typer

from .connection import send_command
from .output import set_cli_json_legacy, set_content_boundaries, set_max_output_chars


def _env_truthy(name: str) -> bool:
    v = os.environ.get(name, "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _get_package_version() -> str:
    """Return installed ziniao package version, or a sentinel if uninstalled."""
    try:
        from importlib.metadata import (  # pylint: disable=import-outside-toplevel
            PackageNotFoundError,
            version,
        )
    except ImportError:  # pragma: no cover — Py<3.8 已不在 requires-python
        return "0.0.0.dev"
    try:
        return version("ziniao")
    except PackageNotFoundError:
        return "0.0.0.dev"


def _version_callback(value: bool) -> None:
    """Eager ``--version`` / ``-V``: 打印后立即退出，不走 daemon / 不解析其它参数。"""
    if value:
        typer.echo(f"ziniao {_get_package_version()}")
        raise typer.Exit(0)


# Paragraph breaks: Rich keeps separate paragraphs readable in root --help.
_CLI_EPILOG = """

[ Global flags ]

See Options above. Typical order: ziniao [OPTIONS] COMMAND [ARGS...]


[ Command layout ]

Flat shortcuts — listed under Commands (navigate, click, snapshot, …).

Grouped — ziniao nav|act|info|get|scroll|store|chrome|session|… (e.g. ziniao nav go URL = ziniao navigate URL).

Group help — ziniao GROUP --help


[ Environment ]

ZINIAO_JSON   ZINIAO_CONTENT_BOUNDARIES   ZINIAO_MAX_OUTPUT

NO_COLOR — when set, disable ANSI colors in terminal output.

""".strip()

app = typer.Typer(
    name="ziniao",
    help="Automate Ziniao stores and Chrome (daemon-backed). Global flags: Options above; commands: table below.",
    epilog=_CLI_EPILOG,
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)

# ---------------------------------------------------------------------------
# Global state shared across commands via typer.Context
# ---------------------------------------------------------------------------

_GLOBAL_STORE: Optional[str] = None
_GLOBAL_SESSION: Optional[str] = None
_GLOBAL_JSON: bool = False
_GLOBAL_JSON_LEGACY: bool = False
_GLOBAL_TIMEOUT: float = 0  # 0 = auto (send_command picks per-command default)
_GLOBAL_TIMEOUT_EXPLICIT: bool = False


def _target_session() -> Optional[str]:
    return _GLOBAL_SESSION or _GLOBAL_STORE


def get_json_mode() -> bool:
    return _GLOBAL_JSON


def get_json_legacy_mode() -> bool:
    return _GLOBAL_JSON_LEGACY


def run_command(command: str, args: dict | None = None) -> dict:
    """Send *command* to the daemon and return the parsed response dict."""
    timeout = _GLOBAL_TIMEOUT if _GLOBAL_TIMEOUT_EXPLICIT else 0
    return send_command(command, args or {}, _target_session(), timeout)


def run_command_with_default_timeout(
    command: str,
    args: dict | None,
    default_timeout: float,
) -> dict:
    """Like :func:`run_command`, but apply *default_timeout* when the user did
    not pass ``--timeout``.

    Precedence (highest → lowest):
    1. CLI ``--timeout`` flag (``_GLOBAL_TIMEOUT_EXPLICIT``)
    2. *default_timeout* (seconds; usually sourced from a preset's
       ``default_timeout_ms`` field)
    3. Daemon auto-default in :func:`send_command`

    Used by long-running presets (e.g. Google Flow reference-image flow with
    uploads) so the preset declares a timeout budget without forcing every
    caller to pass ``--timeout``.
    """
    if _GLOBAL_TIMEOUT_EXPLICIT:
        timeout = _GLOBAL_TIMEOUT
    elif default_timeout and default_timeout > 0:
        timeout = default_timeout
    else:
        timeout = 0
    return send_command(command, args or {}, _target_session(), timeout)


@app.callback()
def _main_callback(
    store: Optional[str] = typer.Option(
        None,
        "--store",
        help='Ziniao store id for this command only (no global session switch). '
        'E.g. ziniao --store mystore click "#ok". Not with --session.',
    ),
    session: Optional[str] = typer.Option(
        None,
        "--session",
        help='Session id (store or Chrome) for this command only. '
        'E.g. ziniao --session abc123 url. Not with --store.',
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help='JSON envelope: success, data, error. '
        'E.g. ziniao --json url | jq .data. Or env ZINIAO_JSON=1.',
    ),
    json_legacy: bool = typer.Option(
        False,
        "--json-legacy",
        help="Raw daemon JSON, no envelope. E.g. ziniao --json-legacy session list. Not with --json.",
    ),
    content_boundaries: bool = typer.Option(
        False,
        "--content-boundaries",
        help="Delimit large page text on stdout: human mode uses ZINIAO_PAGE_CONTENT lines; "
        "with --json adds top-level _boundary. E.g. ziniao --content-boundaries snapshot. "
        "Or ZINIAO_CONTENT_BOUNDARIES=1.",
    ),
    max_output: Optional[int] = typer.Option(
        None,
        "--max-output",
        help="Cap snapshot/eval chars on stdout (default 2000 if unset; 0=unlimited). "
        "E.g. ziniao --max-output 0 snapshot. -o file output is never capped.",
    ),
    timeout: float = typer.Option(
        0,
        "--timeout",
        help="Daemon timeout seconds (0=auto: 120s slow cmds else 60s). E.g. ziniao --timeout 180 navigate URL",
    ),
    # 放在最后，eager=True 保证比其它选项先跑，--version / -V 不会再触发 daemon。
    version: Optional[bool] = typer.Option(  # noqa: ARG001 — 由 callback 处理并 Exit
        None,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show ziniao version and exit.",
    ),
) -> None:
    global _GLOBAL_STORE, _GLOBAL_SESSION, _GLOBAL_JSON, _GLOBAL_JSON_LEGACY  # noqa: PLW0603
    global _GLOBAL_TIMEOUT, _GLOBAL_TIMEOUT_EXPLICIT  # noqa: PLW0603
    if store and session:
        typer.echo("Error: --store and --session are mutually exclusive.", err=True)
        raise typer.Exit(1)
    if json_output and json_legacy:
        typer.echo("Error: use either --json or --json-legacy, not both.", err=True)
        raise typer.Exit(1)

    json_from_env = _env_truthy("ZINIAO_JSON")
    _GLOBAL_JSON = bool(json_output or json_legacy or json_from_env)
    _GLOBAL_JSON_LEGACY = json_legacy
    set_cli_json_legacy(json_legacy)

    boundaries = content_boundaries or _env_truthy("ZINIAO_CONTENT_BOUNDARIES")
    set_content_boundaries(boundaries)

    max_chars = max_output
    if max_chars is None:
        raw_m = os.environ.get("ZINIAO_MAX_OUTPUT", "").strip()
        if raw_m.isdigit():
            max_chars = int(raw_m)
    set_max_output_chars(max_chars)

    _GLOBAL_STORE = store
    _GLOBAL_SESSION = session
    _GLOBAL_TIMEOUT = timeout
    _GLOBAL_TIMEOUT_EXPLICIT = timeout > 0


# ---------------------------------------------------------------------------
# Register command groups
# ---------------------------------------------------------------------------

def _register_commands() -> None:
    from .commands import (  # pylint: disable=import-outside-toplevel
        batch,
        check,
        chrome,
        cluster_cmd,
        config_cmd,
        cookie_vault,
        find,
        flow_cmd,
        get,
        info,
        interact,
        lifecycle,
        mouse,
        navigate,
        network_cmd,
        recorder,
        scroll,
        session,
        site_cmd,
        skill_cmd,
        store,
        update_cmd,
    )
    app.add_typer(store.app, name="store", help="Manage Ziniao stores (list/open/close/…).")
    app.add_typer(
        chrome.app,
        name="chrome",
        help="Chrome (launch/connect/list/close, launch-passive, passive-open, passive-target, input).",
    )
    app.add_typer(config_cmd.app, name="config", help="Configuration (init/show/set/path/env).")
    app.add_typer(session.app, name="session", help="Sessions: Ziniao stores + Chrome.")
    cookie_vault.register_top_level(app)
    cluster_cmd.register_top_level(app)
    app.add_typer(navigate.app, name="nav", help="Navigation (go/tab/wait/back/forward/reload/frame).")
    app.add_typer(interact.app, name="act", help="Page actions (click/fill/type/press/…).")
    app.add_typer(info.app, name="info", help="Inspection (snapshot/screenshot/eval/console/…).")
    app.add_typer(
        recorder.app,
        name="rec",
        help=(
            "Record clicks/fills/navigation in the active tab; stop saves .json + .py under ~/.ziniao/recordings/. "
            "Commands: start, stop [--force], list, view, replay, status, delete."
        ),
    )
    app.add_typer(lifecycle.app, name="sys", help="Daemon lifecycle and emulation.")
    app.add_typer(get.app, name="get", help="Read page/element data (text/url/title/…).")
    app.add_typer(find.app, name="find", help="Find elements by semantic locators.")
    app.add_typer(check.app, name="is", help="Check element state.")
    app.add_typer(scroll.app, name="scroll", help="Scroll page or element into view.")
    app.add_typer(batch.app, name="batch", help="Batch command execution.")
    app.add_typer(mouse.app, name="mouse", help="Mouse control.")
    app.add_typer(network_cmd.app, name="network", help="Network interception, monitoring, HAR & fetch.")
    app.add_typer(
        site_cmd.app,
        name="site",
        help="Site presets (page-context fetch). list/show/fork/enable/disable; see `site list --help` for columns.",
    )

    site_cmd.register_site_commands(app)
    flow_cmd.register_top_level(app)

    app.add_typer(
        skill_cmd.app,
        name="skill",
        help="Manage AI agent skills (install/remove for Cursor, Trae, etc.).",
    )

    # Top-level shortcuts for the most common commands
    store.register_top_level(app)
    chrome.register_top_level(app)
    navigate.register_top_level(app)
    interact.register_top_level(app)
    info.register_top_level(app)
    lifecycle.register_top_level(app)
    get.register_top_level(app)
    scroll.register_top_level(app)

    # ---------------------------------------------------------------------------
    # ziniao version — print version (offline; not via daemon)
    # ---------------------------------------------------------------------------
    @app.command("version")
    def version_cmd() -> None:
        """Show ziniao version and exit (equivalent to ``ziniao --version``)."""
        typer.echo(f"ziniao {_get_package_version()}")

    # ---------------------------------------------------------------------------
    # ziniao update — upgrade CLI via uv (not via daemon)
    # ---------------------------------------------------------------------------
    update_cmd.register(app)

    # ---------------------------------------------------------------------------
    # ziniao serve — start MCP server
    # ---------------------------------------------------------------------------

    @app.command("serve", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
    def serve(ctx: typer.Context) -> None:
        """Start the MCP server.

        All MCP server flags are forwarded as-is, e.g.:
            ziniao serve --config config.yaml --company myco
        """
        # 使用模块级 sys，避免嵌套函数内再次 import sys 触发 reimported
        sys.argv = ["ziniao", "serve"] + ctx.args
        from ..server import main as _serve_main  # pylint: disable=import-outside-toplevel
        _serve_main()


_register_commands()


def main() -> None:
    """CLI entry point."""
    # On Windows, force UTF-8 for stdout/stderr so eval/snapshot output and Rich don't hit GBK encoding errors
    if sys.platform == "win32":
        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8")
            if hasattr(sys.stderr, "reconfigure"):
                sys.stderr.reconfigure(encoding="utf-8")
        except Exception:  # pylint: disable=broad-exception-caught
            pass
    try:
        app()
    except KeyboardInterrupt as exc:
        raise typer.Exit(130) from exc
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)
