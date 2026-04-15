"""Rakuten ad presets: product-dimension (*-item) discovery.

Uses the fake repo from the ``rakuten_repo`` fixture in ``conftest.py``.
"""

from __future__ import annotations

import pytest

from ziniao_mcp.sites import list_presets

_ITEM_IDS = frozenset(
    {
        "rakuten/rpp-search-item",
        "rakuten/cpnadv-performance-retrieve-item",
        "rakuten/tda-reports-search-item",
        "rakuten/rpp-exp-report-item",
        "rakuten/tda-exp-report-item",
    }
)


@pytest.fixture(autouse=True)
def _setup(rakuten_repo):
    pass


def test_rakuten_item_presets_registered() -> None:
    ids = {p["id"] for p in list_presets()}
    missing = sorted(_ITEM_IDS - ids)
    assert not missing, f"missing presets: {missing}"


def test_rpp_search_item_is_paginated() -> None:
    ps = {p["id"]: p for p in list_presets()}
    r = ps["rakuten/rpp-search-item"]
    assert r["paginated"] is True
