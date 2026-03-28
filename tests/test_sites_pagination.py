"""Unit tests for site preset pagination helpers."""

from __future__ import annotations

import json

from ziniao_mcp.sites import list_presets, paginate_all_generic, run_site_fetch


def test_list_presets_auth_and_paginated() -> None:
    ps = list_presets()
    rpp = next(p for p in ps if p["id"] == "rakuten/rpp-search")
    assert rpp["auth"] == "xsrf"
    assert rpp["paginated"] is True
    assert "hint" in rpp or rpp.get("auth_hint")


def test_paginate_body_field_merge() -> None:
    calls: list[int] = []

    def fetch_sync(spec: dict) -> dict:
        body = json.loads(spec["body"])
        calls.append(int(body["page"]))
        p = int(body["page"])
        return {
            "ok": True,
            "status": 201,
            "body": json.dumps({
                "data": {
                    "totalPage": 3,
                    "rppReports": [{"page": p, "i": i} for i in range(2)],
                },
            }),
        }

    spec = {
        "url": "https://example.com",
        "method": "POST",
        "body": json.dumps({"page": 1}),
        "pagination": {
            "type": "body_field",
            "page_field": "page",
            "total_field": "data.totalPage",
            "start": 1,
            "max_pages": 10,
            "merge_items_field": "data.rppReports",
        },
    }
    merged, status, n_pages = paginate_all_generic(spec, spec["pagination"], fetch_sync)
    assert calls == [1, 2, 3]
    assert status == 201
    assert n_pages == 3
    assert len(merged["data"]["rppReports"]) == 6


def test_run_site_fetch_all_includes_pages_fetched() -> None:
    def fetch_sync(spec: dict) -> dict:
        body = json.loads(spec["body"])
        p = int(body["page"])
        return {
            "ok": True,
            "status": 201,
            "body": json.dumps({
                "data": {"totalPage": 2, "rppReports": [{"page": p}]},
            }),
        }

    spec = {
        "url": "https://example.com",
        "method": "POST",
        "body": json.dumps({"page": 1}),
        "pagination": {
            "type": "body_field",
            "page_field": "page",
            "total_field": "data.totalPage",
            "merge_items_field": "data.rppReports",
            "max_pages": 10,
        },
    }
    r = run_site_fetch(spec, None, fetch_sync, fetch_all=True)
    assert r.get("pages_fetched") == 2
    out = json.loads(r["body"])
    assert len(out["data"]["rppReports"]) == 2
