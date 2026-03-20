"""Page inspection commands."""

from __future__ import annotations

from typing import Optional

import typer

from .. import get_json_mode, run_command
from ..help_epilog import GROUP_CLI_EPILOG
from ..output import dumps_cli_json, print_result

app = typer.Typer(no_args_is_help=True, epilog=GROUP_CLI_EPILOG)


@app.command("snapshot")
def snapshot(
    full_page: bool = typer.Option(False, "--full-page", help="Capture full page."),
    selector: Optional[str] = typer.Option(None, "--selector", "-s", help="Limit to a specific element."),
    interactive: bool = typer.Option(False, "--interactive", help="Only show interactive elements (buttons, inputs, links)."),
    compact: bool = typer.Option(False, "--compact", help="Remove scripts/styles/SVG for compact output."),
    out_file: Optional[str] = typer.Option(None, "--out-file", "-o", help="Write output to file (UTF-8), avoids console encoding issues on Windows."),
) -> None:
    """Get the HTML snapshot of the current page.

    Examples:
        ziniao info snapshot
        ziniao snapshot --interactive -o snap.html
        ziniao snapshot --json | jq '.data.html[:200]'
    """
    if selector or interactive or compact:
        result = run_command("snapshot_enhanced", {
            "selector": selector or "", "interactive": interactive, "compact": compact,
        })
    else:
        result = run_command("snapshot", {"full_page": full_page})
    if out_file:
        with open(out_file, "w", encoding="utf-8") as f:
            if get_json_mode():
                f.write(dumps_cli_json(result))
            elif "html" in result:
                f.write(result["html"])
            else:
                f.write(dumps_cli_json(result))
        typer.echo(f"Snapshot written to {out_file}")
    else:
        print_result(result, json_mode=get_json_mode())


@app.command("screenshot")
def screenshot(
    file: Optional[str] = typer.Argument(None, help="Save screenshot to file (optional)."),
    selector: Optional[str] = typer.Option(None, "--selector", "-s", help="Element selector."),
    full_page: bool = typer.Option(False, "--full-page", help="Capture full page."),
) -> None:
    """Capture a screenshot."""
    import base64  # pylint: disable=import-outside-toplevel

    result = run_command("screenshot", {"selector": selector or "", "full_page": full_page})
    if get_json_mode():
        print_result(result, json_mode=True)
        return

    if "error" in result:
        print_result(result)
        return

    if file and "data" in result:
        data_url: str = result["data"]
        b64_part = data_url.split(",", 1)[-1] if "," in data_url else data_url
        raw = base64.b64decode(b64_part)
        with open(file, "wb") as f:
            f.write(raw)
        typer.echo(f"Screenshot saved to {file} ({len(raw)} bytes)")
    else:
        print_result(result)


@app.command("eval")
def eval_cmd(script: str = typer.Argument(..., help="JavaScript to evaluate.")) -> None:
    """Evaluate JavaScript in the current page."""
    result = run_command("eval", {"script": script})
    print_result(result, json_mode=get_json_mode())


@app.command("console")
def console_cmd(
    message_id: int = typer.Option(0, "--id", help="Get details for a specific message ID."),
    level: Optional[str] = typer.Option(None, "--level", help="Filter by level."),
    limit: int = typer.Option(50, "--limit", help="Max items."),
) -> None:
    """List captured console messages."""
    result = run_command("console", {"message_id": message_id, "level": level or "", "limit": limit})
    print_result(result, json_mode=get_json_mode())


@app.command("network")
def network_cmd(
    request_id: int = typer.Option(0, "--id", help="Get details for a specific request ID."),
    url_pattern: Optional[str] = typer.Option(None, "--url-pattern", help="URL substring filter."),
    limit: int = typer.Option(50, "--limit", help="Max items."),
) -> None:
    """List captured network requests."""
    result = run_command("network", {"request_id": request_id, "url_pattern": url_pattern or "", "limit": limit})
    print_result(result, json_mode=get_json_mode())


@app.command("errors")
def errors_cmd(
    limit: int = typer.Option(50, "--limit", help="Max items."),
) -> None:
    """Show uncaught JS errors from the console."""
    result = run_command("errors", {"limit": limit})
    print_result(result, json_mode=get_json_mode())


@app.command("highlight")
def highlight_cmd(
    selector: str = typer.Argument(..., help="CSS selector to highlight."),
) -> None:
    """Highlight elements with a red outline."""
    result = run_command("highlight", {"selector": selector})
    print_result(result, json_mode=get_json_mode())


@app.command("cookies")
def cookies_cmd(
    action: str = typer.Argument("list", help="Action: list, set, clear."),
    name: Optional[str] = typer.Option(None, "--name", help="Cookie name."),
    value: Optional[str] = typer.Option(None, "--value", help="Cookie value."),
    domain: Optional[str] = typer.Option(None, "--domain", help="Cookie domain."),
) -> None:
    """Manage cookies."""
    result = run_command("cookies", {
        "action": action, "name": name or "", "value": value or "", "domain": domain or "",
    })
    print_result(result, json_mode=get_json_mode())


@app.command("storage")
def storage_cmd(
    storage_type: str = typer.Argument("local", help="Storage type: local or session."),
    action: str = typer.Argument("get", help="Action: get, set, clear."),
    key: Optional[str] = typer.Option(None, "--key", "-k", help="Storage key."),
    value: Optional[str] = typer.Option(None, "--value", "-v", help="Storage value (for set)."),
) -> None:
    """Manage localStorage or sessionStorage."""
    result = run_command("storage", {
        "type": storage_type, "action": action, "key": key or "", "value": value or "",
    })
    print_result(result, json_mode=get_json_mode())


@app.command("url")
def url_cmd() -> None:
    """Get the current page URL."""
    result = run_command("get_url", {})
    print_result(result, json_mode=get_json_mode())


@app.command("clipboard")
def clipboard_cmd(
    action: str = typer.Argument("read", help="Action: read or write."),
    text: Optional[str] = typer.Option(None, "--text", help="Text to write (for write action)."),
) -> None:
    """Read or write clipboard content."""
    result = run_command("clipboard", {"action": action, "text": text or ""})
    print_result(result, json_mode=get_json_mode())


def register_top_level(parent: typer.Typer) -> None:
    @parent.command("snapshot")
    def _snapshot(
        full_page: bool = typer.Option(False, "--full-page", help="Capture full page."),
        selector: Optional[str] = typer.Option(None, "--selector", "-s", help="Limit to a specific element."),
        interactive: bool = typer.Option(False, "--interactive", help="Only interactive elements."),
        compact: bool = typer.Option(False, "--compact", help="Compact HTML output."),
        out_file: Optional[str] = typer.Option(None, "--out-file", "-o", help="Write to file (UTF-8)."),
    ) -> None:
        """Get page HTML snapshot. Same options as ``ziniao info snapshot``."""
        snapshot(
            full_page=full_page,
            selector=selector,
            interactive=interactive,
            compact=compact,
            out_file=out_file,
        )

    @parent.command("url")
    def _url() -> None:
        """Get current page URL. Same as ``ziniao info url``."""
        url_cmd()

    @parent.command("screenshot")
    def _screenshot(
        file: Optional[str] = typer.Argument(None, help="Optional path to save PNG."),
        selector: Optional[str] = typer.Option(None, "--selector", "-s", help="Element selector."),
        full_page: bool = typer.Option(False, "--full-page", help="Capture full page."),
    ) -> None:
        """Capture a screenshot. Same options as ``ziniao info screenshot``."""
        screenshot(file, selector, full_page)

    @parent.command("eval")
    def _eval(script: str = typer.Argument(..., help="JavaScript to evaluate.")) -> None:
        """Evaluate JavaScript in the page. Same as ``ziniao info eval``."""
        eval_cmd(script)
