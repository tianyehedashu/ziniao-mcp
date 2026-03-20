"""Self-update via ``uv tool install`` (PyPI or GitHub). Does not use the daemon."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List

import typer

# Same repo as README GitHub link
ZINIAO_GIT_URL = "git+https://github.com/tianyehedashu/ziniao-mcp.git@main"


def _argv_pypi(uv_exe: str) -> List[str]:
    return [uv_exe, "tool", "install", "ziniao", "--upgrade", "--force", "--reinstall"]


def _argv_git(uv_exe: str) -> List[str]:
    return [uv_exe, "tool", "install", ZINIAO_GIT_URL, "--force", "--reinstall"]


def _format_cmd(argv: List[str]) -> str:
    """Single line for copy-paste (POSIX-style quoting; good enough for docs and bash)."""
    return shlex.join(argv)


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
            "检测到可能是 Windows 文件占用（如错误 32）。请按顺序尝试：",
            err=True,
        )
        typer.echo("  1. 执行 `ziniao quit`（用过 CLI 自动化时）", err=True)
        typer.echo(
            "  2. 在 Cursor 中暂时禁用或移除 ziniao MCP，或退出 Cursor（MCP 用 uv run / python -m 时也会占用环境）",
            err=True,
        )
        typer.echo("  3. 关闭所有已打开、可能跑过 ziniao 的终端", err=True)
        typer.echo(
            "  4. 任务管理器中结束残留的 ziniao.exe、python.exe（紫鸟/工具目录相关）",
            err=True,
        )
        typer.echo(
            "  5. 新开 PowerShell（或 CMD）窗口，在「无 ziniao 在跑」的情况下执行下方命令",
            err=True,
        )
        typer.echo("", err=True)
    typer.echo(
        "请在「新的」终端中手动执行（PowerShell 推荐，整行复制；CMD 请去掉开头的 & 与外层引号，直接运行 uv 路径）：",
        err=True,
    )
    # shlex.join 在 CMD 中不便粘贴；PowerShell 用 & "path" 最稳
    typer.echo(
        f'  PyPI: & "{uv_exe}" tool install ziniao --upgrade --force --reinstall',
        err=True,
    )
    typer.echo(
        f'  Git:  & "{uv_exe}" tool install {ZINIAO_GIT_URL} --force --reinstall',
        err=True,
    )
    typer.echo(
        f"  （Bash/WSL/Git Bash 可用）PyPI: {_format_cmd(_argv_pypi(uv_exe))}",
        err=True,
    )
    typer.echo(
        f"  （Bash/WSL/Git Bash 可用）Git:  {_format_cmd(_argv_git(uv_exe))}",
        err=True,
    )


def _no_uv_message() -> None:
    typer.echo("错误：未在 PATH 中找到 uv。", err=True)
    typer.echo("请先安装 uv：https://docs.astral.sh/uv/", err=True)
    typer.echo("然后手动执行：", err=True)
    typer.echo(f"  {_format_cmd(_argv_pypi('uv'))}", err=True)
    typer.echo(f"  {_format_cmd(_argv_git('uv'))}", err=True)


def _windows_spawn_uv_tool_install(uv_exe: str, git: bool) -> None:
    """Avoid Windows exe self-lock: exit this process before uv replaces ziniao.exe.

    Writes a temp .cmd that waits briefly, then runs ``uv tool install ...`` in a new console.
    """
    argv = _argv_git(uv_exe) if git else _argv_pypi(uv_exe)
    uv_line = subprocess.list2cmdline(argv)
    # Delay lets this ziniao.exe process terminate and release the file mapping lock.
    script = "\r\n".join(
        [
            "@echo off",
            "chcp 65001 >nul",
            "echo [ziniao] 等待约 2 秒以释放当前 ziniao.exe 占用，然后执行 uv ...",
            "timeout /t 2 /nobreak >nul",
            uv_line,
            "if errorlevel 1 (",
            "  echo.",
            "  echo [ziniao] uv 失败。若仍报「文件被占用」，请关闭其它 ziniao 终端 / Cursor MCP 后重试。",
            ") else (",
            "  echo.",
            "  echo [ziniao] 升级完成。请新开终端使用 ziniao；必要时 ziniao quit 并重启 Cursor MCP。",
            ")",
            "echo.",
            "pause",
            "del \"%~f0\" 2>nul",
            "exit /b 0",
            "",
        ]
    )
    fd, path = tempfile.mkstemp(prefix="ziniao-update-", suffix=".cmd", text=False)
    try:
        os.write(fd, script.encode("utf-8"))
    finally:
        os.close(fd)

    bat = Path(path)
    creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    try:
        subprocess.Popen(
            ["cmd.exe", "/c", str(bat)],
            close_fds=True,
            creationflags=creationflags,
        )
    except OSError as exc:
        typer.echo(f"无法启动升级子进程: {exc}", err=True)
        try:
            bat.unlink(missing_ok=True)
        except OSError:
            pass
        _print_copy_hints(uv_exe=uv_exe)
        raise typer.Exit(1) from exc

    typer.echo(
        "已在新控制台窗口启动升级（约 2 秒后执行 uv）。"
        "本进程立即退出以解除对 ziniao.exe 的占用，请在新窗口查看结果。",
    )
    raise typer.Exit(0)


def update_cli(
    git: bool = typer.Option(
        False, "--git",
        help="从 GitHub 仓库 main 安装最新版（而非 PyPI）。",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="仅打印将执行的命令，不实际运行。",
    ),
    sync: bool = typer.Option(
        False, "--sync",
        help="在当前进程内同步执行 uv（默认仅 Windows：新开窗口并立即退出本进程，避免 exe 自占用导致错误 32）。",
    ),
) -> None:
    """使用 uv 将 ziniao CLI 升级到最新版（PyPI 或 GitHub）。"""
    uv_exe = shutil.which("uv")
    if not uv_exe:
        _no_uv_message()
        raise typer.Exit(1)

    argv = _argv_git(uv_exe) if git else _argv_pypi(uv_exe)
    line = _format_cmd(argv)

    if dry_run:
        typer.echo(f"[dry-run] {line}")
        if os.name == "nt" and not sync:
            typer.echo(
                "[dry-run] Windows 默认：写入临时 .cmd → 新控制台延迟 2s 后执行上述命令，"
                "当前进程立即退出。需要同步执行与退出码请加 --sync。",
            )
        else:
            typer.echo("在第二个终端执行上述命令可避免「自替换」顾虑。")
        raise typer.Exit(0)

    if os.name == "nt" and not sync:
        _windows_spawn_uv_tool_install(uv_exe, git)

    typer.echo(f"Running: {line}")
    try:
        proc = subprocess.run(
            argv,
            check=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        typer.echo(f"无法启动 uv: {exc}", err=True)
        _print_copy_hints(uv_exe=uv_exe)
        raise typer.Exit(1) from exc

    if proc.stdout:
        sys.stdout.write(proc.stdout)
    if proc.stderr:
        sys.stderr.write(proc.stderr)

    if proc.returncode != 0:
        typer.echo(f"uv 退出码: {proc.returncode}", err=True)
        combined_err = (proc.stderr or "") + (proc.stdout or "")
        _print_copy_hints(uv_exe=uv_exe, stderr_text=combined_err)
        raise typer.Exit(proc.returncode)

    typer.echo("升级完成。")
    typer.echo("请执行 `ziniao quit` 结束旧 daemon，然后新开终端再使用；使用 Cursor MCP 时请重启 MCP。")


def register(app: typer.Typer) -> None:
    """Register ``ziniao update`` on the root Typer app."""
    app.command("update")(update_cli)
