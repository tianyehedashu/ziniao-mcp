"""Unified browser session management tool (1 tool, 3 actions)."""

import json

from mcp.server.fastmcp import FastMCP

from ..session import SessionManager


def register_tools(mcp: FastMCP, session: SessionManager) -> None:

    @mcp.tool()
    async def browser_session(
        action: str = "list",
        session_id: str = "",
    ) -> str:
        """Manage browser sessions across Ziniao stores and Chrome instances.

        Use this tool to list active sessions, switch the current session, or
        get details for one session. Page tools (click, fill, navigate, and
        others) always run on the active session.

        Actions:
            list: List all active sessions and mark the active one.
            switch: Switch the active session to the given session_id.
            info: Get detailed information for the given session_id.

        Args:
            action: The session action ("list" | "switch" | "info").
            session_id: The target session ID for switch and info.
        """
        if action == "list":
            sessions = session.list_all_sessions()
            return json.dumps({
                "active_session": session.active_session_id,
                "sessions": sessions,
                "count": len(sessions),
            }, ensure_ascii=False, indent=2)

        if action == "switch":
            if not session_id:
                return json.dumps(
                    {"status": "error", "message": "session_id is required for action='switch'."},
                    ensure_ascii=False,
                )
            try:
                s = session.switch_session(session_id)
            except RuntimeError as e:
                return json.dumps(
                    {"status": "error", "message": str(e)}, ensure_ascii=False,
                )
            return json.dumps({
                "status": "success",
                "active_session": s.store_id,
                "name": s.store_name,
                "type": s.backend_type,
                "tabs": len(s.tabs),
            }, ensure_ascii=False)

        if action == "info":
            if not session_id:
                return json.dumps(
                    {"status": "error", "message": "session_id is required for action='info'."},
                    ensure_ascii=False,
                )
            try:
                info = session.get_session_info(session_id)
            except RuntimeError as e:
                return json.dumps(
                    {"status": "error", "message": str(e)}, ensure_ascii=False,
                )
            return json.dumps(info, ensure_ascii=False, indent=2)

        return json.dumps(
            {"status": "error", "message": f"Unknown action: {action}. Supported: list, switch, info."},
            ensure_ascii=False,
        )
