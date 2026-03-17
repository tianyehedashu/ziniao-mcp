"""Store management tools (5 tools)."""

import json

from mcp.server.fastmcp import FastMCP

from ..session import SessionManager


def register_tools(mcp: FastMCP, session: SessionManager) -> None:

    @mcp.tool()
    async def start_client() -> str:
        """Start the Ziniao client process in WebDriver mode.

        If the client is already running, it is reused. If the client is
        running in normal mode, it is restarted in WebDriver mode.
        """
        try:
            return await session.start_client()
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

    @mcp.tool()
    async def list_stores(opened_only: bool = False) -> str:
        """Get the list of stores.

        Returns store identifiers, names, platform fields, and whether each
        store is currently open.

        Args:
            opened_only: Whether to return only currently opened stores.
                If false, returns all stores and may auto-start the client.
        """
        open_stores = await SessionManager.get_persisted_stores()
        open_ids = {s["store_id"] for s in open_stores}

        if opened_only:
            if not open_stores:
                return json.dumps({"stores": [], "count": 0}, ensure_ascii=False)
            stores = [
                {
                    "store_id": s["store_id"],
                    "store_name": s.get("store_name", ""),
                    "cdp_port": s["cdp_port"],
                }
                for s in open_stores
            ]
            return json.dumps(
                {"stores": stores, "count": len(stores)},
                ensure_ascii=False, indent=2,
            )

        try:
            all_stores = await session.list_stores()
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)
        if not all_stores:
            return (
                "Store list is empty. Check that: 1) Ziniao client is running; "
                "2) socket_port in config matches the actual client port; "
                "3) login credentials are correct."
            )

        result = []
        for s in all_stores:
            store_id = s.get("browserOauth") or s.get("browserId") or ""
            result.append({
                "browserId": s.get("browserId"),
                "browserOauth": s.get("browserOauth"),
                "browserName": s.get("browserName"),
                "siteId": s.get("siteId"),
                "siteName": s.get("siteName"),
                "is_open": store_id in open_ids,
            })
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def open_store(store_id: str) -> str:
        """Open a Ziniao store and connect through CDP.

        The opened store becomes the active session. The tool checks store
        availability and proxy status before opening. If already running, it
        reuses the existing CDP connection.

        Prerequisites (if you see CDP connection errors or tabs: 0):
        1) In Ziniao client, manually open the store first and wait for the
           browser window to appear.
        2) In Ziniao settings, enable "Remote debugging" / "CDP" and note the
           port (e.g. 9222). Ensure firewall does not block 127.0.0.1:port.
        3) Then call list_stores (confirm is_open: true for that store), then
           open_store(store_id), then tab list. If no tabs, use tab new with
           the target URL.

        Args:
            store_id: The store identifier (browserId or browserOauth from
                list_stores).
        """
        try:
            store_session = await session.open_store(store_id)
        except RuntimeError as e:
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)
        tab_count = len(store_session.tabs)
        result = {
            "status": "success",
            "store_id": store_session.store_id,
            "store_name": store_session.store_name,
            "cdp_port": store_session.cdp_port,
            "tabs": tab_count,
        }
        if store_session.launcher_page:
            result["launcher_page"] = store_session.launcher_page
        if tab_count == 0:
            result["hint"] = (
                "当前无普通网页标签。请使用 tab new 打开目标链接，"
                "或先在紫鸟内打开一次目标页面后再操作。"
            )
        return json.dumps(result, ensure_ascii=False)

    @mcp.tool()
    async def close_store(store_id: str) -> str:
        """Close a Ziniao store and disconnect its CDP session.

        Args:
            store_id: The store identifier.
        """
        await session.close_store(store_id)
        remaining = session.get_open_store_ids()
        return json.dumps({
            "status": "closed",
            "store_id": store_id,
            "remaining_stores": remaining,
        }, ensure_ascii=False)

    @mcp.tool()
    async def stop_client() -> str:
        """Stop the Ziniao client process.

        All opened stores are closed first.
        """
        try:
            await session.stop_client()
        except RuntimeError as e:
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)
        return "Ziniao client has been stopped."
