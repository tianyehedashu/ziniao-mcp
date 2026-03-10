"""输入自动化工具 (8 tools)"""

import json

from mcp.server.fastmcp import FastMCP

from ..session import SessionManager


def register_tools(mcp: FastMCP, session: SessionManager) -> None:

    def _behavior_cfg():
        """从 session 的 stealth_config 中获取 BehaviorConfig（若启用）。"""
        sc = session.stealth_config
        if sc.enabled and sc.human_behavior:
            return sc.to_behavior_config()
        return None

    @mcp.tool()
    async def click(selector: str) -> str:
        """点击页面元素。

        Args:
            selector: CSS 选择器（如 "#submit-btn"、".login-button"）
        """
        from ..iframe import find_element  # pylint: disable=import-outside-toplevel

        tab = session.get_active_tab()
        store = session.get_active_session()
        cfg = _behavior_cfg()

        elem = await find_element(tab, selector, store, timeout=10)
        if not elem:
            raise RuntimeError(f"未找到元素: {selector}")
        if cfg:
            from ..stealth import human_click, random_delay  # pylint: disable=import-outside-toplevel
            await random_delay(cfg=cfg)
            await human_click(tab, selector, cfg=cfg, element=elem)
        else:
            await elem.click()
        return f"已点击: {selector}"

    @mcp.tool()
    async def fill(
        selector: str = "",
        value: str = "",
        fields_json: str = "",
    ) -> str:
        """清空并填写输入框。支持单字段和批量模式。

        单字段模式：提供 selector + value。
        批量模式：提供 fields_json，格式为 [{"selector": "#name", "value": "张三"}, ...]

        Args:
            selector: 输入框的选择器（单字段模式）
            value: 要填入的值（单字段模式）
            fields_json: JSON 格式的字段列表（批量模式，优先级高于 selector+value）
        """
        from ..iframe import find_element  # pylint: disable=import-outside-toplevel

        tab = session.get_active_tab()
        store = session.get_active_session()
        cfg = _behavior_cfg()

        if fields_json:
            fields = json.loads(fields_json)
        elif selector:
            fields = [{"selector": selector, "value": value}]
        else:
            raise RuntimeError("请提供 selector+value 或 fields_json")

        for f in fields:
            elem = await find_element(tab, f["selector"], store, timeout=10)
            if not elem:
                raise RuntimeError(f"未找到元素: {f['selector']}")
            if cfg:
                from ..stealth import human_fill, random_delay  # pylint: disable=import-outside-toplevel
                await random_delay(cfg=cfg)
                await human_fill(
                    tab, f["selector"], f["value"], cfg=cfg, element=elem,
                )
            else:
                await elem.clear_input()
                await elem.send_keys(f["value"])

        if len(fields) == 1:
            return f"已填写 {fields[0]['selector']}"
        return f"已填写 {len(fields)} 个字段"

    @mcp.tool()
    async def type_text(text: str, selector: str = "") -> str:
        """逐字输入文本（模拟真实键盘打字），适用于需要触发输入事件的场景。

        Args:
            text: 要输入的文本
            selector: 可选，目标元素选择器。为空则在当前焦点元素输入
        """
        from ..iframe import find_element  # pylint: disable=import-outside-toplevel

        tab = session.get_active_tab()
        store = session.get_active_session()
        cfg = _behavior_cfg()

        if cfg:
            from ..stealth import human_type, random_delay  # pylint: disable=import-outside-toplevel
            await random_delay(cfg=cfg)
            elem = None
            if selector:
                elem = await find_element(tab, selector, store, timeout=10)
            await human_type(tab, text, selector, cfg=cfg, element=elem)
        else:
            from nodriver import cdp  # pylint: disable=import-outside-toplevel
            if selector:
                elem = await find_element(tab, selector, store, timeout=10)
                if elem:
                    await elem.click()
            for char in text:
                await tab.send(cdp.input_.dispatch_key_event("char", text=char))
        return f"已输入: {text}"

    @mcp.tool()
    async def press_key(key: str) -> str:
        """按下键盘按键。

        Args:
            key: 按键名称，如 "Enter"、"Tab"、"Escape"、"ArrowDown"、"Control+a"
        """
        from nodriver import cdp  # pylint: disable=import-outside-toplevel

        tab = session.get_active_tab()
        cfg = _behavior_cfg()
        if cfg:
            from ..stealth import random_delay  # pylint: disable=import-outside-toplevel
            await random_delay(50, 200, cfg=cfg)

        key_map = {
            "Enter": 13, "Tab": 9, "Escape": 27, "Backspace": 8,
            "Delete": 46, "ArrowUp": 38, "ArrowDown": 40,
            "ArrowLeft": 37, "ArrowRight": 39, "Space": 32,
            "Home": 36, "End": 35, "PageUp": 33, "PageDown": 34,
        }

        modifiers = 0
        actual_key = key
        if "+" in key:
            parts = key.split("+")
            for mod in parts[:-1]:
                mod_lower = mod.strip().lower()
                if mod_lower in ("control", "ctrl"):
                    modifiers |= 2
                elif mod_lower == "alt":
                    modifiers |= 1
                elif mod_lower in ("meta", "command"):
                    modifiers |= 4
                elif mod_lower == "shift":
                    modifiers |= 8
            actual_key = parts[-1].strip()

        vk = key_map.get(actual_key, ord(actual_key.upper()) if len(actual_key) == 1 else 0)
        await tab.send(cdp.input_.dispatch_key_event(
            "rawKeyDown", windows_virtual_key_code=vk, modifiers=modifiers,
            key=actual_key,
        ))
        await tab.send(cdp.input_.dispatch_key_event(
            "keyUp", windows_virtual_key_code=vk, modifiers=modifiers,
            key=actual_key,
        ))
        return f"已按下: {key}"

    @mcp.tool()
    async def hover(selector: str) -> str:
        """将鼠标悬停在元素上。

        Args:
            selector: 目标元素的选择器
        """
        from ..iframe import find_element  # pylint: disable=import-outside-toplevel

        tab = session.get_active_tab()
        store = session.get_active_session()
        cfg = _behavior_cfg()

        elem = await find_element(tab, selector, store, timeout=10)
        if not elem:
            raise RuntimeError(f"未找到元素: {selector}")
        if cfg:
            from ..stealth import human_hover, random_delay  # pylint: disable=import-outside-toplevel
            await random_delay(cfg=cfg)
            await human_hover(tab, selector, cfg=cfg, element=elem)
        else:
            await elem.mouse_move()
        return f"已悬停: {selector}"

    @mcp.tool()
    async def drag(source_selector: str, target_selector: str) -> str:
        """将元素拖拽到另一个元素上。

        Args:
            source_selector: 源元素选择器
            target_selector: 目标元素选择器
        """
        from ..iframe import find_element  # pylint: disable=import-outside-toplevel

        tab = session.get_active_tab()
        store = session.get_active_session()
        cfg = _behavior_cfg()
        if cfg:
            from ..stealth import random_delay  # pylint: disable=import-outside-toplevel
            await random_delay(cfg=cfg)

        src_elem = await find_element(tab, source_selector, store, timeout=10)
        tgt_elem = await find_element(tab, target_selector, store, timeout=10)
        if not src_elem or not tgt_elem:
            raise RuntimeError(
                f"未找到拖拽元素: {source_selector} 或 {target_selector}"
            )

        src_pos = await src_elem.get_position()
        tgt_pos = await tgt_elem.get_position()
        if not src_pos or not tgt_pos:
            raise RuntimeError("无法获取元素位置")

        if store.iframe_context:
            from nodriver import cdp  # pylint: disable=import-outside-toplevel

            sx, sy = src_pos.center
            tx, ty = tgt_pos.center
            await tab.send(cdp.input_.dispatch_mouse_event(
                "mousePressed", x=sx, y=sy,
                button=cdp.input_.MouseButton.LEFT, buttons=1, click_count=1,
            ))
            steps = 10
            for i in range(1, steps + 1):
                ratio = i / steps
                await tab.send(cdp.input_.dispatch_mouse_event(
                    "mouseMoved",
                    x=sx + (tx - sx) * ratio,
                    y=sy + (ty - sy) * ratio,
                ))
            await tab.send(cdp.input_.dispatch_mouse_event(
                "mouseReleased", x=tx, y=ty,
                button=cdp.input_.MouseButton.LEFT, buttons=1, click_count=1,
            ))
        else:
            await tab.mouse_drag(src_pos.center, tgt_pos.center)

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
        from ..iframe import find_element  # pylint: disable=import-outside-toplevel

        tab = session.get_active_tab()
        store = session.get_active_session()
        paths = json.loads(file_paths_json)

        elem = await find_element(tab, selector, store, timeout=10)
        if not elem:
            raise RuntimeError(f"未找到文件输入框: {selector}")
        await elem.send_file(*paths)
        return f"已上传 {len(paths)} 个文件"
