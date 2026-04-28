"""Unit tests for api_transport heuristics."""

from __future__ import annotations

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
