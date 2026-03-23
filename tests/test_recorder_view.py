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
