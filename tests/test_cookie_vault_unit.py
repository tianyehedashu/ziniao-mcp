"""Unit tests for cookie_vault helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from ziniao_mcp import cookie_vault as cv


def test_redact_snapshot_masks_values() -> None:
    snap = {
        "schema_version": cv.SCHEMA_VERSION,
        "cookies": [{"name": "a", "value": "secretvalue", "domain": ".x.com"}],
        "local_storage": {"k": "longsecretstring"},
        "session_storage": {},
    }
    r = cv.redact_snapshot(snap)
    assert r["cookies"][0]["value"].endswith("***")
    assert r["cookies"][0]["value"] != "secretvalue"
    assert r["local_storage"]["k"].endswith("***")
    assert r["redacted"] is True


def test_cookie_header_for_url_filters_domain() -> None:
    cookies = [
        {"name": "a", "value": "1", "domain": ".example.com", "path": "/"},
        {"name": "b", "value": "2", "domain": "other.com", "path": "/"},
    ]
    h = cv.cookie_header_for_url("https://sub.example.com/path", cookies)
    assert "a=1" in h
    assert "b=" not in h


def test_cookie_header_respects_host_only_and_secure() -> None:
    cookies = [
        {"name": "hostonly", "value": "1", "domain": "example.com", "path": "/"},
        {"name": "secure", "value": "2", "domain": ".example.com", "path": "/", "secure": True},
    ]
    sub = cv.cookie_header_for_url("https://sub.example.com/path", cookies)
    assert "hostonly=" not in sub
    assert "secure=2" in sub

    plain = cv.cookie_header_for_url("http://example.com/path", cookies)
    assert "hostonly=1" in plain
    assert "secure=" not in plain


def test_cookie_header_path_match_does_not_match_prefix_sibling() -> None:
    cookies = [
        {"name": "scoped", "value": "1", "domain": "example.com", "path": "/foo"},
    ]
    assert "scoped=1" in cv.cookie_header_for_url("https://example.com/foo/bar", cookies)
    assert "scoped=" not in cv.cookie_header_for_url("https://example.com/foobar", cookies)


def test_apply_header_inject_from_snapshot() -> None:
    snap = {
        "cookies": [{"name": "xs", "value": "tok", "domain": "api.example.com", "path": "/"}],
        "local_storage": {"ls": "v1"},
        "session_storage": {"ss": "v2"},
    }
    inj = [
        {"source": "cookie", "key": "xs", "header": "X-Token"},
        {"source": "localStorage", "key": "ls", "header": "X-Ls"},
        {"source": "eval", "expression": "1", "header": "X-E"},
    ]
    h = cv.apply_header_inject_from_snapshot({"Accept": "application/json"}, inj, snap)
    assert h["X-Token"] == "tok"
    assert h["X-Ls"] == "v1"
    assert "X-E" not in h


def test_load_save_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "snap.json"
    data = cv.build_empty_snapshot(profile_id="p1", site="demo", user_agent="UA/1")
    data["cookies"] = [{"name": "n", "value": "v", "domain": "d.com", "path": "/"}]
    cv.save_auth_snapshot(p, data)
    loaded = cv.load_auth_snapshot(p)
    assert loaded["profile_id"] == "p1"
    assert loaded["cookies"][0]["name"] == "n"


def test_load_rejects_bad_version(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text('{"schema_version": 999, "cookies": []}', encoding="utf-8")
    with pytest.raises(ValueError, match="schema_version"):
        cv.load_auth_snapshot(p)


def test_redacted_snapshot_is_not_executable() -> None:
    snap = cv.redact_snapshot({
        "schema_version": cv.SCHEMA_VERSION,
        "cookies": [{"name": "a", "value": "secret"}],
    })
    with pytest.raises(ValueError, match="redacted snapshot"):
        cv.ensure_executable_snapshot(snap)
