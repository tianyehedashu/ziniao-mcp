"""输入自动化工具 (9 tools)"""

import json

from mcp.server.fastmcp import FastMCP

from ..session import SessionManager


def register_tools(mcp: FastMCP, session: SessionManager) -> None:

    @mcp.tool()
    async def click(selector: str) -> str:
        """点击页面元素。

        Args:
            selector: CSS 选择器、XPath 或 Playwright 选择器（如 "text=登录"、"#submit-btn"）
        """
        page = session.get_active_page()
        await page.locator(selector).click()
        return f"已点击: {selector}"

    @mcp.tool()
    async def fill(selector: str, value: str) -> str:
        """清空并填写输入框。

        Args:
            selector: 输入框的选择器
            value: 要填入的值
        """
        page = session.get_active_page()
        await page.locator(selector).fill(value)
        return f"已填写 {selector}"

    @mcp.tool()
    async def fill_form(fields_json: str) -> str:
        """批量填写表单字段。

        Args:
            fields_json: JSON 格式的字段列表，如 [{"selector": "#name", "value": "张三"}, {"selector": "#email", "value": "a@b.com"}]
        """
        page = session.get_active_page()
        fields = json.loads(fields_json)
        for f in fields:
            await page.locator(f["selector"]).fill(f["value"])
        return f"已填写 {len(fields)} 个字段"

    @mcp.tool()
    async def type_text(text: str, selector: str = "") -> str:
        """逐字输入文本（模拟真实键盘打字），适用于需要触发输入事件的场景。

        Args:
            text: 要输入的文本
            selector: 可选，目标元素选择器。为空则在当前焦点元素输入
        """
        page = session.get_active_page()
        if selector:
            await page.locator(selector).click()
        await page.keyboard.type(text)
        return f"已输入: {text}"

    @mcp.tool()
    async def press_key(key: str) -> str:
        """按下键盘按键。

        Args:
            key: 按键名称，如 "Enter"、"Tab"、"Escape"、"ArrowDown"、"Control+a"
        """
        page = session.get_active_page()
        await page.keyboard.press(key)
        return f"已按下: {key}"

    @mcp.tool()
    async def hover(selector: str) -> str:
        """将鼠标悬停在元素上。

        Args:
            selector: 目标元素的选择器
        """
        page = session.get_active_page()
        await page.locator(selector).hover()
        return f"已悬停: {selector}"

    @mcp.tool()
    async def drag(source_selector: str, target_selector: str) -> str:
        """将元素拖拽到另一个元素上。

        Args:
            source_selector: 源元素选择器
            target_selector: 目标元素选择器
        """
        page = session.get_active_page()
        await page.drag_and_drop(source_selector, target_selector)
        return f"已拖拽 {source_selector} → {target_selector}"

    @mcp.tool()
    async def handle_dialog(action: str = "accept", text: str = "") -> str:
        """设置浏览器弹窗（alert/confirm/prompt）的处理策略。设置后，后续弹窗将自动按此策略处理。

        Args:
            action: "accept" 确认 或 "dismiss" 取消
            text: 可选，prompt 弹窗的输入文本
        """
        store = session.get_active_session()
        store.dialog_action = action
        store.dialog_text = text
        return f"弹窗处理策略已设为: {action}" + (f"，文本: {text}" if text else "")

    @mcp.tool()
    async def upload_file(selector: str, file_paths_json: str) -> str:
        """上传文件到文件输入框。

        Args:
            selector: 文件输入框的选择器（<input type="file">）
            file_paths_json: JSON 格式的文件路径列表，如 ["C:/images/photo.jpg"]
        """
        page = session.get_active_page()
        paths = json.loads(file_paths_json)
        await page.locator(selector).set_input_files(paths)
        return f"已上传 {len(paths)} 个文件"
