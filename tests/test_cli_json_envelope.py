"""Tests for CLI JSON envelope (--json) and legacy mode."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from ziniao_mcp.cli import app
from ziniao_mcp.cli.output import (
    cli_json_uses_legacy,
    daemon_to_envelope,
    dumps_cli_json,
    set_cli_json_legacy,
)


def test_daemon_to_envelope_success() -> None:
    raw = {"ok": True, "url": "https://x.example"}
    env = daemon_to_envelope(raw)
    assert env == {"success": True, "data": raw, "error": None}


def test_daemon_to_envelope_error() -> None:
    env = daemon_to_envelope({"error": "not found"})
    assert env["success"] is False
    assert env["data"] is None
    assert env["error"] == "not found"


def test_dumps_cli_json_envelope_roundtrip() -> None:
    set_cli_json_legacy(False)
    try:
        s = dumps_cli_json({"ok": True, "n": 1})
        obj = json.loads(s)
        assert obj["success"] is True
        assert obj["data"]["n"] == 1
        assert obj["error"] is None
    finally:
        set_cli_json_legacy(False)


def test_dumps_cli_json_legacy() -> None:
    set_cli_json_legacy(True)
    try:
        assert cli_json_uses_legacy() is True
        s = dumps_cli_json({"a": 2})
        assert json.loads(s) == {"a": 2}
    finally:
        set_cli_json_legacy(False)


def test_json_and_json_legacy_mutually_exclusive() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--json", "--json-legacy", "config", "path"])
    assert result.exit_code == 1
    combined = (result.stdout or "") + (result.stderr or "")
    assert "either" in combined.lower() and "both" in combined.lower()


@pytest.mark.parametrize(
    "legacy,expect_top_keys",
    [(False, {"success", "data", "error"}), (True, {"active", "sessions", "count"})],
)
def test_session_list_json_shape_mocked(monkeypatch: pytest.MonkeyPatch, legacy: bool, expect_top_keys: set) -> None:
    from ziniao_mcp import cli as cli_mod

    def fake_send_command(command: str, args: dict, target_session, timeout: float) -> dict:
        assert command == "session_list"
        return {"active": "s1", "sessions": [], "count": 0}

    monkeypatch.setattr(cli_mod, "send_command", fake_send_command)
    set_cli_json_legacy(legacy)
    try:
        args = ["session", "list"]
        if legacy:
            args = ["--json-legacy"] + args
        else:
            args = ["--json"] + args
        runner = CliRunner()
        result = runner.invoke(cli_mod.app, args)
        assert result.exit_code == 0, result.stdout + result.stderr
        obj = json.loads(result.stdout)
        assert set(obj.keys()) == expect_top_keys
    finally:
        set_cli_json_legacy(False)
