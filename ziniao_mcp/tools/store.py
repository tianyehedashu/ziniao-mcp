"""店铺管理工具 (5 tools)"""

import json

from mcp.server.fastmcp import FastMCP

from ..session import SessionManager


def register_tools(mcp: FastMCP, session: SessionManager) -> None:

    @mcp.tool()
    async def start_client() -> str:
        """启动紫鸟客户端进程。以 WebDriver 模式启动，如果客户端已在运行则跳过。
        若检测到客户端以普通模式运行，会自动终止并以 WebDriver 模式重启。"""
        try:
            return await session.start_client()
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

    @mcp.tool()
    async def list_stores(opened_only: bool = False) -> str:
        """获取店铺列表。返回店铺名称、ID、平台等信息，is_open 标识该店铺是否正在运行。

        Args:
            opened_only: 为 True 时只返回已打开的店铺（通过 CDP 端口验证，不会启动客户端）。
                为 False 时获取账号下所有店铺，如果客户端未运行会自动启动（可能需等待数十秒）。
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
                "店铺列表为空。请检查：1) 紫鸟客户端已启动；"
                "2) config 中 socket_port 与客户端实际端口一致；3) 登录信息正确。"
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
        """打开紫鸟店铺并建立 CDP 浏览器连接。成功后该店铺成为当前活动店铺。
        自动执行前置检查（店铺是否存在、代理 IP 是否过期），
        若店铺已在运行则自动复用 CDP 连接而不会重启。

        Args:
            store_id: 店铺标识（browserId 或 browserOauth，从 list_stores 获取）
        """
        try:
            store_session = await session.open_store(store_id)
        except RuntimeError as e:
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)
        result = {
            "status": "success",
            "store_id": store_session.store_id,
            "store_name": store_session.store_name,
            "cdp_port": store_session.cdp_port,
            "tabs": len(store_session.tabs),
        }
        if store_session.launcher_page:
            result["launcher_page"] = store_session.launcher_page
        return json.dumps(result, ensure_ascii=False)

    @mcp.tool()
    async def close_store(store_id: str) -> str:
        """关闭紫鸟店铺并断开 CDP 连接。

        Args:
            store_id: 店铺标识
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
        """退出紫鸟客户端。会先关闭所有已打开的店铺。"""
        try:
            await session.stop_client()
        except RuntimeError as e:
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)
        return "紫鸟客户端已退出"
