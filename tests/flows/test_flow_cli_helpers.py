"""CLI helper coverage for flow variable files and step lookup."""

from __future__ import annotations

import json
from pathlib import Path

from ziniao_mcp.cli.commands.flow_cmd import (
    _apply_typed_vars,
    _emit_repro,
    _find_step,
    _infer_step_inputs,
    _load_vars_file,
    _step_state_inputs,
    _validate_step_inputs,
)


def test_load_vars_file_json(tmp_path: Path) -> None:
    p = tmp_path / "vars.json"
    p.write_text(json.dumps({"items": [1, 2]}), encoding="utf-8")
    assert _load_vars_file(p) == {"items": [1, 2]}


def test_load_vars_file_csv(tmp_path: Path) -> None:
    p = tmp_path / "vars.csv"
    p.write_text("id,name\n1,a\n", encoding="utf-8")
    assert _load_vars_file(p) == {"rows": [{"id": "1", "name": "a"}]}


def test_apply_typed_vars_loads_file_url(tmp_path: Path) -> None:
    data = tmp_path / "data.json"
    data.write_text(json.dumps({"x": 1}), encoding="utf-8")
    spec = {
        "vars": {"payload": {"type": "json"}},
        "_ziniao_merged_vars": {"payload": f"file://{data}"},
    }
    _apply_typed_vars(spec, {})
    assert spec["_ziniao_merged_vars"]["payload"] == {"x": 1}


def test_find_nested_step() -> None:
    step = _find_step(
        [{"id": "outer", "action": "if", "then": [{"id": "target", "action": "sleep"}]}],
        "target",
    )
    assert step == {"id": "target", "action": "sleep"}


def test_validate_step_inputs_rejects_missing_state() -> None:
    step = {"id": "s", "inputs": ["steps.report.value"]}
    state = {"ctx": {"steps": {}}}
    try:
        _validate_step_inputs(step, state)
    except ValueError as exc:
        assert "missing required inputs" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected missing inputs error")


def test_infer_step_inputs_from_templates() -> None:
    step = {
        "id": "assert_total",
        "action": "assert",
        "when": "{{ steps.fetch.value.total > vars.min_total }}",
        "message": "total={{extracted.total}}",
    }
    assert _infer_step_inputs(step) == [
        "steps.fetch.value.total",
        "vars.min_total",
        "extracted.total",
    ]


def test_step_state_inputs_ignore_plain_var_refs() -> None:
    step = {"id": "fill", "action": "fill", "value": "{{vars.username}}"}
    assert _step_state_inputs(step) == []


def test_step_state_inputs_include_prior_step_refs() -> None:
    step = {"id": "assert", "action": "assert", "when": "{{ steps.login.ok }}"}
    assert _step_state_inputs(step) == ["steps.login.ok"]


def test_validate_step_inputs_accepts_inferred_refs() -> None:
    step = {"id": "assert", "action": "assert", "when": "{{ steps.login.ok }}"}
    state = {"ctx": {"steps": {"login": {"ok": True}}, "vars": {}, "extracted": {}}}
    _validate_step_inputs(step, state)


def test_emit_repro_contains_nodriver_connect(tmp_path: Path, monkeypatch) -> None:
    run_id = "unit-repro"
    base = tmp_path / ".ziniao" / "runs" / run_id
    base.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    (base / "state.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "current_step": "x",
                "session": {"cdp_port": 9222, "active_tab_url": "https://example.com/"},
                "ctx": {},
            },
        ),
        encoding="utf-8",
    )
    (base / "report.json").write_text(json.dumps({"diagnostics": {"category": "x"}}), encoding="utf-8")
    repro = _emit_repro(run_id)
    text = repro.read_text(encoding="utf-8")
    assert "nodriver.Browser" in text
    assert "cdp_port" in text
