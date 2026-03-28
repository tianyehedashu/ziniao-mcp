"""Tests for ``ziniao update`` (uv-based self-upgrade)."""

import json
import os
import signal
import subprocess
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from ziniao_mcp.cli import app
from ziniao_mcp.cli.commands.update_cmd import (
    _kill_blocking_nt,
    _kill_blocking_unix,
    _windows_spawn_uv_tool_install,
)

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


@patch("ziniao_mcp.cli.commands.update_cmd.os.name", "nt")
@patch("ziniao_mcp.cli.commands.update_cmd.shutil.which", return_value="/fake/uv")
def test_update_dry_run_no_kill_windows_mentions_cmd(_mock_which: MagicMock) -> None:
    result = runner.invoke(app, ["update", "--dry-run", "--no-kill"])
    assert result.exit_code == 0
    assert "PowerShell" in result.stdout or "powershell" in result.stdout.lower()


@patch("ziniao_mcp.cli.commands.update_cmd._kill_blocking_processes", return_value=[])
@patch("ziniao_mcp.cli.commands.update_cmd.subprocess.run")
@patch("ziniao_mcp.cli.commands.update_cmd.shutil.which", return_value="/fake/uv")
def test_update_runs_uv_and_propagates_exit_code(
    _mock_which: MagicMock, mock_run: MagicMock, _mock_kill: MagicMock,
) -> None:
    mock_proc = MagicMock(returncode=0, stdout="", stderr="")
    mock_run.return_value = mock_proc
    result = runner.invoke(app, ["update", "--sync"])
    assert result.exit_code == 0
    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    assert args[0][0] == "/fake/uv"
    assert "tool" in args[0]
    assert kwargs.get("stdin") == subprocess.DEVNULL


@patch("ziniao_mcp.cli.commands.update_cmd._kill_blocking_processes", return_value=[])
@patch("ziniao_mcp.cli.commands.update_cmd.subprocess.run")
@patch("ziniao_mcp.cli.commands.update_cmd.shutil.which", return_value="/fake/uv")
def test_update_nonzero_uv_exit(
    _mock_which: MagicMock, mock_run: MagicMock, _mock_kill: MagicMock,
) -> None:
    mock_proc = MagicMock(returncode=2, stdout="", stderr="some error")
    mock_run.return_value = mock_proc
    result = runner.invoke(app, ["update", "--sync"])
    assert result.exit_code == 2


@patch("ziniao_mcp.cli.commands.update_cmd._kill_blocking_processes")
@patch("ziniao_mcp.cli.commands.update_cmd.subprocess.run")
@patch("ziniao_mcp.cli.commands.update_cmd.shutil.which", return_value="/fake/uv")
def test_update_kills_blocking_processes_and_reports(
    _mock_which: MagicMock, mock_run: MagicMock, mock_kill: MagicMock,
) -> None:
    mock_kill.return_value = ["PID 1234 (python.exe)", "PID 5678 (ziniao.exe)"]
    mock_proc = MagicMock(returncode=0, stdout="", stderr="")
    mock_run.return_value = mock_proc
    result = runner.invoke(app, ["update", "--sync"])
    assert result.exit_code == 0
    mock_kill.assert_called_once()
    assert "2" in result.stdout
    assert "PID 1234" in result.stdout


@patch("ziniao_mcp.cli.commands.update_cmd._kill_blocking_processes")
@patch("ziniao_mcp.cli.commands.update_cmd.subprocess.run")
@patch("ziniao_mcp.cli.commands.update_cmd.shutil.which", return_value="/fake/uv")
def test_update_no_kill_skips_process_killing(
    _mock_which: MagicMock, mock_run: MagicMock, mock_kill: MagicMock,
) -> None:
    mock_proc = MagicMock(returncode=0, stdout="", stderr="")
    mock_run.return_value = mock_proc
    result = runner.invoke(app, ["update", "--sync", "--no-kill"])
    assert result.exit_code == 0
    mock_kill.assert_not_called()


# ---------- _kill_blocking_nt unit tests ----------


@patch("ziniao_mcp.cli.commands.update_cmd.subprocess.run")
@patch("ziniao_mcp.cli.commands.update_cmd.os.getpid", return_value=1)
def test_kill_blocking_nt_does_not_report_failed_taskkill(
    _mock_pid: MagicMock, mock_run: MagicMock,
) -> None:
    ps_json = json.dumps(
        [{"Id": 99, "Path": r"C:\Users\x\.local\bin\ziniao.exe"}],
    )

    def side_effect(*args: object, **_kwargs: object) -> MagicMock:
        cmd = args[0] if args else None
        if isinstance(cmd, list) and cmd and cmd[0] == "powershell":
            return MagicMock(returncode=0, stdout=ps_json)
        if isinstance(cmd, list) and cmd and cmd[0] == "taskkill":
            return MagicMock(returncode=128)
        raise AssertionError(cmd)

    mock_run.side_effect = side_effect
    assert not _kill_blocking_nt()


@patch("ziniao_mcp.cli.commands.update_cmd.subprocess.run")
@patch("ziniao_mcp.cli.commands.update_cmd.os.getpid", return_value=1)
def test_kill_blocking_nt_reports_successful_taskkill(
    _mock_pid: MagicMock, mock_run: MagicMock,
) -> None:
    ps_json = json.dumps(
        [{"Id": 100, "Path": r"C:\Users\x\AppData\Roaming\uv\tools\ziniao\Scripts\python.exe"}],
    )

    def side_effect(*args: object, **_kwargs: object) -> MagicMock:
        cmd = args[0] if args else None
        if isinstance(cmd, list) and cmd and cmd[0] == "powershell":
            return MagicMock(returncode=0, stdout=ps_json)
        if isinstance(cmd, list) and cmd and cmd[0] == "taskkill":
            return MagicMock(returncode=0)
        raise AssertionError(cmd)

    mock_run.side_effect = side_effect
    killed = _kill_blocking_nt()
    assert len(killed) == 1
    assert "100" in killed[0]


# ---------- _windows_spawn_uv_tool_install (no_kill) ----------


def test_windows_spawn_no_kill_script_omits_powershell(tmp_path) -> None:
    path = tmp_path / "ziniao-update-test.cmd"
    fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_BINARY)
    with (
        patch(
            "ziniao_mcp.cli.commands.update_cmd.tempfile.mkstemp",
            return_value=(fd, str(path)),
        ),
        patch("ziniao_mcp.cli.commands.update_cmd.subprocess.Popen"),
    ):
        with pytest.raises(typer.Exit) as exc:
            _windows_spawn_uv_tool_install(r"C:\fake\uv.exe", False, no_kill=True)
    assert exc.value.exit_code == 0
    txt = path.read_text(encoding="utf-8")
    assert "EncodedCommand" not in txt
    assert "powershell" not in txt.lower()


# ---------- _kill_blocking_unix unit tests ----------


@patch("ziniao_mcp.cli.commands.update_cmd.os.getpid", return_value=999)
@patch("ziniao_mcp.cli.commands.update_cmd.os.kill")
@patch("ziniao_mcp.cli.commands.update_cmd.subprocess.run")
def test_kill_blocking_unix_finds_and_kills(
    mock_run: MagicMock, mock_kill: MagicMock, _mock_pid: MagicMock,
) -> None:
    mock_ps = MagicMock(returncode=0)
    mock_ps.stdout = "\n".join([
        "  PID ARGS",
        " 1001 /home/u/.local/bin/ziniao mcp",
        " 1002 /home/u/.local/share/uv/tools/ziniao/bin/python -m ziniao_mcp",
        "  999 /home/u/.local/bin/ziniao update --sync",
        " 2000 /usr/bin/python3 unrelated.py",
    ])
    mock_run.return_value = mock_ps

    killed = _kill_blocking_unix()

    assert len(killed) == 2
    assert "1001" in killed[0]
    assert "1002" in killed[1]
    mock_kill.assert_any_call(1001, signal.SIGTERM)
    mock_kill.assert_any_call(1002, signal.SIGTERM)
    assert mock_kill.call_count == 2


@patch("ziniao_mcp.cli.commands.update_cmd.os.getpid", return_value=100)
@patch("ziniao_mcp.cli.commands.update_cmd.os.kill")
@patch("ziniao_mcp.cli.commands.update_cmd.subprocess.run")
def test_kill_blocking_unix_skips_unrelated(
    mock_run: MagicMock, mock_kill: MagicMock, _mock_pid: MagicMock,
) -> None:
    mock_ps = MagicMock(returncode=0)
    mock_ps.stdout = "\n".join([
        "  PID ARGS",
        " 3001 /usr/bin/python3 /home/u/project/ziniao/run.py",
        " 3002 vim /home/u/.config/ziniao.toml",
        " 3003 node server.js",
    ])
    mock_run.return_value = mock_ps

    killed = _kill_blocking_unix()

    assert not killed
    mock_kill.assert_not_called()
