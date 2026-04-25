"""Passive Chrome: subprocess launch without nodriver; tab open via DevTools HTTP only."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib import error, parse, request

_LOG = logging.getLogger(__name__)


def passive_targets_state_path() -> Path:
    """JSON file for passive tab aliases (separate from SessionManager state)."""
    return Path.home() / ".ziniao" / "passive_targets.json"


def _read_passive_targets_raw() -> dict[str, Any]:
    path = passive_targets_state_path()
    if not path.is_file():
        return {"aliases": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8")) or {"aliases": {}}
    except (OSError, json.JSONDecodeError) as exc:
        # Don't silently nuke history: log loudly so concurrent-write corruption
        # is visible. We still return an empty map so the CLI keeps working.
        _LOG.warning(
            "passive_targets.json unreadable (%s); falling back to empty map. "
            "If this happens after a parallel ``passive-open --save-as``, the "
            "previous aliases may have been lost.",
            exc,
        )
        return {"aliases": {}}


def _write_passive_targets_raw(data: dict[str, Any]) -> None:
    """Atomic write: tmp file + ``os.replace`` so crashed/interleaved writes
    never leave a half-baked JSON that the next read would treat as empty."""
    path = passive_targets_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}.{int(time.time() * 1000)}")
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        # ``os.replace`` consumes the tmp file; only clean up on partial failure.
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def save_passive_target_alias(
    alias: str,
    *,
    port: int,
    target_id: str,
    web_socket_debugger_url: str,
    page_url: str,
) -> None:
    """Persist a passive tab target for ``chrome input --alias``."""
    name = (alias or "").strip()
    if not name:
        return
    data = _read_passive_targets_raw()
    aliases = data.setdefault("aliases", {})
    aliases[name] = {
        "port": port,
        "target_id": target_id,
        "webSocketDebuggerUrl": web_socket_debugger_url,
        "page_url": page_url,
        "updated_at": time.time(),
    }
    _write_passive_targets_raw(data)


def load_passive_target_alias(alias: str) -> dict[str, Any] | None:
    """Return saved target record or None."""
    name = (alias or "").strip()
    if not name:
        return None
    aliases = _read_passive_targets_raw().get("aliases") or {}
    rec = aliases.get(name)
    return dict(rec) if isinstance(rec, dict) else None


def list_passive_target_aliases() -> dict[str, Any]:
    """Return full aliases map for listing."""
    return dict(_read_passive_targets_raw().get("aliases") or {})


def resolve_target_ws_url(port: int, target_id: str, timeout: float = 10.0) -> str:
    """Look up ``webSocketDebuggerUrl`` for a page target id via DevTools HTTP ``/json/list``."""
    tid = (target_id or "").strip()
    if not tid:
        raise ValueError("target_id is required")
    req = request.Request(f"http://127.0.0.1:{port}/json/list")
    with request.urlopen(req, timeout=timeout) as resp:  # nosec B310
        targets: list[Any] = json.loads(resp.read().decode("utf-8"))
    for t in targets:
        if isinstance(t, dict) and t.get("id") == tid:
            ws = str(t.get("webSocketDebuggerUrl") or "")
            if ws:
                return ws
            break
    raise RuntimeError(f"No webSocketDebuggerUrl for target id={tid!r} on port {port}")


def wait_devtools_http(port: int, timeout: float = 10.0) -> None:
    """Wait until Chrome's DevTools HTTP endpoint is reachable."""
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1.0):
                return
        except (OSError, error.URLError) as exc:
            last_error = exc
            time.sleep(0.2)
    raise RuntimeError(
        f"Chrome DevTools HTTP endpoint did not start on port {port}",
    ) from last_error


def launch_passive_chrome(
    *,
    executable_path: str,
    cdp_port: int,
    user_data_dir: str,
    headless: bool,
    url: str,
) -> dict[str, Any]:
    """Launch Chrome without attaching nodriver or injecting stealth scripts."""
    from .session import (  # pylint: disable=import-outside-toplevel
        SessionManager,
        _chrome_user_data_from_env,
        _find_chrome_executable,
        _find_free_port,
    )

    if not executable_path:
        executable_path = _find_chrome_executable()
    if cdp_port <= 0:
        cdp_port = _find_free_port()
    if not user_data_dir:
        user_data_dir = _chrome_user_data_from_env() or str(Path.home() / ".ziniao" / "chrome-passive")
    Path(user_data_dir).mkdir(parents=True, exist_ok=True)

    args = SessionManager._build_chrome_launch_args(
        executable_path=executable_path,
        cdp_port=cdp_port,
        user_data_dir=user_data_dir,
        headless=headless,
        url=url,
    )
    process = subprocess.Popen(  # pylint: disable=consider-using-with
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    wait_devtools_http(cdp_port)
    return {
        "ok": True,
        "mode": "passive",
        "pid": process.pid,
        "cdp_port": cdp_port,
        "user_data_dir": user_data_dir,
        "executable_path": executable_path,
        "attached": False,
        "message": "Chrome launched without ziniao daemon/CDP Runtime attachment.",
    }


def passive_open_devtools_tab(
    port: int,
    url: str,
    timeout: float = 10.0,
    *,
    save_as: str | None = None,
) -> dict[str, Any]:
    """Open a tab through DevTools HTTP without attaching a Runtime client."""
    encoded_url = parse.quote(url, safe=":/?&=")
    endpoint = f"http://127.0.0.1:{port}/json/new?{encoded_url}"
    req = request.Request(endpoint, method="PUT")
    with request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - local CDP endpoint
        payload = json.loads(resp.read().decode("utf-8"))
    ws_url = str(payload.get("webSocketDebuggerUrl") or "")
    page_url = str(payload.get("url", url) or url)
    result: dict[str, Any] = {
        "ok": True,
        "id": payload.get("id", ""),
        "url": page_url,
        "title": payload.get("title", ""),
        "type": payload.get("type", ""),
        "webSocketDebuggerUrl": ws_url,
    }
    if save_as:
        save_passive_target_alias(
            save_as,
            port=port,
            target_id=str(result["id"]),
            web_socket_debugger_url=ws_url,
            page_url=page_url,
        )
        result["saved_as"] = (save_as or "").strip()
    return result
