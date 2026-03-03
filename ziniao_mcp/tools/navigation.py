"""导航自动化工具 (6 tools)"""

import json

from mcp.server.fastmcp import FastMCP

from ..session import SessionManager


def register_tools(mcp: FastMCP, session: SessionManager) -> None:

    @mcp.tool()
    async def navigate_page(url: str) -> str:
        """导航到指定 URL。

        Args:
            url: 目标 URL（如 "https://www.amazon.com"）
        """
        page = session.get_active_page()
        response = await page.goto(url, wait_until="domcontentloaded")
        status = response.status if response else "unknown"
        title = await page.title()
        return json.dumps({
            "url": page.url,
            "title": title,
            "status": status,
        }, ensure_ascii=False)

    @mcp.tool()
    async def list_pages() -> str:
        """列出当前店铺浏览器的所有标签页。"""
        store = session.get_active_session()
        store.pages = list(store.context.pages)
        result = []
        for i, page in enumerate(store.pages):
            result.append({
                "index": i,
                "url": page.url,
                "title": await page.title(),
                "is_active": i == store.active_page_index,
            })
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def select_page(page_index: int) -> str:
        """切换到指定标签页。

        Args:
            page_index: 标签页索引（从 0 开始，通过 list_pages 查看）
        """
        store = session.get_active_session()
        store.pages = list(store.context.pages)
        if page_index < 0 or page_index >= len(store.pages):
            return f"无效索引 {page_index}，当前共 {len(store.pages)} 个标签页"
        store.active_page_index = page_index
        page = store.pages[page_index]
        await page.bring_to_front()
        session._setup_page_listeners(store, page)
        return json.dumps({
            "index": page_index,
            "url": page.url,
            "title": await page.title(),
        }, ensure_ascii=False)

    @mcp.tool()
    async def new_page(url: str = "") -> str:
        """新建标签页。

        Args:
            url: 可选，新标签页要打开的 URL
        """
        store = session.get_active_session()
        page = await store.context.new_page()
        store.pages = list(store.context.pages)
        store.active_page_index = len(store.pages) - 1
        session._setup_page_listeners(store, page)
        if url:
            await page.goto(url, wait_until="domcontentloaded")
        return json.dumps({
            "index": store.active_page_index,
            "url": page.url,
            "total_pages": len(store.pages),
        }, ensure_ascii=False)

    @mcp.tool()
    async def close_page(page_index: int = -1) -> str:
        """关闭标签页。

        Args:
            page_index: 要关闭的标签页索引，-1 表示关闭当前活动页
        """
        store = session.get_active_session()
        store.pages = list(store.context.pages)
        idx = store.active_page_index if page_index == -1 else page_index
        if idx < 0 or idx >= len(store.pages):
            return f"无效索引 {idx}"
        url = store.pages[idx].url
        await store.pages[idx].close()
        store.pages = list(store.context.pages)
        if store.active_page_index >= len(store.pages):
            store.active_page_index = max(0, len(store.pages) - 1)
        return json.dumps({
            "closed_url": url,
            "remaining_pages": len(store.pages),
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
        page = session.get_active_page()
        if selector:
            await page.locator(selector).wait_for(state=state, timeout=timeout)
            return f"元素 {selector} 已达到状态: {state}"
        await page.wait_for_load_state("networkidle", timeout=timeout)
        return "页面已加载完成"
