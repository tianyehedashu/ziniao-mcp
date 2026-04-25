"""Chrome browser management commands."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Optional
from urllib import error, parse, request

import typer

from .. import get_json_mode, run_command
from ..help_epilog import GROUP_CLI_EPILOG
from ..output import print_result

app = typer.Typer(no_args_is_help=True, epilog=GROUP_CLI_EPILOG)


def _wait_devtools_http(port: int, timeout: float = 10.0) -> None:
    """Wait until Chrome's DevTools HTTP endpoint is reachable."""
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1.0):
                return
        except (OSError, error.URLError) as exc:
            last_error = exc
            time.sleep(0.2)
    raise RuntimeError(f"Chrome DevTools HTTP endpoint did not start on port {port}") from last_error


def _launch_passive_chrome(
    *,
    executable_path: str,
    cdp_port: int,
    user_data_dir: str,
    headless: bool,
    url: str,
) -> dict:
    """Launch Chrome without attaching nodriver or injecting stealth scripts."""
    from ...session import (  # pylint: disable=import-outside-toplevel
        SessionManager,
        _chrome_user_data_from_env,
        _find_chrome_executable,
        _find_free_port,
    )

    if not executable_path:
        executable_path = _find_chrome_executable()
    if cdp_port <= 0:
        cdp_port = _find_free_port()
    if not user_data_dir:
        user_data_dir = _chrome_user_data_from_env() or str(Path.home() / ".ziniao" / "chrome-passive")
    Path(user_data_dir).mkdir(parents=True, exist_ok=True)

    args = SessionManager._build_chrome_launch_args(
        executable_path=executable_path,
        cdp_port=cdp_port,
        user_data_dir=user_data_dir,
        headless=headless,
        url=url,
    )
    process = subprocess.Popen(  # pylint: disable=consider-using-with
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _wait_devtools_http(cdp_port)
    return {
        "ok": True,
        "mode": "passive",
        "pid": process.pid,
        "cdp_port": cdp_port,
        "user_data_dir": user_data_dir,
        "executable_path": executable_path,
        "attached": False,
        "message": "Chrome launched without ziniao daemon/CDP Runtime attachment.",
    }


def _passive_open_devtools_tab(port: int, url: str, timeout: float = 10.0) -> dict:
    """Open a tab through DevTools HTTP without attaching a Runtime client."""
    encoded_url = parse.quote(url, safe=":/?&=")
    endpoint = f"http://127.0.0.1:{port}/json/new?{encoded_url}"
    req = request.Request(endpoint, method="PUT")
    with request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - local CDP endpoint
        payload = json.loads(resp.read().decode("utf-8"))
    return {
        "ok": True,
        "id": payload.get("id", ""),
        "url": payload.get("url", url),
        "title": payload.get("title", ""),
        "type": payload.get("type", ""),
    }


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
    result = _launch_passive_chrome(
        executable_path=executable_path,
        cdp_port=cdp_port,
        user_data_dir=user_data_dir,
        headless=headless,
        url=url,
    )
    print_result(result, json_mode=get_json_mode())


@app.command("connect")
def connect(
    cdp_port: int = typer.Argument(..., help="CDP port to connect to."),
    name: Optional[str] = typer.Option(None, "--name", help="Session name."),
) -> None:
    """Connect to an already running Chrome instance."""
    result = run_command("connect_chrome", {"cdp_port": cdp_port, "name": name or ""})
    print_result(result, json_mode=get_json_mode())


@app.command("passive-open")
def passive_open(
    url: str = typer.Argument(..., help="URL to open without CDP Runtime attachment."),
    cdp_port: int = typer.Option(9222, "--port", help="Existing Chrome CDP port."),
) -> None:
    """Open a URL via DevTools HTTP only.

    This does not start/connect the ziniao daemon and does not inject stealth scripts.
    Use it for sites that react to active CDP Runtime attachment.
    """
    result = _passive_open_devtools_tab(cdp_port, url)
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
