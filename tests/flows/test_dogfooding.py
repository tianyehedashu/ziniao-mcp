"""Mock dogfooding checks for the two P0 RPA examples."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from ziniao_mcp.cli import dispatch as d
from ziniao_mcp.flows.runner import run_flow


def _fake_sm() -> object:
    return type(
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


@pytest.mark.asyncio
async def test_flow_demo_login_and_extract_mock(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    flow_path = Path("examples/rpa/flow-demo-login-and-extract.rpa-flow.json")
    spec = json.loads(flow_path.read_text(encoding="utf-8"))
    spec["_ziniao_merged_vars"] = {"username": "demo"}
    spec["_ziniao_run_dir"] = str(tmp_path / "login")
    monkeypatch.setattr(d, "_fill", AsyncMock(return_value={"ok": True}))
    monkeypatch.setattr(d, "_click", AsyncMock(return_value={"ok": True}))
    monkeypatch.setattr(d, "_extract_step", AsyncMock(return_value={"ok": True, "value": "Welcome"}))
    out = await run_flow(_fake_sm(), spec)
    assert out["ok"] is True
    assert out["output"]["title"] == "Welcome"


@pytest.mark.asyncio
async def test_rakuten_rpp_search_mock_http(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    flow_path = Path("examples/rpa/rakuten-rpp-search.rpa-flow.json")
    spec = json.loads(flow_path.read_text(encoding="utf-8"))
    spec["_ziniao_merged_vars"] = {"api_url": "https://example.com/rakuten/rpp-search"}
    spec["_ziniao_run_dir"] = str(tmp_path / "rpp")

    class _Resp:
        status_code = 200
        text = '{"rows": []}'

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def request(self, *_args, **_kwargs):
            return _Resp()

    monkeypatch.setattr("httpx.AsyncClient", lambda *a, **k: _Client())
    out = await run_flow(_fake_sm(), spec)
    assert out["ok"] is True
    assert out["output"]["status"] == 200


@pytest.mark.e2e
def test_e2e_marker_registered_for_real_browser_dogfooding() -> None:
    """Marker placeholder: real browser dogfooding runs manually/nightly."""
    assert True
