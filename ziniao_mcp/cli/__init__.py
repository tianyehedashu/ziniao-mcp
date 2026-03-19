"""ziniao CLI — command-line interface for Ziniao stores and Chrome browsers.

Entry point registered as ``ziniao`` in pyproject.toml ``[project.scripts]``.
"""

from __future__ import annotations

import sys
from typing import Optional

import typer

from .connection import send_command

app = typer.Typer(
    name="ziniao",
    help="CLI for automating Ziniao stores and Chrome browsers via a background daemon.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)

# ---------------------------------------------------------------------------
# Global state shared across commands via typer.Context
# ---------------------------------------------------------------------------

_GLOBAL_STORE: Optional[str] = None
_GLOBAL_SESSION: Optional[str] = None
_GLOBAL_JSON: bool = False
_GLOBAL_TIMEOUT: float = 60.0


def _target_session() -> Optional[str]:
    return _GLOBAL_SESSION or _GLOBAL_STORE


def get_json_mode() -> bool:
    return _GLOBAL_JSON


def run_command(command: str, args: dict | None = None) -> dict:
    """Send *command* to the daemon and return the parsed response dict."""
    return send_command(command, args or {}, _target_session(), _GLOBAL_TIMEOUT)


@app.callback()
def _main_callback(
    store: Optional[str] = typer.Option(
        None, "--store", help="Target a specific Ziniao store without switching the active session.",
    ),
    session: Optional[str] = typer.Option(
        None, "--session", help="Target a specific session (store or Chrome) without switching the active session.",
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output raw JSON instead of formatted text.",
    ),
    timeout: float = typer.Option(
        60.0, "--timeout", help="Command timeout in seconds.",
    ),
) -> None:
    global _GLOBAL_STORE, _GLOBAL_SESSION, _GLOBAL_JSON, _GLOBAL_TIMEOUT  # noqa: PLW0603
    if store and session:
        typer.echo("Error: --store and --session are mutually exclusive.", err=True)
        raise typer.Exit(1)
    _GLOBAL_STORE = store
    _GLOBAL_SESSION = session
    _GLOBAL_JSON = json_output
    _GLOBAL_TIMEOUT = timeout


# ---------------------------------------------------------------------------
# Register command groups
# ---------------------------------------------------------------------------

def _register_commands() -> None:
    from .commands import (  # pylint: disable=import-outside-toplevel
        batch,
        check,
        chrome,
        find,
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
        store,
    )
    app.add_typer(store.app, name="store", help="Manage Ziniao stores.")
    app.add_typer(chrome.app, name="chrome", help="Manage Chrome browser instances.")
    app.add_typer(session.app, name="session", help="Manage browser sessions (Ziniao + Chrome).")
    app.add_typer(navigate.app, name="nav", help="Navigation commands.")
    app.add_typer(interact.app, name="act", help="Page interaction commands.")
    app.add_typer(info.app, name="info", help="Page inspection commands.")
    app.add_typer(recorder.app, name="rec", help="Record and replay browser actions.")
    app.add_typer(lifecycle.app, name="sys", help="Daemon lifecycle and emulation.")
    app.add_typer(get.app, name="get", help="Get element/page information.")
    app.add_typer(find.app, name="find", help="Find elements by semantic locators.")
    app.add_typer(check.app, name="is", help="Check element state.")
    app.add_typer(scroll.app, name="scroll", help="Scroll commands.")
    app.add_typer(batch.app, name="batch", help="Batch command execution.")
    app.add_typer(mouse.app, name="mouse", help="Mouse control.")
    app.add_typer(network_cmd.app, name="network", help="Network interception, monitoring & HAR.")

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
    # ziniao serve — start MCP server (replaces standalone ziniao-mcp command)
    # ---------------------------------------------------------------------------

    @app.command("serve", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
    def serve(ctx: typer.Context) -> None:
        """Start the MCP server (same as the old ziniao-mcp command).

        All MCP server flags are forwarded as-is, e.g.:
            ziniao serve --config config.yaml --company myco
        """
        import sys as _sys  # pylint: disable=import-outside-toplevel
        _sys.argv = ["ziniao-mcp"] + ctx.args
        from ..server import main as _serve_main  # pylint: disable=import-outside-toplevel
        _serve_main()


_register_commands()


def main() -> None:
    """CLI entry point."""
    try:
        app()
    except KeyboardInterrupt:
        raise typer.Exit(130)
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)
