"""Input action handlers: keydown, keyup, mouse_move, mouse_down, mouse_up, mouse_wheel, clipboard."""

from __future__ import annotations

import json
from typing import Any


async def keydown(sm: Any, args: dict) -> dict:
    from nodriver import cdp  # pylint: disable=import-outside-toplevel
    from ...tools._keys import parse_key  # pylint: disable=import-outside-toplevel

    key = args.get("key", "")
    if not key:
        return {"error": "key is required"}
    tab = sm.get_active_tab()
    actual_key, vk, modifiers = parse_key(key)
    await tab.send(
        cdp.input_.dispatch_key_event(
            "rawKeyDown",
            windows_virtual_key_code=vk,
            modifiers=modifiers,
            key=actual_key,
        )
    )
    return {"ok": True, "keydown": key}


async def keyup(sm: Any, args: dict) -> dict:
    from nodriver import cdp  # pylint: disable=import-outside-toplevel
    from ...tools._keys import parse_key  # pylint: disable=import-outside-toplevel

    key = args.get("key", "")
    if not key:
        return {"error": "key is required"}
    tab = sm.get_active_tab()
    actual_key, vk, modifiers = parse_key(key)
    await tab.send(
        cdp.input_.dispatch_key_event(
            "keyUp", windows_virtual_key_code=vk, modifiers=modifiers, key=actual_key
        )
    )
    return {"ok": True, "keyup": key}


async def mouse_move(sm: Any, args: dict) -> dict:
    from nodriver import cdp  # pylint: disable=import-outside-toplevel

    x = args.get("x", 0)
    y = args.get("y", 0)
    tab = sm.get_active_tab()
    await tab.send(cdp.input_.dispatch_mouse_event(type_="mouseMoved", x=x, y=y))
    return {"ok": True, "x": x, "y": y}


async def mouse_down(sm: Any, args: dict) -> dict:
    from nodriver import cdp  # pylint: disable=import-outside-toplevel

    button = args.get("button", "left")
    tab = sm.get_active_tab()
    await tab.send(
        cdp.input_.dispatch_mouse_event(
            type_="mousePressed",
            x=0,
            y=0,
            button=cdp.input_.MouseButton(button),
            click_count=1,
        )
    )
    return {"ok": True, "button": button, "action": "down"}


async def mouse_up(sm: Any, args: dict) -> dict:
    from nodriver import cdp  # pylint: disable=import-outside-toplevel

    button = args.get("button", "left")
    tab = sm.get_active_tab()
    await tab.send(
        cdp.input_.dispatch_mouse_event(
            type_="mouseReleased",
            x=0,
            y=0,
            button=cdp.input_.MouseButton(button),
            click_count=1,
        )
    )
    return {"ok": True, "button": button, "action": "up"}


async def mouse_wheel(sm: Any, args: dict) -> dict:
    from nodriver import cdp  # pylint: disable=import-outside-toplevel

    delta_x = args.get("delta_x", 0)
    delta_y = args.get("delta_y", 0)
    tab = sm.get_active_tab()
    await tab.send(
        cdp.input_.dispatch_mouse_event(
            type_="mouseWheel",
            x=0,
            y=0,
            delta_x=delta_x,
            delta_y=delta_y,
        )
    )
    return {"ok": True, "delta_x": delta_x, "delta_y": delta_y}


async def clipboard(sm: Any, args: dict) -> dict:
    action = args.get("action", "read")
    tab = sm.get_active_tab()

    if action == "read":
        text = await tab.evaluate(
            "navigator.clipboard.readText()", await_promise=True, return_by_value=True
        )
        return {"ok": True, "text": text}
    if action == "write":
        text = args.get("text", "")
        await tab.evaluate(
            f"navigator.clipboard.writeText({json.dumps(text)})",
            await_promise=True,
            return_by_value=True,
        )
        return {"ok": True, "written": len(text)}
    return {"error": f"Unknown clipboard action: {action}"}
