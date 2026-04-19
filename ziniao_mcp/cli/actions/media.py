"""Media action handlers: snapshot, screenshot."""

from __future__ import annotations

from typing import Any


async def snapshot(sm: Any, args: dict) -> dict:
    tab = sm.get_active_tab()
    store = sm.get_active_session()
    if store.iframe_context:
        from ...iframe import eval_in_frame  # pylint: disable=import-outside-toplevel

        html = await eval_in_frame(
            tab, store.iframe_context.context_id, "document.documentElement.outerHTML"
        )
        return {"ok": True, "html": html or ""}
    html = await tab.get_content()
    return {"ok": True, "html": html}


async def screenshot(sm: Any, args: dict) -> dict:
    from nodriver import cdp  # pylint: disable=import-outside-toplevel

    selector = args.get("selector", "")
    full_page = args.get("full_page", False)
    tab = sm.get_active_tab()
    store = sm.get_active_session()

    if selector:
        from ...iframe import find_element  # pylint: disable=import-outside-toplevel

        elem = await find_element(tab, selector, store, timeout=10)
        if not elem:
            return {"error": f"Element not found: {selector}"}
        pos = await elem.get_position()
        if not pos:
            return {"error": f"Failed to get position: {selector}"}
        clip = cdp.page.Viewport(
            x=pos.x, y=pos.y, width=pos.width, height=pos.height, scale=1
        )
        data = await tab.send(cdp.page.capture_screenshot(format_="png", clip=clip))
    else:
        data = await tab.send(
            cdp.page.capture_screenshot(
                format_="png", capture_beyond_viewport=full_page
            )
        )
    if not data:
        return {"error": "Screenshot failed"}
    return {"ok": True, "data": f"data:image/png;base64,{data}"}
