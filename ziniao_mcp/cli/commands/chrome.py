"""Chrome browser management commands."""

from __future__ import annotations

from typing import Optional

import typer

from ...chrome_passive import (
    launch_passive_chrome,
    list_passive_target_aliases,
    passive_open_devtools_tab,
)
from ...site_policy import policy_hint_for_url
from .chrome_input_cli import app as chrome_input_app
from .. import get_json_mode, run_command
from ..help_epilog import GROUP_CLI_EPILOG
from ..output import print_result

app = typer.Typer(no_args_is_help=True, epilog=GROUP_CLI_EPILOG)

passive_target_app = typer.Typer(
    no_args_is_help=True,
    help="Passive tab aliases written by ``passive-open --save-as`` (separate from daemon sessions).",
)


@passive_target_app.command("list")
def passive_target_list() -> None:
    """List saved passive targets (alias → port, target id, ws URL)."""
    aliases = list_passive_target_aliases()
    payload = {"ok": True, "aliases": aliases, "count": len(aliases)}
    print_result(payload, json_mode=get_json_mode())


app.add_typer(passive_target_app, name="passive-target")
app.add_typer(
    chrome_input_app,
    name="input",
    help="Raw CDP Input.* only (short WebSocket per command); no daemon. Use after ``passive-open``.",
)


@app.command("launch")
def launch(
    name: Optional[str] = typer.Option(None, "--name", help="Session name."),
    url: Optional[str] = typer.Option(None, "--url", help="URL to open after launch."),
    executable_path: Optional[str] = typer.Option(None, "--executable-path", help="Chrome executable path."),
    cdp_port: int = typer.Option(0, "--port", help="CDP port (0 for auto)."),
    user_data_dir: Optional[str] = typer.Option(None, "--user-data-dir", help="Chrome user data directory."),
    headless: bool = typer.Option(False, "--headless", help="Run in headless mode."),
) -> None:
    """Launch a new Chrome instance."""
    # Coerce to JSON-serializable types (avoid Typer OptionInfo leaking when invoked via shortcut)
    name = name if isinstance(name, str) else ""
    url = url if isinstance(url, str) else ""
    executable_path = executable_path if isinstance(executable_path, str) else ""
    cdp_port = cdp_port if isinstance(cdp_port, int) else 0
    user_data_dir = user_data_dir if isinstance(user_data_dir, str) else ""
    headless = headless if isinstance(headless, bool) else False
    result = run_command("launch_chrome", {
        "name": name,
        "url": url,
        "executable_path": executable_path,
        "cdp_port": cdp_port,
        "user_data_dir": user_data_dir,
        "headless": headless,
    })
    print_result(result, json_mode=get_json_mode())


@app.command("launch-passive")
def launch_passive(
    url: Optional[str] = typer.Option(None, "--url", help="URL to open at Chrome startup."),
    executable_path: Optional[str] = typer.Option(None, "--executable-path", help="Chrome executable path."),
    cdp_port: int = typer.Option(0, "--port", help="CDP port (0 for auto)."),
    user_data_dir: Optional[str] = typer.Option(None, "--user-data-dir", help="Chrome user data directory."),
    headless: bool = typer.Option(False, "--headless", help="Run in headless mode."),
) -> None:
    """Launch Chrome without attaching ziniao/nodriver to the browser."""
    executable_path = executable_path if isinstance(executable_path, str) else ""
    url = url if isinstance(url, str) else ""
    user_data_dir = user_data_dir if isinstance(user_data_dir, str) else ""
    cdp_port = cdp_port if isinstance(cdp_port, int) else 0
    headless = headless if isinstance(headless, bool) else False
    result = launch_passive_chrome(
        executable_path=executable_path,
        cdp_port=cdp_port,
        user_data_dir=user_data_dir,
        headless=headless,
        url=url,
    )
    if url and isinstance(result, dict) and result.get("ok"):
        hint = policy_hint_for_url(url)
        if hint:
            result["policy_hint"] = hint
    print_result(result, json_mode=get_json_mode())


@app.command("connect")
def connect(
    cdp_port: int = typer.Argument(..., help="CDP port to connect to."),
    name: Optional[str] = typer.Option(None, "--name", help="Session name."),
) -> None:
    """Connect to an already running Chrome instance.

    Attaches nodriver and applies stealth/listeners (automation+stealth path).
    For Shopee and similar sites prefer ``launch-passive`` + ``passive-open`` + ``chrome input``.
    """
    result = run_command("connect_chrome", {"cdp_port": cdp_port, "name": name or ""})
    print_result(result, json_mode=get_json_mode())


@app.command("passive-open")
def passive_open(
    url: str = typer.Argument(..., help="URL to open without CDP Runtime attachment."),
    cdp_port: int = typer.Option(9222, "--port", help="Existing Chrome CDP port."),
    save_as: Optional[str] = typer.Option(
        None,
        "--save-as",
        "--target-alias",
        help="Persist target id + webSocketDebuggerUrl for ``ziniao chrome input --alias``.",
    ),
) -> None:
    """Open a URL via DevTools HTTP only.

    This does not start/connect the ziniao daemon and does not inject stealth scripts.
    Use it for sites that react to active CDP Runtime attachment.
    """
    alias = save_as if isinstance(save_as, str) else None
    result = passive_open_devtools_tab(cdp_port, url, save_as=alias or None)
    hint = policy_hint_for_url(url)
    if hint:
        result["policy_hint"] = hint
    print_result(result, json_mode=get_json_mode())


@app.command("list")
def list_chrome() -> None:
    """List Chrome sessions."""
    result = run_command("list_chrome")
    print_result(result, json_mode=get_json_mode())


@app.command("close")
def close_chrome(
    session_id: str = typer.Argument(..., help="Chrome session ID to close."),
) -> None:
    """Close a Chrome session."""
    result = run_command("close_chrome", {"session_id": session_id})
    print_result(result, json_mode=get_json_mode())


def register_top_level(parent: typer.Typer) -> None:
    """Register top-level shortcuts."""

    @parent.command("launch")
    def _launch(
        name: Optional[str] = typer.Option(None, "--name", help="Session name."),
        url: Optional[str] = typer.Option(None, "--url", help="URL to open after launch."),
        executable_path: Optional[str] = typer.Option(None, "--executable-path", help="Chrome executable path."),
        cdp_port: int = typer.Option(0, "--port", help="CDP port (0 for auto)."),
        user_data_dir: Optional[str] = typer.Option(None, "--user-data-dir", help="Chrome user data directory."),
        headless: bool = typer.Option(False, "--headless", help="Run headless."),
    ) -> None:
        """launch [--url] [--headless] [--port] ... — Launch Chrome managed by ziniao. Same as ``ziniao chrome launch``."""
        launch(
            name=name,
            url=url,
            executable_path=executable_path,
            cdp_port=cdp_port,
            user_data_dir=user_data_dir,
            headless=headless,
        )

    @parent.command("connect")
    def _connect(
        cdp_port: int = typer.Argument(..., help="CDP port to connect to."),
        name: Optional[str] = typer.Option(None, "--name", help="Session name."),
    ) -> None:
        """connect <port> [--name] — Attach to running Chrome via CDP. Same as ``ziniao chrome connect``."""
        connect(cdp_port, name)

    @parent.command("launch-passive")
    def _launch_passive(
        url: Optional[str] = typer.Option(None, "--url", help="URL to open at Chrome startup."),
        executable_path: Optional[str] = typer.Option(None, "--executable-path", help="Chrome executable path."),
        cdp_port: int = typer.Option(0, "--port", help="CDP port (0 for auto)."),
        user_data_dir: Optional[str] = typer.Option(None, "--user-data-dir", help="Chrome user data directory."),
        headless: bool = typer.Option(False, "--headless", help="Run headless."),
    ) -> None:
        """launch-passive — Start Chrome without ziniao daemon/CDP Runtime attachment."""
        launch_passive(
            url=url,
            executable_path=executable_path,
            cdp_port=cdp_port,
            user_data_dir=user_data_dir,
            headless=headless,
        )
