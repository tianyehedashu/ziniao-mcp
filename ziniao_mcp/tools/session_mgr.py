"""统一浏览器会话管理工具 (1 tool, 3 actions)"""

import json

from mcp.server.fastmcp import FastMCP

from ..session import SessionManager


def register_tools(mcp: FastMCP, session: SessionManager) -> None:

    @mcp.tool()
    async def browser_session(
        action: str = "list",
        session_id: str = "",
    ) -> str:
        """管理浏览器会话（跨紫鸟店铺和 Chrome 实例）。

        当同时打开了多个紫鸟店铺或 Chrome 浏览器时，使用此工具查看所有活跃会话、
        切换当前操作目标、或查看某个会话的详情。
        所有页面操作（click/fill/navigate 等）都作用于当前活跃会话。

        Actions:
            list   - 列出所有活跃会话，标记当前活跃的那个
            switch - 切换当前活跃会话到指定 session_id
            info   - 查看指定会话的详细信息（标签页列表、URL 等）

        Args:
            action: 操作类型 ("list" | "switch" | "info")
            session_id: switch / info 时的目标会话 ID
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
                    {"status": "error", "message": "switch 操作需要提供 session_id"},
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
                    {"status": "error", "message": "info 操作需要提供 session_id"},
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
            {"status": "error", "message": f"未知 action: {action}，支持 list/switch/info"},
            ensure_ascii=False,
        )
