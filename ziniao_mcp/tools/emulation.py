"""仿真工具 (1 tool)"""

import json

from mcp.server.fastmcp import FastMCP

from ..session import SessionManager

DEVICE_PRESETS: dict[str, dict] = {
    "iPhone 14": {"viewport": {"width": 390, "height": 844}, "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1", "mobile": True, "scale": 3},
    "iPhone 14 Pro": {"viewport": {"width": 393, "height": 852}, "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1", "mobile": True, "scale": 3},
    "iPhone 14 Pro Max": {"viewport": {"width": 430, "height": 932}, "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1", "mobile": True, "scale": 3},
    "iPhone 15": {"viewport": {"width": 393, "height": 852}, "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1", "mobile": True, "scale": 3},
    "iPhone 15 Pro": {"viewport": {"width": 393, "height": 852}, "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1", "mobile": True, "scale": 3},
    "iPad Pro 11": {"viewport": {"width": 834, "height": 1194}, "user_agent": "Mozilla/5.0 (iPad; CPU OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1", "mobile": True, "scale": 2},
    "iPad Mini": {"viewport": {"width": 768, "height": 1024}, "user_agent": "Mozilla/5.0 (iPad; CPU OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1", "mobile": True, "scale": 2},
    "Pixel 7": {"viewport": {"width": 412, "height": 915}, "user_agent": "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36", "mobile": True, "scale": 2.625},
    "Pixel 8": {"viewport": {"width": 412, "height": 915}, "user_agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36", "mobile": True, "scale": 2.625},
    "Samsung Galaxy S23": {"viewport": {"width": 360, "height": 780}, "user_agent": "Mozilla/5.0 (Linux; Android 13; SM-S911B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36", "mobile": True, "scale": 3},
    "Desktop 1920x1080": {"viewport": {"width": 1920, "height": 1080}, "user_agent": "", "mobile": False, "scale": 1},
    "Desktop 1366x768": {"viewport": {"width": 1366, "height": 768}, "user_agent": "", "mobile": False, "scale": 1},
    "Desktop 1440x900": {"viewport": {"width": 1440, "height": 900}, "user_agent": "", "mobile": False, "scale": 1},
}


def register_tools(mcp: FastMCP, session: SessionManager) -> None:

    @mcp.tool()
    async def emulate(
        device_name: str = "",
        width: int = 0,
        height: int = 0,
    ) -> str:
        """调整视口大小或模拟指定设备。

        设备模式：提供 device_name（如 "iPhone 14"），自动设置视口和 User-Agent。
        自定义模式：提供 width + height 自定义视口尺寸。

        Args:
            device_name: 设备名，如 "iPhone 14"、"iPad Pro 11"、"Desktop 1920x1080"
            width: 自定义视口宽度（像素），仅在 device_name 为空时生效
            height: 自定义视口高度（像素），仅在 device_name 为空时生效
        """
        from nodriver import cdp  # pylint: disable=import-outside-toplevel

        tab = session.get_active_tab()

        if device_name:
            if device_name not in DEVICE_PRESETS:
                available = sorted(DEVICE_PRESETS.keys())
                return json.dumps({
                    "error": f"未知设备: {device_name}",
                    "available_devices": available,
                }, ensure_ascii=False, indent=2)

            device = DEVICE_PRESETS[device_name]
            vp = device["viewport"]
            await tab.send(
                cdp.emulation.set_device_metrics_override(
                    width=vp["width"],
                    height=vp["height"],
                    device_scale_factor=device.get("scale", 1),
                    mobile=device.get("mobile", False),
                )
            )
            ua = device.get("user_agent", "")
            if ua:
                await tab.send(cdp.emulation.set_user_agent_override(user_agent=ua))
            return json.dumps({
                "device": device_name,
                "viewport": vp,
                "user_agent": ua,
            }, ensure_ascii=False)

        if width > 0 and height > 0:
            await tab.send(
                cdp.emulation.set_device_metrics_override(
                    width=width,
                    height=height,
                    device_scale_factor=1,
                    mobile=False,
                )
            )
            return f"视口已调整为 {width}x{height}"

        raise RuntimeError("请提供 device_name 或 width+height")
