"""Root CLI ``--version`` / ``-V`` / ``ziniao version`` (offline, no daemon)."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from ziniao_mcp.cli import app


@pytest.mark.parametrize("argv", [["--version"], ["-V"], ["version"]])
def test_version_outputs_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch, argv: list[str],
) -> None:
    monkeypatch.setattr("ziniao_mcp.cli._get_package_version", lambda: "9.9.9-test")
    runner = CliRunner()
    result = runner.invoke(app, argv)
    assert result.exit_code == 0
    assert "ziniao 9.9.9-test" in (result.stdout or "")
