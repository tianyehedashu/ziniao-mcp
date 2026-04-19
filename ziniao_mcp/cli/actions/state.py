"""State check action handlers: is_visible, is_enabled, is_checked, scroll, scroll_into."""

from __future__ import annotations

from typing import Any


async def is_visible(sm: Any, args: dict) -> dict:
    selector = args.get("selector", "")
    if not selector:
        return {"error": "selector is required"}
    from ...core.check import is_visible as _is_visible  # pylint: disable=import-outside-toplevel

    return await _is_visible(sm.get_active_tab(), selector)


async def is_enabled(sm: Any, args: dict) -> dict:
    selector = args.get("selector", "")
    if not selector:
        return {"error": "selector is required"}
    from ...core.check import is_enabled as _is_enabled  # pylint: disable=import-outside-toplevel

    return await _is_enabled(sm.get_active_tab(), selector)


async def is_checked(sm: Any, args: dict) -> dict:
    selector = args.get("selector", "")
    if not selector:
        return {"error": "selector is required"}
    from ...core.check import is_checked as _is_checked  # pylint: disable=import-outside-toplevel

    return await _is_checked(sm.get_active_tab(), selector)


async def scroll(sm: Any, args: dict) -> dict:
    from ...core.scroll import scroll as _scroll  # pylint: disable=import-outside-toplevel

    return await _scroll(
        sm.get_active_tab(),
        args.get("direction", "down"),
        args.get("pixels", 300),
        args.get("selector", ""),
    )


async def scroll_into(sm: Any, args: dict) -> dict:
    selector = args.get("selector", "")
    if not selector:
        return {"error": "selector is required"}
    from ...core.scroll import scroll_into as _scroll_into  # pylint: disable=import-outside-toplevel

    return await _scroll_into(sm.get_active_tab(), selector)
