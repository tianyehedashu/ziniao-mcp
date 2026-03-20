"""Tests for ``ziniao update`` (uv-based self-upgrade)."""

import subprocess
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from ziniao_mcp.cli import app

runner = CliRunner()


@patch("ziniao_mcp.cli.commands.update_cmd.shutil.which", return_value=None)
def test_update_exits_when_uv_missing(_mock_which: MagicMock) -> None:
    result = runner.invoke(app, ["update"])
    assert result.exit_code == 1
    combined = (result.stdout or "") + (result.stderr or "")
    assert "uv" in combined.lower()


@patch("ziniao_mcp.cli.commands.update_cmd.shutil.which", return_value="/fake/uv")
def test_update_dry_run_prints_command(_mock_which: MagicMock) -> None:
    result = runner.invoke(app, ["update", "--dry-run"])
    assert result.exit_code == 0
    assert "uv tool install" in result.stdout
    assert "ziniao" in result.stdout


@patch("ziniao_mcp.cli.commands.update_cmd.shutil.which", return_value="/fake/uv")
def test_update_dry_run_git_uses_git_url(_mock_which: MagicMock) -> None:
    result = runner.invoke(app, ["update", "--dry-run", "--git"])
    assert result.exit_code == 0
    assert "git+https://" in result.stdout
    assert "ziniao-mcp" in result.stdout


@patch("ziniao_mcp.cli.commands.update_cmd.subprocess.run")
@patch("ziniao_mcp.cli.commands.update_cmd.shutil.which", return_value="/fake/uv")
def test_update_runs_uv_and_propagates_exit_code(
    _mock_which: MagicMock, mock_run: MagicMock,
) -> None:
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_run.return_value = mock_proc
    result = runner.invoke(app, ["update"])
    assert result.exit_code == 0
    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    assert args[0][0] == "/fake/uv"
    assert "tool" in args[0]
    assert kwargs.get("stdin") == subprocess.DEVNULL


@patch("ziniao_mcp.cli.commands.update_cmd.subprocess.run")
@patch("ziniao_mcp.cli.commands.update_cmd.shutil.which", return_value="/fake/uv")
def test_update_nonzero_uv_exit(
    _mock_which: MagicMock, mock_run: MagicMock,
) -> None:
    mock_proc = MagicMock()
    mock_proc.returncode = 2
    mock_run.return_value = mock_proc
    result = runner.invoke(app, ["update"])
    assert result.exit_code == 2
