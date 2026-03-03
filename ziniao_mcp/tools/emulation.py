"""仿真工具 (2 tools)"""

import json

from mcp.server.fastmcp import FastMCP

from ..session import SessionManager


def register_tools(mcp: FastMCP, session: SessionManager) -> None:

    @mcp.tool()
    async def emulate(device_name: str) -> str:
        """模拟指定设备（调整视口大小和 User-Agent）。

        Args:
            device_name: Playwright 预置设备名，如 "iPhone 14"、"iPad Pro 11"、"Pixel 7"
        """
        pw = session._playwright
        if not pw:
            return "Playwright 未初始化，请先打开店铺"
        devices = pw.devices
        if device_name not in devices:
            available = sorted(devices.keys())[:30]
            return json.dumps({
                "error": f"未知设备: {device_name}",
                "available_devices_sample": available,
            }, ensure_ascii=False, indent=2)

        device = devices[device_name]
        page = session.get_active_page()
        await page.set_viewport_size({
            "width": device["viewport"]["width"],
            "height": device["viewport"]["height"],
        })
        return json.dumps({
            "device": device_name,
            "viewport": device["viewport"],
            "user_agent": device.get("user_agent", ""),
        }, ensure_ascii=False)

    @mcp.tool()
    async def resize_page(width: int, height: int) -> str:
        """调整页面视口大小。

        Args:
            width: 视口宽度（像素）
            height: 视口高度（像素）
        """
        page = session.get_active_page()
        await page.set_viewport_size({"width": width, "height": height})
        return f"视口已调整为 {width}x{height}"
