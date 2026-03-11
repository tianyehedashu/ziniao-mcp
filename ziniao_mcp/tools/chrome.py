"""Chrome 浏览器管理工具 (4 tools)"""

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
        """启动一个新的 Chrome 浏览器实例并通过 CDP 连接。成功后成为当前活动浏览器。

        Args:
            name: 会话名称（可选，用于标识和后续切换）
            url: 启动后打开的 URL（可选）
            executable_path: Chrome 可执行文件路径（空则自动检测系统 Chrome）
            cdp_port: CDP 远程调试端口（0 则自动分配空闲端口）
            user_data_dir: 用户数据目录，用于隔离 profile（空则使用临时目录）
            headless: 是否以无头模式启动
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
        """连接到一个已运行的 Chrome 浏览器（通过 CDP 端口）。
        适用于已手动启动带 --remote-debugging-port 参数的 Chrome。
        成功后成为当前活动浏览器。

        Args:
            cdp_port: Chrome 的 CDP 远程调试端口（如 9222）
            name: 会话名称（可选，用于标识和后续切换）
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
        """列出当前所有 Chrome 浏览器会话。"""
        sessions = session.list_chrome_sessions()
        return json.dumps(
            {"sessions": sessions, "count": len(sessions)},
            ensure_ascii=False, indent=2,
        )

    @mcp.tool()
    async def close_chrome(session_id: str) -> str:
        """关闭指定的 Chrome 浏览器会话。
        若为 launch 模式启动的 Chrome，会终止浏览器进程；
        若为 connect 模式连接的 Chrome，仅断开 CDP 连接。

        Args:
            session_id: 会话标识（从 list_chrome 或 session(action='list') 获取）
        """
        await session.close_chrome(session_id)
        remaining = session.list_chrome_sessions()
        return json.dumps({
            "status": "closed",
            "session_id": session_id,
            "remaining_chrome_sessions": len(remaining),
        }, ensure_ascii=False)
