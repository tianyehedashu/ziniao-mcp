"""CDP 反检测模块。

提供两层防护：
1. JS 环境伪装 — 通过 CDP Page.addScriptToEvaluateOnNewDocument 覆盖自动化痕迹
2. 人类行为模拟 — 为输入操作注入拟人化随机性
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .human_behavior import (
    BehaviorConfig,
    human_click,
    human_fill,
    human_hover,
    human_scroll,
    human_type,
    random_delay,
)
from .js_patches import STEALTH_JS, build_stealth_js

if TYPE_CHECKING:
    from nodriver import Browser, Tab

__all__ = [
    "StealthConfig",
    "apply_stealth",
    "BehaviorConfig",
    "human_click",
    "human_fill",
    "human_hover",
    "human_scroll",
    "human_type",
    "random_delay",
]

_logger = logging.getLogger("ziniao-mcp-debug")


@dataclass
class StealthConfig:
    """Stealth 模块总配置。"""

    enabled: bool = True
    js_patches: bool = True
    human_behavior: bool = True
    delay_min_ms: int = 200
    delay_max_ms: int = 800
    typing_min_ms: int = 50
    typing_max_ms: int = 150
    mouse_movement: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StealthConfig":
        if not data:
            return cls()
        delay_range = data.get("delay_range", [200, 800])
        typing_speed = data.get("typing_speed", [50, 150])
        return cls(
            enabled=data.get("enabled", True),
            js_patches=data.get("js_patches", True),
            human_behavior=data.get("human_behavior", True),
            delay_min_ms=delay_range[0] if isinstance(delay_range, list) else 200,
            delay_max_ms=delay_range[1] if isinstance(delay_range, list) else 800,
            typing_min_ms=typing_speed[0] if isinstance(typing_speed, list) else 50,
            typing_max_ms=typing_speed[1] if isinstance(typing_speed, list) else 150,
            mouse_movement=data.get("mouse_movement", True),
        )

    def to_behavior_config(self) -> BehaviorConfig:
        return BehaviorConfig(
            delay_min_ms=self.delay_min_ms,
            delay_max_ms=self.delay_max_ms,
            typing_min_ms=self.typing_min_ms,
            typing_max_ms=self.typing_max_ms,
            mouse_movement=self.mouse_movement,
        )


async def apply_stealth(
    browser: "Browser",
    *,
    config: StealthConfig | None = None,
    webgl_vendor: bool = False,
) -> None:
    """为 Browser 的所有 tab 注入反检测脚本。

    通过 CDP Page.addScriptToEvaluateOnNewDocument 注入，
    确保后续新页面自动继承。同时对已有页面执行 evaluate 立即生效。
    """
    from nodriver import cdp  # pylint: disable=import-outside-toplevel

    cfg = config or StealthConfig()
    if not cfg.enabled or not cfg.js_patches:
        _logger.debug("stealth JS patches 未启用，跳过注入")
        return

    script = build_stealth_js(webgl_vendor=webgl_vendor)

    from ..session import _filter_tabs  # pylint: disable=import-outside-toplevel

    for tab in _filter_tabs(browser.tabs):
        try:
            await tab.send(
                cdp.page.add_script_to_evaluate_on_new_document(source=script)
            )
            _logger.debug("stealth init_script 已注入到 tab: %s", tab.target.url)
        except Exception:  # pylint: disable=broad-exception-caught
            _logger.debug("注入 init_script 到 tab 失败（tab 可能已关闭）")

        try:
            await tab.evaluate(script)
            _logger.debug("stealth 已 evaluate 到已有 tab: %s", tab.target.url)
        except Exception:  # pylint: disable=broad-exception-caught
            _logger.debug("evaluate stealth 到 tab 失败（tab 可能已关闭）")
