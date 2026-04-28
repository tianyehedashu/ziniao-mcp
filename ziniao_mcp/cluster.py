"""Browser cluster bookkeeping: leases and config in ``~/.ziniao/cluster.json``.

This module does **not** replace :class:`ziniao_mcp.session.SessionManager`; it
persists lightweight metadata for multi-session orchestration and health views.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable

_STATE_DIR = Path.home() / ".ziniao"
CLUSTER_FILE = _STATE_DIR / "cluster.json"
CLUSTER_LOCK = _STATE_DIR / "cluster.lock"


def _acquire_lock() -> int:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(CLUSTER_LOCK), os.O_CREAT | os.O_RDWR)
    if os.name == "nt":
        import msvcrt  # pylint: disable=import-outside-toplevel

        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
    else:
        import fcntl  # pylint: disable=import-outside-toplevel

        fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


def _release_lock(fd: int) -> None:
    try:
        if os.name == "nt":
            import msvcrt  # pylint: disable=import-outside-toplevel

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl  # pylint: disable=import-outside-toplevel

            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _read_locked() -> dict[str, Any]:
    if not CLUSTER_FILE.exists():
        return {"version": 1, "max_concurrent_browsers": 8, "leases": []}
    try:
        data = json.loads(CLUSTER_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "max_concurrent_browsers": 8, "leases": []}
    if not isinstance(data, dict):
        return {"version": 1, "max_concurrent_browsers": 8, "leases": []}
    data.setdefault("version", 1)
    data.setdefault("max_concurrent_browsers", 8)
    if not isinstance(data.get("leases"), list):
        data["leases"] = []
    return data


def _write_locked(data: dict[str, Any]) -> None:
    CLUSTER_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CLUSTER_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CLUSTER_FILE)


def _update_state(updater: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    fd = _acquire_lock()
    try:
        state = _read_locked()
        updater(state)
        _write_locked(state)
        return state
    finally:
        _release_lock(fd)


def prune_expired_leases(state: dict[str, Any]) -> int:
    """Remove expired leases; returns count removed."""
    now = time.time()
    leases = state.get("leases") or []
    if not isinstance(leases, list):
        state["leases"] = []
        return 0
    kept: list[dict[str, Any]] = []
    removed = 0
    for row in leases:
        if not isinstance(row, dict):
            removed += 1
            continue
        exp = float(row.get("expires_at", 0) or 0)
        if exp and exp < now:
            removed += 1
            continue
        kept.append(row)
    state["leases"] = kept
    return removed


def cluster_status() -> dict[str, Any]:
    """Return cluster file state with expired leases pruned."""
    def _mut(s: dict[str, Any]) -> None:
        prune_expired_leases(s)

    return _update_state(_mut)


def acquire_lease(
    *,
    session_id: str,
    ttl_sec: float,
    owner: str = "",
    label: str = "",
) -> dict[str, Any]:
    """Register a lease; returns the lease row including ``lease_id``."""
    if ttl_sec <= 0:
        ttl_sec = 600.0
    lease_id = str(uuid.uuid4())
    now = time.time()
    result: dict[str, Any] = {
        "ok": True,
        "lease_id": lease_id,
        "session_id": session_id,
        "expires_at": now + float(ttl_sec),
    }

    def _mut(s: dict[str, Any]) -> None:
        prune_expired_leases(s)
        leases = s.setdefault("leases", [])
        assert isinstance(leases, list)
        try:
            max_count = int(s.get("max_concurrent_browsers") or 8)
        except (TypeError, ValueError):
            max_count = 8
        if max_count > 0 and len(leases) >= max_count:
            result.clear()
            result.update({
                "ok": False,
                "error": f"cluster lease limit reached: {len(leases)}/{max_count}",
                "max_concurrent_browsers": max_count,
            })
            return
        for existing in leases:
            if isinstance(existing, dict) and existing.get("session_id") == session_id:
                result.clear()
                result.update({
                    "ok": False,
                    "error": f"session already leased: {session_id}",
                    "existing_lease_id": existing.get("lease_id", ""),
                })
                return
        row = {
            "lease_id": lease_id,
            "session_id": session_id,
            "created_at": now,
            "expires_at": now + float(ttl_sec),
            "owner": owner or "",
            "label": label or "",
        }
        leases.append(row)

    _update_state(_mut)
    return result


def release_lease(lease_id: str) -> dict[str, Any]:
    """Remove a lease by id."""
    meta: dict[str, int] = {"released": 0}

    def _mut(s: dict[str, Any]) -> None:
        prune_expired_leases(s)
        leases = s.get("leases") or []
        if not isinstance(leases, list):
            s["leases"] = []
            return
        before = len(leases)
        s["leases"] = [
            x for x in leases
            if not (isinstance(x, dict) and x.get("lease_id") == lease_id)
        ]
        meta["released"] = before - len(s["leases"])

    _update_state(_mut)
    return {"ok": True, "released": meta["released"], "lease_id": lease_id}
