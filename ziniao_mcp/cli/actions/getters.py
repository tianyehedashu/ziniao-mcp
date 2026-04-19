"""Get info action handlers: get_text, get_html, get_value, get_attr, get_title, get_url, get_count."""

from __future__ import annotations

from typing import Any


async def get_text(sm: Any, args: dict) -> dict:
    selector = args.get("selector", "")
    if not selector:
        return {"error": "selector is required"}
    from ...core.get_info import get_text as _get_text  # pylint: disable=import-outside-toplevel

    return await _get_text(sm.get_active_tab(), selector)


async def get_html(sm: Any, args: dict) -> dict:
    selector = args.get("selector", "")
    if not selector:
        return {"error": "selector is required"}
    from ...core.get_info import get_html as _get_html  # pylint: disable=import-outside-toplevel

    return await _get_html(sm.get_active_tab(), selector)


async def get_value(sm: Any, args: dict) -> dict:
    selector = args.get("selector", "")
    if not selector:
        return {"error": "selector is required"}
    from ...core.get_info import get_value as _get_value  # pylint: disable=import-outside-toplevel

    return await _get_value(sm.get_active_tab(), selector)


async def get_attr(sm: Any, args: dict) -> dict:
    selector = args.get("selector", "")
    attribute = args.get("attribute", "")
    if not selector or not attribute:
        return {"error": "selector and attribute are required"}
    from ...core.get_info import get_attr as _get_attr  # pylint: disable=import-outside-toplevel

    return await _get_attr(sm.get_active_tab(), selector, attribute)


async def get_title(sm: Any, args: dict) -> dict:
    from ...core.get_info import get_title as _get_title  # pylint: disable=import-outside-toplevel

    return await _get_title(sm.get_active_tab())


async def get_url(sm: Any, args: dict) -> dict:
    from ...core.get_info import get_url as _get_url  # pylint: disable=import-outside-toplevel

    return await _get_url(sm.get_active_tab())


async def get_count(sm: Any, args: dict) -> dict:
    selector = args.get("selector", "")
    if not selector:
        return {"error": "selector is required"}
    from ...core.get_info import get_count as _get_count  # pylint: disable=import-outside-toplevel

    return await _get_count(sm.get_active_tab(), selector)
