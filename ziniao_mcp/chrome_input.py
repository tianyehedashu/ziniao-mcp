"""Raw CDP over WebSocket: Input.* methods only (no Runtime/DOM/Network)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import websockets

ALLOWED_INPUT_METHODS: frozenset[str] = frozenset(
    {
        "Input.dispatchMouseEvent",
        "Input.dispatchKeyEvent",
        "Input.insertText",
    },
)


def assert_input_only_method(method: str) -> None:
    if method not in ALLOWED_INPUT_METHODS:
        raise ValueError(
            f"CDP method not allowed for input-only client: {method!r} "
            f"(allowed: {sorted(ALLOWED_INPUT_METHODS)})",
        )


async def send_input_only_cdp(
    ws_url: str,
    commands: list[tuple[str, dict[str, Any]]],
    *,
    timeout: float = 30.0,
) -> None:
    """Send a batch of CDP commands; each must be an allowed ``Input.*`` method.

    The whitelist check happens **before** any ``ws.send`` so a single illegal
    method aborts the whole batch without leaking on the wire.

    ``timeout`` is interpreted as a **batch deadline**, not a per-recv timeout —
    CDP may interleave protocol events without an ``id`` (e.g. if Page/Runtime
    were enabled by another client on the same target), and a per-recv timeout
    accumulates linearly with command count in that case.
    """
    if not ws_url.strip():
        raise ValueError("ws_url is required")
    for method, _params in commands:
        assert_input_only_method(method)

    async with websockets.connect(ws_url, max_size=None) as ws:
        n = len(commands)
        for i, (method, params) in enumerate(commands, start=1):
            await ws.send(json.dumps({"id": i, "method": method, "params": params}))
        pending = set(range(1, n + 1))
        errors: list[Any] = []
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(timeout, 0.0)
        while pending:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError(
                    f"input-only CDP timed out after {timeout}s; pending ids={sorted(pending)}",
                )
            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            data: dict[str, Any] = json.loads(raw)
            mid = data.get("id")
            if mid in pending:
                pending.discard(mid)
                if "error" in data:
                    errors.append(data["error"])
            # Non-command messages (CDP events, mismatched ids) are ignored;
            # the batch deadline keeps us bounded even under event spam.
        if errors:
            raise RuntimeError(f"CDP errors: {errors!r}")


def run_input_only_cdp(ws_url: str, commands: list[tuple[str, dict[str, Any]]], *, timeout: float = 30.0) -> None:
    asyncio.run(send_input_only_cdp(ws_url, commands, timeout=timeout))


def input_mouse_click(
    ws_url: str,
    x: float,
    y: float,
    *,
    button: str = "left",
    timeout: float = 30.0,
) -> None:
    btn = button or "left"
    cmds: list[tuple[str, dict[str, Any]]] = [
        ("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y}),
        (
            "Input.dispatchMouseEvent",
            {
                "type": "mousePressed",
                "x": x,
                "y": y,
                "button": btn,
                "buttons": 1,
                "clickCount": 1,
            },
        ),
        (
            "Input.dispatchMouseEvent",
            {
                "type": "mouseReleased",
                "x": x,
                "y": y,
                "button": btn,
                "buttons": 0,
                "clickCount": 1,
            },
        ),
    ]
    run_input_only_cdp(ws_url, cmds, timeout=timeout)


def input_insert_text(ws_url: str, text: str, *, timeout: float = 30.0) -> None:
    run_input_only_cdp(ws_url, [("Input.insertText", {"text": text})], timeout=timeout)


_SPECIAL_KEYS: dict[str, tuple[int, str, str]] = {
    "Enter": (13, "Enter", "Enter"),
    "Tab": (9, "Tab", "Tab"),
    "Escape": (27, "Escape", "Escape"),
    "Backspace": (8, "Backspace", "Backspace"),
    "Delete": (46, "Delete", "Delete"),
    "ArrowUp": (38, "ArrowUp", "ArrowUp"),
    "ArrowDown": (40, "ArrowDown", "ArrowDown"),
    "ArrowLeft": (37, "ArrowLeft", "ArrowLeft"),
    "ArrowRight": (39, "ArrowRight", "ArrowRight"),
}


def input_key(ws_url: str, key: str, *, timeout: float = 30.0) -> None:
    """Single special key by name (Enter, Tab, …) or one Unicode character via ``insertText``."""
    name = (key or "").strip()
    if not name:
        raise ValueError("key is required")
    if name in _SPECIAL_KEYS:
        vk, code, key_id = _SPECIAL_KEYS[name]
        down: dict[str, Any] = {
            "type": "keyDown",
            "windowsVirtualKeyCode": vk,
            "code": code,
            "key": key_id,
        }
        up = dict(down)
        up["type"] = "keyUp"
        run_input_only_cdp(ws_url, [("Input.dispatchKeyEvent", down), ("Input.dispatchKeyEvent", up)], timeout=timeout)
        return
    if len(name) == 1:
        input_insert_text(ws_url, name, timeout=timeout)
        return
    raise ValueError(f"Unknown key {name!r}; use Enter/Tab/… or a single character.")


def input_mouse_wheel(
    ws_url: str,
    *,
    delta_x: float = 0.0,
    delta_y: float = 0.0,
    x: float = 100.0,
    y: float = 100.0,
    timeout: float = 30.0,
) -> None:
    run_input_only_cdp(
        ws_url,
        [
            (
                "Input.dispatchMouseEvent",
                {
                    "type": "mouseWheel",
                    "x": x,
                    "y": y,
                    "deltaX": delta_x,
                    "deltaY": delta_y,
                },
            ),
        ],
        timeout=timeout,
    )
