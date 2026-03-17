"""Input automation tools (8 tools)."""

import asyncio
import json
import random

from mcp.server.fastmcp import FastMCP

from ..session import SessionManager


def register_tools(mcp: FastMCP, session: SessionManager) -> None:

    def _behavior_cfg():
        """Get BehaviorConfig from stealth_config when enabled."""
        sc = session.stealth_config
        if sc.enabled and sc.human_behavior:
            return sc.to_behavior_config()
        return None

    def _is_ziniao() -> bool:
        """Check if the active session is a Ziniao store."""
        try:
            return session.get_active_session().backend_type == "ziniao"
        except RuntimeError:
            return False

    @mcp.tool()
    async def click(selector: str) -> str:
        """Click the element matching the provided CSS selector.

        Args:
            selector: The CSS selector of the target element.
        """
        from ..iframe import find_element  # pylint: disable=import-outside-toplevel

        tab = session.get_active_tab()
        store = session.get_active_session()
        cfg = _behavior_cfg()

        elem = await find_element(tab, selector, store, timeout=10)
        if not elem:
            raise RuntimeError(f"Element not found: {selector}")
        if cfg:
            from ..stealth import human_click, random_delay  # pylint: disable=import-outside-toplevel
            await random_delay(cfg=cfg)
            await human_click(tab, selector, cfg=cfg, element=elem)
        elif _is_ziniao():
            from ..stealth.human_behavior import _move_mouse_humanlike, _get_box_from_element  # pylint: disable=import-outside-toplevel
            box = await _get_box_from_element(elem)
            if box:
                cx = box["x"] + box["width"] / 2
                cy = box["y"] + box["height"] / 2
                await _move_mouse_humanlike(tab, cx, cy)
                await tab.mouse_click(cx, cy)
            else:
                await elem.mouse_click()
        else:
            await elem.click()
        return f"Clicked: {selector}"

    @mcp.tool()
    async def fill(
        selector: str = "",
        value: str = "",
        fields_json: str = "",
    ) -> str:
        """Clear and fill input fields.

        Supports single-field and batch modes. Single-field mode uses
        selector + value. Batch mode uses fields_json, for example
        [{"selector": "#name", "value": "Alice"}].

        Args:
            selector: The input selector for single-field mode.
            value: The value to type for single-field mode.
            fields_json: A JSON array of selector/value pairs. When provided,
                it takes priority over selector + value.
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
            raise RuntimeError("Provide selector+value or fields_json.")

        for f in fields:
            elem = await find_element(tab, f["selector"], store, timeout=10)
            if not elem:
                raise RuntimeError(f"Element not found: {f['selector']}")
            if cfg:
                from ..stealth import human_fill, random_delay  # pylint: disable=import-outside-toplevel
                await random_delay(cfg=cfg)
                await human_fill(
                    tab, f["selector"], f["value"], cfg=cfg, element=elem,
                )
            elif _is_ziniao():
                from ..stealth.human_behavior import human_fill as _hfill  # pylint: disable=import-outside-toplevel
                await _hfill(tab, f["selector"], f["value"], element=elem)
            else:
                await elem.clear_input()
                await elem.send_keys(f["value"])

        if len(fields) == 1:
            return f"Filled: {fields[0]['selector']}"
        return f"Filled {len(fields)} fields."

    @mcp.tool()
    async def type_text(text: str, selector: str = "") -> str:
        """Type text character by character to simulate real keyboard input.

        Args:
            text: The text to type.
            selector: Optional target element selector. If empty, types into
                the currently focused element.
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
        elif _is_ziniao():
            from ..stealth.human_behavior import human_type as _htype  # pylint: disable=import-outside-toplevel
            elem = None
            if selector:
                elem = await find_element(tab, selector, store, timeout=10)
            await _htype(tab, text, selector, element=elem)
        else:
            from nodriver import cdp  # pylint: disable=import-outside-toplevel
            if selector:
                elem = await find_element(tab, selector, store, timeout=10)
                if elem:
                    await elem.click()
            for char in text:
                await tab.send(cdp.input_.dispatch_key_event("char", text=char))
                await asyncio.sleep(random.uniform(0.03, 0.1))
        return f"Typed: {text}"

    @mcp.tool()
    async def press_key(key: str) -> str:
        """Press a keyboard key on the current page.

        Args:
            key: The key name, such as "Enter", "Tab", "Escape", "ArrowDown",
                or "Control+a".
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
        return f"Pressed: {key}"

    @mcp.tool()
    async def hover(selector: str) -> str:
        """Move the mouse over the element matching the selector.

        Args:
            selector: The CSS selector of the target element.
        """
        from ..iframe import find_element  # pylint: disable=import-outside-toplevel

        tab = session.get_active_tab()
        store = session.get_active_session()
        cfg = _behavior_cfg()

        elem = await find_element(tab, selector, store, timeout=10)
        if not elem:
            raise RuntimeError(f"Element not found: {selector}")
        if cfg:
            from ..stealth import human_hover, random_delay  # pylint: disable=import-outside-toplevel
            await random_delay(cfg=cfg)
            await human_hover(tab, selector, cfg=cfg, element=elem)
        elif _is_ziniao():
            from ..stealth.human_behavior import human_hover as _hhover  # pylint: disable=import-outside-toplevel
            await _hhover(tab, selector, element=elem)
        else:
            await elem.mouse_move()
        return f"Hovered: {selector}"

    @mcp.tool()
    async def drag(source_selector: str, target_selector: str) -> str:
        """Drag one element and drop it onto another element.

        Args:
            source_selector: The CSS selector of the source element.
            target_selector: The CSS selector of the target element.
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
                f"Drag target not found: {source_selector} or {target_selector}"
            )

        src_pos = await src_elem.get_position()
        tgt_pos = await tgt_elem.get_position()
        if not src_pos or not tgt_pos:
            raise RuntimeError("Failed to get element position.")

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

        return f"Dragged {source_selector} -> {target_selector}"

    @mcp.tool()
    async def handle_dialog(action: str = "accept", text: str = "") -> str:
        """Set how browser dialogs (alert, confirm, prompt) are handled.

        After this is set, subsequent dialogs are handled automatically.

        Args:
            action: Whether to accept or dismiss the dialog ("accept" |
                "dismiss").
            text: Optional prompt text to send for prompt dialogs.
        """
        store = session.get_active_session()
        store.dialog_action = action
        store.dialog_text = text
        return f"Dialog handling set to: {action}" + (f", promptText: {text}" if text else "")

    @mcp.tool()
    async def upload_file(selector: str, file_paths_json: str) -> str:
        """Upload files to a file input element.

        Args:
            selector: The selector of the file input element
                (<input type="file">).
            file_paths_json: A JSON array of file paths, for example
                ["C:/images/photo.jpg"].
        """
        from ..iframe import find_element  # pylint: disable=import-outside-toplevel

        tab = session.get_active_tab()
        store = session.get_active_session()
        paths = json.loads(file_paths_json)

        elem = await find_element(tab, selector, store, timeout=10)
        if not elem:
            raise RuntimeError(f"File input not found: {selector}")
        await elem.send_file(*paths)
        return f"Uploaded {len(paths)} file(s)."
