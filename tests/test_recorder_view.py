"""Tests for recorder view / metadata helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_do_view_full_and_metadata_only(tmp_path, monkeypatch) -> None:
    from ziniao_mcp.tools import recorder as rec

    monkeypatch.setattr(rec, "_RECORDINGS_DIR", tmp_path)
    meta = {
        "name": "t1",
        "created_at": "2026-01-01T00:00:00",
        "start_url": "https://example.com",
        "cdp_port": 9222,
        "session_id": "shop-x",
        "backend_type": "ziniao",
        "store_name": "Shop X",
        "action_count": 1,
        "actions": [{"type": "click", "selector": "#a"}],
    }
    (tmp_path / "t1.json").write_text(json.dumps(meta), encoding="utf-8")

    out = json.loads(rec._do_view("t1", metadata_only=True))
    assert out["status"] == "ok"
    assert "actions" not in out["recording"]
    assert out["recording"]["action_count"] == 1
    assert Path(out["path"]).resolve() == (tmp_path / "t1.json").resolve()

    out2 = json.loads(rec._do_view("t1", metadata_only=False))
    assert out2["recording"]["actions"][0]["type"] == "click"


def test_do_view_requires_name() -> None:
    from ziniao_mcp.tools import recorder as rec

    with pytest.raises(RuntimeError, match="View requires"):
        rec._do_view("", metadata_only=False)


def test_generate_python_script_opens_new_tab_not_tabs_zero() -> None:
    from ziniao_mcp.recording.emit_nodriver import generate_nodriver_script

    actions = [{"type": "click", "selector": "#x", "timestamp": 0, "delay_ms": 0}]
    py = generate_nodriver_script(
        actions, 9222, "https://example.com/start", "r1",
        session_id="shop-1", backend_type="ziniao", store_name="A",
    )
    assert "new_tab=True" in py
    assert "browser.tabs[0]" not in py
    assert "https://example.com/start" in py
    assert "session_id:" in py
    assert "shop-1" in py
    assert "ziniao" in py

    py_blank = generate_nodriver_script(actions, 9222, "", "r2")
    assert "about:blank" in py_blank
    assert "new_tab=True" in py_blank
