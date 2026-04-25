"""Navigation commands."""

from __future__ import annotations

from typing import Optional

import typer

from .. import get_json_mode, run_command
from ..help_epilog import GROUP_CLI_EPILOG
from ..output import print_result

app = typer.Typer(no_args_is_help=True, epilog=GROUP_CLI_EPILOG)


@app.command("go")
def go_cmd(url: str = typer.Argument(..., help="URL to navigate to.")) -> None:
    """Navigate the active tab to a URL.

    Uses the active daemon session (nodriver). For Shopee-class high-risk hosts prefer
    ``ziniao chrome launch-passive`` → ``passive-open`` → ``ziniao chrome input``; see docs/passive-input-automation.md.

    Examples:
        ziniao nav go https://example.com
        ziniao navigate https://example.com
        ziniao --session mystore nav go https://example.com
    """
    result = run_command("navigate", {"url": url})
    print_result(result, json_mode=get_json_mode())


@app.command("navigate")
def nav_navigate(url: str = typer.Argument(..., help="URL to navigate to.")) -> None:
    """Navigate to a URL (alias for 'nav go')."""
    go_cmd(url)


@app.command("tab")
def tab_cmd(
    action: str = typer.Argument("list", help="Tab action: list, switch, new, close."),
    url_or_index: Optional[str] = typer.Argument(None, help="URL for 'new' tab, or omit for list."),
    page_index: int = typer.Option(-1, "--index", "-i", help="Tab index for switch/close."),
    url: Optional[str] = typer.Option(None, "--url", help="URL for new tab (alternative to positional)."),
) -> None:
    """Manage browser tabs. Use: tab list | tab new [URL] | tab new --url URL."""
    # Allow both 'tab new https://...' and 'tab new --url https://...'
    resolved_url = url or (url_or_index if action == "new" and url_or_index else None) or ""
    result = run_command("tab", {"action": action, "page_index": page_index, "url": resolved_url})
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
    """Wait for an element state or page settle.

    Examples:
        ziniao nav wait "#main"
        ziniao wait ".loader" --timeout 120
        ziniao nav wait --state hidden ".spinner"
    """
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
    def _navigate(url: str = typer.Argument(..., help="URL to open (https:// added if no scheme).")) -> None:
        """navigate <url> — Open URL in the active tab (https:// added if no scheme). Same as ``ziniao nav go``."""
        go_cmd(url)

    @parent.command("tab")
    def _tab(
        action: str = typer.Argument("list", help="Tab action: list, switch, new, close."),
        url_or_index: Optional[str] = typer.Argument(None, help="URL for 'new' tab, or omit for list."),
        page_index: int = typer.Option(-1, "--index", "-i", help="Tab index for switch/close."),
        url: Optional[str] = typer.Option(None, "--url", help="URL for new tab (alternative to positional)."),
    ) -> None:
        """tab [list|new|switch|close] [url] [--index N] [--url U] — Manage tabs. Same as ``ziniao nav tab``."""
        tab_cmd(action, url_or_index, page_index, url)

    @parent.command("wait")
    def _wait(
        selector: Optional[str] = typer.Argument(None, help="Element CSS selector to wait for."),
        state: str = typer.Option("visible", help="Wait state: visible, hidden, attached, detached."),
        timeout: int = typer.Option(30000, help="Timeout in milliseconds."),
    ) -> None:
        """wait [selector] [--state ...] [--timeout MS] — Wait for element state; without selector, short settle sleep. Same as ``ziniao nav wait``."""
        wait_cmd(selector, state=state, timeout=timeout)

    @parent.command("back")
    def _back() -> None:
        """back — Browser back. Same as ``ziniao nav back``."""
        back()

    @parent.command("forward")
    def _forward() -> None:
        """forward — Browser forward. Same as ``ziniao nav forward``."""
        forward()

    @parent.command("reload")
    def _reload(
        ignore_cache: bool = typer.Option(False, "--ignore-cache", help="Bypass browser cache."),
    ) -> None:
        """reload [--ignore-cache] — Reload the page. Same as ``ziniao nav reload``."""
        reload(ignore_cache=ignore_cache)
