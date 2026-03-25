"""CLI --store / --session: 解析与发往 daemon 的 target_session。"""

from __future__ import annotations

from typing import Any

import pytest
from typer.testing import CliRunner

from ziniao_mcp.cli import app
from ziniao_mcp.cli.output import set_cli_json_legacy


def test_store_and_session_mutually_exclusive() -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["--store", "a", "--session", "b", "session", "list"],
    )
    assert result.exit_code == 1
    combined = (result.stdout or "") + (result.stderr or "")
    assert "mutually exclusive" in combined.lower()


def test_store_passes_target_session_to_send_command(monkeypatch: pytest.MonkeyPatch) -> None:
    from ziniao_mcp import cli as cli_mod

    captured: dict[str, object] = {}

    def fake_send_command(
        command: str,
        args: dict,
        target_session: str | None,
        timeout: float,
    ) -> dict:
        captured["command"] = command
        captured["args"] = args
        captured["target_session"] = target_session
        captured["timeout"] = timeout
        return {"active": "x", "sessions": [], "count": 0}

    monkeypatch.setattr(cli_mod, "send_command", fake_send_command)
    set_cli_json_legacy(True)
    try:
        runner = CliRunner()
        result = runner.invoke(
            cli_mod.app,
            ["--store", "my-store-001", "--json-legacy", "session", "list"],
        )
        assert result.exit_code == 0, result.stdout + result.stderr
        assert captured["command"] == "session_list"
        assert captured["target_session"] == "my-store-001"
    finally:
        set_cli_json_legacy(False)


def test_session_passes_target_session_to_send_command(monkeypatch: pytest.MonkeyPatch) -> None:
    from ziniao_mcp import cli as cli_mod

    captured: dict[str, object] = {}

    def fake_send_command(
        _command: str,
        _args: dict,
        target_session: str | None,
        _timeout: float,
    ) -> dict:
        captured["target_session"] = target_session
        return {"ok": True, "url": "https://example.com"}

    monkeypatch.setattr(cli_mod, "send_command", fake_send_command)
    set_cli_json_legacy(True)
    try:
        runner = CliRunner()
        result = runner.invoke(
            cli_mod.app,
            ["--session", "chrome-sess-9", "--json-legacy", "get", "url"],
        )
        assert result.exit_code == 0, result.stdout + result.stderr
        assert captured["target_session"] == "chrome-sess-9"
    finally:
        set_cli_json_legacy(False)


@pytest.mark.asyncio
async def test_dispatch_target_session_restores_active() -> None:
    from ziniao_mcp.cli.dispatch import dispatch

    class FakeSM:
        def __init__(self) -> None:
            self._stores = {"s1": object(), "s2": object()}
            self._active_store_id = "s1"

        @property
        def active_session_id(self) -> str | None:
            return self._active_store_id

        def list_all_sessions(self) -> list[Any]:
            return []

    sm = FakeSM()
    request = {
        "command": "session_list",
        "args": {},
        "target_session": "s2",
    }
    out = await dispatch(sm, request)
    assert sm.active_session_id == "s1"
    assert out.get("active") == "s2"


@pytest.mark.asyncio
async def test_dispatch_unknown_target_returns_error() -> None:
    from ziniao_mcp.cli.dispatch import dispatch

    class FakeSM:
        def __init__(self) -> None:
            self._stores = {"only": object()}
            self._active_store_id = "only"

        @property
        def active_session_id(self) -> str | None:
            return self._active_store_id

    sm = FakeSM()
    out = await dispatch(sm, {"command": "session_list", "args": {}, "target_session": "missing"})
    assert sm.active_session_id == "only"
    assert "error" in out
    assert "not found" in out["error"].lower()
