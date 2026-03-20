"""Network interception, monitoring, and HAR recording commands."""

from __future__ import annotations

from typing import Optional

import typer

from .. import get_json_mode, run_command
from ..help_epilog import GROUP_CLI_EPILOG
from ..output import print_result

app = typer.Typer(no_args_is_help=True, epilog=GROUP_CLI_EPILOG)


@app.command("route")
def route(
    url_pattern: str = typer.Argument(..., help="URL pattern to intercept (supports * glob)."),
    abort: bool = typer.Option(False, "--abort", help="Block matching requests."),
    body: Optional[str] = typer.Option(None, "--body", help="Mock response body (JSON string or plain text)."),
    status: int = typer.Option(200, "--status", help="Mock response status code."),
    content_type: str = typer.Option("text/plain", "--content-type", help="Mock response Content-Type."),
) -> None:
    """Add a request interception route.

    Examples:
        ziniao network route "*.png" --abort
        ziniao network route "*/api/data" --body '{"mock":true}' --content-type application/json
        ziniao network route "*ads*" --abort
    """
    result = run_command("network_route", {
        "url_pattern": url_pattern,
        "abort": abort,
        "response_status": status,
        "response_body": body or "",
        "response_content_type": content_type,
    })
    print_result(result, json_mode=get_json_mode())


@app.command("unroute")
def unroute(
    url_pattern: Optional[str] = typer.Argument(None, help="URL pattern to remove (omit to remove all)."),
) -> None:
    """Remove request interception route(s).

    If no pattern is specified, all routes are removed.
    """
    result = run_command("network_unroute", {"url_pattern": url_pattern or ""})
    print_result(result, json_mode=get_json_mode())


@app.command("routes")
def routes() -> None:
    """List all active interception routes."""
    result = run_command("network_routes", {})
    print_result(result, json_mode=get_json_mode())


@app.command("list")
def list_requests(
    request_id: int = typer.Option(0, "--id", help="Get details for a specific request ID."),
    url_pattern: Optional[str] = typer.Option(None, "--filter", help="URL substring filter."),
    limit: int = typer.Option(50, "--limit", help="Max items."),
    clear: bool = typer.Option(False, "--clear", help="Clear captured requests."),
) -> None:
    """List captured network requests."""
    if clear:
        result = run_command("network", {"request_id": 0, "url_pattern": "", "limit": 0})
        print_result({"ok": True, "message": "Request history cleared"}, json_mode=get_json_mode())
        return
    result = run_command("network", {
        "request_id": request_id, "url_pattern": url_pattern or "", "limit": limit,
    })
    print_result(result, json_mode=get_json_mode())


@app.command("har-start")
def har_start() -> None:
    """Start recording requests in HAR format."""
    result = run_command("har_start", {})
    print_result(result, json_mode=get_json_mode())


@app.command("har-stop")
def har_stop(
    path: Optional[str] = typer.Argument(None, help="Output file path (default: ~/.ziniao/har/)."),
) -> None:
    """Stop HAR recording and export to file."""
    result = run_command("har_stop", {"path": path or ""})
    print_result(result, json_mode=get_json_mode())
