"""Bounded in-memory buffer for recording events (backpressure)."""

from __future__ import annotations

from collections import deque
from typing import Any


class RecordingBuffer:
    """Ring buffer: newest events kept when over capacity; counts dropped pushes."""

    __slots__ = ("_dq", "_maxlen", "dropped")

    def __init__(self, maxlen: int = 10_000) -> None:
        self._maxlen = max(1, int(maxlen))
        self._dq: deque[dict[str, Any]] = deque()
        self.dropped = 0

    def append(self, item: dict[str, Any]) -> None:
        if len(self._dq) >= self._maxlen:
            self._dq.popleft()
            self.dropped += 1
        self._dq.append(item)

    def clear(self) -> list[dict[str, Any]]:
        out = list(self._dq)
        self._dq.clear()
        self.dropped = 0
        return out

    def drain_keep_stats(self) -> tuple[list[dict[str, Any]], int]:
        """Return (events, dropped_count) and reset dropped counter after drain."""
        out = list(self._dq)
        self._dq.clear()
        dropped = self.dropped
        self.dropped = 0
        return out, dropped

    def __len__(self) -> int:
        return len(self._dq)
