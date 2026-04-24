"""Stealth 模块单元测试 — 覆盖 JS 脚本构建、配置解析、行为模拟和 session 集成。"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ziniao_mcp.stealth import (
    StealthConfig,
    apply_stealth,
    evaluate_stealth_existing_document,
    BehaviorConfig,
)
from ziniao_mcp.stealth.js_patches import (
    STEALTH_JS,
    STEALTH_JS_MINIMAL,
    build_stealth_js,
)
from ziniao_webdriver.js_patches import (
    _WEBGL_POOL,
    derive_profile_fingerprint,
)
from ziniao_mcp.stealth.human_behavior import (
    random_delay,
    _bezier_curve,
    human_click,
    human_type,
    human_fill,
    human_hover,
    human_scroll,
)


# ------------------------------------------------------------------ #
#  JS 脚本构建
# ------------------------------------------------------------------ #

class TestBuildStealthJs:

    def test_default_includes_plugins_patch(self):
        js = build_stealth_js()
        assert "Chrome PDF Plugin" in js

    def test_default_includes_chrome_patch(self):
        js = build_stealth_js()
        assert "chrome.runtime" in js or "window.chrome" in js

    def test_default_excludes_webgl_vendor(self):
        js = build_stealth_js()
        assert "UNMASKED_VENDOR" not in js

    def test_webgl_vendor_opt_in(self):
        js = build_stealth_js(webgl_vendor=True)
        assert "UNMASKED_VENDOR" in js
        assert "Intel" in js

    def test_all_disabled_returns_empty(self):
        js = build_stealth_js(
            native_tostring=False, webdriver=False,
            plugins=False, permissions=False,
            chrome_obj=False, iframe_webdriver=False,
            webgl_vendor=False, canvas_fingerprint=False,
            audio_fingerprint=False, webrtc_leak=False,
            automation_flags=False,
        )
        assert js.strip() == ""

    def test_stealth_js_is_nonempty_string(self):
        assert isinstance(STEALTH_JS, str)
        assert len(STEALTH_JS) > 100

    def test_minimal_is_smaller_than_full(self):
        assert len(STEALTH_JS_MINIMAL) < len(STEALTH_JS)

    def test_default_includes_iframe_webdriver(self):
        js = build_stealth_js()
        assert "iframe" in js.lower()

    def test_default_includes_permissions(self):
        js = build_stealth_js()
        assert "permissions" in js

    def test_default_includes_native_tostring(self):
        js = build_stealth_js()
        assert "__stealth_native" in js
        assert "WeakMap" in js

    def test_default_includes_webdriver_override(self):
        js = build_stealth_js()
        assert "navigator" in js and "webdriver" in js

    def test_default_includes_chrome_app(self):
        js = build_stealth_js()
        assert "chrome.app" in js
        assert "InstallState" in js

    def test_default_includes_canvas_fingerprint(self):
        js = build_stealth_js()
        assert "toDataURL" in js
        assert "toBlob" in js

    def test_default_includes_audio_fingerprint(self):
        js = build_stealth_js()
        assert "AudioBuffer" in js
        assert "getChannelData" in js

    def test_default_includes_webrtc_leak(self):
        js = build_stealth_js()
        assert "RTCPeerConnection" in js
        assert "iceTransportPolicy" in js

    def test_cleanup_is_last_when_native_tostring_enabled(self):
        js = build_stealth_js()
        # 外层幂等 guard 以 `}` 收尾；cleanup 的 IIFE `})();` 应为 guard 之前的最后一个补丁。
        assert "delete window.__stealth_native" in js
        stripped = js.rstrip()
        assert stripped.endswith("}")
        # 确认 cleanup IIFE 出现在脚本后半段（位置接近末尾）
        cleanup_pos = js.rfind("})();")
        assert cleanup_pos > len(js) * 0.7

    def test_idempotent_guard_present(self):
        """整体脚本应带 __stealth_applied__ 幂等 guard，允许重复注入不重置状态。"""
        js = build_stealth_js()
        assert "__stealth_applied__" in js
        assert "if (!window.__stealth_applied__)" in js

    def test_native_marks_applied_to_overridden_fns(self):
        js = build_stealth_js()
        assert js.count("__stealth_native") > 2

    def test_canvas_disabled(self):
        js = build_stealth_js(canvas_fingerprint=False)
        assert "toDataURL" not in js

    def test_audio_disabled(self):
        js = build_stealth_js(audio_fingerprint=False)
        assert "AudioBuffer" not in js

    def test_webrtc_disabled(self):
        js = build_stealth_js(webrtc_leak=False)
        assert "RTCPeerConnection" not in js


# ------------------------------------------------------------------ #
#  稳定 profile_seed 派生：Canvas/Audio/WebGL 指纹
# ------------------------------------------------------------------ #

class TestProfileSeedDerivation:

    def test_none_returns_all_none(self):
        fp = derive_profile_fingerprint(None)
        assert fp == {
            "canvas_seed": None,
            "audio_seed": None,
            "webgl_vendor": None,
            "webgl_renderer": None,
        }

    def test_empty_string_returns_all_none(self):
        fp = derive_profile_fingerprint("")
        assert all(v is None for v in fp.values())

    def test_same_seed_is_stable(self):
        fp1 = derive_profile_fingerprint("ziniao:store-42")
        fp2 = derive_profile_fingerprint("ziniao:store-42")
        assert fp1 == fp2

    def test_different_seed_differs(self):
        # 两个不同 profile_seed 至少有一项输出不同（冲突概率可忽略）。
        fp_a = derive_profile_fingerprint("ziniao:store-A")
        fp_b = derive_profile_fingerprint("ziniao:store-B")
        assert fp_a != fp_b

    def test_canvas_seed_range(self):
        fp = derive_profile_fingerprint("ziniao:store-range")
        assert isinstance(fp["canvas_seed"], int)
        assert 0 <= fp["canvas_seed"] <= 0xFF

    def test_audio_seed_range(self):
        fp = derive_profile_fingerprint("ziniao:store-audio")
        assert isinstance(fp["audio_seed"], int)
        assert 0 <= fp["audio_seed"] <= 0xFFFF

    def test_webgl_pair_from_pool(self):
        fp = derive_profile_fingerprint("ziniao:store-webgl")
        assert (fp["webgl_vendor"], fp["webgl_renderer"]) in _WEBGL_POOL

    def test_pool_is_nonempty_and_realistic(self):
        assert len(_WEBGL_POOL) >= 5
        for vendor, renderer in _WEBGL_POOL:
            # 规避占位值：真实 Chrome 格式应带 "Google Inc." 前缀，
            # 绝非 "Intel Inc. / Intel Iris OpenGL Engine"。
            assert vendor.startswith("Google Inc."), vendor
            assert renderer.startswith("ANGLE ("), renderer


class TestBuildStealthJsWithSeed:

    def test_no_seed_has_no_seed_injection(self):
        # 没有 profile_seed 时，不应生成 defineProperty 赋值段；
        # PATCH_CANVAS_FINGERPRINT 里仍保留 typeof 兜底分支，属预期。
        js = build_stealth_js()
        assert 'value: ' not in js or \
            "Object.defineProperty(window, \"__STEALTH_SEED_CANVAS__\"" not in js

    def test_seed_injects_canvas_constant(self):
        js = build_stealth_js(profile_seed="ziniao:store-1")
        # 稳定 seed 下必有 defineProperty 写入 Canvas/Audio 两个全局。
        assert 'Object.defineProperty(window, "__STEALTH_SEED_CANVAS__"' in js
        assert 'Object.defineProperty(window, "__STEALTH_SEED_AUDIO__"' in js

    def test_seed_injects_webgl_when_enabled(self):
        js = build_stealth_js(
            profile_seed="ziniao:store-1", webgl_vendor=True,
        )
        assert "__STEALTH_WEBGL_VENDOR__" in js
        # 应包含 _WEBGL_POOL 中某一条 renderer 字符串（不再是 Intel 占位）。
        fp = derive_profile_fingerprint("ziniao:store-1")
        assert fp["webgl_renderer"] in js

    def test_cleanup_always_removes_seed_globals(self):
        js = build_stealth_js(profile_seed="ziniao:store-1")
        # CLEANUP 应统一清理所有 stealth 全局，避免残留痕迹。
        for name in (
            "__stealth_native",
            "__STEALTH_SEED_CANVAS__",
            "__STEALTH_SEED_AUDIO__",
            "__STEALTH_WEBGL_VENDOR__",
            "__STEALTH_WEBGL_RENDERER__",
        ):
            assert name in js

    def test_seed_stable_build_output(self):
        # 同 seed 构建的 JS 字节串稳定（便于 addScript 缓存/幂等 guard）。
        a = build_stealth_js(profile_seed="ziniao:store-42")
        b = build_stealth_js(profile_seed="ziniao:store-42")
        assert a == b

    def test_different_seed_produces_different_script(self):
        a = build_stealth_js(profile_seed="ziniao:store-A")
        b = build_stealth_js(profile_seed="ziniao:store-B")
        assert a != b

    def test_stealth_js_minimal_still_has_no_seed(self):
        # 模块级 STEALTH_JS_MINIMAL 不带 profile_seed，保持向后兼容；
        # 也不包含 Canvas/Audio 指纹补丁，故完全不应出现 SEED 全局名。
        assert "__STEALTH_SEED_CANVAS__" not in STEALTH_JS_MINIMAL
        assert "__STEALTH_WEBGL_VENDOR__" not in STEALTH_JS_MINIMAL


# ------------------------------------------------------------------ #
#  StealthConfig
# ------------------------------------------------------------------ #

class TestStealthConfig:

    def test_defaults(self):
        cfg = StealthConfig()
        assert cfg.enabled is True
        assert cfg.js_patches is True
        assert cfg.human_behavior is True
        assert cfg.delay_min_ms == 200
        assert cfg.delay_max_ms == 800

    def test_from_dict_empty(self):
        cfg = StealthConfig.from_dict({})
        assert cfg.enabled is True

    def test_from_dict_full(self):
        cfg = StealthConfig.from_dict({
            "enabled": False,
            "js_patches": False,
            "human_behavior": False,
            "delay_range": [100, 500],
            "typing_speed": [30, 120],
            "mouse_movement": False,
        })
        assert cfg.enabled is False
        assert cfg.js_patches is False
        assert cfg.delay_min_ms == 100
        assert cfg.delay_max_ms == 500
        assert cfg.typing_min_ms == 30
        assert cfg.typing_max_ms == 120
        assert cfg.mouse_movement is False

    def test_from_dict_none(self):
        cfg = StealthConfig.from_dict(None)
        assert cfg.enabled is True

    def test_profile_seed_default_none(self):
        cfg = StealthConfig()
        assert cfg.profile_seed is None

    def test_profile_seed_from_dict(self):
        cfg = StealthConfig.from_dict({"profile_seed": "ziniao:store-dict"})
        assert cfg.profile_seed == "ziniao:store-dict"

    def test_to_behavior_config(self):
        cfg = StealthConfig(delay_min_ms=100, delay_max_ms=400,
                            typing_min_ms=40, typing_max_ms=100,
                            mouse_movement=False)
        bc = cfg.to_behavior_config()
        assert isinstance(bc, BehaviorConfig)
        assert bc.delay_min_ms == 100
        assert bc.delay_max_ms == 400
        assert bc.typing_min_ms == 40
        assert bc.typing_max_ms == 100
        assert bc.mouse_movement is False


# ------------------------------------------------------------------ #
#  apply_stealth (now works with nodriver.Browser)
# ------------------------------------------------------------------ #

class TestApplyStealth:

    @pytest.mark.asyncio
    async def test_injects_script_to_tabs(self):
        tab = AsyncMock()
        tab.target = MagicMock()
        tab.target.url = "https://example.com"
        browser = MagicMock()
        browser.tabs = [tab]
        await apply_stealth(browser)
        tab.send.assert_awaited()
        tab.evaluate.assert_awaited()

    @pytest.mark.asyncio
    async def test_handles_multiple_tabs(self):
        tab1 = AsyncMock()
        tab1.target = MagicMock()
        tab1.target.url = "https://example.com"
        tab2 = AsyncMock()
        tab2.target = MagicMock()
        tab2.target.url = "https://other.com"
        browser = MagicMock()
        browser.tabs = [tab1, tab2]
        await apply_stealth(browser)
        assert tab1.send.await_count >= 1
        assert tab2.send.await_count >= 1

    @pytest.mark.asyncio
    async def test_skips_evaluate_when_evaluate_existing_documents_false(self):
        tab1 = AsyncMock()
        tab1.target = MagicMock()
        tab1.target.url = "https://a.com"
        tab2 = AsyncMock()
        tab2.target = MagicMock()
        tab2.target.url = "https://b.com"
        browser = MagicMock()
        browser.tabs = [tab1, tab2]
        await apply_stealth(browser, evaluate_existing_documents=False)
        tab1.send.assert_awaited()
        tab2.send.assert_awaited()
        tab1.evaluate.assert_not_awaited()
        tab2.evaluate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_evaluate_stealth_existing_document(self):
        tab = AsyncMock()
        tab.target = MagicMock()
        tab.target.url = "https://example.com"
        await evaluate_stealth_existing_document(tab)
        tab.evaluate.assert_awaited()

    @pytest.mark.asyncio
    async def test_skips_when_disabled(self):
        browser = MagicMock()
        browser.tabs = []
        cfg = StealthConfig(enabled=False)
        await apply_stealth(browser, config=cfg)

    @pytest.mark.asyncio
    async def test_skips_when_js_patches_disabled(self):
        tab = AsyncMock()
        browser = MagicMock()
        browser.tabs = [tab]
        cfg = StealthConfig(enabled=True, js_patches=False)
        await apply_stealth(browser, config=cfg)
        tab.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_handles_tab_evaluate_failure(self):
        tab = AsyncMock()
        tab.target = MagicMock()
        tab.target.url = "about:blank"
        tab.evaluate.side_effect = Exception("tab closed")
        browser = MagicMock()
        browser.tabs = [tab]
        await apply_stealth(browser)
        tab.send.assert_awaited()


# ------------------------------------------------------------------ #
#  贝塞尔曲线
# ------------------------------------------------------------------ #

class TestBezierCurve:

    def test_returns_correct_number_of_points(self):
        points = _bezier_curve((0, 0), (100, 100), 10)
        assert len(points) == 11

    def test_starts_at_start(self):
        points = _bezier_curve((0, 0), (100, 100), 20)
        assert points[0] == (0, 0)

    def test_ends_at_end(self):
        points = _bezier_curve((0, 0), (100, 100), 20)
        assert points[-1] == (100, 100)

    def test_points_are_int_tuples(self):
        points = _bezier_curve((10, 20), (300, 400), 5)
        for x, y in points:
            assert isinstance(x, int)
            assert isinstance(y, int)


# ------------------------------------------------------------------ #
#  random_delay
# ------------------------------------------------------------------ #

class TestRandomDelay:

    @pytest.mark.asyncio
    async def test_completes_without_error(self):
        cfg = BehaviorConfig(delay_min_ms=1, delay_max_ms=5)
        await random_delay(cfg=cfg)

    @pytest.mark.asyncio
    async def test_explicit_range(self):
        await random_delay(1, 5)


# ------------------------------------------------------------------ #
#  Helper: mock nodriver Tab
# ------------------------------------------------------------------ #

def _make_tab(**overrides):
    """构造一个模拟 nodriver Tab 对象。"""
    tab = AsyncMock()

    elem = AsyncMock()
    pos = MagicMock()
    bb = overrides.get("bounding_box", {"x": 100, "y": 200, "width": 50, "height": 30})
    if bb:
        pos.left = bb["x"]
        pos.top = bb["y"]
        pos.width = bb["width"]
        pos.height = bb["height"]
        pos.center = (bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2)
        elem.get_position = AsyncMock(return_value=pos)
    else:
        elem.get_position = AsyncMock(return_value=None)
    elem.click = AsyncMock()
    elem.mouse_move = AsyncMock()
    elem.send_keys = AsyncMock()

    tab.select = AsyncMock(return_value=elem)
    tab.evaluate = AsyncMock(return_value={"x": 0, "y": 0})
    tab.mouse_click = AsyncMock()
    tab.mouse_drag = AsyncMock()
    tab.send = AsyncMock()
    return tab


# ------------------------------------------------------------------ #
#  human_click
# ------------------------------------------------------------------ #

class TestHumanClick:

    @pytest.mark.asyncio
    async def test_clicks_with_dom_click_on_element(self):
        tab = _make_tab()
        cfg = BehaviorConfig(mouse_movement=False, delay_min_ms=1, delay_max_ms=2)
        elem = tab.select.return_value
        await human_click(tab, "#btn", cfg=cfg)
        elem.click.assert_awaited_once()
        tab.mouse_click.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_iframe_element_uses_protocol_mouse(self):
        from ziniao_mcp.iframe import IFrameElement

        tab = _make_tab()
        cfg = BehaviorConfig(mouse_movement=False, delay_min_ms=1, delay_max_ms=2)
        iframe_el = IFrameElement(
            tab=tab, abs_x=100, abs_y=200, width=50, height=30, context_id=1,
        )
        await human_click(tab, "#btn", cfg=cfg, element=iframe_el)
        tab.mouse_click.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fallback_when_no_bounding_box(self):
        tab = _make_tab(bounding_box=None)
        cfg = BehaviorConfig(mouse_movement=False, delay_min_ms=1, delay_max_ms=2)
        await human_click(tab, "#btn", cfg=cfg)
        elem = await tab.select("#btn", timeout=5)
        elem.click.assert_awaited()
        elem.mouse_click.assert_not_awaited()


# ------------------------------------------------------------------ #
#  human_type
# ------------------------------------------------------------------ #

class TestHumanType:

    @pytest.mark.asyncio
    async def test_types_each_character(self):
        tab = _make_tab()
        cfg = BehaviorConfig(typing_min_ms=1, typing_max_ms=2,
                             delay_min_ms=1, delay_max_ms=2,
                             mouse_movement=False)
        await human_type(tab, "abc", cfg=cfg)
        assert tab.send.await_count == 3

    @pytest.mark.asyncio
    async def test_clicks_selector_first(self):
        tab = _make_tab()
        cfg = BehaviorConfig(typing_min_ms=1, typing_max_ms=2,
                             delay_min_ms=1, delay_max_ms=2,
                             mouse_movement=False)
        elem = tab.select.return_value
        await human_type(tab, "a", selector="#input", cfg=cfg)
        elem.click.assert_awaited()


# ------------------------------------------------------------------ #
#  human_fill
# ------------------------------------------------------------------ #

class TestHumanFill:

    @pytest.mark.asyncio
    async def test_clears_and_types(self):
        tab = _make_tab()
        cfg = BehaviorConfig(typing_min_ms=1, typing_max_ms=2,
                             delay_min_ms=1, delay_max_ms=2,
                             mouse_movement=False)
        await human_fill(tab, "#input", "hi", cfg=cfg)
        assert tab.send.await_count >= 4  # Ctrl+A down, up, Backspace down, up + 2 char types


# ------------------------------------------------------------------ #
#  human_hover
# ------------------------------------------------------------------ #

class TestHumanHover:

    @pytest.mark.asyncio
    async def test_moves_mouse_to_element(self):
        tab = _make_tab(bounding_box={"x": 50, "y": 50, "width": 100, "height": 40})
        cfg = BehaviorConfig(mouse_movement=False, delay_min_ms=1, delay_max_ms=2)
        await human_hover(tab, "#el", cfg=cfg)
        tab.send.assert_awaited()

    @pytest.mark.asyncio
    async def test_fallback_when_no_bounding_box(self):
        tab = _make_tab(bounding_box=None)
        cfg = BehaviorConfig(mouse_movement=False, delay_min_ms=1, delay_max_ms=2)
        await human_hover(tab, "#el", cfg=cfg)
        elem = await tab.select("#el", timeout=5)
        elem.mouse_move.assert_awaited()


# ------------------------------------------------------------------ #
#  human_scroll
# ------------------------------------------------------------------ #

class TestHumanScroll:

    @pytest.mark.asyncio
    async def test_scrolls_down(self):
        tab = _make_tab()
        cfg = BehaviorConfig(delay_min_ms=1, delay_max_ms=2)
        await human_scroll(tab, "down", 200, cfg=cfg)
        assert tab.send.await_count > 0

    @pytest.mark.asyncio
    async def test_scrolls_up(self):
        tab = _make_tab()
        cfg = BehaviorConfig(delay_min_ms=1, delay_max_ms=2)
        await human_scroll(tab, "up", 200, cfg=cfg)
        assert tab.send.await_count > 0


# ------------------------------------------------------------------ #
#  SessionManager stealth 集成
# ------------------------------------------------------------------ #

class TestSessionManagerStealthIntegration:

    def test_default_stealth_config(self):
        from ziniao_mcp.session import SessionManager
        client = MagicMock()
        sm = SessionManager(client)
        assert sm.stealth_config.enabled is True
        assert sm.stealth_config.js_patches is True

    def test_custom_stealth_config(self):
        from ziniao_mcp.session import SessionManager
        client = MagicMock()
        cfg = StealthConfig(enabled=False)
        sm = SessionManager(client, stealth_config=cfg)
        assert sm.stealth_config.enabled is False

    @pytest.mark.asyncio
    async def test_apply_stealth_called_on_browser(self):
        from ziniao_mcp.session import SessionManager
        client = MagicMock()
        sm = SessionManager(client)
        tab = AsyncMock()
        tab.target = MagicMock()
        tab.target.url = "https://example.com"
        browser = MagicMock()
        browser.tabs = [tab]
        await sm._apply_stealth_to_browser(browser)
        tab.send.assert_awaited()

    @pytest.mark.asyncio
    async def test_apply_stealth_skipped_when_disabled(self):
        from ziniao_mcp.session import SessionManager
        client = MagicMock()
        sm = SessionManager(client, stealth_config=StealthConfig(enabled=False))
        browser = MagicMock()
        browser.tabs = []
        await sm._apply_stealth_to_browser(browser)
