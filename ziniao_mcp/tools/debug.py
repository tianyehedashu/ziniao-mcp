"""Debug tools (4 tools)."""

import json

from mcp.server.fastmcp import FastMCP

from ..session import SessionManager


def register_tools(mcp: FastMCP, session: SessionManager) -> None:

    @mcp.tool()
    async def evaluate_script(script: str) -> str:
        """Evaluate JavaScript in the current page and return the result.

        If an iframe is active, the script is evaluated in that frame context.

        Args:
            script: The JavaScript expression or code to evaluate.
        """
        tab = session.get_active_tab()
        store = session.get_active_session()
        if store.iframe_context:
            from ..iframe import eval_in_frame  # pylint: disable=import-outside-toplevel
            result = await eval_in_frame(
                tab, store.iframe_context.context_id, script,
            )
        else:
            result = await tab.evaluate(script, return_by_value=True)
        return json.dumps(result, ensure_ascii=False, default=str)

    @mcp.tool()
    async def take_screenshot(selector: str = "", full_page: bool = False) -> str:
        """Capture a screenshot of the page or a specific element.

        Returns a base64-encoded PNG data URL.

        Args:
            selector: Optional element selector. If empty, captures the
                viewport or full page.
            full_page: Whether to capture the full page when selector is
                empty.
        """
        from nodriver import cdp  # pylint: disable=import-outside-toplevel

        tab = session.get_active_tab()
        store = session.get_active_session()

        if selector:
            from ..iframe import find_element  # pylint: disable=import-outside-toplevel

            elem = await find_element(tab, selector, store, timeout=10)
            if not elem:
                raise RuntimeError(f"Element not found: {selector}")
            pos = await elem.get_position()
            if not pos:
                raise RuntimeError(f"Failed to get element position: {selector}")
            clip = cdp.page.Viewport(
                x=pos.x, y=pos.y,
                width=pos.width, height=pos.height, scale=1,
            )
            data = await tab.send(
                cdp.page.capture_screenshot(format_="png", clip=clip)
            )
        else:
            data = await tab.send(
                cdp.page.capture_screenshot(
                    format_="png",
                    capture_beyond_viewport=full_page,
                )
            )
        if not data:
            raise RuntimeError("Screenshot failed. The page may not be fully ready.")
        return f"data:image/png;base64,{data}"

    @mcp.tool()
    async def take_snapshot() -> str:
        """Get the full HTML snapshot of the current page."""
        tab = session.get_active_tab()
        store = session.get_active_session()
        if store.iframe_context:
            from ..iframe import eval_in_frame  # pylint: disable=import-outside-toplevel
            html = await eval_in_frame(
                tab, store.iframe_context.context_id,
                "document.documentElement.outerHTML",
            )
            return html or ""
        return await tab.get_content()

    @mcp.tool()
    async def console(
        message_id: int = 0,
        level: str = "",
        limit: int = 50,
    ) -> str:
        """List captured console messages from the active session.

        If message_id is provided, returns full details for that message.
        Otherwise, returns message summaries.

        Args:
            message_id: Optional message ID to get full details.
            level: Optional level filter (log, warning, error, info, debug).
            limit: Maximum number of items in list mode. Default is 50.
        """
        store = session.get_active_session()

        if message_id:
            for m in store.console_messages:
                if m.id == message_id:
                    return json.dumps({
                        "id": m.id,
                        "level": m.level,
                        "text": m.text,
                        "timestamp": m.timestamp,
                    }, ensure_ascii=False, indent=2)
            return f"Message ID not found: {message_id}"

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
