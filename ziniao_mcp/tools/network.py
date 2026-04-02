"""Network tools: request monitoring, route interception, and HAR recording."""

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
            return json.dumps({"error": f"Request ID not found: {request_id}"}, ensure_ascii=False)

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
    async def network_route(
        url_pattern: str,
        abort: bool = False,
        response_body: str = "",
        response_status: int = 200,
        response_content_type: str = "text/plain",
    ) -> str:
        """Add a request interception route using CDP Fetch domain.

        Matching requests will be either blocked (abort=True) or served
        with a mock response.  Supports glob-like URL patterns:
        "*" matches all, "prefix*suffix" for glob, or substring match.

        Args:
            url_pattern: URL pattern to intercept (e.g. "*.png", "*api/data*").
            abort: If True, block the matching requests entirely.
            response_body: Mock response body (used when abort is False).
            response_status: Mock response HTTP status code.
            response_content_type: Mock response Content-Type header.
        """
        from ..core.network import add_route  # pylint: disable=import-outside-toplevel

        tab = session.get_active_tab()
        store = session.get_active_session()
        result = await add_route(
            tab, store,
            url_pattern=url_pattern,
            abort=abort,
            response_status=response_status,
            response_body=response_body,
            response_content_type=response_content_type,
        )
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def network_unroute(
        url_pattern: str = "",
    ) -> str:
        """Remove request interception route(s).

        If url_pattern is provided, removes only matching routes.
        If empty, removes all routes and disables Fetch interception.

        Args:
            url_pattern: URL pattern to remove (empty = remove all).
        """
        from ..core.network import remove_route  # pylint: disable=import-outside-toplevel

        tab = session.get_active_tab()
        store = session.get_active_session()
        result = await remove_route(tab, store, url_pattern=url_pattern)
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def network_routes() -> str:
        """List all active request interception routes."""
        from ..core.network import list_routes  # pylint: disable=import-outside-toplevel

        store = session.get_active_session()
        result = list_routes(store)
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def har_start() -> str:
        """Start recording network activity in HAR (HTTP Archive) format.

        All subsequent network requests will be captured until har_stop
        is called.  The HAR data includes request/response headers,
        status codes, timing, and resource types.
        """
        from ..core.network import har_start as _har_start  # pylint: disable=import-outside-toplevel

        store = session.get_active_session()
        result = _har_start(store)
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def har_stop(
        path: str = "",
    ) -> str:
        """Stop HAR recording and export to file.

        If path is empty, saves to ~/.ziniao/har/har-<timestamp>.har.

        Args:
            path: Optional output file path for the HAR file.
        """
        from ..core.network import har_stop as _har_stop  # pylint: disable=import-outside-toplevel

        store = session.get_active_session()
        result = _har_stop(store, path=path)
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def page_fetch(
        url: str = "",
        method: str = "GET",
        body: str = "",
        headers: str = "",
        xsrf_cookie: str = "",
        xsrf_headers: str = "",
        mode: str = "fetch",
        script: str = "",
        navigate_url: str = "",
    ) -> str:
        """Execute an HTTP request in the browser page context, leveraging the page's login session.

        Two modes:
        - **fetch** (default): builds a fetch() call with auto cookie inclusion.
        - **js**: evaluates a custom JS expression (for sites with framework auth).

        In js mode, ``__BODY__`` and ``__BODY_STR__`` variables are injected from body.

        Args:
            url: Request URL (required for fetch mode).
            method: HTTP method (default GET).
            body: Request body as JSON string.
            headers: Request headers as JSON string (e.g. '{"Accept":"application/json"}').
            xsrf_cookie: Cookie name to auto-extract XSRF token (e.g. "XSRF-TOKEN").
            xsrf_headers: JSON array of header names to set with that token, e.g. '["x-csrf-token"]'. Defaults to ["X-XSRF-TOKEN"] when xsrf_cookie is set.
            mode: Execution mode: "fetch" or "js".
            script: JS expression (required for js mode).
            navigate_url: Navigate to this URL first if current page doesn't match.
        """
        from ..cli.dispatch import _page_fetch  # pylint: disable=import-outside-toplevel

        headers_dict = json.loads(headers) if headers else {}
        args: dict = {
            "mode": mode,
            "url": url,
            "method": method,
            "body": body,
            "headers": headers_dict,
            "xsrf_cookie": xsrf_cookie,
            "script": script,
            "navigate_url": navigate_url,
        }
        if xsrf_headers.strip():
            try:
                parsed = json.loads(xsrf_headers)
                if isinstance(parsed, list) and parsed:
                    args["xsrf_headers"] = [str(x) for x in parsed if str(x).strip()]
            except (json.JSONDecodeError, TypeError):
                pass
        result = await _page_fetch(session, args)
        return json.dumps(result, ensure_ascii=False, indent=2)
