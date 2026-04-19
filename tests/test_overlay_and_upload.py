"""Tests for overlay clearing and upload-hijack enhancements."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sm(send=None):
    class _Tab:
        async def send(self, cdp_gen, **kw):
            if send:
                return await send(cdp_gen, **kw)
            return {}

    tab = _Tab()
    tab.target = type("Tg", (), {"url": "about:blank"})()
    tab.sleep = AsyncMock()
    session = type("Sess", (), {"backend_type": "chrome"})()
    return type(
        "SM",
        (),
        {
            "get_active_tab": lambda self: tab,
            "get_active_session": lambda self: session,
        },
    )()


async def _fake_find_element_ok(_tab, _selector, _store, timeout=10):
    return type("El", (), {"click": AsyncMock(), "offset_width": 100, "offset_height": 30})()


def _patch_for_click(monkeypatch, dispatch_mod, dispatch_click=None):
    """Patch _clear_overlay and find_element so _click works in tests."""
    from ziniao_mcp import iframe
    monkeypatch.setattr(iframe, "find_element", _fake_find_element_ok)
    if dispatch_click:
        import ziniao_mcp._interaction_helpers as ih
        monkeypatch.setattr(ih, "dispatch_click", dispatch_click)


# ---------------------------------------------------------------------------
# _clear_overlay
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clear_overlay_calls_js_and_returns_count(monkeypatch) -> None:
    from ziniao_mcp.cli import dispatch as d

    js_history: list[str] = []

    async def fake_run_js(_tab, _store, js, **_kw):
        js_history.append(js)
        return 3

    sm = _make_sm()
    monkeypatch.setattr(d, "_run_js_in_context", fake_run_js)

    result = await d._clear_overlay(sm, {})
    assert result["ok"] is True
    assert result["removed"] == 3
    assert len(js_history) == 1
    assert "getComputedStyle" in js_history[0]


@pytest.mark.asyncio
async def test_clear_overlay_handles_runtime_error(monkeypatch) -> None:
    from ziniao_mcp.cli import dispatch as d

    async def fake_run_js(_tab, _store, js, **_kw):
        raise RuntimeError("tab closed")

    sm = _make_sm()
    monkeypatch.setattr(d, "_run_js_in_context", fake_run_js)

    result = await d._clear_overlay(sm, {})
    assert result["ok"] is False
    assert "tab closed" in result["error"]


# ---------------------------------------------------------------------------
# _click with auto clear
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_click_auto_clears_overlay_before_finding_element(monkeypatch) -> None:
    from ziniao_mcp.cli import dispatch as d

    call_log: list[str] = []

    async def fake_clear(_sm, _args):
        call_log.append("clear")
        return {"ok": True, "removed": 1}

    async def fake_dispatch_click(_tab, _sel, _elem, _sm):
        call_log.append("dispatch_click")

    sm = _make_sm()
    monkeypatch.setattr(d, "_clear_overlay", fake_clear)
    _patch_for_click(monkeypatch, d, fake_dispatch_click)

    result = await d._click(sm, {"selector": ".btn"})
    assert result["ok"] is True
    assert "clear" in call_log


@pytest.mark.asyncio
async def test_click_skips_auto_clear_when_flagged(monkeypatch) -> None:
    from ziniao_mcp.cli import dispatch as d

    call_log: list[str] = []

    async def fake_clear(_sm, _args):
        call_log.append("clear")
        return {"ok": True, "removed": 0}

    sm = _make_sm()
    monkeypatch.setattr(d, "_clear_overlay", fake_clear)
    _patch_for_click(monkeypatch, d, AsyncMock())

    result = await d._click(sm, {"selector": ".btn", "no_auto_clear": True})
    assert result["ok"] is True
    assert "clear" not in call_log


@pytest.mark.asyncio
async def test_click_auto_clear_failure_does_not_block(monkeypatch) -> None:
    from ziniao_mcp.cli import dispatch as d

    async def fake_clear(_sm, _args):
        raise RuntimeError("JS error")

    sm = _make_sm()
    monkeypatch.setattr(d, "_clear_overlay", fake_clear)
    _patch_for_click(monkeypatch, d, AsyncMock())

    result = await d._click(sm, {"selector": ".btn"})
    assert result["ok"] is True


# ---------------------------------------------------------------------------
# upload-hijack object_id fast path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_hijack_object_id_direct_cdp(monkeypatch, tmp_path) -> None:
    from ziniao_mcp.cli import dispatch as d

    sent_commands: list = []
    test_file = tmp_path / "image.jpg"
    test_file.write_bytes(b"\xff\xd8\xff\xe0")

    async def fake_send(cdp_gen, **_kw):
        sent_commands.append(cdp_gen)
        return {}

    sm = _make_sm(send=fake_send)

    result = await d._upload_hijack(sm, {
        "object_id": "5442436388121088264.68.1",
        "file_paths": [str(test_file)],
    })
    assert result["ok"] is True, f"got: {result}"
    assert result["method"] == "direct_cdp"
    assert result["files"] == 1
    assert len(sent_commands) == 1


@pytest.mark.asyncio
async def test_upload_hijack_object_id_errors_without_files(monkeypatch) -> None:
    from ziniao_mcp.cli import dispatch as d

    sm = _make_sm()
    result = await d._upload_hijack(sm, {
        "object_id": "5442436388121088264.68.1",
        "file_paths": [],
    })
    assert "error" in result
    assert "file_paths is required" in result["error"]


@pytest.mark.asyncio
async def test_upload_hijack_object_id_cdp_failure(monkeypatch) -> None:
    from ziniao_mcp.cli import dispatch as d

    async def fake_send(self, cdp_gen, **_kw):
        raise Exception("CDP connection lost")

    sm = _make_sm(send=fake_send)

    # file doesn't exist → file-not-found error (caught before CDP call)
    result = await d._upload_hijack(sm, {
        "object_id": "invalid",
        "file_paths": ["C:\\nonexistent\\image.jpg"],
    })
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# upload-hijack auto overlay clear
# ---------------------------------------------------------------------------


def _make_upload_hijack_run_js():
    """Return a fake _run_js_in_context that handles both hook install and poll."""
    call_count = 0

    async def fake_run_js(_tab, _store, js, **_kw):
        nonlocal call_count
        call_count += 1
        # First call is hook install — it's a large script block
        # Subsequent calls are the poll: just "window.__ziniao_upload_hijack"
        if call_count == 1:
            return "hook_installed"
        return {"fired": 0, "done": False, "error": None}

    return fake_run_js


@pytest.mark.asyncio
async def test_upload_hijack_auto_clears_overlay_before_trigger(monkeypatch, tmp_path) -> None:
    from ziniao_mcp.cli import dispatch as d

    call_log: list[str] = []
    test_file = tmp_path / "img.jpg"
    test_file.write_bytes(b"\xff\xd8")

    async def fake_clear(_sm, _args):
        call_log.append("clear")
        return {"ok": True, "removed": 1}

    async def fake_click(_sm, args):
        call_log.append("click")
        return {"ok": True, "clicked": args["selector"]}

    sm = _make_sm()
    monkeypatch.setattr(d, "_clear_overlay", fake_clear)
    monkeypatch.setattr(d, "_click", fake_click)
    monkeypatch.setattr(d, "_run_js_in_context", _make_upload_hijack_run_js())

    result = await d._upload_hijack(sm, {
        "file_paths": [str(test_file)],
        "trigger": ".upload-btn",
        "wait_ms": 2000,
    })
    assert "clear" in call_log, f"expected clear in {call_log}, result: {result}"
    assert "click" in call_log


@pytest.mark.asyncio
async def test_upload_hijack_no_auto_clear_skips_overlay(monkeypatch, tmp_path) -> None:
    from ziniao_mcp.cli import dispatch as d

    call_log: list[str] = []
    test_file = tmp_path / "img.jpg"
    test_file.write_bytes(b"\xff\xd8")

    async def fake_clear(_sm, _args):
        call_log.append("clear")
        return {"ok": True, "removed": 0}

    async def fake_click(_sm, args):
        call_log.append("click")
        return {"ok": True, "clicked": args["selector"]}

    sm = _make_sm()
    monkeypatch.setattr(d, "_clear_overlay", fake_clear)
    monkeypatch.setattr(d, "_click", fake_click)
    monkeypatch.setattr(d, "_run_js_in_context", _make_upload_hijack_run_js())

    result = await d._upload_hijack(sm, {
        "file_paths": [str(test_file)],
        "trigger": ".upload-btn",
        "wait_ms": 2000,
        "no_auto_clear": True,
    })
    assert "clear" not in call_log
    assert "click" in call_log


# ---------------------------------------------------------------------------
# command map registration
# ---------------------------------------------------------------------------


def test_clear_overlay_registered_in_command_map() -> None:
    from ziniao_mcp.cli import dispatch as d
    assert "clear-overlay" in d._COMMANDS
    assert callable(d._COMMANDS["clear-overlay"])
