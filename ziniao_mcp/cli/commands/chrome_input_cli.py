"""``ziniao chrome input`` — raw CDP Input.* only; no daemon / nodriver."""

from __future__ import annotations

from typing import Optional

import typer

from ...chrome_input import (
    input_insert_text,
    input_key,
    input_mouse_click,
    input_mouse_wheel,
)
from ...chrome_passive import (
    load_passive_target_alias,
    resolve_target_ws_url,
    save_passive_target_alias,
)
from ...site_policy import policy_hint_for_url
from .. import get_json_mode
from ..help_epilog import GROUP_CLI_EPILOG
from ..output import print_result

app = typer.Typer(no_args_is_help=True, epilog=GROUP_CLI_EPILOG)


def _resolve_alias_ws(alias: str) -> str:
    """Resolve an alias to a **live** ``webSocketDebuggerUrl``.

    ``passive-open --save-as`` snapshots the ws URL at tab creation time, but
    that URL becomes invalid as soon as the tab is closed or Chrome restarts.
    We always re-resolve via ``/json/list`` (one cheap HTTP roundtrip) and
    rewrite the cache on success — this keeps the alias robust without the
    UX disaster of a ``WebSocket`` connect that hangs against a dead target.

    Raises ``typer.BadParameter`` when the alias is unknown, missing
    ``port``/``target_id``, or the target is no longer present.
    """
    rec = load_passive_target_alias(alias)
    if not rec:
        raise typer.BadParameter(f"Unknown passive target alias: {alias!r}")
    port = rec.get("port")
    target_id = str(rec.get("target_id") or "").strip()
    if not isinstance(port, int) or not target_id:
        cached = str(rec.get("webSocketDebuggerUrl") or "").strip()
        if cached:
            return cached
        raise typer.BadParameter(
            f"Alias {alias!r} record is incomplete (missing port/target_id and webSocketDebuggerUrl).",
        )
    try:
        fresh = resolve_target_ws_url(port, target_id)
    except (RuntimeError, OSError, ValueError) as exc:
        raise typer.BadParameter(
            f"Alias {alias!r} target is no longer live on port {port}: {exc}. "
            "Re-open with ``ziniao chrome passive-open ... --save-as``.",
        ) from exc
    if fresh != str(rec.get("webSocketDebuggerUrl") or ""):
        save_passive_target_alias(
            alias,
            port=port,
            target_id=target_id,
            web_socket_debugger_url=fresh,
            page_url=str(rec.get("page_url") or ""),
        )
    return fresh


def _resolve_ws_url(
    ws_url: Optional[str],
    port: Optional[int],
    target: Optional[str],
    alias: Optional[str],
) -> str:
    if ws_url:
        return ws_url.strip()
    if alias:
        return _resolve_alias_ws(alias)
    if port is not None and target:
        return resolve_target_ws_url(port, target)
    raise typer.BadParameter("Provide --ws-url, or --alias, or both --port and --target.")


def _maybe_policy_hint(ws_url: str, alias: Optional[str]) -> Optional[str]:
    if alias:
        rec = load_passive_target_alias(alias)
        if rec:
            page_url = str(rec.get("page_url") or "")
            return policy_hint_for_url(page_url)
    return None


@app.command("click")
def input_click_cmd(
    x: float = typer.Option(..., "--x", help="Viewport X coordinate."),
    y: float = typer.Option(..., "--y", help="Viewport Y coordinate."),
    ws_url: Optional[str] = typer.Option(None, "--ws-url", help="Page target webSocketDebuggerUrl."),
    port: Optional[int] = typer.Option(None, "--port", help="DevTools HTTP port (with --target)."),
    target: Optional[str] = typer.Option(None, "--target", help="Target id from passive-open."),
    alias: Optional[str] = typer.Option(
        None,
        "--alias",
        "--save-as",
        help="Alias saved via ``passive-open --save-as``.",
    ),
    button: str = typer.Option("left", "--button", help="mouse button: left, right, middle."),
) -> None:
    """Click at (x, y) using ``Input.dispatchMouseEvent`` only."""
    ws = _resolve_ws_url(ws_url, port, target, alias)
    input_mouse_click(ws, x, y, button=button)
    out: dict = {"ok": True, "mode": "input_only", "action": "click", "x": x, "y": y}
    hint = _maybe_policy_hint(ws, alias)
    if hint:
        out["policy_hint"] = hint
    print_result(out, json_mode=get_json_mode())


@app.command("type")
def input_type_cmd(
    text: str = typer.Argument(..., help="Text to insert at the focused element."),
    ws_url: Optional[str] = typer.Option(None, "--ws-url"),
    port: Optional[int] = typer.Option(None, "--port"),
    target: Optional[str] = typer.Option(None, "--target"),
    alias: Optional[str] = typer.Option(None, "--alias", "--save-as"),
) -> None:
    """Insert text via ``Input.insertText``."""
    ws = _resolve_ws_url(ws_url, port, target, alias)
    input_insert_text(ws, text)
    out: dict = {"ok": True, "mode": "input_only", "action": "type", "length": len(text)}
    hint = _maybe_policy_hint(ws, alias)
    if hint:
        out["policy_hint"] = hint
    print_result(out, json_mode=get_json_mode())


@app.command("key")
def input_key_cmd(
    key: str = typer.Argument(..., help="Special key (Enter, Tab, …) or one character."),
    ws_url: Optional[str] = typer.Option(None, "--ws-url"),
    port: Optional[int] = typer.Option(None, "--port"),
    target: Optional[str] = typer.Option(None, "--target"),
    alias: Optional[str] = typer.Option(None, "--alias", "--save-as"),
) -> None:
    """Key down/up via ``Input.dispatchKeyEvent`` or ``Input.insertText`` for one char."""
    ws = _resolve_ws_url(ws_url, port, target, alias)
    input_key(ws, key)
    out: dict = {"ok": True, "mode": "input_only", "action": "key", "key": key}
    hint = _maybe_policy_hint(ws, alias)
    if hint:
        out["policy_hint"] = hint
    print_result(out, json_mode=get_json_mode())


@app.command("scroll")
def input_scroll_cmd(
    delta_y: float = typer.Option(..., "--delta-y", help="Vertical scroll delta (positive = down)."),
    delta_x: float = typer.Option(0.0, "--delta-x", help="Horizontal scroll delta."),
    x: float = typer.Option(100.0, "--x", help="Wheel event X."),
    y: float = typer.Option(100.0, "--y", help="Wheel event Y."),
    ws_url: Optional[str] = typer.Option(None, "--ws-url"),
    port: Optional[int] = typer.Option(None, "--port"),
    target: Optional[str] = typer.Option(None, "--target"),
    alias: Optional[str] = typer.Option(None, "--alias", "--save-as"),
) -> None:
    """Scroll using ``Input.dispatchMouseEvent`` mouseWheel."""
    ws = _resolve_ws_url(ws_url, port, target, alias)
    input_mouse_wheel(ws, delta_x=delta_x, delta_y=delta_y, x=x, y=y)
    out: dict = {
        "ok": True,
        "mode": "input_only",
        "action": "scroll",
        "delta_x": delta_x,
        "delta_y": delta_y,
    }
    hint = _maybe_policy_hint(ws, alias)
    if hint:
        out["policy_hint"] = hint
    print_result(out, json_mode=get_json_mode())
