"""Recording metadata: resolve which browser session a replay should attach to."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

_logger = logging.getLogger("ziniao-debug")


@dataclass(frozen=True)
class RecordingBrowserContext:
    """Enough information to call SessionManager.connect_store or connect_chrome."""

    session_id: str
    backend_type: str
    cdp_port: int


def resolve_recording_browser_context(
    meta: dict[str, Any],
    state: dict[str, Any],
) -> RecordingBrowserContext | None:
    """Derive attach context from recording JSON + ~/.ziniao/sessions.json snapshot.

    New recordings carry session_id + backend_type + cdp_port. Legacy files may
    only have cdp_port; we match the first state entry (sorted by key) with that port.
    """
    sid = (meta.get("session_id") or meta.get("store_id") or "").strip()
    bt = (meta.get("backend_type") or "").strip().lower()
    port = int(meta.get("cdp_port") or 0)

    if sid and bt in ("ziniao", "chrome"):
        if port <= 0 and isinstance(state.get(sid), dict):
            port = int(state[sid].get("cdp_port") or 0)
        if bt == "chrome" and port <= 0:
            _logger.debug("Recording has chrome backend but no cdp_port; cannot resolve context")
            return None
        return RecordingBrowserContext(session_id=sid, backend_type=bt, cdp_port=port)

    if port <= 0:
        return None

    matches = [
        (k, v)
        for k, v in state.items()
        if isinstance(v, dict) and int(v.get("cdp_port") or 0) == port
    ]
    matches.sort(key=lambda x: x[0])
    if not matches:
        return None
    if len(matches) > 1:
        _logger.debug(
            "Multiple sessions.json keys share cdp_port=%s; using %r (sorted first)",
            port,
            matches[0][0],
        )
    key, info = matches[0]
    btype = (info.get("backend_type") or "ziniao").strip().lower()
    if btype not in ("ziniao", "chrome"):
        btype = "ziniao"
    return RecordingBrowserContext(session_id=key, backend_type=btype, cdp_port=port)
