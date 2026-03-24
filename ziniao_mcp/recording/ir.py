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
    # Drag locators are not consumed by replay/codegen; strip for smaller JSON.
    "sourceLocator", "targetLocator",
})


def _interval_ms_between(actions: list[dict[str, Any]], j: int, i: int) -> float | None:
    """Elapsed ms from action j to action i (i > j). None if timing is unknown."""
    if j >= i:
        return None
    aj, ai = actions[j], actions[i]
    mj, mi = aj.get("mono_ts"), ai.get("mono_ts")
    if mj is not None and mi is not None:
        return max(0.0, (float(mi) - float(mj)) * 1000.0)
    tj = int(aj.get("timestamp", 0) or 0)
    ti = int(ai.get("timestamp", 0) or 0)
    if tj > 0 and ti > 0:
        return float(max(0, ti - tj))
    total = 0
    for k in range(j + 1, i + 1):
        total += int(actions[k].get("delay_ms", 0) or 0)
    if total <= 0:
        return None
    return float(total)


def _dedup_dblclick(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove click events that precede a dblclick on the same selector within 500ms.

    Only removes when a reliable interval exists (mono_ts, valid timestamps, or
    positive summed delay_ms). Missing clocks no longer drop arbitrary clicks.
    """
    if len(actions) < 2:
        return actions
    skip: set[int] = set()
    for i, a in enumerate(actions):
        if a.get("type") != "dblclick":
            continue
        sel = a.get("selector", "")
        for j in range(i - 1, max(i - 3, -1), -1):
            prev = actions[j]
            if prev.get("type") != "click" or prev.get("selector") != sel:
                continue
            span = _interval_ms_between(actions, j, i)
            if span is not None and span < 500:
                skip.add(j)
    return [a for idx, a in enumerate(actions) if idx not in skip]


def actions_for_disk(
    actions: list[dict[str, Any]],
    *,
    record_secrets: bool,
) -> list[dict[str, Any]]:
    """Compute delays while mono_ts is still available, then strip internal fields."""
    compute_delay_ms(actions)
    actions = _dedup_dblclick(actions)
    cleaned: list[dict[str, Any]] = []
    for a in actions:
        ac = {k: v for k, v in a.items() if k not in _INTERNAL_KEYS}
        ac = normalize_action_for_replay(ac)
        cleaned.append(ac)
    if not record_secrets:
        cleaned = redact_actions_secrets(cleaned)
    return cleaned
