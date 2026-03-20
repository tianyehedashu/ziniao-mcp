"""Output formatting: Rich tables for humans, raw JSON for machines."""

from __future__ import annotations

import contextvars
import json
import sys
from typing import Any

# Set by CLI callback: when True, --json prints the daemon dict as-is (legacy scripts).
_CLI_JSON_LEGACY: bool = False
_CLI_LLM: bool = False
_CLI_PLAIN: bool = False

_last_daemon_command: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "ziniao_last_daemon_command", default=None,
)


def set_cli_json_legacy(enabled: bool) -> None:
    """Whether ``--json`` / ``--json-legacy`` should skip the success/data/error envelope."""
    global _CLI_JSON_LEGACY  # noqa: PLW0603
    _CLI_JSON_LEGACY = enabled


def set_cli_llm(enabled: bool) -> None:
    """When True and not legacy JSON, envelope includes ``meta`` for LLM-friendly parsing hints."""
    global _CLI_LLM  # noqa: PLW0603
    _CLI_LLM = enabled


def set_cli_plain(enabled: bool) -> None:
    """When True (and not JSON mode), skip Rich and print UTF-8 JSON text for easy copy-paste."""
    global _CLI_PLAIN  # noqa: PLW0603
    _CLI_PLAIN = enabled


def cli_json_uses_legacy() -> bool:
    return _CLI_JSON_LEGACY


def cli_llm_enabled() -> bool:
    return _CLI_LLM


def cli_plain_enabled() -> bool:
    return _CLI_PLAIN


def set_last_daemon_command(name: str) -> None:
    """Record the daemon command name for ``meta.daemon_command`` (set from ``run_command``)."""
    _last_daemon_command.set(name)


def daemon_to_envelope(raw: dict[str, Any]) -> dict[str, Any]:
    """Wrap a daemon response like agent-browser: ``{success, data, error}``."""
    if "error" in raw:
        return {"success": False, "data": None, "error": str(raw["error"])}
    return {"success": True, "data": raw, "error": None}


def _build_llm_meta(envelope: dict[str, Any], daemon_command: str | None) -> dict[str, Any]:
    """Short, stable hints so models know how to interpret ``data`` without guessing."""
    meta: dict[str, Any] = {
        "schema_version": 1,
        "role": "ziniao_cli_response",
        "how_to_read": (
            "If success is true, interpret `data` (object; shape depends on daemon_command). "
            "If success is false, read `error` (string); `data` is null."
        ),
        "docs": "docs/cli-llm.md",
    }
    if daemon_command:
        meta["daemon_command"] = daemon_command

    if envelope.get("success") and isinstance(envelope.get("data"), dict):
        d = envelope["data"]
        keys = sorted(d.keys())
        meta["data_field_names"] = keys[:80]
        if len(keys) > 80:
            meta["data_field_names_truncated"] = True

        if daemon_command in ("snapshot", "snapshot_enhanced"):
            meta["snapshot_semantics"] = (
                "Unlike agent-browser CLI default snapshot (accessibility tree + @refs), ziniao returns HTML in "
                "`data.html` unless using snapshot_enhanced with interactive/compact/selector. "
                "Prefer CSS selectors; with interactive=true check `interactive_elements` if returned."
            )
        elif "html" in d:
            meta["note"] = "`data.html` is an HTML string (length can be large)."

        if isinstance(d.get("data"), str) and str(d["data"]).startswith("data:image"):
            meta["screenshot"] = (
                "`data.data` is a data URL; base64 payload follows the first comma — decode for raw image bytes."
            )

        if "results" in d and "total" in d and "executed" in d and isinstance(d.get("results"), list):
            meta["batch"] = (
                "`data.results` is a list of per-step daemon dicts (not individually enveloped); "
                "each item may contain `error` on failure."
            )

    elif not envelope.get("success"):
        meta["note"] = "Request failed; use `error` string. Optional: retry with `--timeout` or check session."

    return meta


def dumps_cli_json(data: dict[str, Any], *, indent: int = 2) -> str:
    """Serialize for stdout/file when JSON mode is on (envelope unless legacy)."""
    if _CLI_JSON_LEGACY:
        return json.dumps(data, ensure_ascii=False, indent=indent)
    env = daemon_to_envelope(data)
    if _CLI_LLM:
        cmd = _last_daemon_command.get()
        env = {**env, "meta": _build_llm_meta(env, cmd)}
    return json.dumps(env, ensure_ascii=False, indent=indent)


def print_result(data: dict[str, Any], *, json_mode: bool = False) -> None:
    """Print a daemon response dict in the appropriate format."""
    if json_mode:
        print(dumps_cli_json(data))
        return

    if "error" in data:
        if _CLI_PLAIN:
            print(json.dumps({"success": False, "error": str(data["error"])}, ensure_ascii=False, indent=2))
        else:
            _print_error(data["error"])
        return

    if _CLI_PLAIN:
        print(json.dumps(data, ensure_ascii=False, indent=2))
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
        if len(html) > 2000:
            console.print(html[:2000] + "\n... (truncated)")
        else:
            console.print(html)
        return

    if "data" in data and str(data.get("data", "")).startswith("data:image"):
        console.print(f"[green]Screenshot captured[/green] ({len(data['data'])} chars base64)")
        return

    if "result" in data and data.get("ok"):
        result = data["result"]
        if isinstance(result, str) and len(result) > 2000:
            console.print(result[:2000] + "\n... (truncated)")
        else:
            console.print(repr(result) if not isinstance(result, str) else result)
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
