"""Unit tests for page_fetch transport routing."""

from __future__ import annotations

import pytest

from ziniao_mcp.cli import dispatch as d


class _Target:
    url = "https://example.com/"


class _Tab:
    target = _Target()


class _Store:
    iframe_context = None


class _Session:
    def get_active_session(self) -> _Store:
        return _Store()

    def get_active_tab(self) -> _Tab:
        return _Tab()


@pytest.mark.asyncio
async def test_auto_unsafe_method_skips_direct_http(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"browser": 0, "direct": 0}

    async def fake_browser_fetch(_sm, _args):
        calls["browser"] += 1
        return {"ok": True, "status": 200}

    async def fake_direct(_args, _snapshot):
        calls["direct"] += 1
        return {"ok": True, "status": 200}

    monkeypatch.setattr(d, "_page_fetch_fetch", fake_browser_fetch)

    from ziniao_mcp import api_transport

    monkeypatch.setattr(api_transport, "direct_http_fetch", fake_direct)

    result = await d._page_fetch(
        _Session(),
        {
            "mode": "fetch",
            "transport": "auto",
            "method": "POST",
            "url": "https://example.com/api",
            "auth_snapshot_path": "unused.json",
        },
    )

    assert result["transport_used"] == "browser_fetch"
    assert result["fallback_reason"] == "unsafe_method_not_probed"
    assert calls == {"browser": 1, "direct": 0}


@pytest.mark.asyncio
async def test_transport_direct_alias_requires_snapshot() -> None:
    result = await d._page_fetch(
        _Session(),
        {
            "mode": "fetch",
            "transport": "direct",
            "method": "GET",
            "url": "https://example.com/api",
        },
    )

    assert "direct_http requires auth_snapshot_path" in result["error"]


def test_origin_of_url_normalizes_origin() -> None:
    assert d._origin_of_url("https://Example.com/path?q=1") == "https://example.com"
    assert d._origin_of_url("about:blank") == ""
