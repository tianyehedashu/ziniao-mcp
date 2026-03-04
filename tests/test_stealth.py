"""Stealth 模块单元测试 — 覆盖 JS 脚本构建、配置解析、行为模拟和 session 集成。"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ziniao_mcp.stealth import StealthConfig, apply_stealth, BehaviorConfig
from ziniao_mcp.stealth.js_patches import (
    STEALTH_JS,
    STEALTH_JS_MINIMAL,
    build_stealth_js,
    PATCH_NAVIGATOR_WEBDRIVER,
    PATCH_NAVIGATOR_PLUGINS,
    PATCH_WINDOW_CHROME,
    PATCH_PLAYWRIGHT_GLOBALS,
    PATCH_WEBGL_VENDOR,
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

    def test_default_includes_webdriver_patch(self):
        js = build_stealth_js()
        assert "navigator" in js
        assert "webdriver" in js

    def test_default_includes_plugins_patch(self):
        js = build_stealth_js()
        assert "Chrome PDF Plugin" in js

    def test_default_includes_chrome_patch(self):
        js = build_stealth_js()
        assert "chrome.runtime" in js or "window.chrome" in js

    def test_default_includes_playwright_cleanup(self):
        js = build_stealth_js()
        assert "__playwright" in js

    def test_default_excludes_webgl_vendor(self):
        js = build_stealth_js()
        assert "UNMASKED_VENDOR" not in js

    def test_webgl_vendor_opt_in(self):
        js = build_stealth_js(webgl_vendor=True)
        assert "UNMASKED_VENDOR" in js
        assert "Intel" in js

    def test_all_disabled_returns_empty(self):
        js = build_stealth_js(
            webdriver=False, plugins=False, permissions=False,
            chrome_obj=False, playwright_globals=False, console_debug=False,
            iframe_webdriver=False, webgl_vendor=False, automation_flags=False,
        )
        assert js.strip() == ""

    def test_stealth_js_is_nonempty_string(self):
        assert isinstance(STEALTH_JS, str)
        assert len(STEALTH_JS) > 100

    def test_minimal_is_smaller_than_full(self):
        assert len(STEALTH_JS_MINIMAL) < len(STEALTH_JS)

    def test_minimal_still_has_webdriver_patch(self):
        assert "webdriver" in STEALTH_JS_MINIMAL


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
#  apply_stealth
# ------------------------------------------------------------------ #

class TestApplyStealth:

    @pytest.mark.asyncio
    async def test_injects_script_to_context(self):
        ctx = AsyncMock()
        ctx.pages = []
        await apply_stealth(ctx)
        ctx.add_init_script.assert_awaited_once()
        script_arg = ctx.add_init_script.call_args
        assert "webdriver" in script_arg.kwargs.get("script", "")

    @pytest.mark.asyncio
    async def test_evaluates_on_existing_pages(self):
        page1, page2 = AsyncMock(), AsyncMock()
        page1.url = "https://example.com"
        page2.url = "https://other.com"
        ctx = AsyncMock()
        ctx.pages = [page1, page2]
        await apply_stealth(ctx)
        page1.evaluate.assert_awaited_once()
        page2.evaluate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_when_disabled(self):
        ctx = AsyncMock()
        cfg = StealthConfig(enabled=False)
        await apply_stealth(ctx, config=cfg)
        ctx.add_init_script.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_when_js_patches_disabled(self):
        ctx = AsyncMock()
        cfg = StealthConfig(enabled=True, js_patches=False)
        await apply_stealth(ctx, config=cfg)
        ctx.add_init_script.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_handles_page_evaluate_failure(self):
        page = AsyncMock()
        page.evaluate.side_effect = Exception("page closed")
        page.url = "about:blank"
        ctx = AsyncMock()
        ctx.pages = [page]
        await apply_stealth(ctx)
        ctx.add_init_script.assert_awaited_once()


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
#  human_click
# ------------------------------------------------------------------ #

def _make_page(**overrides):
    """构造一个模拟 Playwright Page 对象，locator() 同步返回 locator mock。"""
    page = AsyncMock()
    locator_mock = MagicMock()
    locator_mock.bounding_box = AsyncMock(
        return_value=overrides.get("bounding_box", {"x": 100, "y": 200, "width": 50, "height": 30})
    )
    locator_mock.click = AsyncMock()
    locator_mock.hover = AsyncMock()
    page.locator = MagicMock(return_value=locator_mock)
    page.evaluate = AsyncMock(return_value={"x": 0, "y": 0})
    page.mouse = AsyncMock()
    page.keyboard = AsyncMock()
    return page


class TestHumanClick:

    @pytest.mark.asyncio
    async def test_clicks_with_mouse(self):
        page = _make_page()
        cfg = BehaviorConfig(mouse_movement=False, delay_min_ms=1, delay_max_ms=2)
        await human_click(page, "#btn", cfg=cfg)
        page.mouse.click.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fallback_when_no_bounding_box(self):
        page = _make_page(bounding_box=None)
        cfg = BehaviorConfig(mouse_movement=False, delay_min_ms=1, delay_max_ms=2)
        await human_click(page, "#btn", cfg=cfg)
        page.locator.return_value.click.assert_awaited_once()


# ------------------------------------------------------------------ #
#  human_type
# ------------------------------------------------------------------ #

class TestHumanType:

    @pytest.mark.asyncio
    async def test_types_each_character(self):
        page = _make_page()
        cfg = BehaviorConfig(typing_min_ms=1, typing_max_ms=2,
                             delay_min_ms=1, delay_max_ms=2,
                             mouse_movement=False)
        await human_type(page, "abc", cfg=cfg)
        assert page.keyboard.type.await_count == 3

    @pytest.mark.asyncio
    async def test_clicks_selector_first(self):
        page = _make_page()
        cfg = BehaviorConfig(typing_min_ms=1, typing_max_ms=2,
                             delay_min_ms=1, delay_max_ms=2,
                             mouse_movement=False)
        await human_type(page, "a", selector="#input", cfg=cfg)
        page.mouse.click.assert_awaited()


# ------------------------------------------------------------------ #
#  human_fill
# ------------------------------------------------------------------ #

class TestHumanFill:

    @pytest.mark.asyncio
    async def test_clears_and_types(self):
        page = _make_page()
        cfg = BehaviorConfig(typing_min_ms=1, typing_max_ms=2,
                             delay_min_ms=1, delay_max_ms=2,
                             mouse_movement=False)
        await human_fill(page, "#input", "hi", cfg=cfg)
        page.keyboard.press.assert_any_await("Control+a")
        page.keyboard.press.assert_any_await("Backspace")
        assert page.keyboard.type.await_count == 2


# ------------------------------------------------------------------ #
#  human_hover
# ------------------------------------------------------------------ #

class TestHumanHover:

    @pytest.mark.asyncio
    async def test_moves_mouse_to_element(self):
        page = _make_page(bounding_box={"x": 50, "y": 50, "width": 100, "height": 40})
        cfg = BehaviorConfig(mouse_movement=False, delay_min_ms=1, delay_max_ms=2)
        await human_hover(page, "#el", cfg=cfg)
        page.mouse.move.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fallback_when_no_bounding_box(self):
        page = _make_page(bounding_box=None)
        cfg = BehaviorConfig(mouse_movement=False, delay_min_ms=1, delay_max_ms=2)
        await human_hover(page, "#el", cfg=cfg)
        page.locator.return_value.hover.assert_awaited_once()


# ------------------------------------------------------------------ #
#  human_scroll
# ------------------------------------------------------------------ #

class TestHumanScroll:

    @pytest.mark.asyncio
    async def test_scrolls_down(self):
        page = AsyncMock()
        page.mouse = AsyncMock()

        cfg = BehaviorConfig(delay_min_ms=1, delay_max_ms=2)
        await human_scroll(page, "down", 200, cfg=cfg)
        assert page.mouse.wheel.await_count > 0

    @pytest.mark.asyncio
    async def test_scrolls_up(self):
        page = AsyncMock()
        page.mouse = AsyncMock()

        cfg = BehaviorConfig(delay_min_ms=1, delay_max_ms=2)
        await human_scroll(page, "up", 200, cfg=cfg)
        first_call_args = page.mouse.wheel.call_args_list[0].args
        assert first_call_args[1] < 0


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
    async def test_apply_stealth_called_on_context(self):
        from ziniao_mcp.session import SessionManager
        client = MagicMock()
        sm = SessionManager(client)
        ctx = AsyncMock()
        ctx.pages = []
        await sm._apply_stealth_to_context(ctx)
        ctx.add_init_script.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_apply_stealth_skipped_when_disabled(self):
        from ziniao_mcp.session import SessionManager
        client = MagicMock()
        sm = SessionManager(client, stealth_config=StealthConfig(enabled=False))
        ctx = AsyncMock()
        await sm._apply_stealth_to_context(ctx)
        ctx.add_init_script.assert_not_awaited()
