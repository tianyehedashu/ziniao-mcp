"""Tests for ``ziniao update`` (uv-based self-upgrade)."""

from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path, PurePosixPath
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from ziniao_mcp.cli import app
from ziniao_mcp.cli.commands.update_cmd import (
    _build_nt_kill_ps,
    _graceful_quit_timeout,
    _graceful_stop_daemon,
    _kill_blocking_nt,
    _kill_blocking_unix,
    _parse_state,
    _path_matches_target,
    _self_protected_pids,
    _wait_for_update_state,
    _windows_spawn_uv_tool_install,
    _windows_update_cmd_body,
)

runner = CliRunner()


# 走 ``update_cli`` 真实入口的 CLI 集成测试，必须**显式** patch
# ``_graceful_stop_daemon``：
#
# - 不 patch 就可能在有 daemon 的开发机上真的 TCP 发送 quit，污染环境；
# - 老版本用 autouse fixture 全局 stub，但隐式默认会让"新增用例"忘了断言
#   graceful 行为，且需要配合 pytest marker 做豁免，复杂度溢价；
# - 显式 patch 把依赖写在调用侧，读测试时能一眼看出它期望什么。


# ---------------------------------------------------------------------------
# update_cli top-level
# ---------------------------------------------------------------------------


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


@patch("ziniao_mcp.cli.commands.update_cmd._graceful_stop_daemon", return_value=True)
@patch("ziniao_mcp.cli.commands.update_cmd._kill_blocking_processes", return_value=[])
@patch("ziniao_mcp.cli.commands.update_cmd.subprocess.run")
@patch("ziniao_mcp.cli.commands.update_cmd.shutil.which", return_value="/fake/uv")
def test_update_prints_version_banner(
    _mock_which: MagicMock,
    mock_run: MagicMock,
    _mock_kill: MagicMock,
    _mock_graceful: MagicMock,
) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    result = runner.invoke(app, ["update", "--sync"])
    assert result.exit_code == 0
    assert "当前版本" in result.stdout
    assert "升级来源" in result.stdout
    assert "PyPI" in result.stdout
    assert "uv tool install" in result.stdout


@patch("ziniao_mcp.cli.commands.update_cmd._graceful_stop_daemon", return_value=True)
@patch("ziniao_mcp.cli.commands.update_cmd._kill_blocking_processes", return_value=[])
@patch("ziniao_mcp.cli.commands.update_cmd.subprocess.run")
@patch("ziniao_mcp.cli.commands.update_cmd.shutil.which", return_value="/fake/uv")
def test_update_runs_uv_and_propagates_exit_code(
    _mock_which: MagicMock,
    mock_run: MagicMock,
    _mock_kill: MagicMock,
    _mock_graceful: MagicMock,
) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    result = runner.invoke(app, ["update", "--sync"])
    assert result.exit_code == 0
    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    assert args[0][0] == "/fake/uv"
    assert "tool" in args[0]
    assert kwargs.get("stdin") == subprocess.DEVNULL


@patch("ziniao_mcp.cli.commands.update_cmd._graceful_stop_daemon", return_value=True)
@patch("ziniao_mcp.cli.commands.update_cmd._kill_blocking_processes", return_value=[])
@patch("ziniao_mcp.cli.commands.update_cmd.subprocess.run")
@patch("ziniao_mcp.cli.commands.update_cmd.shutil.which", return_value="/fake/uv")
def test_update_nonzero_uv_exit(
    _mock_which: MagicMock,
    mock_run: MagicMock,
    _mock_kill: MagicMock,
    _mock_graceful: MagicMock,
) -> None:
    mock_run.return_value = MagicMock(returncode=2, stdout="", stderr="some error")
    result = runner.invoke(app, ["update", "--sync"])
    assert result.exit_code == 2


@patch("ziniao_mcp.cli.commands.update_cmd._graceful_stop_daemon", return_value=True)
@patch("ziniao_mcp.cli.commands.update_cmd._kill_blocking_processes")
@patch("ziniao_mcp.cli.commands.update_cmd.subprocess.run")
@patch("ziniao_mcp.cli.commands.update_cmd.shutil.which", return_value="/fake/uv")
def test_update_kills_blocking_processes_and_reports(
    _mock_which: MagicMock,
    mock_run: MagicMock,
    mock_kill: MagicMock,
    _mock_graceful: MagicMock,
) -> None:
    mock_kill.return_value = ["PID 1234 (python.exe)", "PID 5678 (ziniao.exe)"]
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    result = runner.invoke(app, ["update", "--sync"])
    assert result.exit_code == 0
    mock_kill.assert_called_once()
    args, _kwargs = mock_kill.call_args
    assert args and args[0] == "/fake/uv"
    assert "2" in result.stdout
    assert "PID 1234" in result.stdout


@patch("ziniao_mcp.cli.commands.update_cmd._graceful_stop_daemon", return_value=True)
@patch("ziniao_mcp.cli.commands.update_cmd._kill_blocking_processes")
@patch("ziniao_mcp.cli.commands.update_cmd.subprocess.run")
@patch("ziniao_mcp.cli.commands.update_cmd.shutil.which", return_value="/fake/uv")
def test_update_no_kill_skips_process_killing(
    _mock_which: MagicMock,
    mock_run: MagicMock,
    mock_kill: MagicMock,
    _mock_graceful: MagicMock,
) -> None:
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    result = runner.invoke(app, ["update", "--sync", "--no-kill"])
    assert result.exit_code == 0
    mock_kill.assert_not_called()


# ---------------------------------------------------------------------------
# 自身进程保护
# ---------------------------------------------------------------------------


@patch("ziniao_mcp.cli.commands.update_cmd.os.getppid", return_value=4321)
@patch("ziniao_mcp.cli.commands.update_cmd.os.getpid", return_value=1234)
def test_self_protected_pids_includes_self_and_parent(
    _mock_pid: MagicMock, _mock_ppid: MagicMock,
) -> None:
    protected = _self_protected_pids()
    assert 1234 in protected
    assert 4321 in protected


# ---------------------------------------------------------------------------
# _path_matches_target
# ---------------------------------------------------------------------------


@patch("ziniao_mcp.cli.commands.update_cmd.os.name", "nt")
def test_path_matches_target_nt_exact_shim() -> None:
    shim = Path(r"C:\Users\x\.local\bin\ziniao.exe")
    assert _path_matches_target(
        r"c:\users\x\.local\bin\ZINIAO.EXE", shim, [],
    ) is True


@patch("ziniao_mcp.cli.commands.update_cmd.os.name", "nt")
def test_path_matches_target_nt_under_tool_dir() -> None:
    shim = Path(r"C:\Users\x\.local\bin\ziniao.exe")
    tool_dir = Path(r"C:\Users\x\AppData\Roaming\uv\tools\ziniao")
    assert _path_matches_target(
        r"C:\Users\x\AppData\Roaming\uv\tools\ziniao\Scripts\python.exe",
        shim, [tool_dir],
    ) is True


@patch("ziniao_mcp.cli.commands.update_cmd.os.name", "nt")
def test_path_matches_target_nt_skips_same_name_but_unrelated_path() -> None:
    """紫鸟浏览器 / 其他 ziniao.exe 不得被误伤。"""
    shim = Path(r"C:\Users\x\.local\bin\ziniao.exe")
    tool_dir = Path(r"C:\Users\x\AppData\Roaming\uv\tools\ziniao")
    # 紫鸟浏览器客户端的常见路径（示例）
    assert _path_matches_target(
        r"C:\Program Files (x86)\Ziniao\ziniao.exe",
        shim, [tool_dir],
    ) is False
    # 名字相似的邻居目录（uv 里别的工具）
    assert _path_matches_target(
        r"C:\Users\x\AppData\Roaming\uv\tools\ziniao-other\Scripts\python.exe",
        shim, [tool_dir],
    ) is False


@patch("ziniao_mcp.cli.commands.update_cmd.os.name", "posix")
def test_path_matches_target_posix_case_sensitive() -> None:
    shim = PurePosixPath("/home/u/.local/bin/ziniao")
    assert _path_matches_target("/home/u/.local/bin/ziniao", shim, []) is True
    assert _path_matches_target("/home/u/.local/bin/ZINIAO", shim, []) is False


# ---------------------------------------------------------------------------
# _kill_blocking_nt
# ---------------------------------------------------------------------------


@patch("ziniao_mcp.cli.commands.update_cmd.os.name", "nt")
@patch("ziniao_mcp.cli.commands.update_cmd._self_protected_pids",
       return_value={1, 2})
@patch("ziniao_mcp.cli.commands.update_cmd._ziniao_shim_path",
       return_value=Path(r"C:\Users\x\.local\bin\ziniao.exe"))
@patch("ziniao_mcp.cli.commands.update_cmd._ziniao_tool_dirs",
       return_value=[Path(r"C:\Users\x\AppData\Roaming\uv\tools\ziniao")])
@patch("ziniao_mcp.cli.commands.update_cmd._query_nt_candidate_procs")
@patch("ziniao_mcp.cli.commands.update_cmd.subprocess.run")
def test_kill_blocking_nt_kills_matching(
    mock_run: MagicMock,
    mock_query: MagicMock,
    *_patches: MagicMock,
) -> None:
    mock_query.return_value = [
        (100, r"C:\Users\x\AppData\Roaming\uv\tools\ziniao\Scripts\python.exe"),
    ]
    mock_run.return_value = MagicMock(returncode=0)
    killed = _kill_blocking_nt()
    assert len(killed) == 1
    assert "100" in killed[0]
    mock_run.assert_called_once()
    args, _ = mock_run.call_args
    assert args[0][:3] == ["taskkill", "/F", "/PID"]


@patch("ziniao_mcp.cli.commands.update_cmd.os.name", "nt")
@patch("ziniao_mcp.cli.commands.update_cmd._self_protected_pids",
       return_value={100})
@patch("ziniao_mcp.cli.commands.update_cmd._ziniao_shim_path",
       return_value=Path(r"C:\Users\x\.local\bin\ziniao.exe"))
@patch("ziniao_mcp.cli.commands.update_cmd._ziniao_tool_dirs",
       return_value=[Path(r"C:\Users\x\AppData\Roaming\uv\tools\ziniao")])
@patch("ziniao_mcp.cli.commands.update_cmd._query_nt_candidate_procs")
@patch("ziniao_mcp.cli.commands.update_cmd.subprocess.run")
def test_kill_blocking_nt_skips_protected_pid(
    mock_run: MagicMock,
    mock_query: MagicMock,
    *_patches: MagicMock,
) -> None:
    """关键回归：自身/父 shim PID 在 protected 里，必须不被 taskkill。"""
    mock_query.return_value = [
        (100, r"C:\Users\x\.local\bin\ziniao.exe"),  # uv shim = 父进程
    ]
    killed = _kill_blocking_nt()
    assert killed == []
    mock_run.assert_not_called()


@patch("ziniao_mcp.cli.commands.update_cmd.os.name", "nt")
@patch("ziniao_mcp.cli.commands.update_cmd._self_protected_pids",
       return_value={1})
@patch("ziniao_mcp.cli.commands.update_cmd._ziniao_shim_path",
       return_value=Path(r"C:\Users\x\.local\bin\ziniao.exe"))
@patch("ziniao_mcp.cli.commands.update_cmd._ziniao_tool_dirs",
       return_value=[Path(r"C:\Users\x\AppData\Roaming\uv\tools\ziniao")])
@patch("ziniao_mcp.cli.commands.update_cmd._query_nt_candidate_procs")
@patch("ziniao_mcp.cli.commands.update_cmd.subprocess.run")
def test_kill_blocking_nt_skips_same_name_unrelated_path(
    mock_run: MagicMock,
    mock_query: MagicMock,
    *_patches: MagicMock,
) -> None:
    """紫鸟浏览器等同名 ziniao.exe 绝对路径不匹配 → 不杀。"""
    mock_query.return_value = [
        (200, r"C:\Program Files (x86)\Ziniao\ziniao.exe"),
    ]
    killed = _kill_blocking_nt()
    assert killed == []
    mock_run.assert_not_called()


@patch("ziniao_mcp.cli.commands.update_cmd.os.name", "nt")
@patch("ziniao_mcp.cli.commands.update_cmd._self_protected_pids",
       return_value={1})
@patch("ziniao_mcp.cli.commands.update_cmd._ziniao_shim_path",
       return_value=Path(r"C:\Users\x\.local\bin\ziniao.exe"))
@patch("ziniao_mcp.cli.commands.update_cmd._ziniao_tool_dirs",
       return_value=[Path(r"C:\Users\x\AppData\Roaming\uv\tools\ziniao")])
@patch("ziniao_mcp.cli.commands.update_cmd._query_nt_candidate_procs")
@patch("ziniao_mcp.cli.commands.update_cmd.subprocess.run")
def test_kill_blocking_nt_does_not_report_failed_taskkill(
    mock_run: MagicMock,
    mock_query: MagicMock,
    *_patches: MagicMock,
) -> None:
    mock_query.return_value = [
        (99, r"C:\Users\x\AppData\Roaming\uv\tools\ziniao\Scripts\python.exe"),
    ]
    mock_run.return_value = MagicMock(returncode=128)  # taskkill 失败
    killed = _kill_blocking_nt()
    assert killed == []


# ---------------------------------------------------------------------------
# _kill_blocking_unix
# ---------------------------------------------------------------------------


@patch("ziniao_mcp.cli.commands.update_cmd.os.name", "posix")
@patch("ziniao_mcp.cli.commands.update_cmd._self_protected_pids",
       return_value={999, 1})
@patch("ziniao_mcp.cli.commands.update_cmd._ziniao_shim_path",
       return_value=PurePosixPath("/home/u/.local/bin/ziniao"))
@patch("ziniao_mcp.cli.commands.update_cmd._ziniao_tool_dirs",
       return_value=[PurePosixPath("/home/u/.local/share/uv/tools/ziniao")])
@patch("ziniao_mcp.cli.commands.update_cmd.os.kill")
@patch("ziniao_mcp.cli.commands.update_cmd.subprocess.run")
def test_kill_blocking_unix_finds_and_kills(
    mock_run: MagicMock,
    mock_kill: MagicMock,
    *_patches: MagicMock,
) -> None:
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="\n".join([
            "  PID ARGS",
            " 1001 /home/u/.local/bin/ziniao mcp",
            " 1002 /home/u/.local/share/uv/tools/ziniao/bin/python -m ziniao_mcp",
            "  999 /home/u/.local/bin/ziniao update --sync",  # 自身 — skip
            " 2000 /usr/bin/python3 unrelated.py",
            " 2001 /opt/ziniao-browser/ziniao 浏览器模拟 — skip",
        ]),
    )
    killed = _kill_blocking_unix()
    assert len(killed) == 2
    assert "1001" in killed[0]
    assert "1002" in killed[1]
    mock_kill.assert_any_call(1001, signal.SIGTERM)
    mock_kill.assert_any_call(1002, signal.SIGTERM)
    assert mock_kill.call_count == 2


@patch("ziniao_mcp.cli.commands.update_cmd.os.name", "posix")
@patch("ziniao_mcp.cli.commands.update_cmd._self_protected_pids",
       return_value={100})
@patch("ziniao_mcp.cli.commands.update_cmd._ziniao_shim_path",
       return_value=PurePosixPath("/home/u/.local/bin/ziniao"))
@patch("ziniao_mcp.cli.commands.update_cmd._ziniao_tool_dirs",
       return_value=[PurePosixPath("/home/u/.local/share/uv/tools/ziniao")])
@patch("ziniao_mcp.cli.commands.update_cmd.os.kill")
@patch("ziniao_mcp.cli.commands.update_cmd.subprocess.run")
def test_kill_blocking_unix_skips_unrelated(
    mock_run: MagicMock,
    mock_kill: MagicMock,
    *_patches: MagicMock,
) -> None:
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="\n".join([
            "  PID ARGS",
            " 3001 /usr/bin/python3 /home/u/project/ziniao/run.py",
            " 3002 vim /home/u/.config/ziniao.toml",
            " 3003 node server.js",
        ]),
    )
    killed = _kill_blocking_unix()
    assert killed == []
    mock_kill.assert_not_called()


# ---------------------------------------------------------------------------
# state file
# ---------------------------------------------------------------------------


def test_parse_state_key_value() -> None:
    text = "uv_exit_code=0\nnew_version=0.2.51\nstatus=success\n"
    kv = _parse_state(text)
    assert kv == {"uv_exit_code": "0", "new_version": "0.2.51", "status": "success"}


def test_parse_state_ignores_blank_and_comments() -> None:
    text = "\n# hello\nfoo = bar \n=\nstatus=failed\n"
    kv = _parse_state(text)
    assert kv["status"] == "failed"
    assert kv["foo"] == "bar"


def test_wait_for_update_state_reads_status(tmp_path) -> None:
    state = tmp_path / "s.state"
    state.write_text("uv_exit_code=0\nstatus=success\n", encoding="utf-8")
    kv = _wait_for_update_state(state, timeout_sec=2)
    assert kv is not None
    assert kv["status"] == "success"


def test_wait_for_update_state_times_out(tmp_path) -> None:
    state = tmp_path / "missing.state"
    kv = _wait_for_update_state(state, timeout_sec=1)
    assert kv is None


# ---------------------------------------------------------------------------
# .cmd body
# ---------------------------------------------------------------------------


def test_windows_update_cmd_body_writes_state_and_version_probe() -> None:
    body = _windows_update_cmd_body(
        uv_line=r'"C:\uv.exe" tool install ziniao --upgrade --force --reinstall',
        state_path=r"C:\Temp\ziniao-update.state",
        no_kill=False,
        python_for_version=r"C:\uv\tools\ziniao\Scripts\python.exe",
        kill_ps_script="echo stub-kill",
    )
    assert "status=success" in body
    assert "status=failed" in body
    assert r"C:\Temp\ziniao-update.state" in body
    assert r"C:\uv\tools\ziniao\Scripts\python.exe" in body
    assert "importlib.metadata" in body
    # kill 分支使用 encoded PS
    assert "EncodedCommand" in body
    # 最终自删除
    assert 'del "%~f0"' in body


def test_windows_update_cmd_body_no_kill_skips_powershell() -> None:
    body = _windows_update_cmd_body(
        uv_line=r'"C:\uv.exe" tool install ziniao --upgrade --force --reinstall',
        state_path=r"C:\Temp\ziniao-update.state",
        no_kill=True,
        python_for_version=None,
        kill_ps_script=None,
    )
    assert "EncodedCommand" not in body
    assert "powershell" not in body.lower()
    # 没有 python 探测时，new_version 不会被写入（ZINIAO_VER 保持空）
    assert "importlib.metadata" not in body
    assert "status=success" in body


# ---------------------------------------------------------------------------
# _build_nt_kill_ps：.cmd 内 PS 的精确路径 + protected 白名单语义
# ---------------------------------------------------------------------------


def test_build_nt_kill_ps_embeds_exact_shim_and_dirs() -> None:
    shim = Path(r"C:\Users\x\.local\bin\ziniao.exe")
    tool_dir = Path(r"C:\Users\x\AppData\Roaming\uv\tools\ziniao")
    ps = _build_nt_kill_ps(shim=shim, tool_dirs=[tool_dir], protected_pids=[1234])
    low = ps.lower()
    # 精确路径字面量（小写化后）必须出现
    assert r"c:\users\x\.local\bin\ziniao.exe" in low
    assert r"c:\users\x\appdata\roaming\uv\tools\ziniao" in low
    # protected PID 出现在白名单里
    assert "1234" in ps
    # 关键 guard：对 protected 的排除 + 按 ToLower/StartsWith 比较
    assert "$protected -contains" in ps
    assert "ToLower()" in ps
    assert "StartsWith" in ps
    # 绝不能再出现旧实现里模糊 wildcard
    assert "-like '*" not in ps


def test_build_nt_kill_ps_escapes_single_quote_in_paths() -> None:
    """路径里真的有单引号时，必须按 PowerShell 规则 `'` → `''` 转义，避免注入。"""
    shim = Path(r"C:\Users\o'ne\.local\bin\ziniao.exe")
    ps = _build_nt_kill_ps(shim=shim, tool_dirs=[], protected_pids=[])
    # 转义后 shim 字面量出现两次单引号
    assert r"c:\users\o''ne\.local\bin\ziniao.exe" in ps.lower()


def test_windows_update_cmd_body_kill_script_none_skips_powershell() -> None:
    """防御性：即便 ``no_kill=False``，如果调用方没给 kill 脚本，也必须跳过 PS。"""
    body = _windows_update_cmd_body(
        uv_line=r'"C:\uv.exe" tool install ziniao',
        state_path=r"C:\Temp\ziniao-update.state",
        no_kill=False,
        python_for_version=None,
        kill_ps_script=None,
    )
    assert "EncodedCommand" not in body
    assert "powershell" not in body.lower()


# ---------------------------------------------------------------------------
# _windows_spawn_uv_tool_install
# ---------------------------------------------------------------------------


def _open_writable_fd(path: Path) -> int:
    flags = os.O_CREAT | os.O_WRONLY | os.O_TRUNC | getattr(os, "O_BINARY", 0)
    return os.open(path, flags)


@patch("ziniao_mcp.cli.commands.update_cmd._skip_parent_wait", return_value=True)
@patch("ziniao_mcp.cli.commands.update_cmd._uv_tool_dir", return_value=None)
@patch("ziniao_mcp.cli.commands.update_cmd.subprocess.Popen")
def test_windows_spawn_no_kill_script_omits_powershell(
    _mock_popen: MagicMock,
    _mock_dir: MagicMock,
    _mock_skip: MagicMock,
    tmp_path,
) -> None:
    cmd_path = tmp_path / "ziniao-update-test.cmd"
    fd = _open_writable_fd(cmd_path)
    with patch(
        "ziniao_mcp.cli.commands.update_cmd.tempfile.mkstemp",
        return_value=(fd, str(cmd_path)),
    ):
        with pytest.raises(typer.Exit) as exc:
            _windows_spawn_uv_tool_install(r"C:\fake\uv.exe", False, no_kill=True)
    assert exc.value.exit_code == 0
    txt = cmd_path.read_text(encoding="utf-8")
    assert "EncodedCommand" not in txt
    assert "powershell" not in txt.lower()


@patch("ziniao_mcp.cli.commands.update_cmd._skip_parent_wait", return_value=True)
@patch("ziniao_mcp.cli.commands.update_cmd._uv_tool_dir",
       return_value=Path(r"C:\Users\x\AppData\Roaming\uv\tools"))
@patch("ziniao_mcp.cli.commands.update_cmd.subprocess.Popen")
def test_windows_spawn_default_script_has_kill_and_version_probe(
    _mock_popen: MagicMock,
    _mock_dir: MagicMock,
    _mock_skip: MagicMock,
    tmp_path,
) -> None:
    cmd_path = tmp_path / "ziniao-update-default.cmd"
    fd = _open_writable_fd(cmd_path)
    with patch(
        "ziniao_mcp.cli.commands.update_cmd.tempfile.mkstemp",
        return_value=(fd, str(cmd_path)),
    ):
        with pytest.raises(typer.Exit) as exc:
            _windows_spawn_uv_tool_install(r"C:\fake\uv.exe", False, no_kill=False)
    assert exc.value.exit_code == 0
    txt = cmd_path.read_text(encoding="utf-8")
    # kill 分支存在
    assert "EncodedCommand" in txt
    # 版本探测路径来自 uv tool dir + /ziniao/Scripts/python.exe
    assert r"ziniao\Scripts\python.exe" in txt
    # state 写入 + 自删除
    assert "status=success" in txt
    assert 'del "%~f0"' in txt


@patch("ziniao_mcp.cli.commands.update_cmd._graceful_stop_daemon", return_value=True)
@patch("ziniao_mcp.cli.commands.update_cmd._windows_spawn_uv_tool_install")
@patch("ziniao_mcp.cli.commands.update_cmd.os.name", "nt")
@patch("ziniao_mcp.cli.commands.update_cmd.shutil.which", return_value=r"C:\fake\uv.exe")
def test_update_windows_default_delegates_to_spawn(
    _mock_which: MagicMock,
    mock_spawn: MagicMock,
    _mock_graceful: MagicMock,
) -> None:
    """Windows 默认（非 --sync）必须走异步 spawn；主进程不得直接 kill/run uv。"""
    def _exit(*_a, **_k):
        raise typer.Exit(0)

    mock_spawn.side_effect = _exit
    result = runner.invoke(app, ["update"])
    assert result.exit_code == 0
    mock_spawn.assert_called_once()
    args, kwargs = mock_spawn.call_args
    assert args[0] == r"C:\fake\uv.exe"
    assert args[1] is False  # git
    assert kwargs.get("no_kill") is False


# ---------------------------------------------------------------------------
# _graceful_stop_daemon：升级前的优雅停机
# ---------------------------------------------------------------------------


def test_graceful_quit_timeout_defaults_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ZINIAO_UPDATE_QUIT_TIMEOUT", raising=False)
    assert _graceful_quit_timeout() == 15.0
    monkeypatch.setenv("ZINIAO_UPDATE_QUIT_TIMEOUT", "1.5")
    assert _graceful_quit_timeout() == pytest.approx(1.5)
    monkeypatch.setenv("ZINIAO_UPDATE_QUIT_TIMEOUT", "not-a-number")
    assert _graceful_quit_timeout() == 15.0
    monkeypatch.setenv("ZINIAO_UPDATE_QUIT_TIMEOUT", "-3")
    assert _graceful_quit_timeout() == 0.0


@patch("ziniao_mcp.cli.connection.find_daemon", return_value=None)
def test_graceful_stop_no_daemon_returns_true(_mock_find: MagicMock) -> None:
    """没 daemon 时直接返回 True，绝对不能触发 socket 连接。"""
    with patch(
        "ziniao_mcp.cli.commands.update_cmd.socket.create_connection",
    ) as mock_conn:
        assert _graceful_stop_daemon(timeout=1.0) is True
        mock_conn.assert_not_called()


@patch("ziniao_mcp.cli.commands.update_cmd.time.sleep")
def test_graceful_stop_daemon_exits_after_quit(_mock_sleep: MagicMock) -> None:
    """发 quit 后 daemon 在 poll 期间退出 → 返回 True。"""
    find_seq = iter([19816, 19816, None, None])

    def _find_side(*_args, **_kwargs):
        return next(find_seq)

    mock_sock = MagicMock()
    mock_sock.recv.side_effect = [b"", b""]
    ctx = MagicMock()
    ctx.__enter__.return_value = mock_sock
    ctx.__exit__.return_value = False

    with (
        patch("ziniao_mcp.cli.connection.find_daemon", side_effect=_find_side),
        patch(
            "ziniao_mcp.cli.commands.update_cmd.socket.create_connection",
            return_value=ctx,
        ) as mock_create,
    ):
        assert _graceful_stop_daemon(timeout=2.0) is True
    mock_create.assert_called_once_with(("127.0.0.1", 19816), timeout=2.0)
    sent = mock_sock.sendall.call_args[0][0]
    assert b'"quit"' in sent


@patch("ziniao_mcp.cli.commands.update_cmd.time.sleep")
def test_graceful_stop_daemon_times_out(_mock_sleep: MagicMock) -> None:
    """daemon 一直存活 → 返回 False，交给兜底 kill 路径。"""
    mock_sock = MagicMock()
    mock_sock.recv.return_value = b""
    ctx = MagicMock()
    ctx.__enter__.return_value = mock_sock
    ctx.__exit__.return_value = False

    # 用 monotonic 让 deadline 很快到期，避免真等 5s。
    ticks = iter([0.0, 0.0, 0.1, 0.2, 0.3, 10.0, 10.0, 10.0])
    with (
        patch("ziniao_mcp.cli.connection.find_daemon", return_value=19816),
        patch(
            "ziniao_mcp.cli.commands.update_cmd.socket.create_connection",
            return_value=ctx,
        ),
        patch(
            "ziniao_mcp.cli.commands.update_cmd.time.monotonic",
            side_effect=lambda: next(ticks),
        ),
    ):
        assert _graceful_stop_daemon(timeout=1.0) is False


def test_graceful_stop_daemon_send_failure_returns_false() -> None:
    """TCP 连不上（daemon 刚崩）→ 返回 False 并记入 stderr。"""
    with (
        patch("ziniao_mcp.cli.connection.find_daemon", return_value=19816),
        patch(
            "ziniao_mcp.cli.commands.update_cmd.socket.create_connection",
            side_effect=ConnectionRefusedError("nope"),
        ),
    ):
        assert _graceful_stop_daemon(timeout=1.0) is False


# ---------------------------------------------------------------------------
# update_cli 调用顺序：必须先 graceful stop，再 spawn / kill
# ---------------------------------------------------------------------------


@patch("ziniao_mcp.cli.commands.update_cmd._windows_spawn_uv_tool_install")
@patch("ziniao_mcp.cli.commands.update_cmd._graceful_stop_daemon", return_value=True)
@patch("ziniao_mcp.cli.commands.update_cmd.os.name", "nt")
@patch("ziniao_mcp.cli.commands.update_cmd.shutil.which", return_value=r"C:\fake\uv.exe")
def test_update_windows_calls_graceful_stop_before_spawn(
    _mock_which: MagicMock,
    mock_graceful: MagicMock,
    mock_spawn: MagicMock,
) -> None:
    call_order: list[str] = []
    mock_graceful.side_effect = lambda *a, **k: call_order.append("graceful") or True

    def _spawn(*_a, **_k):
        call_order.append("spawn")
        raise typer.Exit(0)

    mock_spawn.side_effect = _spawn
    result = runner.invoke(app, ["update"])
    assert result.exit_code == 0
    assert call_order == ["graceful", "spawn"]


@patch("ziniao_mcp.cli.commands.update_cmd._windows_spawn_uv_tool_install")
@patch("ziniao_mcp.cli.commands.update_cmd._graceful_stop_daemon", return_value=True)
@patch("ziniao_mcp.cli.commands.update_cmd.os.name", "nt")
@patch("ziniao_mcp.cli.commands.update_cmd.shutil.which", return_value=r"C:\fake\uv.exe")
def test_update_no_kill_still_calls_graceful_stop(
    _mock_which: MagicMock,
    mock_graceful: MagicMock,
    mock_spawn: MagicMock,
) -> None:
    """--no-kill 只跳过强杀，graceful quit 仍必须执行——否则 daemon 持有
    <uv tool dir>/ziniao/** 的 .pyd/python.exe 句柄，uv 安装必然 ERROR 32。
    """
    mock_spawn.side_effect = lambda *a, **k: (_ for _ in ()).throw(typer.Exit(0))
    result = runner.invoke(app, ["update", "--no-kill"])
    assert result.exit_code == 0
    mock_graceful.assert_called_once()


@patch("ziniao_mcp.cli.commands.update_cmd._kill_blocking_processes", return_value=[])
@patch("ziniao_mcp.cli.commands.update_cmd.subprocess.run")
@patch("ziniao_mcp.cli.commands.update_cmd._graceful_stop_daemon", return_value=True)
@patch("ziniao_mcp.cli.commands.update_cmd.shutil.which", return_value="/fake/uv")
def test_update_sync_calls_graceful_stop_before_kill(
    _mock_which: MagicMock,
    mock_graceful: MagicMock,
    mock_run: MagicMock,
    mock_kill: MagicMock,
) -> None:
    """--sync 路径同样走 graceful → kill → uv 的顺序。"""
    call_order: list[str] = []
    mock_graceful.side_effect = lambda *a, **k: call_order.append("graceful") or True
    mock_kill.side_effect = lambda *a, **k: call_order.append("kill") or []

    def _run(*_a, **_k):
        call_order.append("uv")
        return MagicMock(returncode=0, stdout="", stderr="")

    mock_run.side_effect = _run
    result = runner.invoke(app, ["update", "--sync"])
    assert result.exit_code == 0
    assert call_order == ["graceful", "kill", "uv"]


@patch("ziniao_mcp.cli.commands.update_cmd._graceful_stop_daemon", return_value=True)
@patch("ziniao_mcp.cli.commands.update_cmd.subprocess.run")
@patch("ziniao_mcp.cli.commands.update_cmd.shutil.which", return_value="/fake/uv")
def test_update_sync_no_kill_still_calls_graceful(
    _mock_which: MagicMock,
    mock_run: MagicMock,
    mock_graceful: MagicMock,
) -> None:
    """--sync --no-kill：graceful 必调，force kill 必跳。"""
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    result = runner.invoke(app, ["update", "--sync", "--no-kill"])
    assert result.exit_code == 0
    mock_graceful.assert_called_once()
