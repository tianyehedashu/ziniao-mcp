"""Find action handlers: find_nth, find_text, find_role."""

from __future__ import annotations

from typing import Any


async def find_nth(sm: Any, args: dict) -> dict:
    selector = args.get("selector", "")
    index = args.get("index", 0)
    action = args.get("action", "click")
    if not selector:
        return {"error": "selector is required"}
    from ...core.find import find_nth as _find_nth  # pylint: disable=import-outside-toplevel

    return await _find_nth(sm.get_active_tab(), selector, index, action)


async def find_text(sm: Any, args: dict) -> dict:
    text = args.get("text", "")
    action = args.get("action", "click")
    tag = args.get("tag", "")
    if not text:
        return {"error": "text is required"}
    from ...core.find import find_text as _find_text  # pylint: disable=import-outside-toplevel

    return await _find_text(sm.get_active_tab(), text, action, tag)


async def find_role(sm: Any, args: dict) -> dict:
    role = args.get("role", "")
    action = args.get("action", "click")
    name = args.get("name", "")
    if not role:
        return {"error": "role is required"}
    from ...core.find import find_role as _find_role  # pylint: disable=import-outside-toplevel

    return await _find_role(sm.get_active_tab(), role, action, name)
