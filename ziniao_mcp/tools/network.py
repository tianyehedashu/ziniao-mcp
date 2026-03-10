"""网络工具 (1 tool)"""

import json

from mcp.server.fastmcp import FastMCP

from ..session import SessionManager


def register_tools(mcp: FastMCP, session: SessionManager) -> None:

    @mcp.tool()
    async def network(
        request_id: int = 0,
        url_pattern: str = "",
        limit: int = 50,
    ) -> str:
        """查看已捕获的网络请求。从打开店铺起自动捕获。

        提供 request_id 时返回该请求的详细信息（含请求头、响应头）；否则列出请求摘要。

        Args:
            request_id: 可选，指定请求 ID 查看详情（从列表结果中获取）
            url_pattern: 可选，URL 子串过滤（如 "api" 只显示含 api 的请求）
            limit: 列表模式的返回条数上限，默认 50
        """
        store = session.get_active_session()

        if request_id:
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
