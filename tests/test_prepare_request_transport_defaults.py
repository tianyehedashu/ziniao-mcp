"""prepare_request sets default fetch transport and auth_strategy hints."""

from __future__ import annotations

import json
from pathlib import Path

from ziniao_mcp.sites import prepare_request


def test_fetch_mode_gets_default_browser_fetch(tmp_path: Path) -> None:
    pf = tmp_path / "req.json"
    pf.write_text(
        json.dumps({"mode": "fetch", "url": "https://example.com/api"}),
        encoding="utf-8",
    )
    spec, _ = prepare_request(file=str(pf))
    assert spec.get("transport") == "browser_fetch"


def test_auth_strategy_preferred_transport(tmp_path: Path) -> None:
    pf = tmp_path / "req.json"
    pf.write_text(
        json.dumps({
            "mode": "fetch",
            "url": "https://example.com/",
            "auth_strategy": {"preferred_transport": "auto"},
        }),
        encoding="utf-8",
    )
    spec, _ = prepare_request(file=str(pf))
    assert spec.get("transport") == "auto"


def test_transport_aliases_are_normalized(tmp_path: Path) -> None:
    pf = tmp_path / "req.json"
    pf.write_text(
        json.dumps({
            "mode": "fetch",
            "url": "https://example.com/",
            "transport": "direct",
        }),
        encoding="utf-8",
    )
    spec, _ = prepare_request(file=str(pf))
    assert spec.get("transport") == "direct_http"
