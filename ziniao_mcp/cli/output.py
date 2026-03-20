"""Output formatting: Rich tables for humans, JSON envelope for machines (agent-browser aligned)."""

from __future__ import annotations

import json
import secrets
import sys
from typing import Any, Optional

# --json-legacy: print raw daemon dict (no envelope).
_CLI_JSON_LEGACY: bool = False
# Mirror agent-browser --content-boundaries / AGENT_BROWSER_CONTENT_BOUNDARIES.
_CLI_CONTENT_BOUNDARIES: bool = False
# Mirror agent-browser --max-output / AGENT_BROWSER_MAX_OUTPUT (character count).
# None = not set on CLI / env: apply DEFAULT_TERMINAL_MAX_OUTPUT_CHARS for stdout paths.
# Explicit 0 or negative = opt out of truncation (full payload to terminal).
_CLI_MAX_OUTPUT_CHARS: Optional[int] = None
# Historical safeguard: large snapshot HTML / eval strings were capped for terminal stability.
DEFAULT_TERMINAL_MAX_OUTPUT_CHARS: int = 2000

_BOUNDARY_NONCE: str | None = None


def set_cli_json_legacy(enabled: bool) -> None:
    """Whether ``--json`` / ``--json-legacy`` should skip the success/data/error envelope."""
    global _CLI_JSON_LEGACY  # noqa: PLW0603
    _CLI_JSON_LEGACY = enabled


def set_content_boundaries(enabled: bool) -> None:
    """Wrap page-like output and add JSON ``_boundary`` (same idea as agent-browser)."""
    global _CLI_CONTENT_BOUNDARIES  # noqa: PLW0603
    _CLI_CONTENT_BOUNDARIES = enabled


def set_max_output_chars(limit: Optional[int]) -> None:
    """Set explicit ``--max-output`` / ``ZINIAO_MAX_OUTPUT`` (None = use default terminal cap).

    ``None`` here means the user did not specify a limit; stdout still uses
    :data:`DEFAULT_TERMINAL_MAX_OUTPUT_CHARS` for snapshot HTML and eval ``result`` strings.
    ``0`` or negative means no truncation when writing to the terminal.
    """
    global _CLI_MAX_OUTPUT_CHARS  # noqa: PLW0603
    _CLI_MAX_OUTPUT_CHARS = limit


def cli_json_uses_legacy() -> bool:
    return _CLI_JSON_LEGACY


def _get_boundary_nonce() -> str:
    global _BOUNDARY_NONCE  # noqa: PLW0603
    if _BOUNDARY_NONCE is None:
        _BOUNDARY_NONCE = secrets.token_hex(16)
    return _BOUNDARY_NONCE


def daemon_to_envelope(raw: dict[str, Any]) -> dict[str, Any]:
    """Wrap a daemon response like agent-browser: ``{success, data, error}``."""
    if "error" in raw:
        return {"success": False, "data": None, "error": str(raw["error"])}
    return {"success": True, "data": raw, "error": None}


def _origin_from_data(data: Any) -> str:
    if isinstance(data, dict):
        return str(data.get("url") or data.get("origin") or "unknown")[:500]
    return "unknown"


def _effective_max_output_limit() -> Optional[int]:
    """Character limit for terminal-oriented output (None = do not truncate)."""
    if _CLI_MAX_OUTPUT_CHARS is None:
        return DEFAULT_TERMINAL_MAX_OUTPUT_CHARS
    if _CLI_MAX_OUTPUT_CHARS <= 0:
        return None
    return _CLI_MAX_OUTPUT_CHARS


def truncate_if_needed(content: str, max_chars: Optional[int]) -> str:
    """Character-based truncation (aligned with agent-browser ``--max-output``)."""
    if max_chars is None or len(content) <= max_chars:
        return content
    total = len(content)
    # Byte-safe slice by char count
    out = content[:max_chars]
    return (
        f"{out}\n[truncated: showing {max_chars} of {total} chars. Use --max-output to adjust]"
    )


def _envelope_with_boundary(envelope: dict[str, Any]) -> dict[str, Any]:
    """Insert top-level ``_boundary`` like agent-browser JSON + content-boundaries."""
    origin = "unknown"
    if envelope.get("success") and isinstance(envelope.get("data"), dict):
        origin = _origin_from_data(envelope["data"])
    return {
        **envelope,
        "_boundary": {"nonce": _get_boundary_nonce(), "origin": origin},
    }


def _truncate_large_fields_deep(obj: Any, limit: int) -> Any:
    """Copy ``obj`` and truncate ``html`` / eval ``result`` strings (e.g. batch ``results[]``)."""
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if k == "html" and isinstance(v, str):
                out[k] = truncate_if_needed(v, limit)
            elif k == "result" and isinstance(v, str) and obj.get("ok"):
                out[k] = truncate_if_needed(v, limit)
            else:
                out[k] = _truncate_large_fields_deep(v, limit)
        return out
    if isinstance(obj, list):
        return [_truncate_large_fields_deep(x, limit) for x in obj]
    return obj


def dumps_cli_json(
    data: dict[str, Any],
    *,
    indent: int = 2,
    terminal_safety: bool = True,
) -> str:
    """Serialize for stdout or file when JSON mode is on (envelope unless legacy).

    When ``terminal_safety`` is True (default), snapshot ``html`` and string ``result`` fields
    are truncated using :func:`_effective_max_output_limit` so megabyte payloads do not
    freeze the terminal. Pass ``terminal_safety=False`` when writing full payloads to a file
    (e.g. ``ziniao info snapshot -o``).
    """
    payload: dict[str, Any] = data
    if terminal_safety:
        lim = _effective_max_output_limit()
        if lim is not None:
            payload = _truncate_large_fields_deep(data, lim)
    if _CLI_JSON_LEGACY:
        return json.dumps(payload, ensure_ascii=False, indent=indent)
    env = daemon_to_envelope(payload)
    if _CLI_CONTENT_BOUNDARIES:
        env = _envelope_with_boundary(env)
    return json.dumps(env, ensure_ascii=False, indent=indent)


def _print_page_markers(origin: str, body: str) -> None:
    nonce = _get_boundary_nonce()
    print(f"--- ZINIAO_PAGE_CONTENT nonce={nonce} origin={origin} ---")
    print(body)
    print(f"--- END_ZINIAO_PAGE_CONTENT nonce={nonce} ---")


def print_result(data: dict[str, Any], *, json_mode: bool = False) -> None:
    """Print a daemon response dict in the appropriate format."""
    if json_mode:
        print(dumps_cli_json(data, terminal_safety=True))
        return

    if "error" in data:
        _print_error(data["error"])
        return

    try:
        from rich.console import Console  # pylint: disable=import-outside-toplevel
        from rich.table import Table  # pylint: disable=import-outside-toplevel
        from rich.panel import Panel  # pylint: disable=import-outside-toplevel
        _print_rich(data)
    except ImportError:
        print(json.dumps(data, ensure_ascii=False, indent=2))


def _print_error(msg: str) -> None:
    try:
        from rich.console import Console  # pylint: disable=import-outside-toplevel
        Console(stderr=True).print(f"[bold red]Error:[/] {msg}")
    except ImportError:
        print(f"Error: {msg}", file=sys.stderr)


def _emit_large_text(*, origin: str, text: str, console: Any) -> None:
    text = truncate_if_needed(text, _effective_max_output_limit())
    if _CLI_CONTENT_BOUNDARIES:
        _print_page_markers(origin, text)
    else:
        console.print(text)


def _print_rich(data: dict) -> None:
    from rich.console import Console  # pylint: disable=import-outside-toplevel
    from rich.table import Table  # pylint: disable=import-outside-toplevel
    console = Console()

    if "sessions" in data and isinstance(data["sessions"], list):
        _print_sessions_table(console, data)
        return

    if "stores" in data and isinstance(data["stores"], list):
        _print_stores_table(console, data)
        return

    if "tabs" in data and isinstance(data["tabs"], list):
        _print_tabs_table(console, data)
        return

    if "messages" in data:
        _print_messages(console, data)
        return

    if "requests" in data:
        _print_requests(console, data)
        return

    if "routes" in data and isinstance(data["routes"], list):
        _print_routes(console, data)
        return

    if "path" in data and data.get("ok") and "entries" in data:
        console.print(f"[green]HAR saved:[/] {data['path']} ({data['entries']} entries)")
        return

    if "active_routes" in data and data.get("ok"):
        action = "[red]ABORT[/]" if data.get("abort") else "[cyan]MOCK[/]"
        console.print(f"Route added: [bold]{data.get('url_pattern')}[/] → {action}  (total: {data['active_routes']})")
        return

    if "removed" in data and data.get("ok") and "remaining_routes" in data:
        console.print(f"Removed {data['removed']} route(s), {data['remaining_routes']} remaining")
        return

    if "text" in data and data.get("ok") and "selector" in data:
        console.print(data["text"])
        return

    if "value" in data and data.get("ok") and "selector" in data:
        console.print(repr(data["value"]))
        return

    if "count" in data and data.get("ok") and "selector" in data:
        console.print(f"[cyan]{data['count']}[/] elements match [dim]{data['selector']}[/]")
        return

    if "title" in data and data.get("ok") and "selector" not in data:
        title_val = data["title"]
        if isinstance(title_val, dict) and "value" in title_val:
            title_val = title_val["value"]
        console.print(title_val)
        return

    if "url" in data and data.get("ok") and "selector" not in data and "clicked" not in data:
        console.print(data["url"])
        return

    if "visible" in data and data.get("ok"):
        state = "[green]visible[/]" if data["visible"] else "[red]not visible[/]"
        console.print(f"{data.get('selector', '')}: {state}")
        return

    if "enabled" in data and data.get("ok"):
        state = "[green]enabled[/]" if data["enabled"] else "[red]disabled[/]"
        console.print(f"{data.get('selector', '')}: {state}")
        return

    if "checked" in data and data.get("ok") and "selector" in data and isinstance(data["checked"], bool):
        state = "[green]checked[/]" if data["checked"] else "[dim]unchecked[/]"
        console.print(f"{data.get('selector', '')}: {state}")
        return

    if "interactive_elements" in data:
        from rich.table import Table as _Tbl  # pylint: disable=import-outside-toplevel
        table = _Tbl(title=f"Interactive Elements ({data.get('count', 0)})")
        table.add_column("Ref", style="cyan")
        table.add_column("Tag")
        table.add_column("Role")
        table.add_column("Type")
        table.add_column("Text")
        for el in data["interactive_elements"]:
            table.add_row(el.get("ref", ""), el.get("tag", ""), el.get("role", ""), el.get("type", ""), el.get("text", "")[:60])
        console.print(table)
        return

    if "errors" in data and isinstance(data["errors"], list):
        from rich.table import Table as _Tbl  # pylint: disable=import-outside-toplevel
        table = _Tbl(title="JS Errors")
        table.add_column("ID", justify="right")
        table.add_column("Text")
        for e in data["errors"]:
            table.add_row(str(e.get("id", "")), e.get("text", "")[:120])
        console.print(table)
        return

    if "cookies" in data and isinstance(data["cookies"], list):
        from rich.table import Table as _Tbl  # pylint: disable=import-outside-toplevel
        table = _Tbl(title="Cookies")
        table.add_column("Name", style="cyan")
        table.add_column("Value")
        table.add_column("Domain")
        for c in data["cookies"]:
            table.add_row(c.get("name", ""), c.get("value", "")[:50], c.get("domain", ""))
        console.print(table)
        return

    if "storage" in data and isinstance(data["storage"], dict):
        from rich.table import Table as _Tbl  # pylint: disable=import-outside-toplevel
        table = _Tbl(title="Storage")
        table.add_column("Key", style="cyan")
        table.add_column("Value")
        for k, v in data["storage"].items():
            table.add_row(k, str(v)[:80])
        console.print(table)
        return

    if "html" in data:
        html = data["html"]
        origin = _origin_from_data(data)
        _emit_large_text(origin=origin, text=html, console=console)
        return

    if "data" in data and str(data.get("data", "")).startswith("data:image"):
        console.print(f"[green]Screenshot captured[/green] ({len(data['data'])} chars base64)")
        return

    if "result" in data and data.get("ok"):
        result = data["result"]
        if isinstance(result, str):
            _emit_large_text(origin="eval", text=result, console=console)
        else:
            console.print(repr(result))
        return

    if "frames" in data and isinstance(data["frames"], list):
        _print_frames_table(console, data)
        return

    for key in ("message", "ok"):
        if key in data:
            if data.get("ok"):
                msg = data.get("message", "")
                extra = {k: v for k, v in data.items() if k not in ("ok", "message")}
                parts = [f"[green]OK[/]"]
                if msg:
                    parts.append(msg)
                for k, v in extra.items():
                    parts.append(f"  {k}: {v}")
                console.print("\n".join(parts))
            else:
                console.print(json.dumps(data, ensure_ascii=False, indent=2))
            return

    console.print(json.dumps(data, ensure_ascii=False, indent=2))


def _print_sessions_table(console: Any, data: dict) -> None:
    from rich.table import Table  # pylint: disable=import-outside-toplevel
    table = Table(title="Sessions")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Type")
    table.add_column("Tabs", justify="right")
    table.add_column("Active")
    for s in data["sessions"]:
        active = "[green]*[/]" if s.get("is_active") else ""
        table.add_row(
            s.get("session_id", ""), s.get("name", ""),
            s.get("type", ""), str(s.get("tabs", "")), active,
        )
    console.print(table)


def _print_stores_table(console: Any, data: dict) -> None:
    from rich.table import Table  # pylint: disable=import-outside-toplevel
    table = Table(title="Stores")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Site")
    table.add_column("Open")
    for s in data["stores"]:
        sid = s.get("browserOauth") or s.get("store_id") or s.get("browserId", "")
        table.add_row(
            sid, s.get("browserName", s.get("store_name", "")),
            s.get("siteName", ""), "[green]yes[/]" if s.get("is_open") else "no",
        )
    console.print(table)


def _print_tabs_table(console: Any, data: dict) -> None:
    from rich.table import Table  # pylint: disable=import-outside-toplevel
    table = Table(title="Tabs")
    table.add_column("#", justify="right")
    table.add_column("URL")
    table.add_column("Title")
    table.add_column("Active")
    for t in data["tabs"]:
        active = "[green]*[/]" if t.get("is_active") else ""
        table.add_row(str(t.get("index", "")), t.get("url", "")[:80], t.get("title", "")[:40], active)
    console.print(table)


def _print_messages(console: Any, data: dict) -> None:
    from rich.table import Table  # pylint: disable=import-outside-toplevel
    table = Table(title="Console Messages")
    table.add_column("ID", justify="right")
    table.add_column("Level")
    table.add_column("Text")
    for m in data["messages"]:
        table.add_row(str(m.get("id", "")), m.get("level", ""), m.get("text", "")[:120])
    console.print(table)


def _print_requests(console: Any, data: dict) -> None:
    from rich.table import Table  # pylint: disable=import-outside-toplevel
    table = Table(title="Network Requests")
    table.add_column("ID", justify="right")
    table.add_column("Method")
    table.add_column("URL")
    table.add_column("Status", justify="right")
    table.add_column("Type")
    for r in data["requests"]:
        table.add_row(
            str(r.get("id", "")), r.get("method", ""),
            r.get("url", "")[:80], str(r.get("status", "")), r.get("resource_type", ""),
        )
    console.print(table)


def _print_routes(console: Any, data: dict) -> None:
    from rich.table import Table  # pylint: disable=import-outside-toplevel
    table = Table(title=f"Active Routes ({data.get('count', 0)})")
    table.add_column("#", justify="right")
    table.add_column("URL Pattern", style="cyan")
    table.add_column("Action")
    table.add_column("Status")
    table.add_column("Body Preview")
    for i, r in enumerate(data["routes"]):
        action = "[red]ABORT[/]" if r.get("abort") else "[green]MOCK[/]"
        status = str(r.get("response_status", "")) if not r.get("abort") else "-"
        body = r.get("response_body_preview", "")[:60] if not r.get("abort") else "-"
        table.add_row(str(i), r.get("url_pattern", ""), action, status, body)
    console.print(table)
    if data.get("fetch_enabled"):
        console.print("[dim]Fetch interception: [green]enabled[/][/]")


def _print_frames_table(console: Any, data: dict) -> None:
    from rich.table import Table  # pylint: disable=import-outside-toplevel
    table = Table(title="Frames")
    table.add_column("#", justify="right")
    table.add_column("Selector")
    table.add_column("URL")
    table.add_column("Name")
    for i, f in enumerate(data["frames"]):
        table.add_row(
            str(i),
            f.get("selector", ""),
            f.get("url", "")[:80],
            f.get("name", ""),
        )
    console.print(table)
