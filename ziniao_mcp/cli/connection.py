"""Daemon connection layer: find, start, and communicate with the daemon."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

_STATE_DIR = Path.home() / ".ziniao"
_PID_FILE = _STATE_DIR / "daemon.pid"
_DEFAULT_PORT = 19816


def _read_pid_file() -> tuple[int, int] | None:
    """Return (pid, port) from the PID file, or None."""
    if not _PID_FILE.exists():
        return None
    try:
        lines = _PID_FILE.read_text().strip().splitlines()
        if len(lines) >= 2:
            return int(lines[0]), int(lines[1])
    except (ValueError, OSError):
        pass
    return None


def _is_process_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes  # pylint: disable=import-outside-toplevel
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        SYNCHRONIZE = 0x00100000
        handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _is_port_open(port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def find_daemon() -> int | None:
    """Return the daemon TCP port if alive, else None."""
    info = _read_pid_file()
    if not info:
        return None
    pid, port = info
    if _is_process_alive(pid) and _is_port_open(port):
        return port
    # Stale PID file
    try:
        _PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass
    return None


def ensure_daemon(timeout: float = 15.0) -> int:
    """Ensure the daemon is running and return its TCP port."""
    port = find_daemon()
    if port:
        return port

    _STATE_DIR.mkdir(parents=True, exist_ok=True)

    daemon_module = "ziniao_mcp.cli.daemon"
    env = os.environ.copy()
    env["ZINIAO_DAEMON"] = "1"

    if os.name == "nt":
        exe = sys.executable
        pythonw = Path(exe).with_name("pythonw.exe")
        if pythonw.is_file():
            exe = str(pythonw)
        creation_flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
        subprocess.Popen(  # pylint: disable=consider-using-with
            [exe, "-m", daemon_module],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
    else:
        subprocess.Popen(  # pylint: disable=consider-using-with
            [sys.executable, "-m", daemon_module],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        port = find_daemon()
        if port:
            return port
        time.sleep(0.3)

    raise RuntimeError(
        "Failed to start daemon within timeout. "
        "Try running `python -m ziniao_mcp.cli.daemon` manually to check for errors."
    )


def _json_safe(value: Any) -> Any:
    """Convert value to JSON-serializable form; unwrap Typer OptionInfo."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "default"):
        return _json_safe(getattr(value, "default"))
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


_SLOW_COMMANDS = frozenset({
    "click", "fill", "type_text", "hover", "drag", "dblclick",
    "screenshot", "snapshot", "snapshot_enhanced",
    "navigate", "wait", "recorder",
    "launch_chrome", "open_store",
})


def send_command(
    command: str,
    args: dict[str, Any] | None = None,
    target_session: str | None = None,
    timeout: float = 0,
) -> dict[str, Any]:
    """Send a JSON-line command to the daemon and return the response.

    *timeout* = 0 means auto: 120s for slow commands (click/type/screenshot/…),
    60s for everything else.  The user can override via ``--timeout``.
    """
    if timeout <= 0:
        timeout = 120.0 if command in _SLOW_COMMANDS else 60.0

    port = ensure_daemon()
    request = {"command": command, "args": _json_safe(args or {})}
    if target_session:
        request["target_session"] = target_session

    payload = json.dumps(request, ensure_ascii=False) + "\n"

    deadline = time.monotonic() + timeout
    with socket.create_connection(("127.0.0.1", port), timeout=min(timeout, 10)) as sock:
        sock.sendall(payload.encode("utf-8"))
        sock.shutdown(socket.SHUT_WR)

        chunks: list[bytes] = []
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("timed out")
            sock.settimeout(remaining)
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)

    raw = b"".join(chunks).decode("utf-8").strip()
    if not raw:
        return {"error": "Empty response from daemon"}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"error": f"Invalid JSON from daemon: {raw[:500]}"}
