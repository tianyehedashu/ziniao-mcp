"""Self-update via ``uv tool install`` (PyPI or GitHub). Does not use the daemon."""

from __future__ import annotations

import shlex
import shutil
import subprocess
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


def _print_copy_hints() -> None:
    typer.echo("", err=True)
    typer.echo("若升级失败（例如 Windows 文件占用），请关闭其它 ziniao 窗口后重试，或在「另一个终端」执行：", err=True)
    uv = shutil.which("uv") or "uv"
    typer.echo(f"  PyPI: {_format_cmd(_argv_pypi(uv))}", err=True)
    typer.echo(f"  Git:  {_format_cmd(_argv_git(uv))}", err=True)


def _no_uv_message() -> None:
    typer.echo("错误：未在 PATH 中找到 uv。", err=True)
    typer.echo("请先安装 uv：https://docs.astral.sh/uv/", err=True)
    typer.echo("然后手动执行：", err=True)
    typer.echo(f"  {_format_cmd(_argv_pypi('uv'))}", err=True)
    typer.echo(f"  {_format_cmd(_argv_git('uv'))}", err=True)


def update_cli(
    git: bool = typer.Option(
        False, "--git",
        help="从 GitHub 仓库 main 安装最新版（而非 PyPI）。",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="仅打印将执行的命令，不实际运行。",
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
        typer.echo("在第二个终端执行上述命令可避免「自替换」顾虑。")
        raise typer.Exit(0)

    typer.echo(f"Running: {line}")
    try:
        proc = subprocess.run(argv, check=False, stdin=subprocess.DEVNULL)
    except OSError as exc:
        typer.echo(f"无法启动 uv: {exc}", err=True)
        _print_copy_hints()
        raise typer.Exit(1) from exc

    if proc.returncode != 0:
        typer.echo(f"uv 退出码: {proc.returncode}", err=True)
        _print_copy_hints()
        raise typer.Exit(proc.returncode)

    typer.echo("升级完成。")
    typer.echo("请执行 `ziniao quit` 结束旧 daemon，然后新开终端再使用；使用 Cursor MCP 时请重启 MCP。")


def register(app: typer.Typer) -> None:
    """Register ``ziniao update`` on the root Typer app."""
    app.command("update")(update_cli)
