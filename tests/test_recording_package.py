"""Unit tests for ziniao_mcp.recording (IR, locator, buffer, parse_emit)."""

from __future__ import annotations

import pytest

from ziniao_mcp.recording.buffer import RecordingBuffer
from ziniao_mcp.recording.ir import actions_for_disk, compute_delay_ms, redact_actions_secrets
from ziniao_mcp.recording.locator import locator_to_css_selector, normalize_action_for_replay
from ziniao_mcp.recording.ir import parse_emit


def test_parse_emit() -> None:
    assert parse_emit("") == ["nodriver"]
    assert parse_emit("nodriver,playwright") == ["nodriver", "playwright"]
    assert parse_emit("unknown") == ["nodriver"]


def test_recording_buffer_overflow() -> None:
    b = RecordingBuffer(maxlen=3)
    b.append({"a": 1})
    b.append({"a": 2})
    b.append({"a": 3})
    b.append({"a": 4})
    assert len(b) == 3
    assert b.dropped >= 1


def test_compute_delay_ms_mono() -> None:
    acts = [
        {"type": "click", "mono_ts": 0.0, "timestamp": 1},
        {"type": "click", "mono_ts": 0.5, "timestamp": 2},
    ]
    compute_delay_ms(acts)
    assert acts[0]["delay_ms"] == 0
    assert acts[1]["delay_ms"] == 500


def test_locator_to_css() -> None:
    assert "[data-testid=" in locator_to_css_selector({"strategy": "testid", "value": "x"})
    s = locator_to_css_selector({"strategy": "attr", "attr": "name", "value": "email"})
    assert "name=" in s


def test_normalize_action_for_replay() -> None:
    a = normalize_action_for_replay({"type": "click", "locator": {"strategy": "testid", "value": "btn"}})
    assert "selector" in a
    assert a["selector"]


def test_actions_for_disk_redact() -> None:
    raw = [{"type": "fill", "selector": "#x", "value": "secret"}]
    out = actions_for_disk(raw, record_secrets=False)
    assert "redacted" in out[0]["value"].lower()
    out2 = actions_for_disk(list(raw), record_secrets=True)
    assert out2[0]["value"] == "secret"


def test_actions_for_disk_uses_mono_ts_for_delay() -> None:
    """Regression: mono_ts must be used for delay before being stripped."""
    raw = [
        {"type": "click", "selector": "#a", "mono_ts": 0.0, "timestamp": 100},
        {"type": "click", "selector": "#b", "mono_ts": 1.2, "timestamp": 200},
    ]
    out = actions_for_disk(raw, record_secrets=True)
    assert out[0]["delay_ms"] == 0
    assert out[1]["delay_ms"] == 1200
    assert "mono_ts" not in out[0]
    assert "mono_ts" not in out[1]


def test_actions_for_disk_strips_internal_fields() -> None:
    raw = [
        {
            "type": "click", "selector": "#btn",
            "mono_ts": 0.1, "perfTs": 12.3, "perf_ts": 0,
            "seq": 5, "target_id": "abc", "frameUrl": "http://x",
            "timestamp": 1000,
        },
    ]
    out = actions_for_disk(raw, record_secrets=True)
    for key in ("mono_ts", "perfTs", "perf_ts", "seq", "target_id", "frameUrl"):
        assert key not in out[0], f"{key} should be stripped"
    assert out[0]["selector"] == "#btn"


def test_playwright_emitter_basic() -> None:
    from ziniao_mcp.recording.emit_playwright import generate_playwright_typescript

    actions = [
        {"type": "click", "selector": "#btn", "locator": {"strategy": "testid", "value": "submit"}, "delay_ms": 0},
        {"type": "fill", "selector": "input", "locator": {"strategy": "aria", "value": "Email"}, "value": "a@b.c", "delay_ms": 200},
    ]
    ts = generate_playwright_typescript(actions, "https://example.com", name="test")
    assert "getByTestId" in ts
    assert "getByLabel" in ts
    assert ".fill(" in ts
    assert ".click()" in ts
    assert "example.com" in ts
