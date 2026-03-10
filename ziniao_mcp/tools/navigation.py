"""导航自动化工具 (4 tools)"""

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
        """管理浏览器标签页。

        Args:
            action: "list" 列出所有标签页 | "switch" 切换到指定标签页 | "new" 新建标签页 | "close" 关闭标签页
            page_index: 标签页索引（switch/close 时使用，-1 表示当前活动页）
            url: 新标签页的 URL（action="new" 时使用，为空则打开空白页）
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
                return f"无效索引 {page_index}，当前共 {len(store.tabs)} 个标签页"
            store.active_tab_index = page_index
            store.iframe_context = None
            t = store.tabs[page_index]
            await t.bring_to_front()
            await session._setup_tab_listeners(store, t)
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
            await session._setup_tab_listeners(store, new_tab)
            return json.dumps({
                "index": store.active_tab_index,
                "url": new_tab.target.url,
                "total_pages": len(store.tabs),
            }, ensure_ascii=False)

        if action == "close":
            store.tabs = _filter_tabs(store.browser.tabs)
            idx = store.active_tab_index if page_index == -1 else page_index
            if idx < 0 or idx >= len(store.tabs):
                return f"无效索引 {idx}"
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

        raise RuntimeError(f"未知 action: {action}，可选值: list, switch, new, close")

    @mcp.tool()
    async def switch_frame(action: str = "list", selector: str = "") -> str:
        """管理 iframe 上下文：列出所有 frame、切换到 iframe、切回主文档。

        切换到 iframe 后，click/fill/hover/evaluate_script 等工具会自动在 iframe 内操作。

        Args:
            action: "list" 列出所有 frame | "switch" 切换到指定 iframe | "main" 切回主文档
            selector: CSS 选择器（action="switch" 时必填，如 "iframe#login"、"iframe[name='content']"）
        """
        from ..iframe import collect_frames, switch_to_frame  # pylint: disable=import-outside-toplevel

        tab = session.get_active_tab()
        store = session.get_active_session()

        if action == "list":
            frames = await collect_frames(tab)
            return json.dumps({"frames": frames}, ensure_ascii=False, indent=2)

        if action == "switch":
            if not selector:
                raise RuntimeError("切换 iframe 需要提供 selector 参数")
            ctx = await switch_to_frame(tab, selector)
            store.iframe_context = ctx
            return json.dumps({
                "frame_id": ctx.frame_id,
                "url": ctx.url,
                "message": f"已切换到 iframe: {selector}",
            }, ensure_ascii=False)

        if action == "main":
            store.iframe_context = None
            return json.dumps({"message": "已切回主文档"}, ensure_ascii=False)

        raise RuntimeError(f"未知 action: {action}，可选值: list, switch, main")

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
                    return f"元素 {selector} 已达到状态: {state}"
                raise RuntimeError(f"等待元素 {selector} 超时")
            elif state in ("hidden", "detached"):
                deadline = asyncio.get_event_loop().time() + timeout_sec
                while asyncio.get_event_loop().time() < deadline:
                    try:
                        elem = await find_element(
                            tab, selector, store, timeout=0.5,
                        )
                        if not elem:
                            return f"元素 {selector} 已达到状态: {state}"
                    except Exception:  # pylint: disable=broad-exception-caught
                        return f"元素 {selector} 已达到状态: {state}"
                    await asyncio.sleep(0.5)
                raise RuntimeError(f"等待元素 {selector} 消失超时")
        await tab.sleep(min(timeout_sec, 5))
        await tab
        return "页面已加载完成"
