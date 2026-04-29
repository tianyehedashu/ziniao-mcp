"""Unit tests for recording → rpa_flow draft conversion."""

from __future__ import annotations

from ziniao_mcp.recording.emit_preset import actions_to_flow_steps, build_rpa_flow_draft


def test_actions_to_flow_steps_maps_click_and_fill() -> None:
    steps = actions_to_flow_steps(
        [
            {"type": "click", "selector": "#go"},
            {"type": "fill", "selector": "#q", "value": "hello"},
        ],
    )
    assert steps[0]["action"] == "click"
    assert steps[1]["action"] == "fill"
    assert steps[1]["value"] == "hello"


def test_build_rpa_flow_draft_meta_draft() -> None:
    doc = build_rpa_flow_draft(name="demo", start_url="https://a/", actions=[])
    assert doc["kind"] == "rpa_flow"
    assert doc["schema_version"] == "rpa/1"
    assert doc["meta"]["draft"] is True
