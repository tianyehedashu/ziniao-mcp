"""Self-update via ``uv tool install`` (PyPI or GitHub). Does not use the daemon.

Design notes
------------
- Windows default (``ziniao update``) writes a temporary ``.cmd`` that runs uv in a
  separate console, then the main process polls a state file and prints the final
  result (success/failure + installed version) in the ORIGINAL terminal.
- The main process NEVER kills processes on the Windows default path.  This fixes
  the historical bug where ``_kill_blocking_*`` would terminate the uv trampoline
  (the Python process's parent shim ``~/.local/bin/ziniao.exe``), which — because
  uv wraps children in a Windows Job Object — took the main Python process down
  with it, so the upgrade never actually started.
- Process targeting uses EXACT paths (``Path.home()/.local/bin/ziniao[.exe]`` and
  ``<uv tool dir>/ziniao/**``).  Same-named executables such as 紫鸟浏览器
  (Ziniao Browser) are guaranteed to be skipped because they live nowhere near
  those uv-managed paths.
"""

from __future__ import annotations

import base64
import json
import os
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import typer

ZINIAO_GIT_URL = "git+https://github.com/tianyehedashu/ziniao-mcp.git@main"

# Windows: START 首个引号参数为控制台标题（任务栏/Alt+Tab 可辨），与常见安装程序一致。
_WIN_UPDATE_CONSOLE_TITLE = "Ziniao CLI - upgrade"

# 主进程 spawn .cmd 后轮询 state 文件的参数。
_SPAWN_WAIT_TIMEOUT_SEC = 180
_SPAWN_POLL_INTERVAL_SEC = 0.8
_PROGRESS_REPORT_EVERY_SEC = 5.0

# Ask the daemon to ``quit`` gracefully before any kill path runs.
# SessionManager.cleanup() 在空闲时 <2s，但在活跃店铺较多 / 录制器 flush 大量数据
# / 远端 CDP 断开慢 的场景下可能明显更久，实测 10s+ 也不罕见。默认给 15s，既不
# 过度阻塞交互升级，又把"优雅退出"这条路径做成真实有效而不是走过场；紧急情况下
# 可通过 ZINIAO_UPDATE_QUIT_TIMEOUT 覆盖（含 0 = 不等直接走强杀）。
_GRACEFUL_QUIT_DEFAULT_TIMEOUT = 15.0
_GRACEFUL_QUIT_POLL_INTERVAL = 0.2
_GRACEFUL_QUIT_SEND_TIMEOUT = 2.0


# ---------------------------------------------------------------------------
# env helpers
# ---------------------------------------------------------------------------


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _windows_update_skip_final_pause() -> bool:
    """非交互/CI 下不在 .cmd 末尾 pause，避免脚本挂死（与 GitHub Actions、通用 CI 约定一致）。"""
    return (
        _env_truthy("ZINIAO_UPDATE_NO_PAUSE")
        or _env_truthy("CI")
        or os.environ.get("GITHUB_ACTIONS", "").strip().lower() == "true"
    )


def _skip_parent_wait() -> bool:
    """True 时主进程 spawn 后立即退出，不轮询 state（CI / 显式环境变量）。"""
    return _env_truthy("ZINIAO_UPDATE_NO_WAIT") or _env_truthy("CI")


# ---------------------------------------------------------------------------
# uv / target paths
# ---------------------------------------------------------------------------


def _uv_tool_dir(uv_exe: str) -> Optional[Path]:
    """Return ``uv tool dir`` absolute path, or ``None`` if uv failed."""
    try:
        proc = subprocess.run(
            [uv_exe, "tool", "dir"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    if not lines:
        return None
    try:
        return Path(lines[-1]).expanduser().resolve()
    except (OSError, ValueError):
        return None


def _normalize_path_str(s: str) -> str:
    """Normalize a path string for matching.

    - Windows: lowercase + replace forward slashes with backslashes.
    - Unix: leave case as-is (paths are case-sensitive).
    Trailing separators are stripped so ``foo\\`` and ``foo`` compare equal.
    """
    if os.name == "nt":
        s = s.replace("/", "\\").lower()
    return s.rstrip("\\/")


def _ziniao_shim_path() -> Path:
    """uv tool install 生成的 CLI shim 的**精确路径**。

    匹配时和 Get-Process 返回的 ``Path`` 字段严格比较（小写不敏感），任何
    不在该绝对路径的同名 ziniao 可执行（例如紫鸟浏览器客户端）都会被跳过。
    """
    home = Path.home()
    name = "ziniao.exe" if os.name == "nt" else "ziniao"
    return home / ".local" / "bin" / name


def _ziniao_tool_dirs(uv_exe: Optional[str]) -> List[Path]:
    """uv 管理下的 ziniao 工具子目录（其下 python.exe、.pyd、daemon 等归属本工具）。

    优先使用 ``uv tool dir`` 的精确结果；失败时 fallback 到几个常见默认位置，
    保证 uv 配置变更或临时不可用时仍能识别文件锁来源。
    """
    dirs: List[Path] = []
    if uv_exe:
        base = _uv_tool_dir(uv_exe)
        if base is not None:
            dirs.append(base / "ziniao")

    home = Path.home()
    if os.name == "nt":
        dirs.append(home / "AppData" / "Roaming" / "uv" / "tools" / "ziniao")
        dirs.append(home / "AppData" / "Local" / "uv" / "tools" / "ziniao")
    else:
        dirs.append(home / ".local" / "share" / "uv" / "tools" / "ziniao")

    seen: Set[str] = set()
    out: List[Path] = []
    for d in dirs:
        key = _normalize_path_str(str(d))
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out


def _path_matches_target(
    path_str: str,
    shim: Path,
    tool_dirs: Iterable[Path],
) -> bool:
    """True iff ``path_str`` is the shim, or lives under one of the tool dirs."""
    if not path_str:
        return False
    norm = _normalize_path_str(path_str)
    if not norm:
        return False
    if norm == _normalize_path_str(str(shim)):
        return True
    sep = "\\" if os.name == "nt" else "/"
    for d in tool_dirs:
        dn = _normalize_path_str(str(d))
        if not dn:
            continue
        if norm == dn:
            return True
        if norm.startswith(dn + sep):
            return True
    return False


# ---------------------------------------------------------------------------
# 自身进程保护：至少包含当前 PID 与直接父 PID（通常就是 uv shim）。
# 实测祖父（PowerShell/cmd）和更上层不会落在 ziniao 匹配路径内，因此无需递归。
# ---------------------------------------------------------------------------


def _self_protected_pids() -> Set[int]:
    pids: Set[int] = {os.getpid()}
    try:
        ppid = os.getppid()
    except (OSError, AttributeError):
        ppid = 0
    if isinstance(ppid, int) and ppid > 0:
        pids.add(ppid)
    return pids


# ---------------------------------------------------------------------------
# 优雅停止 daemon：升级前必走这条路径
# ---------------------------------------------------------------------------


def _graceful_quit_timeout() -> float:
    raw = os.environ.get("ZINIAO_UPDATE_QUIT_TIMEOUT", "").strip()
    if not raw:
        return _GRACEFUL_QUIT_DEFAULT_TIMEOUT
    try:
        val = float(raw)
    except ValueError:
        return _GRACEFUL_QUIT_DEFAULT_TIMEOUT
    # 负值或 0 视作"跳过等待"，与 _skip_parent_wait 语义一致。
    return max(val, 0.0)


def _graceful_stop_daemon(timeout: Optional[float] = None) -> bool:
    """Ask a running daemon to ``quit`` gracefully before the kill path runs.

    Why not reuse ``send_command`` from ``connection``：

    - ``send_command`` 会在没有 daemon 时 fall back 到 ``ensure_daemon`` 拉起一个
      新 daemon，正好是我们不想要的——升级前拉起新 daemon 只为立刻杀掉它，是
      一笔纯浪费且会让新 daemon 的 SessionManager 做一次无意义的初始化。
    - 正常 ``quit`` 的响应与 ``loop.stop()`` 只隔一个 event-loop tick，客户端读
      响应时经常会收到 EOF / RST，必须容忍。

    返回语义：

    - True  — 没有 daemon，或 daemon 在 *timeout* 秒内已退出。
    - False — daemon 仍在运行（未响应 quit，或 quit 返回但未在 *timeout* 内关
              闭 loop）；后续强制终止路径会兜底处理。
    """
    try:
        # 延迟导入避免顶部循环（update_cmd → connection → server → ...）。
        from ..connection import find_daemon  # pylint: disable=import-outside-toplevel
    except ImportError:  # pragma: no cover - should never happen in-tree
        return True

    port = find_daemon()
    if port is None:
        return True

    if timeout is None:
        timeout = _graceful_quit_timeout()

    typer.echo("[ziniao] 检测到运行中的 daemon，正在请它优雅退出 (quit) ...")
    sys.stdout.flush()

    payload = (json.dumps({"command": "quit", "args": {}}) + "\n").encode("utf-8")
    try:
        with socket.create_connection(
            ("127.0.0.1", port), timeout=_GRACEFUL_QUIT_SEND_TIMEOUT,
        ) as sock:
            sock.sendall(payload)
            sock.shutdown(socket.SHUT_WR)
            sock.settimeout(_GRACEFUL_QUIT_SEND_TIMEOUT)
            # 读响应仅为确认 daemon 接受到请求；EOF / RST 都视作正常——
            # daemon 在写完响应后会 call_soon(loop.stop)，随即进入 cleanup。
            try:
                while sock.recv(4096):
                    pass
            except OSError:
                pass
    except OSError as exc:
        typer.echo(
            f"[ziniao] 发送 quit 请求失败 ({exc})；将由强制终止路径兜底。",
            err=True,
        )
        return False

    if timeout <= 0:
        return find_daemon() is None

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if find_daemon() is None:
            typer.echo("[ziniao] daemon 已优雅退出。")
            return True
        time.sleep(_GRACEFUL_QUIT_POLL_INTERVAL)

    typer.echo(
        f"[ziniao] daemon 未在 {timeout:.1f}s 内退出；后续会强制终止残留进程。"
        " 可通过环境变量 ZINIAO_UPDATE_QUIT_TIMEOUT=<秒数> 调整（0=不等直接强杀）。",
        err=True,
    )
    return False


# ---------------------------------------------------------------------------
# argv / help
# ---------------------------------------------------------------------------


def _argv_pypi(uv_exe: str) -> List[str]:
    return [uv_exe, "tool", "install", "ziniao", "--upgrade", "--force", "--reinstall"]


def _argv_git(uv_exe: str) -> List[str]:
    return [uv_exe, "tool", "install", ZINIAO_GIT_URL, "--force", "--reinstall"]


def _format_cmd(argv: List[str]) -> str:
    """Single line for copy-paste (POSIX-style quoting; good enough for docs and bash)."""
    return shlex.join(argv)


# ---------------------------------------------------------------------------
# PS helpers
# ---------------------------------------------------------------------------


def _ps_encoded_command(script: str) -> str:
    """Encode a PowerShell script for ``-EncodedCommand``（规避 cmd 的引号陷阱）。"""
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


# 宽匹配：PS 侧先粗筛候选；Python 侧做精确路径比对，避开同名进程（紫鸟浏览器等）。
_NT_CANDIDATE_PS = (
    "Get-Process -ErrorAction SilentlyContinue | "
    "Where-Object { $_.Path -ne $null -and ("
    "$_.Path -like '*\\.local\\bin\\ziniao.exe' -or "
    "$_.Path -like '*\\uv\\tools\\ziniao\\*' -or "
    "$_.Path -like '*\\uv\\data\\tools\\ziniao\\*'"
    ") } | Select-Object Id, Path | ConvertTo-Json -Compress"
)


def _ps_single_quote(s: str) -> str:
    """Escape a string literal for PowerShell single-quoted form."""
    return s.replace("'", "''")


def _build_nt_kill_ps(
    shim: Path,
    tool_dirs: Iterable[Path],
    protected_pids: Iterable[int],
) -> str:
    """Build a PowerShell script that kills ziniao processes by **exact path**.

    与 Python 侧 ``_path_matches_target`` / ``_self_protected_pids`` 语义一致：

    - 匹配条件：``$_.Path`` 小写化后等于 ``shim`` 或等于/前缀于 ``tool_dirs`` 中的某项；
    - 排除条件：``$_.Id`` 落在 ``protected_pids`` 白名单里。

    所有路径/PID 以 PS 字面量序列化，**不再依赖 wildcard**。这样 CHANGELOG 声称
    的"紫鸟浏览器等同名进程不误杀"保护在 Windows 异步升级路径也成立——只要
    同名进程的绝对路径不等于 shim、且不在 tool_dirs 前缀之下，就一定安全。
    """
    shim_lit = _ps_single_quote(_normalize_path_str(str(shim)))
    dir_lits = ", ".join(
        f"'{_ps_single_quote(_normalize_path_str(str(d)))}'" for d in tool_dirs
    )
    pid_lits = ", ".join(str(int(p)) for p in protected_pids)
    # PS 5 兼容写法：单行用 ';' 拼接，变量全部前置声明避免嵌套作用域问题。
    return (
        f"$shim = '{shim_lit}'; "
        f"$dirs = @({dir_lits}); "
        f"$protected = @({pid_lits}); "
        "Get-Process -ErrorAction SilentlyContinue | "
        "Where-Object { $_.Path -ne $null } | "
        "ForEach-Object { "
        "  if ($protected -contains $_.Id) { return } "
        "  $p = $_.Path.ToLower().Replace('/', '\\').TrimEnd('\\'); "
        "  $hit = ($p -eq $shim); "
        "  if (-not $hit) { "
        "    foreach ($d in $dirs) { "
        "      if ($d -and ($p -eq $d -or $p.StartsWith($d + '\\'))) { $hit = $true; break } "
        "    } "
        "  } "
        "  if ($hit) { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue } "
        "}"
    )


# ---------------------------------------------------------------------------
# NT kill
# ---------------------------------------------------------------------------


def _query_nt_candidate_procs() -> List[Tuple[int, str]]:
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", _NT_CANDIDATE_PS],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []
    if result.returncode != 0:
        return []
    raw = (result.stdout or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return []
    if isinstance(data, dict):
        data = [data]
    out: List[Tuple[int, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        pid = item.get("Id")
        path = item.get("Path") or ""
        if isinstance(pid, int) and pid > 0:
            out.append((pid, path))
    return out


def _kill_blocking_nt(uv_exe: Optional[str] = None) -> List[str]:
    """Kill Windows processes holding ziniao files.

    双重安全：
      - Python 侧按 **精确路径** 过滤（shim 绝对路径 + uv tool 目录前缀），
        任何同名但位置无关的进程（例如 紫鸟浏览器客户端）都不会命中。
      - 排除 ``_self_protected_pids()``：当前 Python + 直接父进程（uv shim），
        避免"杀自己的父进程"导致的 Job-Object 连带终止。
    """
    killed: List[str] = []
    protected = _self_protected_pids()
    shim = _ziniao_shim_path()
    tool_dirs = _ziniao_tool_dirs(uv_exe)

    for pid, path in _query_nt_candidate_procs():
        if pid in protected:
            continue
        if not _path_matches_target(path, shim, tool_dirs):
            continue
        try:
            tk = subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True,
                timeout=5,
                check=False,
            )
            if tk.returncode == 0:
                killed.append(f"PID {pid} ({Path(path).name})")
        except (subprocess.TimeoutExpired, OSError):
            pass

    return killed


# ---------------------------------------------------------------------------
# Unix kill
# ---------------------------------------------------------------------------


def _kill_blocking_unix(uv_exe: Optional[str] = None) -> List[str]:
    killed: List[str] = []
    protected = _self_protected_pids()
    shim = _ziniao_shim_path()
    tool_dirs = _ziniao_tool_dirs(uv_exe)

    try:
        result = subprocess.run(
            ["ps", "-eo", "pid,args"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []
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
        if pid in protected:
            continue

        args_str = parts[1]
        exe = args_str.split()[0] if args_str else ""
        if not _path_matches_target(exe, shim, tool_dirs):
            continue

        try:
            os.kill(pid, signal.SIGTERM)
            killed.append(f"PID {pid} ({Path(exe).name})")
        except OSError:
            pass

    return killed


def _kill_blocking_processes(uv_exe: Optional[str] = None) -> List[str]:
    """Kill processes that lock or use ziniao's uv-managed files.

    Windows: resolves file-lock (error 32) that blocks ``uv tool install``.
    Unix:    stops old-version processes so the new binary takes effect immediately.
    """
    if os.name == "nt":
        return _kill_blocking_nt(uv_exe)
    return _kill_blocking_unix(uv_exe)


# ---------------------------------------------------------------------------
# 文件锁诊断提示（保留老逻辑）
# ---------------------------------------------------------------------------


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
        typer.echo("检测到 Windows 文件占用（错误 32）。请手动排查：", err=True)
        typer.echo("  1. 执行 `ziniao quit`（用过 CLI 自动化时）", err=True)
        typer.echo("  2. 在 Cursor 中暂时禁用 ziniao MCP，或退出 Cursor", err=True)
        typer.echo("  3. 关闭所有可能跑过 ziniao 的终端", err=True)
        typer.echo("  4. 任务管理器中结束残留的 ziniao.exe / python.exe（uv 工具目录相关）", err=True)
        typer.echo("  5. 新开 PowerShell 窗口执行下方命令", err=True)
        typer.echo("", err=True)
    typer.echo("手动执行（PowerShell 推荐，整行复制）：", err=True)
    typer.echo(f'  PyPI: & "{uv_exe}" tool install ziniao --upgrade --force --reinstall', err=True)
    typer.echo(f'  Git:  & "{uv_exe}" tool install {ZINIAO_GIT_URL} --force --reinstall', err=True)
    typer.echo(f"  （Bash/WSL）PyPI: {_format_cmd(_argv_pypi(uv_exe))}", err=True)
    typer.echo(f"  （Bash/WSL）Git:  {_format_cmd(_argv_git(uv_exe))}", err=True)


def _no_uv_message() -> None:
    typer.echo("错误：未在 PATH 中找到 uv。", err=True)
    typer.echo("请先安装 uv：https://docs.astral.sh/uv/", err=True)
    typer.echo("手动执行：", err=True)
    typer.echo(f"  {_format_cmd(_argv_pypi('uv'))}", err=True)
    typer.echo(f"  {_format_cmd(_argv_git('uv'))}", err=True)


# ---------------------------------------------------------------------------
# Windows 异步 .cmd
# ---------------------------------------------------------------------------


def _windows_update_cmd_body(
    *,
    uv_line: str,
    state_path: str,
    no_kill: bool,
    python_for_version: Optional[str],
    kill_ps_script: Optional[str] = None,
) -> str:
    """Inner .cmd content: kill / wait / uv / write-state / verify / pause / self-delete.

    state 文件格式（ASCII，一行一对 ``key=value``）：

        uv_exit_code=<int>
        new_version=<pep440>      # 可选：uv 工具目录中 python.exe 查询成功时写入
        status=success|failed      # 写入该行即视为完成，主进程凭此结束等待

    保证："先写入 tmp，再 ``move /y`` 为最终名"——主进程读到的状态要么完全缺失、
    要么至少包含 status 行，避免读到"撕裂"的半成品。
    """
    lines: List[str] = [
        "@echo off",
        "setlocal ENABLEEXTENSIONS",
        "chcp 65001 >nul",
        f'set "STATE={state_path}"',
        'set "TMPSTATE=%STATE%.tmp"',
    ]

    if no_kill or kill_ps_script is None:
        lines += [
            "echo [ziniao] 已跳过自动终止进程（--no-kill）。",
            "echo [ziniao] 等待约 2 秒以释放 ziniao.exe 占用，然后执行 uv ...",
        ]
    else:
        ps_encoded = _ps_encoded_command(kill_ps_script)
        lines += [
            "echo [ziniao] 正在终止占用文件的进程 (MCP / daemon / CLI) ...",
            f"powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand {ps_encoded}",
            "echo [ziniao] 等待约 2 秒以释放文件占用 ...",
        ]

    lines += [
        "timeout /t 2 /nobreak >nul",
        f"echo [ziniao] 正在执行: {uv_line}",
        uv_line,
        'set "UV_EXIT=%ERRORLEVEL%"',
        'set "ZINIAO_VER="',
    ]

    if python_for_version:
        # importlib.metadata 的单引号需要用 ^' 在 cmd 中转义。
        py_cmd = (
            '"%ZINIAO_PY%" -c "from importlib.metadata import version;'
            "print(version(^'ziniao^'))\" 2^>nul"
        )
        lines += [
            f'set "ZINIAO_PY={python_for_version}"',
            'if exist "%ZINIAO_PY%" (',
            f'  for /f "usebackq tokens=* delims=" %%v in (`{py_cmd}`) do set "ZINIAO_VER=%%v"',
            ")",
        ]

    lines += [
        '> "%TMPSTATE%" echo uv_exit_code=%UV_EXIT%',
        'if defined ZINIAO_VER >> "%TMPSTATE%" echo new_version=%ZINIAO_VER%',
        "if %UV_EXIT%==0 (",
        '  >> "%TMPSTATE%" echo status=success',
        ") else (",
        '  >> "%TMPSTATE%" echo status=failed',
        ")",
        'move /y "%TMPSTATE%" "%STATE%" >nul 2>nul',
        "echo.",
        "if %UV_EXIT%==0 (",
        "  if defined ZINIAO_VER (",
        "    echo [ziniao] 升级完成。当前已安装版本: %ZINIAO_VER%",
        "  ) else (",
        "    echo [ziniao] 升级完成。",
        "  )",
        "  echo [ziniao] 请新开终端使用 ziniao；Cursor MCP 会自动重连。",
        ") else (",
        "  echo [ziniao] uv 退出码: %UV_EXIT%。",
        "  echo [ziniao] 若仍报「文件被占用 (错误 32)」，请关闭占用 ziniao 的所有进程/终端再重试。",
        ")",
    ]

    if _windows_update_skip_final_pause():
        lines += [
            "echo.",
            "echo [ziniao] 非交互环境（CI 等）：跳过 pause，2 秒后关闭。",
            "timeout /t 2 /nobreak >nul",
        ]
    else:
        lines += [
            "echo.",
            "echo [ziniao] 按任意键关闭本窗口 ...",
            "pause >nul",
        ]

    lines += [
        'del "%~f0" 2>nul',
        "endlocal",
        "exit /b %UV_EXIT%",
        "",
    ]
    return "\r\n".join(lines)


def _parse_state(text: str) -> Dict[str, str]:
    kv: Dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            kv[k.strip()] = v.strip()
    return kv


def _wait_for_update_state(
    state_path: Path, timeout_sec: int
) -> Optional[Dict[str, str]]:
    """Poll the state file until ``status`` appears or timeout."""
    deadline = time.monotonic() + timeout_sec
    start = time.monotonic()
    next_report = start + _PROGRESS_REPORT_EVERY_SEC
    while time.monotonic() < deadline:
        try:
            raw = state_path.read_text(encoding="utf-8", errors="replace")
        except (FileNotFoundError, OSError):
            raw = ""
        kv = _parse_state(raw)
        if "status" in kv:
            return kv
        now = time.monotonic()
        if now >= next_report:
            elapsed = int(now - start)
            typer.echo(f"[ziniao] 等待升级窗口完成 ... ({elapsed}s)")
            next_report = now + _PROGRESS_REPORT_EVERY_SEC
        time.sleep(_SPAWN_POLL_INTERVAL_SEC)
    return None


def _windows_spawn_uv_tool_install(
    uv_exe: str, git: bool, *, no_kill: bool = False
) -> None:
    """Avoid Windows exe self-lock: let a new console run uv, and poll its result.

    Behavior:
      1. Build a temporary ``.cmd`` with:
         (a) PowerShell kill of locking processes (unless ``--no-kill``);
         (b) 2-second wait for handle release;
         (c) ``uv tool install …``;
         (d) probe installed version via ``<uv tool dir>/ziniao/Scripts/python.exe``;
         (e) atomically write ``state=success|failed`` to a state file;
         (f) pause (interactive) or timeout (CI) and self-delete.
      2. Spawn it under ``start "<title>" cmd /c …`` (new console, recognizable title).
      3. Main process does NOT kill anything here — doing so from the Python running
         under the uv trampoline would kill our own parent shim, terminating us
         prematurely via the uv Job Object and leaving the upgrade un-started.
      4. Main process polls the state file and prints the final verdict
         (success + new version, or failure + exit code) in the ORIGINAL terminal,
         so the user never has to guess whether the upgrade actually happened.
    """
    argv = _argv_git(uv_exe) if git else _argv_pypi(uv_exe)
    uv_line = subprocess.list2cmdline(argv)

    tmpdir = Path(tempfile.gettempdir())
    token = os.urandom(4).hex()
    state_path = tmpdir / f"ziniao-update-{os.getpid()}-{token}.state"

    python_for_version: Optional[str] = None
    uv_base = _uv_tool_dir(uv_exe)
    if uv_base is not None:
        # uv tool install 默认把 python 放到 <base>/ziniao/Scripts/python.exe
        python_for_version = str(uv_base / "ziniao" / "Scripts" / "python.exe")

    # .cmd 执行时，主 ziniao.exe 已在新窗口启动后退出；protected_pids 只需兜住
    # 新 cmd/powershell 自己——PowerShell 侧 $PID 变量在进程启动后不可用（脚本
    # 中已引用 $protected 白名单）。这里显式传本进程 PID 做额外保险；调用 Popen
    # 之后当前进程会立即 Exit，与 PID 冲撞的概率为 0。
    kill_ps_script: Optional[str] = None
    if not no_kill:
        kill_ps_script = _build_nt_kill_ps(
            shim=_ziniao_shim_path(),
            tool_dirs=_ziniao_tool_dirs(uv_exe),
            protected_pids=_self_protected_pids(),
        )

    script = _windows_update_cmd_body(
        uv_line=uv_line,
        state_path=str(state_path),
        no_kill=no_kill,
        python_for_version=python_for_version,
        kill_ps_script=kill_ps_script,
    )
    fd, path = tempfile.mkstemp(prefix="ziniao-update-", suffix=".cmd", text=False)
    try:
        os.write(fd, script.encode("utf-8"))
    finally:
        os.close(fd)
    bat = Path(path)
    bat_resolved = str(bat.resolve())
    inner = subprocess.list2cmdline(["cmd.exe", "/c", bat_resolved])
    start_cmdline = f'start "{_WIN_UPDATE_CONSOLE_TITLE}" {inner}'

    try:
        subprocess.Popen(  # pylint: disable=consider-using-with
            start_cmdline, shell=True, close_fds=True,
        )
    except OSError as exc:
        typer.echo(f"无法启动升级子进程: {exc}", err=True)
        try:
            bat.unlink(missing_ok=True)
        except OSError:
            pass
        _print_copy_hints(uv_exe=uv_exe)
        raise typer.Exit(1) from exc

    head = (
        "[ziniao] 已跳过自动终止进程（--no-kill），新控制台 2 秒后执行 uv。"
        if no_kill
        else "[ziniao] 升级子窗口已启动（先终止占用进程，2 秒后执行 uv）。"
    )
    typer.echo(head)
    typer.echo(
        f"  升级窗口标题：「{_WIN_UPDATE_CONSOLE_TITLE}」（Alt+Tab 可见 uv 日志）"
    )

    if _skip_parent_wait():
        typer.echo("  [ZINIAO_UPDATE_NO_WAIT/CI] 主进程不等待结果，立即返回。")
        sys.stdout.flush()
        raise typer.Exit(0)

    typer.echo(
        f"  本终端将等待最多 {_SPAWN_WAIT_TIMEOUT_SEC}s 读取升级结果；"
        "Ctrl+C 可立即返回（升级窗口继续运行）。"
    )
    sys.stdout.flush()

    try:
        kv = _wait_for_update_state(state_path, _SPAWN_WAIT_TIMEOUT_SEC)
    except KeyboardInterrupt:
        typer.echo(
            "\n[ziniao] 已中断等待；升级窗口未关闭，请到其中查看结果。",
            err=True,
        )
        raise typer.Exit(130) from None

    if kv is None:
        typer.echo(
            f"[ziniao] 超时（{_SPAWN_WAIT_TIMEOUT_SEC}s）未读到升级结果。"
            " 请查看升级窗口；升级仍在后台进行。",
            err=True,
        )
        raise typer.Exit(0)

    status = kv.get("status", "unknown")
    exit_code_raw = kv.get("uv_exit_code", "")
    new_ver = kv.get("new_version", "")

    if status == "success":
        if new_ver:
            typer.echo(f"[ziniao] 升级完成。当前已安装版本: {new_ver}")
        else:
            typer.echo("[ziniao] 升级完成（uv 返回 0，但版本探测未成功）。")
        typer.echo(
            "[ziniao] 旧 daemon 已在升级前优雅停止；下次 ziniao 命令会自动启动新 daemon。"
        )
        try:
            state_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise typer.Exit(0)

    typer.echo(f"[ziniao] 升级失败（uv 退出码 {exit_code_raw}）。", err=True)
    typer.echo(f"  升级窗口里有完整日志；状态文件：{state_path}", err=True)
    _print_copy_hints(uv_exe=uv_exe)
    try:
        code = int(exit_code_raw)
    except (TypeError, ValueError):
        code = 1
    raise typer.Exit(code)


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


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
            "Run uv in this terminal with live output (default on Windows: new console + "
            "poll state file to print the result here, avoiding exe self-replace error 32)."
        ),
    ),
    no_kill: bool = typer.Option(
        False, "--no-kill",
        help=(
            "Skip FORCE-kill of locking processes (main process + Windows .cmd "
            "PowerShell step). The graceful daemon quit still runs — without it, "
            "uv tool install is almost guaranteed to fail with ERROR 32 "
            "(file in use) because the daemon keeps the installed files open."
        ),
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
                f'"{_WIN_UPDATE_CONSOLE_TITLE}" 独立控制台执行 uv（延迟 2s），'
                "主进程轮询状态文件并在原终端打印升级结果。"
            )
            if no_kill:
                msg += " 使用 --no-kill 时 .cmd 内跳过 PowerShell 终止逻辑。"
            typer.echo(msg)
        else:
            typer.echo("在第二个终端执行上述命令可避免「自替换」顾虑。")
        raise typer.Exit(0)

    try:
        from importlib.metadata import version as _pkg_version
        _cur_ver = _pkg_version("ziniao")
    except Exception:
        _cur_ver = "dev"
    source_label = "GitHub main" if git else "PyPI"
    typer.echo(f"[ziniao] 当前版本: {_cur_ver} | 升级来源: {source_label}")
    typer.echo(f"[ziniao] {line}")
    sys.stdout.flush()

    # 在任何 kill 路径之前先"优雅停 daemon"：让 SessionManager 正常 cleanup
    # （关 CDP、flush 录制器），之后 .cmd / SIGTERM 只处理兜底残留。
    #
    # 注意：--no-kill 的语义是"别强杀"，而非"别让 daemon 退出"。如果这里也
    # 跳过 graceful quit，uv tool install 在 Windows 上几乎必然撞 ERROR 32
    # （daemon 一直持有 <uv tool dir>/ziniao/** 下的 .pyd / python.exe 句柄），
    # 让 --no-kill 变成"必败路径"。因此这里永远尝试优雅退出；拒绝响应的
    # daemon 由后续分支按 --no-kill 决定是否强杀。
    _graceful_stop_daemon()

    # Windows 默认异步：主进程不 kill，.cmd 内 kill（此时主 ziniao.exe 已退出，
    # 不会自杀）。这条分支内部会 Exit，不会回到下方同步路径。
    if os.name == "nt" and not sync:
        _windows_spawn_uv_tool_install(uv_exe, git, no_kill=no_kill)

    # 同步路径（Unix 默认 / Windows --sync）。仍然允许 kill，但 _self_protected_pids()
    # 排除了当前进程与直接父进程，避免 shim 自杀。
    if not no_kill:
        killed = _kill_blocking_processes(uv_exe)
        if killed:
            typer.echo(f"已终止 {len(killed)} 个占用进程：")
            for desc in killed:
                typer.echo(f"  - {desc}")

    typer.echo(f"Running: {line}")
    try:
        if sync:
            # 同步模式不捕获输出，便于看到 uv 实时进度。
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
        _print_copy_hints(uv_exe=uv_exe, stderr_text=err_tail + out_tail)
        raise typer.Exit(proc.returncode)

    typer.echo(
        "升级完成。旧 daemon 已在升级前优雅停止；下次 ziniao 命令会自动启动新 daemon。"
    )


def register(app: typer.Typer) -> None:
    """Register ``ziniao update`` on the root Typer app."""
    app.command("update")(update_cli)
