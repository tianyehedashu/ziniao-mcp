"""Navigation automation tools (4 tools)."""

import asyncio
import json

from mcp.server.fastmcp import FastMCP

from ..session import SessionManager, _filter_tabs


def register_tools(mcp: FastMCP, session: SessionManager) -> None:

    @mcp.tool()
    async def navigate_page(url: str) -> str:
        """Navigate the current page to the provided URL.

        Args:
            url: The target URL.
        """
        from nodriver import cdp  # pylint: disable=import-outside-toplevel

        tab = session.get_active_tab()
        frame_id, loader_id, *_ = await tab.send(cdp.page.navigate(url=url))
        await tab
        await tab.sleep(0.5)
        await tab
        title = tab.target.title or ""
        return json.dumps({
            "url": tab.target.url,
            "title": title,
            "status": "ok",
        }, ensure_ascii=False)

    @mcp.tool()
    async def tab(
        action: str = "list",
        page_index: int = -1,
        url: str = "",
    ) -> str:
        """List, switch, create, or close browser tabs.

        Args:
            action: The tab action ("list" | "switch" | "new" | "close").
            page_index: The tab index used by switch and close. Use -1 for the
                active tab.
            url: The URL for action="new". If empty, opens about:blank.
        """
        store = session.get_active_session()

        if action == "list":
            store.tabs = _filter_tabs(store.browser.tabs)
            result = []
            for i, t in enumerate(store.tabs):
                result.append({
                    "index": i,
                    "url": t.target.url,
                    "title": t.target.title or "",
                    "is_active": i == store.active_tab_index,
                })
            return json.dumps(result, ensure_ascii=False, indent=2)

        if action == "switch":
            store.tabs = _filter_tabs(store.browser.tabs)
            if page_index < 0 or page_index >= len(store.tabs):
                return f"Invalid tab index {page_index}. Total tabs: {len(store.tabs)}."
            store.active_tab_index = page_index
            store.iframe_context = None
            t = store.tabs[page_index]
            await t.bring_to_front()
            await session.setup_tab_listeners(store, t)
            return json.dumps({
                "index": page_index,
                "url": t.target.url,
                "title": t.target.title or "",
            }, ensure_ascii=False)

        if action == "new":
            target_url = url or "about:blank"
            new_tab = await store.browser.get(target_url, new_tab=True)
            store.tabs = _filter_tabs(store.browser.tabs)
            store.active_tab_index = len(store.tabs) - 1
            store.iframe_context = None
            await session.setup_tab_listeners(store, new_tab)
            return json.dumps({
                "index": store.active_tab_index,
                "url": new_tab.target.url,
                "total_pages": len(store.tabs),
            }, ensure_ascii=False)

        if action == "close":
            store.tabs = _filter_tabs(store.browser.tabs)
            idx = store.active_tab_index if page_index == -1 else page_index
            if idx < 0 or idx >= len(store.tabs):
                return f"Invalid tab index {idx}."
            closed_url = store.tabs[idx].target.url
            await store.tabs[idx].close()
            await asyncio.sleep(0.3)
            store.tabs = _filter_tabs(store.browser.tabs)
            if store.active_tab_index >= len(store.tabs):
                store.active_tab_index = max(0, len(store.tabs) - 1)
            store.iframe_context = None
            return json.dumps({
                "closed_url": closed_url,
                "remaining_pages": len(store.tabs),
            }, ensure_ascii=False)

        raise RuntimeError(f"Unknown action: {action}. Supported: list, switch, new, close.")

    @mcp.tool()
    async def switch_frame(action: str = "list", selector: str = "") -> str:
        """List frames, switch to an iframe, or switch back to main document.

        After switching, page tools such as click, fill, hover, and
        evaluate_script run inside the selected frame.

        Args:
            action: The frame action ("list" | "switch" | "main").
            selector: The iframe CSS selector used by action="switch".
        """
        from ..iframe import collect_frames, switch_to_frame  # pylint: disable=import-outside-toplevel

        tab = session.get_active_tab()
        store = session.get_active_session()

        if action == "list":
            frames = await collect_frames(tab)
            return json.dumps({"frames": frames}, ensure_ascii=False, indent=2)

        if action == "switch":
            if not selector:
                raise RuntimeError("selector is required for action='switch'.")
            ctx = await switch_to_frame(tab, selector)
            store.iframe_context = ctx
            return json.dumps({
                "frame_id": ctx.frame_id,
                "url": ctx.url,
                "message": f"Switched to iframe: {selector}",
            }, ensure_ascii=False)

        if action == "main":
            store.iframe_context = None
            return json.dumps({"message": "Switched back to main document."}, ensure_ascii=False)

        raise RuntimeError(f"Unknown action: {action}. Supported: list, switch, main.")

    @mcp.tool()
    async def wait_for(
        selector: str = "",
        state: str = "visible",
        timeout: int = 30000,
    ) -> str:
        """Wait for an element state or a short page settle delay.

        Args:
            selector: Optional element selector to wait for. If empty, waits
                for a short settle delay on the current page.
            state: The wait state (visible, hidden, attached, detached).
            timeout: Maximum wait time in milliseconds. Default is 30000.
        """
        from ..iframe import find_element  # pylint: disable=import-outside-toplevel

        tab = session.get_active_tab()
        store = session.get_active_session()
        timeout_sec = timeout / 1000

        if selector:
            if state in ("visible", "attached"):
                elem = await find_element(
                    tab, selector, store, timeout=timeout_sec,
                )
                if elem:
                    return f"Element {selector} reached state: {state}."
                raise RuntimeError(f"Timeout waiting for element: {selector}.")
            elif state in ("hidden", "detached"):
                deadline = asyncio.get_event_loop().time() + timeout_sec
                while asyncio.get_event_loop().time() < deadline:
                    try:
                        elem = await find_element(
                            tab, selector, store, timeout=0.5,
                        )
                        if not elem:
                            return f"Element {selector} reached state: {state}."
                    except Exception:  # pylint: disable=broad-exception-caught
                        return f"Element {selector} reached state: {state}."
                    await asyncio.sleep(0.5)
                raise RuntimeError(f"Timeout waiting for element to disappear: {selector}.")
        await tab.sleep(min(timeout_sec, 5))
        await tab
        return "Wait completed."
