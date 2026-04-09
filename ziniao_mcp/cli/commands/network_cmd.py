"""Network interception, monitoring, HAR recording, and page-context fetch commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

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


# ---------------------------------------------------------------------------
# fetch — page-context HTTP requests
# ---------------------------------------------------------------------------

def _parse_headers(raw: List[str]) -> dict:
    """Parse ``["Name:Value", ...]`` into a dict."""
    result = {}
    for h in raw:
        if ":" in h:
            k, v = h.split(":", 1)
            result[k.strip()] = v.strip()
    return result


def _parse_inject(raw: str) -> dict:
    """Parse a single ``--inject`` value into a header_inject entry.

    Accepts either a JSON object string (starts with ``{``) or the compact
    format ``source:key=header`` / ``eval:expression=header``.
    """
    raw = raw.strip()
    if raw.startswith("{"):
        return json.loads(raw)
    # compact: source:key_or_expr=header[:transform]
    eq_pos = raw.find("=")
    if eq_pos < 0:
        raise ValueError(f"Invalid --inject format (missing '='): {raw}")
    left, right = raw[:eq_pos], raw[eq_pos + 1:]
    colon_pos = left.find(":")
    if colon_pos < 0:
        raise ValueError(f"Invalid --inject format (missing source): {raw}")
    source = left[:colon_pos].strip()
    key_or_expr = left[colon_pos + 1:].strip()
    header = right.strip()
    entry: dict = {"source": source, "header": header}
    if source == "eval":
        entry["expression"] = key_or_expr
    else:
        entry["key"] = key_or_expr
    return entry


@app.command("fetch")
def fetch_cmd(
    url: Optional[str] = typer.Argument(None, help="URL to fetch (or use --preset / --file)."),
    preset: Optional[str] = typer.Option(None, "--preset", "-p", help="Site preset ID (e.g. rakuten/rpp-search)."),
    file: Optional[str] = typer.Option(None, "--file", "-f", help="JSON request definition file."),
    script: Optional[str] = typer.Option(None, "--script", help="JS expression (activates js mode)."),
    method: str = typer.Option("GET", "--method", "-X", help="HTTP method."),
    body: Optional[str] = typer.Option(None, "--body", "-d", help="Request body (JSON string)."),
    header: Optional[List[str]] = typer.Option(None, "--header", "-H", help="Header in Name:Value format (repeatable)."),
    inject: Optional[List[str]] = typer.Option(
        None,
        "--inject",
        help='Header injection rule (repeatable). Compact: "cookie:XSRF-TOKEN=x-csrf-token" or JSON object.',
    ),
    var: Optional[List[str]] = typer.Option(None, "--var", "-V", help="Template variable key=value (repeatable)."),
    page: Optional[int] = typer.Option(None, "--page", help="Override page number (paginated preset/file)."),
    fetch_all: bool = typer.Option(False, "--all", help="Fetch and merge all pages (needs pagination in JSON)."),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save response body to file."),
    output_encoding: Optional[str] = typer.Option(
        None, "--output-encoding",
        help="Transcode output to this encoding (e.g. utf-8). Default: write raw bytes.",
    ),
) -> None:
    """Execute an HTTP request in the browser page context.

    Leverages the page's login session (cookies, tokens). Four input modes:

    \b
    1. Preset:  ziniao network fetch -p rakuten/rpp-search -V start_date=2026-03-01
    2. File:    ziniao network fetch -f request.json
    3. CLI:     ziniao network fetch https://example.com/api -X POST -d '{"q":"test"}'
    4. JS mode: ziniao network fetch --script "axios.post('/api', __BODY__)" -d '{"q":"test"}'
    """
    if not url and not preset and not file and not script:
        typer.echo("Error: provide URL, --preset, --file, or --script.", err=True)
        raise typer.Exit(1)

    if fetch_all and page is not None:
        typer.echo("Error: use either --page or --all, not both.", err=True)
        raise typer.Exit(1)

    from ...sites import (  # pylint: disable=import-outside-toplevel
        prepare_request,
        run_site_fetch,
        save_response_body,
    )

    parsed_vars: dict[str, str] = {}
    for v in (var or []):
        if "=" in v:
            k, val = v.split("=", 1)
            parsed_vars[k.strip()] = val.strip()
    if page is not None:
        parsed_vars["page"] = str(page)

    parsed_inject: list[dict] | None = None
    if inject:
        try:
            parsed_inject = [_parse_inject(i) for i in inject]
        except (json.JSONDecodeError, ValueError) as exc:
            typer.echo(f"Error parsing --inject: {exc}", err=True)
            raise typer.Exit(1) from exc

    try:
        spec, plugin = prepare_request(
            preset=preset or "",
            file=file or "",
            script=script or "",
            url=url or "",
            method=method,
            body=body or "",
            headers=_parse_headers(header or []) or None,
            header_inject=parsed_inject,
            var_values=parsed_vars,
        )
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    if not get_json_mode():
        auth = spec.get("auth") or {}
        if auth.get("show_hint", True) and auth.get("hint"):
            typer.echo(typer.style(f"  ℹ {auth['hint']}", dim=True))

    def _fetch_sync(s: dict) -> dict:
        return run_command("page_fetch", s)

    result = run_site_fetch(spec, plugin, _fetch_sync, fetch_all=fetch_all)

    if output and (result.get("body") or result.get("body_b64")):
        typer.echo(save_response_body(
            result.get("body", ""),
            output,
            body_b64=result.get("body_b64", ""),
            content_type=result.get("content_type", ""),
            output_encoding=output_encoding or "",
        ))
        return

    print_result(result, json_mode=get_json_mode())


# ---------------------------------------------------------------------------
# fetch-save — generate request JSON from captured requests
# ---------------------------------------------------------------------------

_AUTO_HEADERS = frozenset({
    "accept-encoding", "connection", "host", "origin", "referer",
    "user-agent", "cookie", "content-length",
})
_AUTO_PREFIXES = ("sec-ch-", "sec-fetch-")

# Lowercase names; first match in *req_headers* wins (preference order).
_CSRF_REQUEST_HEADER_NAMES_ORDERED = (
    "x-xsrf-token",
    "x-csrf-token",
    "csrf-token",
    "x-xsrftoken",
)
_CSRF_HEADER_NAMES_LOWER = frozenset(_CSRF_REQUEST_HEADER_NAMES_ORDERED)


def _is_auto_header(name: str) -> bool:
    low = name.lower()
    return low in _AUTO_HEADERS or any(low.startswith(p) for p in _AUTO_PREFIXES)


@app.command("fetch-save")
def fetch_save(
    request_id: int = typer.Option(0, "--id", help="Captured request ID."),
    url_filter: Optional[str] = typer.Option(None, "--filter", help="URL substring (picks last match)."),
    output: str = typer.Option(..., "--output", "-o", help="Output JSON file path."),
    full_headers: bool = typer.Option(False, "--full-headers", help="Include ALL original request headers."),
    as_preset: bool = typer.Option(False, "--as-preset", help="Add vars/name/description skeleton."),
) -> None:
    """Generate a fetch request JSON file from a captured network request.

    Examples:
        ziniao network fetch-save --id 52 -o rpp.json
        ziniao network fetch-save --filter "api/reports/search" --as-preset -o rpp.json
    """
    if not request_id and not url_filter:
        typer.echo("Error: provide --id or --filter.", err=True)
        raise typer.Exit(1)

    if request_id:
        captured = run_command("network", {"request_id": request_id, "url_pattern": "", "limit": 0})
    else:
        captured = run_command("network", {"request_id": 0, "url_pattern": url_filter or "", "limit": 200})
        if "requests" in captured:
            post_reqs = [r for r in captured["requests"] if r.get("method", "").upper() in ("POST", "PUT", "PATCH")]
            pick = post_reqs[-1] if post_reqs else (captured["requests"][-1] if captured["requests"] else None)
            if not pick:
                typer.echo("Error: no matching request found.", err=True)
                raise typer.Exit(1)
            captured = run_command("network", {"request_id": pick["id"], "url_pattern": "", "limit": 0})

    if "error" in captured:
        typer.echo(f"Error: {captured['error']}", err=True)
        raise typer.Exit(1)

    req_headers = captured.get("request_headers") or {}
    if full_headers:
        headers = dict(req_headers)
    else:
        headers = {k: v for k, v in req_headers.items() if not _is_auto_header(k)}

    spec: dict = {
        "mode": "fetch",
        "url": captured.get("url", ""),
        "method": captured.get("method", "GET"),
    }
    if headers:
        spec["headers"] = headers

    by_lower = {k.lower(): k for k in req_headers}
    found_csrf_orig: Optional[str] = None
    for name in _CSRF_REQUEST_HEADER_NAMES_ORDERED:
        if name in by_lower:
            found_csrf_orig = by_lower[name]
            break
    if found_csrf_orig:
        spec["header_inject"] = [
            {"header": found_csrf_orig, "source": "cookie", "key": "XSRF-TOKEN"}
        ]
        for key in list(headers.keys()):
            if key.lower() in _CSRF_HEADER_NAMES_LOWER:
                headers.pop(key, None)

    post_data = captured.get("post_data", "")
    if post_data:
        try:
            spec["body"] = json.loads(post_data)
        except (json.JSONDecodeError, TypeError):
            spec["body"] = post_data

    if as_preset:
        spec["name"] = ""
        spec["description"] = ""
        spec["vars"] = {}

    Path(output).write_text(
        json.dumps(spec, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    typer.echo(f"Request definition saved to {output}")


