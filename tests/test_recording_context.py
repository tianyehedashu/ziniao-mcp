"""Tests for recording browser context resolution and session attach."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from ziniao_mcp.recording_context import RecordingBrowserContext, resolve_recording_browser_context
from ziniao_mcp.session import SessionManager


def test_resolve_from_new_meta_fields() -> None:
    meta = {
        "session_id": "store-a",
        "backend_type": "ziniao",
        "cdp_port": 12345,
    }
    ctx = resolve_recording_browser_context(meta, {})
    assert ctx == RecordingBrowserContext("store-a", "ziniao", 12345)


def test_resolve_chrome_fills_port_from_state() -> None:
    meta = {"session_id": "chrome-9333", "backend_type": "chrome", "cdp_port": 0}
    state = {"chrome-9333": {"cdp_port": 9333, "backend_type": "chrome"}}
    ctx = resolve_recording_browser_context(meta, state)
    assert ctx == RecordingBrowserContext("chrome-9333", "chrome", 9333)


def test_resolve_legacy_cdp_port_picks_sorted_key() -> None:
    meta = {"cdp_port": 9000}
    state = {
        "z2": {"cdp_port": 9000, "backend_type": "ziniao"},
        "z1": {"cdp_port": 9000, "backend_type": "ziniao"},
    }
    ctx = resolve_recording_browser_context(meta, state)
    assert ctx is not None
    assert ctx.session_id == "z1"
    assert ctx.cdp_port == 9000


def test_resolve_returns_none_when_unmatched() -> None:
    assert resolve_recording_browser_context({"cdp_port": 1}, {}) is None


@pytest.mark.asyncio
async def test_attach_from_recording_context_ziniao() -> None:
    sm = SessionManager()
    sm.connect_store = AsyncMock()
    sm.connect_chrome = AsyncMock()
    ctx = RecordingBrowserContext("s1", "ziniao", 111)
    await sm.attach_from_recording_context(ctx)
    sm.connect_store.assert_awaited_once_with("s1")
    sm.connect_chrome.assert_not_awaited()


@pytest.mark.asyncio
async def test_attach_from_recording_context_chrome_default_name() -> None:
    sm = SessionManager()
    sm.connect_store = AsyncMock()
    sm.connect_chrome = AsyncMock()
    ctx = RecordingBrowserContext("chrome-9222", "chrome", 9222)
    await sm.attach_from_recording_context(ctx)
    sm.connect_chrome.assert_awaited_once_with(9222, name="")
    sm.connect_store.assert_not_awaited()


@pytest.mark.asyncio
async def test_attach_from_recording_context_chrome_custom_id() -> None:
    sm = SessionManager()
    sm.connect_store = AsyncMock()
    sm.connect_chrome = AsyncMock()
    ctx = RecordingBrowserContext("my-profile", "chrome", 9515)
    await sm.attach_from_recording_context(ctx)
    sm.connect_chrome.assert_awaited_once_with(9515, name="my-profile")
