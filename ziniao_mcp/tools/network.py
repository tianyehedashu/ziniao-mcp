"""Network tool (1 tool)."""

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
        """List captured network requests from the active session.

        If request_id is provided, returns full details for that request
        (including headers). Otherwise, returns request summaries.

        Args:
            request_id: Optional request ID to get full details.
            url_pattern: Optional URL substring filter.
            limit: Maximum number of items in list mode. Default is 50.
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
            return f"Request ID not found: {request_id}"

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
