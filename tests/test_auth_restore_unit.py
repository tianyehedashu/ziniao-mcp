"""Unit tests for ziniao_mcp.core.auth_restore."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from ziniao_mcp import cookie_vault as cv
from ziniao_mcp.cli import dispatch as d_dispatch
from ziniao_mcp.core import auth_restore


class _ProbeTab:
    target = type("_T", (), {"url": ""})()


class _ProbeSession:
    runtime_config: dict = {}

    def get_active_tab(self) -> _ProbeTab:
        return _ProbeTab()

    def get_active_session(self) -> object:
        return object()


@pytest.mark.asyncio
async def test_cookie_vault_restore_uses_configured_settle_defaults(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    captured: dict = {}

    async def _fake_restore(_tab, _snap, **kwargs):
        captured.update(kwargs)
        return {"ok": True, "restored": True, "verified": False}

    monkeypatch.setattr("ziniao_mcp.core.auth_restore.restore_tab_session", _fake_restore)
    snap = tmp_path / "s.json"
    snap.write_text(
        '{"schema_version": 1, "page_url": "https://x.com/", '
        '"cookies": [{"name": "a", "value": "b", "domain": "x.com", "path": "/"}]}',
        encoding="utf-8",
    )
    session = _ProbeSession()
    session.runtime_config = {
        "cookie_vault": {
            "restore": {
                "navigate_settle_sec": 0.25,
                "reload_settle_sec": 0.5,
            }
        }
    }
    r = await d_dispatch._cookie_vault(
        session,
        {"action": "restore", "path": str(snap)},
    )
    assert r.get("ok") is True
    assert captured["navigate_settle_sec"] == 0.25
    assert captured["reload_settle_sec"] == 0.5


@pytest.mark.asyncio
async def test_cookie_vault_restore_reloads_current_yaml_defaults(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    captured: dict = {}

    async def _fake_restore(_tab, _snap, **kwargs):
        captured.update(kwargs)
        return {"ok": True, "restored": True, "verified": False}

    monkeypatch.setattr("ziniao_mcp.core.auth_restore.restore_tab_session", _fake_restore)
    monkeypatch.setattr(
        "ziniao_mcp.config_yaml.load_merged_project_and_global_yaml",
        lambda: {
            "cookie_vault": {
                "restore": {
                    "navigate_settle_sec": 0.75,
                    "reload_settle_sec": 1.25,
                }
            }
        },
    )
    snap = tmp_path / "s.json"
    snap.write_text(
        '{"schema_version": 1, "page_url": "https://x.com/", '
        '"cookies": [{"name": "a", "value": "b", "domain": "x.com", "path": "/"}]}',
        encoding="utf-8",
    )
    session = _ProbeSession()
    session.runtime_config = {
        "cookie_vault": {
            "restore": {
                "navigate_settle_sec": 0.25,
                "reload_settle_sec": 0.5,
            }
        }
    }
    r = await d_dispatch._cookie_vault(
        session,
        {"action": "restore", "path": str(snap)},
    )
    assert r.get("ok") is True
    assert captured["navigate_settle_sec"] == 0.75
    assert captured["reload_settle_sec"] == 1.25


@pytest.mark.asyncio
async def test_restore_tab_session_navigate_failure() -> None:
    tab = MagicMock()
    tab.send = AsyncMock(side_effect=RuntimeError("cdp navigate failed"))
    tab.sleep = AsyncMock()
    tab.target = type("_T", (), {"url": ""})()
    tab.evaluate = AsyncMock()
    snap = {
        "schema_version": cv.SCHEMA_VERSION,
        "page_url": "https://example.com/",
        "cookies": [{"name": "sid", "value": "1", "domain": "example.com", "path": "/"}],
        "local_storage": {},
        "session_storage": {},
    }
    r = await auth_restore.restore_tab_session(
        tab,
        snap,
        navigate_url="https://example.com/",
        default_snap_url="https://example.com/",
        clear_cookies_first=False,
        allow_origin_mismatch=False,
        reload_after=False,
        verify_selector="",
        verify_timeout_sec=1.0,
        navigate_settle_sec=0.0,
        reload_settle_sec=0.0,
    )
    assert r.get("ok") is False
    assert r.get("phase") == "navigate"
    assert "navigate failed" in r.get("error", "")


@pytest.mark.asyncio
async def test_cookie_vault_probe_api_shape(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    async def _fake_fetch(_merged: dict, _snap: dict) -> dict:
        return {"ok": True, "status": 200, "content_type": "application/json", "body": "{}"}

    monkeypatch.setattr("ziniao_mcp.api_transport.direct_http_fetch", _fake_fetch)
    snap = tmp_path / "s.json"
    snap.write_text(
        '{"schema_version": 1, "cookies": [{"name": "a", "value": "b", "domain": "x.com", "path": "/"}]}',
        encoding="utf-8",
    )
    r = await d_dispatch._cookie_vault(
        _ProbeSession(),
        {"action": "probe_api", "path": str(snap), "url": "https://x.com/api", "method": "GET"},
    )
    assert r.get("ok") is True
    assert r.get("probe_invocation_ok") is True
    assert r.get("probe_http_ok") is True
    assert r.get("direct_http_usable") is True
    assert r.get("probe", {}).get("ok") is True


@pytest.mark.asyncio
async def test_cookie_vault_probe_api_rejects_unsafe_method(tmp_path) -> None:
    snap = tmp_path / "s.json"
    snap.write_text(
        '{"schema_version": 1, "cookies": [{"name": "a", "value": "b", "domain": "x.com", "path": "/"}]}',
        encoding="utf-8",
    )
    r = await d_dispatch._cookie_vault(
        _ProbeSession(),
        {"action": "probe_api", "path": str(snap), "url": "https://x.com/api", "method": "POST"},
    )
    assert "probe_api only allows" in r.get("error", "")


@pytest.mark.asyncio
async def test_apply_snapshot_rejects_origin_mismatch() -> None:
    tab = MagicMock()
    snap = {
        "schema_version": cv.SCHEMA_VERSION,
        "page_url": "https://a.com/",
        "cookies": [],
        "local_storage": {},
        "session_storage": {},
    }
    r = await auth_restore.apply_snapshot_to_tab(
        tab,
        snap,
        tab_url="https://b.com/",
        clear_cookies_first=False,
        allow_origin_mismatch=False,
    )
    assert r.get("error")
    assert "origin" in r["error"].lower() or "navigate" in r["error"].lower()


@pytest.mark.asyncio
async def test_apply_snapshot_rejects_redacted() -> None:
    tab = MagicMock()
    snap = cv.redact_snapshot({
        "schema_version": cv.SCHEMA_VERSION,
        "cookies": [{"name": "a", "value": "secret"}],
    })
    r = await auth_restore.apply_snapshot_to_tab(
        tab,
        snap,
        tab_url="https://example.com/",
        clear_cookies_first=False,
        allow_origin_mismatch=False,
    )
    assert "redacted" in r.get("error", "").lower()


@pytest.mark.asyncio
async def test_apply_snapshot_writes_cookies_and_storage() -> None:
    tab = MagicMock()
    tab.send = AsyncMock()
    tab.evaluate = AsyncMock()
    snap = {
        "schema_version": cv.SCHEMA_VERSION,
        "page_url": "https://example.com/app",
        "cookies": [{"name": "sid", "value": "1", "domain": "example.com", "path": "/", "secure": True}],
        "local_storage": {"k": "v"},
        "session_storage": {"s": "t"},
    }
    r = await auth_restore.apply_snapshot_to_tab(
        tab,
        snap,
        tab_url="https://example.com/other",
        clear_cookies_first=False,
        allow_origin_mismatch=False,
    )
    assert r.get("ok") is True
    assert r["imported_cookies"] == 1
    assert r["imported_local_storage_keys"] == 1
    assert r["imported_session_storage_keys"] == 1
    assert tab.send.await_count >= 1
    assert tab.evaluate.await_count == 2


@pytest.mark.asyncio
async def test_wait_for_selector_times_out() -> None:
    tab = MagicMock()
    tab.evaluate = AsyncMock(return_value=False)
    ok = await auth_restore.wait_for_selector(tab, ".missing", timeout_sec=0.15)
    assert ok is False


@pytest.mark.asyncio
async def test_wait_for_selector_succeeds() -> None:
    tab = MagicMock()
    tab.evaluate = AsyncMock(return_value=True)
    ok = await auth_restore.wait_for_selector(tab, "body", timeout_sec=1.0)
    assert ok is True
