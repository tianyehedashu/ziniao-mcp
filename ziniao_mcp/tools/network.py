"""网络工具 (2 tools)"""

import json

from mcp.server.fastmcp import FastMCP

from ..session import SessionManager


def register_tools(mcp: FastMCP, session: SessionManager) -> None:

    @mcp.tool()
    async def list_network_requests(url_pattern: str = "", limit: int = 50) -> str:
        """列出已捕获的网络请求。从打开店铺或切换页面起自动捕获。

        Args:
            url_pattern: 可选，URL 子串过滤（如 "api" 只显示含 api 的请求）
            limit: 返回条数上限，默认 50
        """
        store = session.get_active_session()
        requests = store.network_requests
        if url_pattern:
            requests = [r for r in requests if url_pattern in r.url]
        result = []
        for req in requests[-limit:]:
            result.append({
                "id": req.id,
                "method": req.method,
                "url": req.url[:200],
                "status": req.status,
                "resource_type": req.resource_type,
            })
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def get_network_request(request_id: int) -> str:
        """获取指定网络请求的详细信息（含请求头、响应头）。

        Args:
            request_id: 请求 ID（从 list_network_requests 获取）
        """
        store = session.get_active_session()
        for req in store.network_requests:
            if req.id == request_id:
                return json.dumps({
                    "id": req.id,
                    "url": req.url,
                    "method": req.method,
                    "status": req.status,
                    "status_text": req.status_text,
                    "resource_type": req.resource_type,
                    "request_headers": req.request_headers,
                    "response_headers": req.response_headers,
                }, ensure_ascii=False, indent=2)
        return f"未找到请求 ID: {request_id}"
