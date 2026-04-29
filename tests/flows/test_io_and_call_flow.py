"""read_json / call_flow / run timing fields."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from ziniao_mcp.cli import dispatch as d
from ziniao_mcp.flows.runner import run_flow


@pytest.mark.asyncio
async def test_read_write_json_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(d, "_inject_flow_vars", AsyncMock(return_value=[]))
    inp = tmp_path / "data.json"
    inp.write_text(json.dumps({"a": 1}), encoding="utf-8")
    out = tmp_path / "out.json"

    sm = type(
        "SM",
        (),
        {
            "get_active_tab": lambda self: type(
                "T",
                (),
                {
                    "target": type("Tg", (), {"url": "https://example.com/"})(),
                    "sleep": AsyncMock(),
                    "send": AsyncMock(),
                },
            )(),
        },
    )()

    spec = {
        "kind": "rpa_flow",
        "schema_version": "rpa/1",
        "steps": [
            {"id": "r", "action": "read_json", "path": str(inp)},
            {"id": "w", "action": "write_json", "path": str(out), "value": "{{steps.r.value}}"},
        ],
        "_ziniao_run_dir": str(tmp_path / "run"),
    }
    out_env = await run_flow(sm, spec)
    assert out_env.get("ok") is True
    assert json.loads(out.read_text(encoding="utf-8")) == {"a": 1}


@pytest.mark.asyncio
async def test_write_json_decodes_json_string(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(d, "_inject_flow_vars", AsyncMock(return_value=[]))
    out = tmp_path / "out.json"
    sm = type(
        "SM",
        (),
        {
            "get_active_tab": lambda self: type(
                "T",
                (),
                {
                    "target": type("Tg", (), {"url": "https://example.com/"})(),
                    "sleep": AsyncMock(),
                    "send": AsyncMock(),
                },
            )(),
        },
    )()
    result = await run_flow(
        sm,
        {
            "kind": "rpa_flow",
            "schema_version": "rpa/1",
            "steps": [{"id": "w", "action": "write_json", "path": str(out), "value": "{\"a\": 1}"}],
            "_ziniao_run_dir": str(tmp_path / "run-json-string"),
        },
    )
    assert result.get("ok") is True
    assert json.loads(out.read_text(encoding="utf-8")) == {"a": 1}


@pytest.mark.asyncio
async def test_pure_data_flow_does_not_require_active_tab(tmp_path: Path) -> None:
    class _NoBrowserSession:
        def get_active_tab(self):
            raise RuntimeError("no browser")

    out = tmp_path / "out.txt"
    result = await run_flow(
        _NoBrowserSession(),
        {
            "kind": "rpa_flow",
            "schema_version": "rpa/1",
            "steps": [
                {"id": "set", "action": "set_var", "name": "msg", "value": "ok"},
                {"id": "write", "action": "write_text", "path": str(out), "from_var": "msg"},
            ],
            "_ziniao_run_dir": str(tmp_path / "run-pure"),
        },
    )
    assert result.get("ok") is True
    assert out.read_text(encoding="utf-8") == "ok"


@pytest.mark.asyncio
async def test_run_flow_has_timing_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(d, "_inject_flow_vars", AsyncMock(return_value=[]))

    sm = type(
        "SM",
        (),
        {
            "get_active_tab": lambda self: type(
                "T",
                (),
                {
                    "target": type("Tg", (), {"url": "https://example.com/"})(),
                    "sleep": AsyncMock(),
                    "send": AsyncMock(),
                },
            )(),
        },
    )()

    spec = {
        "kind": "rpa_flow",
        "schema_version": "rpa/1",
        "steps": [{"id": "z", "action": "sleep", "ms": 1}],
        "_ziniao_run_dir": str(tmp_path / "run"),
    }
    out = await run_flow(sm, spec)
    assert "started_at" in out and "ended_at" in out and "duration_ms" in out


@pytest.mark.asyncio
async def test_call_flow_nested(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(d, "_inject_flow_vars", AsyncMock(return_value=[]))

    child = tmp_path / "child.json"
    child.write_text(
        json.dumps(
            {
                "kind": "rpa_flow",
                "schema_version": "rpa/1",
                "steps": [{"id": "s", "action": "sleep", "ms": 1}],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    sm = type(
        "SM",
        (),
        {
            "get_active_tab": lambda self: type(
                "T",
                (),
                {
                    "target": type("Tg", (), {"url": "https://example.com/"})(),
                    "sleep": AsyncMock(),
                    "send": AsyncMock(),
                },
            )(),
        },
    )()

    spec = {
        "kind": "rpa_flow",
        "schema_version": "rpa/1",
        "steps": [{"id": "c", "action": "call_flow", "path": "child.json"}],
        "_ziniao_flow_base_dir": str(tmp_path),
        "_ziniao_run_dir": str(tmp_path / "run"),
    }
    out = await run_flow(sm, spec)
    assert out.get("ok") is True
