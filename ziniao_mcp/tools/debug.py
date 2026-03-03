"""调试工具 (5 tools)"""

import base64
import json

from mcp.server.fastmcp import FastMCP

from ..session import SessionManager


def register_tools(mcp: FastMCP, session: SessionManager) -> None:

    @mcp.tool()
    async def evaluate_script(script: str) -> str:
        """在当前页面执行 JavaScript 代码并返回结果。

        Args:
            script: 要执行的 JavaScript 代码（如 "document.title"、"window.location.href"）
        """
        page = session.get_active_page()
        result = await page.evaluate(script)
        return json.dumps(result, ensure_ascii=False, default=str)

    @mcp.tool()
    async def take_screenshot(selector: str = "", full_page: bool = False) -> str:
        """截取页面或指定元素的截图，返回 base64 编码的 PNG 图片。

        Args:
            selector: 可选，元素选择器。为空则截取整个可视区域
            full_page: 是否截取完整页面（包括滚动区域），仅在无 selector 时生效
        """
        page = session.get_active_page()
        if selector:
            screenshot = await page.locator(selector).screenshot()
        else:
            screenshot = await page.screenshot(full_page=full_page)
        b64 = base64.b64encode(screenshot).decode()
        return f"data:image/png;base64,{b64}"

    @mcp.tool()
    async def take_snapshot() -> str:
        """获取当前页面的完整 HTML 快照。"""
        page = session.get_active_page()
        return await page.content()

    @mcp.tool()
    async def list_console_messages(level: str = "", limit: int = 50) -> str:
        """列出页面控制台消息。从打开店铺或切换页面起自动捕获。

        Args:
            level: 可选，按级别过滤（log、warning、error、info、debug）
            limit: 返回条数上限，默认 50
        """
        store = session.get_active_session()
        messages = store.console_messages
        if level:
            messages = [m for m in messages if m.level == level]
        result = []
        for m in messages[-limit:]:
            result.append({
                "id": m.id,
                "level": m.level,
                "text": m.text[:500],
            })
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def get_console_message(message_id: int) -> str:
        """获取指定控制台消息的完整内容。

        Args:
            message_id: 消息 ID（从 list_console_messages 获取）
        """
        store = session.get_active_session()
        for m in store.console_messages:
            if m.id == message_id:
                return json.dumps({
                    "id": m.id,
                    "level": m.level,
                    "text": m.text,
                    "timestamp": m.timestamp,
                }, ensure_ascii=False, indent=2)
        return f"未找到消息 ID: {message_id}"
