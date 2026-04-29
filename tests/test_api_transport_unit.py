"""Unit tests for api_transport heuristics."""

from __future__ import annotations

import httpx
import pytest

from ziniao_mcp import api_transport as at


def test_auto_probe_only_allows_safe_methods() -> None:
    assert at.can_auto_probe_method("GET")
    assert at.can_auto_probe_method("head")
    assert not at.can_auto_probe_method("POST")
    assert not at.can_auto_probe_method("PATCH")


def test_looks_successful_json() -> None:
    assert at.direct_http_response_looks_successful({
        "ok": True,
        "status": 200,
        "content_type": "application/json",
        "body": '{"a":1}',
    })


def test_looks_successful_rejects_html_login() -> None:
    assert not at.direct_http_response_looks_successful({
        "ok": True,
        "status": 200,
        "content_type": "text/html; charset=utf-8",
        "body": "<html><title>login</title></html>",
    })


def test_looks_successful_rejects_error_status() -> None:
    assert not at.direct_http_response_looks_successful({
        "ok": True,
        "status": 401,
        "content_type": "application/json",
        "body": "{}",
    })


def test_looks_successful_rejects_ok_false() -> None:
    assert not at.direct_http_response_looks_successful({"ok": False, "error": "x"})


@pytest.mark.asyncio
async def test_direct_http_rejects_redacted_snapshot() -> None:
    result = await at.direct_http_fetch(
        {"url": "https://example.com/", "method": "GET"},
        {"redacted": True, "cookies": []},
    )
    assert result["ok"] is False
    assert "redacted snapshot" in result["error"]
    assert result.get("auth_snapshot_used") is True
    assert "browser_context_reused" in result


@pytest.mark.asyncio
async def test_direct_http_sends_cookie_and_default_ua(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class Resp:
        status_code = 200
        reason_phrase = "OK"
        content = b'{"x":1}'
        headers = {"content-type": "application/json"}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def request(self, method, url, headers=None, content=None):
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = dict(headers or {})
            return Resp()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: Client())

    snap = {
        "cookies": [{"name": "sid", "value": "abc", "domain": "example.com", "path": "/"}],
        "user_agent": "ZiniaoTestUA/1",
        "local_storage": {},
        "session_storage": {},
        "site": "demo",
        "profile_id": "p1",
    }
    r = await at.direct_http_fetch({"url": "https://example.com/api", "method": "GET"}, snap)
    assert r["ok"] is True
    assert r["auth_snapshot_used"] is True
    assert r["snapshot_site"] == "demo"
    assert r["snapshot_profile_id"] == "p1"
    assert captured["headers"].get("Cookie") == "sid=abc"
    assert captured["headers"].get("User-Agent") == "ZiniaoTestUA/1"


@pytest.mark.asyncio
async def test_direct_http_does_not_override_explicit_ua(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class Resp:
        status_code = 200
        reason_phrase = "OK"
        content = b"{}"
        headers = {"content-type": "application/json"}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def request(self, method, url, headers=None, content=None):
            captured["headers"] = dict(headers or {})
            return Resp()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: Client())

    snap = {
        "cookies": [],
        "user_agent": "Ignored",
        "local_storage": {},
        "session_storage": {},
    }
    await at.direct_http_fetch(
        {"url": "https://example.com/", "method": "GET", "headers": {"User-Agent": "Explicit/2"}},
        snap,
    )
    assert captured["headers"].get("User-Agent") == "Explicit/2"


@pytest.mark.asyncio
async def test_direct_http_header_inject_from_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class Resp:
        status_code = 200
        reason_phrase = "OK"
        content = b"{}"
        headers = {"content-type": "application/json"}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def request(self, method, url, headers=None, content=None):
            captured["headers"] = dict(headers or {})
            return Resp()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: Client())

    snap = {
        "cookies": [{"name": "t", "value": "cval", "domain": "example.com", "path": "/"}],
        "user_agent": "",
        "local_storage": {"ls": "tok"},
        "session_storage": {},
    }
    injections = [
        {"source": "localStorage", "key": "ls", "header": "X-Token"},
        {"source": "cookie", "key": "t", "header": "X-C"},
        {"source": "eval", "expression": "1", "header": "X-E"},
    ]
    await at.direct_http_fetch(
        {"url": "https://example.com/", "method": "GET", "header_inject": injections},
        snap,
    )
    assert captured["headers"].get("X-Token") == "tok"
    assert captured["headers"].get("X-C") == "cval"
    assert "X-E" not in captured["headers"]


@pytest.mark.asyncio
async def test_direct_http_skips_secure_cookie_on_http_url(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class Resp:
        status_code = 200
        reason_phrase = "OK"
        content = b"{}"
        headers = {"content-type": "application/json"}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def request(self, method, url, headers=None, content=None):
            captured["headers"] = dict(headers or {})
            return Resp()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: Client())

    snap = {
        "cookies": [{"name": "sec", "value": "1", "domain": ".example.com", "path": "/", "secure": True}],
        "user_agent": "",
        "local_storage": {},
        "session_storage": {},
    }
    await at.direct_http_fetch({"url": "http://example.com/", "method": "GET"}, snap)
    assert "sec=" not in (captured["headers"].get("Cookie") or "")
