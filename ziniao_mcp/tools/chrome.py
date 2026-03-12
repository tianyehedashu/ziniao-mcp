"""Chrome browser management tools (4 tools)."""

import json

from mcp.server.fastmcp import FastMCP

from ..session import SessionManager


def register_tools(mcp: FastMCP, session: SessionManager) -> None:

    @mcp.tool()
    async def launch_chrome(
        name: str = "",
        url: str = "",
        executable_path: str = "",
        cdp_port: int = 0,
        user_data_dir: str = "",
        headless: bool = False,
    ) -> str:
        """Launch a new Chrome instance and connect via CDP.

        The browser becomes the active session.

        Args:
            name: Optional session name for identification and switching.
            url: Optional URL to open after launch.
            executable_path: Optional Chrome executable path. If empty,
                auto-detects system Chrome.
            cdp_port: CDP remote debugging port. If 0, an available port is
                selected automatically.
            user_data_dir: Optional user data directory for profile isolation.
            headless: Whether to run Chrome in headless mode.
        """
        try:
            store_session = await session.launch_chrome(
                name=name,
                executable_path=executable_path,
                cdp_port=cdp_port,
                user_data_dir=user_data_dir,
                headless=headless,
                url=url,
            )
        except RuntimeError as e:
            return json.dumps(
                {"status": "error", "message": str(e)}, ensure_ascii=False,
            )
        return json.dumps({
            "status": "success",
            "session_id": store_session.store_id,
            "name": store_session.store_name,
            "cdp_port": store_session.cdp_port,
            "tabs": len(store_session.tabs),
        }, ensure_ascii=False)

    @mcp.tool()
    async def connect_chrome(cdp_port: int, name: str = "") -> str:
        """Connect to an already running Chrome instance by CDP port.

        Suitable for Chrome started with --remote-debugging-port. The
        connected browser becomes the active session.

        Args:
            cdp_port: The Chrome CDP remote debugging port, such as 9222.
            name: Optional session name for identification and switching.
        """
        try:
            store_session = await session.connect_chrome(
                cdp_port=cdp_port, name=name,
            )
        except RuntimeError as e:
            return json.dumps(
                {"status": "error", "message": str(e)}, ensure_ascii=False,
            )
        return json.dumps({
            "status": "success",
            "session_id": store_session.store_id,
            "name": store_session.store_name,
            "cdp_port": store_session.cdp_port,
            "tabs": len(store_session.tabs),
        }, ensure_ascii=False)

    @mcp.tool()
    async def list_chrome() -> str:
        """Get a list of active Chrome sessions."""
        sessions = session.list_chrome_sessions()
        return json.dumps(
            {"sessions": sessions, "count": len(sessions)},
            ensure_ascii=False, indent=2,
        )

    @mcp.tool()
    async def close_chrome(session_id: str) -> str:
        """Close the specified Chrome session.

        For launch mode sessions, this stops the browser process. For connect
        mode sessions, this only disconnects CDP.

        Args:
            session_id: The session identifier from list_chrome or
                browser_session(action='list').
        """
        await session.close_chrome(session_id)
        remaining = session.list_chrome_sessions()
        return json.dumps({
            "status": "closed",
            "session_id": session_id,
            "remaining_chrome_sessions": len(remaining),
        }, ensure_ascii=False)
