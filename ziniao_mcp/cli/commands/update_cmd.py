"""Self-update via ``uv tool install`` (PyPI or GitHub). Does not use the daemon."""

from __future__ import annotations

import base64
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List

import typer

ZINIAO_GIT_URL = "git+https://github.com/tianyehedashu/ziniao-mcp.git@main"

# Windows: START 的首个引号参数为控制台窗口标题（任务栏/Alt+Tab 可辨），与常见安装程序一致。
_WIN_UPDATE_CONSOLE_TITLE = "Ziniao CLI - upgrade"


def _windows_update_skip_final_pause() -> bool:
    """非交互/CI 下不在 .cmd 末尾 pause，避免脚本挂死（与 GitHub Actions、通用 CI 约定一致）。"""
    if os.environ.get("ZINIAO_UPDATE_NO_PAUSE", "").strip().lower() in ("1", "true", "yes"):
        return True
    if os.environ.get("CI", "").strip().lower() in ("1", "true", "yes"):
        return True
    if os.environ.get("GITHUB_ACTIONS", "").strip().lower() == "true":
        return True
    return False


# PowerShell snippet: kill processes whose path matches the uv-installed ziniao
# entrypoint (~/.local/bin/ziniao.exe) or anything under uv/tools/ziniao/.
_PS_KILL_LOCKING = (
    "Get-Process -ErrorAction SilentlyContinue | "
    "Where-Object { $_.Path -ne $null -and ("
    "$_.Path -like '*\\.local\\bin\\ziniao.exe' -or "
    "$_.Path -like '*\\uv\\tools\\ziniao\\*'"
    ")} | Stop-Process -Force -ErrorAction SilentlyContinue"
)


def _argv_pypi(uv_exe: str) -> List[str]:
    return [uv_exe, "tool", "install", "ziniao", "--upgrade", "--force", "--reinstall"]


def _argv_git(uv_exe: str) -> List[str]:
    return [uv_exe, "tool", "install", ZINIAO_GIT_URL, "--force", "--reinstall"]


def _format_cmd(argv: List[str]) -> str:
    """Single line for copy-paste (POSIX-style quoting; good enough for docs and bash)."""
    return shlex.join(argv)


def _ps_encoded_command(script: str) -> str:
    """Encode a PowerShell script for ``-EncodedCommand`` (avoids CMD quoting pitfalls)."""
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


def _kill_blocking_processes() -> List[str]:
    """Kill processes that may lock or use ziniao's uv-managed files.

    Windows: resolves file-lock (error 32) that blocks ``uv tool install``.
    Unix:    stops old-version processes so the new binary takes effect immediately.

    Targets on all platforms:
      - ziniao binary at ``~/.local/bin/`` (uv-installed CLI entrypoint)
      - Executables under ``uv/tools/ziniao/`` (MCP server, daemon)

    Skips the current process.  Returns descriptions of killed processes.
    """
    if os.name == "nt":
        return _kill_blocking_nt()
    return _kill_blocking_unix()


def _kill_blocking_nt() -> List[str]:
    killed: List[str] = []
    current_pid = os.getpid()

    ps_cmd = (
        "Get-Process -ErrorAction SilentlyContinue | "
        "Where-Object { $_.Path -ne $null -and ("
        "$_.Path -like '*\\.local\\bin\\ziniao.exe' -or "
        "$_.Path -like '*\\uv\\tools\\ziniao\\*'"
        ")} | Select-Object Id, Path | ConvertTo-Json -Compress"
    )

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []

        data = json.loads(result.stdout)
        if isinstance(data, dict):
            data = [data]

        for proc in data:
            pid = proc.get("Id")
            path_str = proc.get("Path", "")
            if not pid or pid == current_pid:
                continue
            try:
                tk = subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    capture_output=True,
                    timeout=5,
                )
                if tk.returncode == 0:
                    killed.append(f"PID {pid} ({Path(path_str).name})")
            except (subprocess.TimeoutExpired, OSError):
                pass
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError, ValueError):
        pass

    return killed


def _kill_blocking_unix() -> List[str]:
    killed: List[str] = []
    current_pid = os.getpid()

    try:
        result = subprocess.run(
            ["ps", "-eo", "pid,args"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return []

        for line in result.stdout.splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 1)
            if len(parts) < 2:
                continue
            try:
                pid = int(parts[0])
            except ValueError:
                continue
            if pid == current_pid:
                continue

            cmd = parts[1]
            if "/.local/bin/ziniao" not in cmd and "/uv/tools/ziniao/" not in cmd:
                continue

            try:
                os.kill(pid, signal.SIGTERM)
                name = Path(cmd.split()[0]).name
                killed.append(f"PID {pid} ({name})")
            except OSError:
                pass
    except (subprocess.TimeoutExpired, OSError):
        pass

    return killed


def _stderr_suggests_file_lock(stderr: str) -> bool:
    low = stderr.lower()
    return (
        "error 32" in low
        or "os error 32" in low
        or "另一个程序正在使用" in stderr
        or "being used by another process" in low
        or "进程无法访问" in stderr
    )


def _print_copy_hints(*, uv_exe: str, stderr_text: str = "") -> None:
    typer.echo("", err=True)
    if os.name == "nt" and stderr_text and _stderr_suggests_file_lock(stderr_text):
        typer.echo(
            "检测到 Windows 文件占用（错误 32）。自动终止未能完全解除锁定，请手动排查：",
            err=True,
        )
        typer.echo("  1. 执行 `ziniao quit`（用过 CLI 自动化时）", err=True)
        typer.echo(
            "  2. 在 Cursor 中暂时禁用 ziniao MCP，或退出 Cursor",
            err=True,
        )
        typer.echo("  3. 关闭所有可能跑过 ziniao 的终端", err=True)
        typer.echo(
            "  4. 任务管理器中结束残留的 ziniao.exe / python.exe（uv 工具目录相关）",
            err=True,
        )
        typer.echo("  5. 新开 PowerShell 窗口执行下方命令", err=True)
        typer.echo("", err=True)
    typer.echo(
        "手动执行（PowerShell 推荐，整行复制）：",
        err=True,
    )
    typer.echo(
        f'  PyPI: & "{uv_exe}" tool install ziniao --upgrade --force --reinstall',
        err=True,
    )
    typer.echo(
        f'  Git:  & "{uv_exe}" tool install {ZINIAO_GIT_URL} --force --reinstall',
        err=True,
    )
    typer.echo(
        f"  （Bash/WSL）PyPI: {_format_cmd(_argv_pypi(uv_exe))}",
        err=True,
    )
    typer.echo(
        f"  （Bash/WSL）Git:  {_format_cmd(_argv_git(uv_exe))}",
        err=True,
    )


def _no_uv_message() -> None:
    typer.echo("错误：未在 PATH 中找到 uv。", err=True)
    typer.echo("请先安装 uv：https://docs.astral.sh/uv/", err=True)
    typer.echo("手动执行：", err=True)
    typer.echo(f"  {_format_cmd(_argv_pypi('uv'))}", err=True)
    typer.echo(f"  {_format_cmd(_argv_git('uv'))}", err=True)


def _windows_update_cmd_body(*, uv_line: str, no_kill: bool) -> str:
    """Inner .cmd content (kill / delay / uv / optional pause / self-delete)."""
    if _windows_update_skip_final_pause():
        pause_block = "\r\n".join([
            "echo.",
            "echo [ziniao] 非交互环境（CI 等）：已跳过 pause，约 2 秒后关闭窗口。",
            "timeout /t 2 /nobreak >nul",
        ])
    else:
        pause_block = "\r\n".join([
            "echo.",
            "echo [ziniao] 按任意键关闭本窗口 ...",
            "pause >nul",
        ])
    if no_kill:
        head = [
            "@echo off",
            "setlocal",
            "chcp 65001 >nul",
            "echo [ziniao] 已跳过自动终止进程（与 --no-kill 一致）。",
            "echo [ziniao] 等待约 2 秒以释放当前 ziniao.exe 占用，然后执行 uv ...",
            "timeout /t 2 /nobreak >nul",
            uv_line,
            "if errorlevel 1 (",
            "  echo.",
            "  echo [ziniao] uv 失败。若仍报文件被占用，请手动关闭相关进程后重试。",
            ") else (",
            "  echo.",
            "  echo [ziniao] 升级完成。请新开终端使用 ziniao；Cursor MCP 会自动重连。",
            ")",
        ]
    else:
        ps_encoded = _ps_encoded_command(_PS_KILL_LOCKING)
        head = [
            "@echo off",
            "setlocal",
            "chcp 65001 >nul",
            "echo [ziniao] 正在终止占用文件的进程 (MCP / daemon / CLI) ...",
            f"powershell -NoProfile -EncodedCommand {ps_encoded}",
            "echo [ziniao] 等待约 2 秒以释放文件占用 ...",
            "timeout /t 2 /nobreak >nul",
            uv_line,
            "if errorlevel 1 (",
            "  echo.",
            "  echo [ziniao] uv 失败。若仍报文件被占用，请手动关闭所有 ziniao 相关进程后重试。",
            ") else (",
            "  echo.",
            "  echo [ziniao] 升级完成。请新开终端使用 ziniao；Cursor MCP 会自动重连。",
            ")",
        ]
    tail = [
        pause_block,
        'del "%~f0" 2>nul',
        "endlocal",
        "exit /b 0",
        "",
    ]
    return "\r\n".join(head + tail)


def _windows_spawn_uv_tool_install(uv_exe: str, git: bool, *, no_kill: bool = False) -> None:
    """Avoid Windows exe self-lock: exit this process before uv replaces ziniao.exe.

    Writes a temp .cmd that:
    1. (Unless ``no_kill``) Kills processes locking ziniao files (MCP, daemon, other CLI)
    2. Waits briefly for file handles to release
    3. Runs ``uv tool install ...`` in a new console

    Spawns via ``start "<title>" cmd /c ...`` so the upgrade window has a recognizable
    taskbar title (same idea as many Windows installers / updaters).
    """
    argv = _argv_git(uv_exe) if git else _argv_pypi(uv_exe)
    uv_line = subprocess.list2cmdline(argv)
    script = _windows_update_cmd_body(uv_line=uv_line, no_kill=no_kill)
    fd, path = tempfile.mkstemp(prefix="ziniao-update-", suffix=".cmd", text=False)
    try:
        os.write(fd, script.encode("utf-8"))
    finally:
        os.close(fd)

    bat = Path(path)
    bat_resolved = str(bat.resolve())
    inner = subprocess.list2cmdline(["cmd.exe", "/c", bat_resolved])
    # start 的首个引号串为窗口标题；路径经 list2cmdline 转义，避免空格/特殊字符拆参。
    start_cmdline = f'start "{_WIN_UPDATE_CONSOLE_TITLE}" {inner}'
    try:
        subprocess.Popen(
            start_cmdline,
            shell=True,
            close_fds=True,
        )
    except OSError as exc:
        typer.echo(f"无法启动升级子进程: {exc}", err=True)
        try:
            bat.unlink(missing_ok=True)
        except OSError:
            pass
        _print_copy_hints(uv_exe=uv_exe)
        raise typer.Exit(1) from exc

    if no_kill:
        head = (
            "[ziniao] 已在新控制台启动升级（--no-kill：未自动终止其它进程，约 2 秒后执行 uv）。"
        )
    else:
        head = "[ziniao] 已在新控制台启动升级（先终止占用进程，约 2 秒后执行 uv）。"
    # stderr + flush：避免 Windows 上父进程很快 Exit(0) 时 stdout 提示未刷出、看起来像「无输出」
    for part in (
        head,
        f"  uv 的下载与安装日志在任务栏标题为「{_WIN_UPDATE_CONSOLE_TITLE}」的新窗口，请 Alt+Tab 查找。",
        "  本窗口即将退出；升级窗口结束前可按提示按键关窗（CI 下自动省略 pause）。",
        "  若要在当前窗口看完整过程，请使用: ziniao update --sync",
    ):
        typer.echo(part, err=True)
    sys.stdout.flush()
    sys.stderr.flush()
    raise typer.Exit(0)


def update_cli(
    git: bool = typer.Option(
        False, "--git",
        help="Install latest from GitHub main (instead of PyPI).",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="Print the command only; do not run it.",
    ),
    sync: bool = typer.Option(
        False, "--sync",
        help=(
            "Run uv in this terminal with live output (default on Windows: new console + exit "
            "to avoid exe self-replace error 32)."
        ),
    ),
    no_kill: bool = typer.Option(
        False, "--no-kill",
        help="Skip auto-killing (in-process + Windows upgrade .cmd PowerShell step).",
    ),
) -> None:
    """Upgrade ziniao CLI to latest via uv (PyPI or GitHub)."""
    uv_exe = shutil.which("uv")
    if not uv_exe:
        _no_uv_message()
        raise typer.Exit(1)

    argv = _argv_git(uv_exe) if git else _argv_pypi(uv_exe)
    line = _format_cmd(argv)

    if dry_run:
        typer.echo(f"[dry-run] {line}")
        if os.name == "nt" and not sync:
            msg = (
                "[dry-run] Windows 默认：临时 .cmd → start "
                f'"{_WIN_UPDATE_CONSOLE_TITLE}" 独立控制台跑 uv（延迟 2s），'
                "当前进程立即退出。同步执行请加 --sync。"
            )
            if no_kill:
                msg += " 使用 --no-kill 时 .cmd 内不会执行 PowerShell 终止逻辑。"
            typer.echo(msg)
        else:
            typer.echo("在第二个终端执行上述命令可避免「自替换」顾虑。")
        raise typer.Exit(0)

    if not no_kill:
        killed = _kill_blocking_processes()
        if killed:
            typer.echo(f"已终止 {len(killed)} 个占用进程：")
            for desc in killed:
                typer.echo(f"  - {desc}")

    if os.name == "nt" and not sync:
        _windows_spawn_uv_tool_install(uv_exe, git, no_kill=no_kill)

    typer.echo(f"Running: {line}")
    try:
        if sync:
            # 同步模式：不捕获输出，便于看到 uv 实时进度（此前 capture 会导致结束前一屏空白）
            proc = subprocess.run(argv, check=False, stdin=subprocess.DEVNULL)
            out_tail = ""
            err_tail = ""
        else:
            proc = subprocess.run(
                argv,
                check=False,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            out_tail = proc.stdout or ""
            err_tail = proc.stderr or ""
    except OSError as exc:
        typer.echo(f"无法启动 uv: {exc}", err=True)
        _print_copy_hints(uv_exe=uv_exe)
        raise typer.Exit(1) from exc

    if out_tail:
        sys.stdout.write(out_tail)
    if err_tail:
        sys.stderr.write(err_tail)

    if proc.returncode != 0:
        typer.echo(f"uv 退出码: {proc.returncode}", err=True)
        combined_err = err_tail + out_tail
        _print_copy_hints(uv_exe=uv_exe, stderr_text=combined_err)
        raise typer.Exit(proc.returncode)

    typer.echo("升级完成。请执行 `ziniao quit` 结束旧 daemon；Cursor MCP 会自动重连。")


def register(app: typer.Typer) -> None:
    """Register ``ziniao update`` on the root Typer app."""
    app.command("update")(update_cli)
