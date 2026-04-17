"""Tests for declarative ``response_contract`` extension chain."""

from __future__ import annotations

import json

from ziniao_mcp.sites._base import SitePlugin
from ziniao_mcp.sites.response_contract import apply_response_contract


def _resp(body_obj) -> dict:
    return {"status": 200, "body": json.dumps(body_obj)}


def test_none_contract_is_noop() -> None:
    r = _resp({"a": 1})
    original = dict(r)
    assert apply_response_contract(r, None) == original
    assert apply_response_contract(r, {}) == original


def test_invalid_parser_is_noop() -> None:
    r = _resp({"a": 1})
    out = apply_response_contract(r, {"parse": "yaml", "lift": []})
    assert "parsed" not in out


def test_body_missing_is_noop() -> None:
    r = {"status": 204}
    out = apply_response_contract(r, {"parse": "json", "lift": [{"from": "x", "to": "y"}]})
    assert out == r


def test_body_not_json_is_noop() -> None:
    r = {"status": 200, "body": "<html>oops</html>"}
    out = apply_response_contract(r, {"parse": "json", "lift": [{"from": "x", "to": "y"}]})
    assert "y" not in out


def test_simple_lift_writes_top_level_key() -> None:
    r = _resp({"data": {"items": [1, 2, 3]}})
    apply_response_contract(
        r,
        {"parse": "json", "lift": [{"from": "data", "to": "parsed"}]},
    )
    assert r["parsed"] == {"items": [1, 2, 3]}


def test_when_eq_matches() -> None:
    r = _resp({"status": "SUCCESS", "data": {"n": 7}})
    apply_response_contract(
        r,
        {
            "parse": "json",
            "lift": [
                {"from": "data", "to": "parsed", "when_eq": {"status": "SUCCESS"}},
            ],
        },
    )
    assert r["parsed"] == {"n": 7}


def test_when_eq_mismatch_skips_rule() -> None:
    r = _resp({"status": "ERROR", "data": {"n": 7}})
    apply_response_contract(
        r,
        {
            "parse": "json",
            "lift": [
                {"from": "data", "to": "parsed", "when_eq": {"status": "SUCCESS"}},
            ],
        },
    )
    assert "parsed" not in r


def test_when_eq_conjunction_requires_all_keys() -> None:
    r = _resp({"status": "SUCCESS", "code": 1, "data": "x"})
    apply_response_contract(
        r,
        {
            "parse": "json",
            "lift": [
                {
                    "from": "data",
                    "to": "parsed",
                    "when_eq": {"status": "SUCCESS", "code": 2},
                },
            ],
        },
    )
    assert "parsed" not in r


def test_from_path_missing_skips_rule() -> None:
    r = _resp({"other": 1})
    apply_response_contract(
        r,
        {"parse": "json", "lift": [{"from": "data.items", "to": "parsed"}]},
    )
    assert "parsed" not in r


def test_lift_supports_list_index_in_path() -> None:
    r = _resp({"pages": [{"url": "a"}, {"url": "b"}]})
    apply_response_contract(
        r,
        {"parse": "json", "lift": [{"from": "pages.1.url", "to": "second_url"}]},
    )
    assert r["second_url"] == "b"


def test_multiple_lifts_are_independent() -> None:
    r = _resp({"status": "SUCCESS", "data": {"x": 1}, "meta": {"trace": "abc"}})
    apply_response_contract(
        r,
        {
            "parse": "json",
            "lift": [
                {"from": "data", "to": "parsed", "when_eq": {"status": "SUCCESS"}},
                {"from": "meta.trace", "to": "trace_id"},
                {"from": "missing", "to": "should_skip"},
            ],
        },
    )
    assert r["parsed"] == {"x": 1}
    assert r["trace_id"] == "abc"
    assert "should_skip" not in r


def test_rejects_nested_to_path() -> None:
    r = _resp({"data": 1})
    apply_response_contract(
        r,
        {"parse": "json", "lift": [{"from": "data", "to": "a.b"}]},
    )
    assert "a" not in r


def test_rejects_malformed_rule_entries() -> None:
    r = _resp({"data": 1})
    apply_response_contract(
        r,
        {
            "parse": "json",
            "lift": [
                "not a dict",
                {"from": "", "to": "parsed"},
                {"from": "data", "to": ""},
                {"from": "data", "to": "parsed"},
            ],
        },
    )
    assert r["parsed"] == 1


def test_default_site_plugin_after_fetch_reads_preset() -> None:
    r = _resp({"status": "SUCCESS", "data": {"n": 1}})
    spec = {
        "response_contract": {
            "parse": "json",
            "lift": [
                {"from": "data", "to": "parsed", "when_eq": {"status": "SUCCESS"}},
            ],
        },
    }
    out = SitePlugin().after_fetch(r, spec)
    assert out["parsed"] == {"n": 1}


def test_default_site_plugin_after_fetch_noop_without_contract() -> None:
    r = _resp({"whatever": 1})
    out = SitePlugin().after_fetch(r, {})
    assert "parsed" not in out


def test_plugin_override_can_call_super() -> None:
    class MyPlugin(SitePlugin):
        def after_fetch(self, response: dict, spec: dict) -> dict:
            super().after_fetch(response, spec)
            response["extra"] = "from-override"
            return response

    r = _resp({"status": "SUCCESS", "data": 42})
    spec = {
        "response_contract": {
            "parse": "json",
            "lift": [
                {"from": "data", "to": "parsed", "when_eq": {"status": "SUCCESS"}},
            ],
        },
    }
    out = MyPlugin().after_fetch(r, spec)
    assert out["parsed"] == 42
    assert out["extra"] == "from-override"


def test_when_eq_on_non_dict_tree_skips() -> None:
    # parsed tree is a list — when_eq path can't resolve, rule skipped
    r = {"status": 200, "body": json.dumps([1, 2, 3])}
    apply_response_contract(
        r,
        {
            "parse": "json",
            "lift": [
                {"from": "0", "to": "first", "when_eq": {"status": "SUCCESS"}},
            ],
        },
    )
    assert "first" not in r
