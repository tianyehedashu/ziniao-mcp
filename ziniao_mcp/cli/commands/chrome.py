"""Chrome browser management commands."""

from __future__ import annotations

from typing import Optional

import typer

from .. import get_json_mode, run_command
from ..help_epilog import GROUP_CLI_EPILOG
from ..output import print_result

app = typer.Typer(no_args_is_help=True, epilog=GROUP_CLI_EPILOG)


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


@app.command("connect")
def connect(
    cdp_port: int = typer.Argument(..., help="CDP port to connect to."),
    name: Optional[str] = typer.Option(None, "--name", help="Session name."),
) -> None:
    """Connect to an already running Chrome instance."""
    result = run_command("connect_chrome", {"cdp_port": cdp_port, "name": name or ""})
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
