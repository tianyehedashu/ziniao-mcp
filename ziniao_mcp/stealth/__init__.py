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
from .js_patches import build_stealth_js
from ziniao_webdriver.js_patches import derive_profile_fingerprint

if TYPE_CHECKING:
    from nodriver import Browser, Tab

__all__ = [
    "StealthConfig",
    "apply_stealth",
    "evaluate_stealth_existing_document",
    "build_stealth_js",
    "derive_profile_fingerprint",
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
    # 是否伪造 WebGL vendor/renderer。
    # 紫鸟客户端通常自行处理 WebGL 指纹，默认关闭以避免双重改写。
    # Chrome launch/connect 场景应显式开启以抹平真实 GPU 信息。
    webgl_vendor: bool = False
    # 稳定指纹种子：非空时 Canvas/Audio/WebGL 按 BLAKE2b 派生固定参数，
    # 同 profile 跨刷新指纹一致；为 None 则保留页面会话级随机。一般由
    # SessionManager 根据 user_data_dir / store_id 自动推导，显式 None
    # 交由 evaluate/apply 调用方以参数覆盖。
    profile_seed: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "StealthConfig":
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
            webgl_vendor=data.get("webgl_vendor", False),
            profile_seed=data.get("profile_seed"),
        )

    def to_behavior_config(self) -> BehaviorConfig:
        return BehaviorConfig(
            delay_min_ms=self.delay_min_ms,
            delay_max_ms=self.delay_max_ms,
            typing_min_ms=self.typing_min_ms,
            typing_max_ms=self.typing_max_ms,
            mouse_movement=self.mouse_movement,
        )


def _resolve_webgl_vendor(cfg: StealthConfig, override: bool | None) -> bool:
    """将显式参数与配置合并；显式 *override* 优先，None 回退到配置。"""
    if override is not None:
        return override
    return cfg.webgl_vendor


_SEED_UNSET: Any = object()


def _resolve_profile_seed(cfg: StealthConfig, override: Any) -> str | None:
    """合并显式 *override* 与 ``StealthConfig.profile_seed``。

    - ``_SEED_UNSET``（sentinel）：使用 ``cfg.profile_seed``
    - ``None``：显式关闭稳定种子（保留随机）
    - 非空字符串：显式指定稳定种子
    """
    if override is _SEED_UNSET:
        return cfg.profile_seed
    return override


async def evaluate_stealth_existing_document(
    tab: "Tab",
    *,
    config: StealthConfig | None = None,
    webgl_vendor: bool | None = None,
    profile_seed: Any = _SEED_UNSET,
) -> None:
    """对当前文档执行一次 stealth 脚本（不注册 addScriptToEvaluateOnNewDocument）。"""
    cfg = config or StealthConfig()
    if not cfg.enabled or not cfg.js_patches:
        return
    script = build_stealth_js(
        webgl_vendor=_resolve_webgl_vendor(cfg, webgl_vendor),
        profile_seed=_resolve_profile_seed(cfg, profile_seed),
    )
    try:
        await tab.evaluate(script)
        _logger.debug("stealth 已 evaluate 到已有 tab: %s", tab.target.url)
    except Exception:  # pylint: disable=broad-exception-caught
        _logger.debug("evaluate stealth 到 tab 失败（tab 可能已关闭）")


async def apply_stealth(
    browser: "Browser",
    *,
    config: StealthConfig | None = None,
    webgl_vendor: bool | None = None,
    profile_seed: Any = _SEED_UNSET,
    evaluate_existing_documents: bool = True,
) -> None:
    """为 Browser 的所有 tab 注入反检测脚本。

    通过 CDP Page.addScriptToEvaluateOnNewDocument 注入，
    确保后续新页面自动继承。若 *evaluate_existing_documents* 为 True，
    还对每个已有页面并行执行 evaluate 立即生效；并行化避免了
    外部 Chrome tab 较多时按序 evaluate 导致的长尾等待。

    *profile_seed* 显式指定为字符串时，启用基于 BLAKE2b 的稳定指纹派生；
    传 ``None`` 显式关闭；省略（sentinel）则回退到 ``cfg.profile_seed``。
    """
    import asyncio  # pylint: disable=import-outside-toplevel

    from nodriver import cdp  # pylint: disable=import-outside-toplevel

    cfg = config or StealthConfig()
    if not cfg.enabled or not cfg.js_patches:
        _logger.debug("stealth JS patches 未启用，跳过注入")
        return

    script = build_stealth_js(
        webgl_vendor=_resolve_webgl_vendor(cfg, webgl_vendor),
        profile_seed=_resolve_profile_seed(cfg, profile_seed),
    )

    from ziniao_webdriver.cdp_tabs import filter_tabs  # pylint: disable=import-outside-toplevel

    async def _inject_init(tab: "Tab") -> None:
        try:
            await tab.send(
                cdp.page.add_script_to_evaluate_on_new_document(source=script)
            )
            _logger.debug("stealth init_script 已注入到 tab: %s", tab.target.url)
        except Exception:  # pylint: disable=broad-exception-caught
            _logger.debug("注入 init_script 到 tab 失败（tab 可能已关闭）")

    async def _evaluate_existing(tab: "Tab") -> None:
        try:
            await tab.evaluate(script)
            _logger.debug("stealth 已 evaluate 到已有 tab: %s", tab.target.url)
        except Exception:  # pylint: disable=broad-exception-caught
            _logger.debug("evaluate stealth 到 tab 失败（tab 可能已关闭）")

    tabs = list(filter_tabs(browser.tabs))
    if not tabs:
        return

    # 先并行注册 init_script，保证后续新 tab 即时继承；
    # 再按需对已有文档并行 evaluate。gather return_exceptions 吞掉单 tab 失败。
    await asyncio.gather(
        *[_inject_init(tab) for tab in tabs],
        return_exceptions=True,
    )
    if evaluate_existing_documents:
        await asyncio.gather(
            *[_evaluate_existing(tab) for tab in tabs],
            return_exceptions=True,
        )
