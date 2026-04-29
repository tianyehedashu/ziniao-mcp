"""Unit tests for CLI config commands."""

from __future__ import annotations

from ziniao_mcp.cli.commands import config_cmd


def test_config_set_supports_nested_float(monkeypatch) -> None:
    written: dict = {}

    monkeypatch.setattr(config_cmd, "_read_global_config", lambda: {})
    monkeypatch.setattr(config_cmd, "_write_global_config", lambda cfg: written.update(cfg))

    config_cmd.set_value("cookie_vault.restore.navigate_settle_sec", "0.25")

    assert written == {
        "cookie_vault": {
            "restore": {
                "navigate_settle_sec": 0.25,
            }
        }
    }
