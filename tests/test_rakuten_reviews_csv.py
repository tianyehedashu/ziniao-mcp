"""Rakuten RMS review CSV preset + plugin URL build."""

from __future__ import annotations

from datetime import date, datetime
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import pytest

from ziniao_mcp.sites import _spec_for_page_fetch, load_preset, prepare_request
from ziniao_mcp.sites.rakuten import RakutenPlugin


def test_reviews_csv_rejects_start_after_end() -> None:
    plugin = RakutenPlugin()
    spec = {
        "rakuten_review_csv": True,
        "url": "",
        "_ziniao_merged_vars": {
            "start_date": "2026-04-10",
            "end_date": "2026-03-01",
            "kw": "",
            "ao": "A",
            "st": "1",
            "tc": "0",
            "ev": "0",
            "sh": "0",
            "si": "0",
            "eh": "23",
            "ei": "59",
        },
    }
    with pytest.raises(ValueError, match="start_date must be on or before end_date"):
        plugin.before_fetch(spec)


def test_rakuten_plugin_builds_review_csv_url() -> None:
    plugin = RakutenPlugin()
    spec = {
        "rakuten_review_csv": True,
        "url": "",
        "_ziniao_merged_vars": {
            "start_date": "2026-03-10",
            "end_date": "2026-04-10",
            "kw": "test kw",
            "ao": "A",
            "st": "1",
            "tc": "0",
            "ev": "0",
            "sh": "0",
            "si": "0",
            "eh": "23",
            "ei": "59",
        },
    }
    out = plugin.before_fetch(spec)
    assert "rakuten_review_csv" not in out
    assert "_ziniao_merged_vars" not in out
    assert out["url"].startswith("https://review.rms.rakuten.co.jp/search/csv/?")
    assert "sy=2026" in out["url"] and "sm=3" in out["url"] and "sd=10" in out["url"]
    assert "ey=2026" in out["url"] and "em=4" in out["url"] and "ed=10" in out["url"]
    assert "kw=test+kw" in out["url"] or "kw=test%20kw" in out["url"]


def test_prepare_request_review_csv_preset_and_strip_internal_keys() -> None:
    spec, _plugin = prepare_request(
        preset="rakuten/reviews-csv",
        var_values={"start_date": "2026-01-05", "end_date": "2026-01-06"},
    )
    assert spec["url"].startswith("https://review.rms.rakuten.co.jp/search/csv/?")
    assert spec["_ziniao_output_decode_encoding"] == "cp932"
    assert "_ziniao_merged_vars" not in spec
    assert "rakuten_review_csv" not in spec
    daemon = _spec_for_page_fetch(spec)
    assert "_ziniao_output_decode_encoding" not in daemon


def test_reviews_csv_json_has_output_decode() -> None:
    data = load_preset("rakuten/reviews-csv")
    assert data.get("output_decode_encoding") == "cp932"
    assert data.get("rakuten_review_csv") is True


def _dates_from_csv_url(url: str) -> tuple[date, date]:
    q = parse_qs(urlparse(url).query)
    d1 = date(int(q["sy"][0]), int(q["sm"][0]), int(q["sd"][0]))
    d2 = date(int(q["ey"][0]), int(q["em"][0]), int(q["ed"][0]))
    return d1, d2


def test_prepare_request_last_days_defaults_and_span() -> None:
    today = datetime.now(ZoneInfo("Asia/Tokyo")).date()
    spec, _ = prepare_request(preset="rakuten/reviews-csv", var_values={})
    d1, d2 = _dates_from_csv_url(spec["url"])
    assert d2 == today
    assert (d2 - d1).days == 29

    spec7, _ = prepare_request(preset="rakuten/reviews-csv", var_values={"last_days": "7"})
    a, b = _dates_from_csv_url(spec7["url"])
    assert b == today
    assert (b - a).days == 6

    spec1, _ = prepare_request(preset="rakuten/reviews-csv", var_values={"last_days": "1"})
    x, y = _dates_from_csv_url(spec1["url"])
    assert x == y == today
