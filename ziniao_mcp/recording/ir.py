"""Recording IR versioning, delay_ms, and disk normalization."""

from __future__ import annotations

import hashlib
from typing import Any

from .locator import normalize_action_for_replay

RECORDING_SCHEMA_VERSION = 2


def parse_emit(s: str) -> list[str]:
    """Parse comma-separated emit targets; defaults to ['nodriver']."""
    parts = [x.strip().lower() for x in (s or "").split(",") if x.strip()]
    if not parts:
        return ["nodriver"]
    valid = {"nodriver", "playwright"}
    return [p for p in parts if p in valid] or ["nodriver"]


def compute_delay_ms(actions: list[dict[str, Any]]) -> None:
    """Mutate actions in place: set delay_ms from mono_ts or timestamp."""
    for i in range(len(actions) - 1, 0, -1):
        cur = actions[i]
        prev = actions[i - 1]
        c = cur.get("mono_ts")
        p = prev.get("mono_ts")
        if c is not None and p is not None:
            cur["delay_ms"] = max(0, int((float(c) - float(p)) * 1000))
        else:
            ct = int(cur.get("timestamp", 0) or 0)
            pt = int(prev.get("timestamp", 0) or 0)
            cur["delay_ms"] = max(0, ct - pt)
    if actions:
        actions[0]["delay_ms"] = 0


def redact_actions_secrets(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replace fill values with placeholder + sha256 prefix."""
    out: list[dict[str, Any]] = []
    for a in actions:
        ac = dict(a)
        if ac.get("type") == "fill" and "value" in ac:
            raw = str(ac.get("value", ""))
            h = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:12]
            ac["value"] = f"<redacted sha256:{h}>"
        out.append(ac)
    return out


_INTERNAL_KEYS = frozenset({
    "mono_ts", "perf_ts", "perfTs", "seq", "target_id", "frameUrl",
})


def actions_for_disk(
    actions: list[dict[str, Any]],
    *,
    record_secrets: bool,
) -> list[dict[str, Any]]:
    """Compute delays while mono_ts is still available, then strip internal fields."""
    compute_delay_ms(actions)
    cleaned: list[dict[str, Any]] = []
    for a in actions:
        ac = {k: v for k, v in a.items() if k not in _INTERNAL_KEYS}
        ac = normalize_action_for_replay(ac)
        cleaned.append(ac)
    if not record_secrets:
        cleaned = redact_actions_secrets(cleaned)
    return cleaned
