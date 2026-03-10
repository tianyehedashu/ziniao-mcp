"""导航自动化工具 (6 tools)"""

import asyncio
import json

from mcp.server.fastmcp import FastMCP

from ..session import SessionManager, _filter_tabs


def register_tools(mcp: FastMCP, session: SessionManager) -> None:

    @mcp.tool()
    async def navigate_page(url: str) -> str:
        """导航到指定 URL。

        Args:
            url: 目标 URL（如 "https://www.amazon.com"）
        """
        from nodriver import cdp  # pylint: disable=import-outside-toplevel

        tab = session.get_active_tab()
        frame_id, loader_id, *_ = await tab.send(cdp.page.navigate(url=url))
        await tab  # wait for events
        await tab.sleep(0.5)
        await tab  # refresh target info
        title = tab.target.title or ""
        return json.dumps({
            "url": tab.target.url,
            "title": title,
            "status": "ok",
        }, ensure_ascii=False)

    @mcp.tool()
    async def list_pages() -> str:
        """列出当前店铺浏览器的所有标签页。"""
        store = session.get_active_session()
        store.tabs = _filter_tabs(store.browser.tabs)
        result = []
        for i, tab in enumerate(store.tabs):
            result.append({
                "index": i,
                "url": tab.target.url,
                "title": tab.target.title or "",
                "is_active": i == store.active_tab_index,
            })
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def select_page(page_index: int) -> str:
        """切换到指定标签页。

        Args:
            page_index: 标签页索引（从 0 开始，通过 list_pages 查看）
        """
        store = session.get_active_session()
        store.tabs = _filter_tabs(store.browser.tabs)
        if page_index < 0 or page_index >= len(store.tabs):
            return f"无效索引 {page_index}，当前共 {len(store.tabs)} 个标签页"
        store.active_tab_index = page_index
        tab = store.tabs[page_index]
        await tab.bring_to_front()
        await session._setup_tab_listeners(store, tab)
        return json.dumps({
            "index": page_index,
            "url": tab.target.url,
            "title": tab.target.title or "",
        }, ensure_ascii=False)

    @mcp.tool()
    async def new_page(url: str = "") -> str:
        """新建标签页。

        Args:
            url: 可选，新标签页要打开的 URL
        """
        store = session.get_active_session()
        target_url = url or "about:blank"
        new_tab = await store.browser.get(target_url, new_tab=True)
        store.tabs = _filter_tabs(store.browser.tabs)
        store.active_tab_index = len(store.tabs) - 1
        await session._setup_tab_listeners(store, new_tab)
        return json.dumps({
            "index": store.active_tab_index,
            "url": new_tab.target.url,
            "total_pages": len(store.tabs),
        }, ensure_ascii=False)

    @mcp.tool()
    async def close_page(page_index: int = -1) -> str:
        """关闭标签页。

        Args:
            page_index: 要关闭的标签页索引，-1 表示关闭当前活动页
        """
        store = session.get_active_session()
        store.tabs = _filter_tabs(store.browser.tabs)
        idx = store.active_tab_index if page_index == -1 else page_index
        if idx < 0 or idx >= len(store.tabs):
            return f"无效索引 {idx}"
        url = store.tabs[idx].target.url
        await store.tabs[idx].close()
        await asyncio.sleep(0.3)
        store.tabs = _filter_tabs(store.browser.tabs)
        if store.active_tab_index >= len(store.tabs):
            store.active_tab_index = max(0, len(store.tabs) - 1)
        return json.dumps({
            "closed_url": url,
            "remaining_pages": len(store.tabs),
        }, ensure_ascii=False)

    @mcp.tool()
    async def wait_for(
        selector: str = "",
        state: str = "visible",
        timeout: int = 30000,
    ) -> str:
        """等待条件满足。

        Args:
            selector: 等待的元素选择器。为空则等待页面加载完成
            state: 等待状态：visible、hidden、attached、detached
            timeout: 超时毫秒数，默认 30000
        """
        tab = session.get_active_tab()
        timeout_sec = timeout / 1000
        if selector:
            if state in ("visible", "attached"):
                elem = await tab.select(selector, timeout=timeout_sec)
                if elem:
                    return f"元素 {selector} 已达到状态: {state}"
                raise RuntimeError(f"等待元素 {selector} 超时")
            elif state in ("hidden", "detached"):
                deadline = asyncio.get_event_loop().time() + timeout_sec
                while asyncio.get_event_loop().time() < deadline:
                    try:
                        elem = await tab.select(selector, timeout=0.5)
                        if not elem:
                            return f"元素 {selector} 已达到状态: {state}"
                    except Exception:
                        return f"元素 {selector} 已达到状态: {state}"
                    await asyncio.sleep(0.5)
                raise RuntimeError(f"等待元素 {selector} 消失超时")
        await tab.sleep(min(timeout_sec, 5))
        await tab
        return "页面已加载完成"
