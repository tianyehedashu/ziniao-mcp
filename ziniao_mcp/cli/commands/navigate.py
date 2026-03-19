"""Navigation commands."""

from __future__ import annotations

from typing import Optional

import typer

from .. import get_json_mode, run_command
from ..output import print_result

app = typer.Typer(no_args_is_help=True)


@app.command("go")
def navigate(url: str = typer.Argument(..., help="URL to navigate to.")) -> None:
    """Navigate the active tab to a URL."""
    result = run_command("navigate", {"url": url})
    print_result(result, json_mode=get_json_mode())


@app.command("tab")
def tab_cmd(
    action: str = typer.Argument("list", help="Tab action: list, switch, new, close."),
    page_index: int = typer.Option(-1, "--index", "-i", help="Tab index for switch/close."),
    url: Optional[str] = typer.Option(None, "--url", help="URL for new tab."),
) -> None:
    """Manage browser tabs."""
    result = run_command("tab", {"action": action, "page_index": page_index, "url": url or ""})
    print_result(result, json_mode=get_json_mode())


@app.command("frame")
def frame_cmd(
    action: str = typer.Argument("list", help="Frame action: list, switch, main."),
    selector: Optional[str] = typer.Option(None, "--selector", "-s", help="iframe CSS selector."),
) -> None:
    """Manage iframes."""
    result = run_command("frame", {"action": action, "selector": selector or ""})
    print_result(result, json_mode=get_json_mode())


@app.command("wait")
def wait_cmd(
    selector: Optional[str] = typer.Argument(None, help="Element CSS selector to wait for."),
    state: str = typer.Option("visible", help="Wait state: visible, hidden, attached, detached."),
    timeout: int = typer.Option(30000, help="Timeout in milliseconds."),
) -> None:
    """Wait for an element state or page settle."""
    result = run_command("wait", {"selector": selector or "", "state": state, "timeout": timeout})
    print_result(result, json_mode=get_json_mode())


@app.command("back")
def back() -> None:
    """Navigate back in history."""
    result = run_command("back", {})
    print_result(result, json_mode=get_json_mode())


@app.command("forward")
def forward() -> None:
    """Navigate forward in history."""
    result = run_command("forward", {})
    print_result(result, json_mode=get_json_mode())


@app.command("reload")
def reload(
    ignore_cache: bool = typer.Option(False, "--ignore-cache", help="Bypass browser cache."),
) -> None:
    """Reload the current page."""
    result = run_command("reload", {"ignore_cache": ignore_cache})
    print_result(result, json_mode=get_json_mode())


def register_top_level(parent: typer.Typer) -> None:
    @parent.command("navigate")
    def _navigate(url: str = typer.Argument(...)) -> None:
        """Navigate to a URL."""
        navigate(url)

    @parent.command("tab")
    def _tab(
        action: str = typer.Argument("list"),
        page_index: int = typer.Option(-1, "-i"),
        url: Optional[str] = typer.Option(None, "--url"),
    ) -> None:
        """Manage tabs."""
        tab_cmd(action, page_index, url)

    @parent.command("wait")
    def _wait(
        selector: Optional[str] = typer.Argument(None),
        timeout: int = typer.Option(30000),
    ) -> None:
        """Wait for an element."""
        wait_cmd(selector, timeout=timeout)

    @parent.command("back")
    def _back() -> None:
        """Go back."""
        back()

    @parent.command("forward")
    def _forward() -> None:
        """Go forward."""
        forward()

    @parent.command("reload")
    def _reload() -> None:
        """Reload page."""
        reload()
