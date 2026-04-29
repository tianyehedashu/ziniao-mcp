"""Smoke tests for ``flows.runner`` (control flow + dry-run plan)."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from ziniao_mcp.cli import dispatch as d
from ziniao_mcp.flows.runner import dry_run_plan, dry_run_static, run_flow
from ziniao_mcp.flows.schema import validate_flow_document


@pytest.mark.asyncio
async def test_run_flow_if_branch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(d, "_click", AsyncMock(return_value={"ok": True, "clicked": "yes"}))

    sm = type(
        "SM",
        (),
        {
            "get_active_tab": lambda self: type(
                "T",
                (),
                {
                    "target": type("Tg", (), {"url": "https://example.com/"})(),
                    "sleep": AsyncMock(),
                    "send": AsyncMock(),
                },
            )(),
        },
    )()

    spec = {
        "kind": "rpa_flow",
        "schema_version": "rpa/1",
        "name": "if-test",
        "steps": [
            {"id": "set", "action": "set_var", "name": "flag", "value": True},
            {
                "id": "br",
                "action": "if",
                "when": "{{vars.flag}}",
                "then": [{"id": "c1", "action": "click", "selector": "#ok"}],
                "else": [{"id": "c2", "action": "click", "selector": "#no"}],
            },
        ],
        "_ziniao_run_dir": str(tmp_path / "r"),
    }
    out = await run_flow(sm, spec)
    assert out.get("ok") is True
    assert d._click.await_count == 1
    args = d._click.call_args[0][1]
    assert args["selector"] == "#ok"


@pytest.mark.asyncio
async def test_run_flow_for_each(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    clicks: list[str] = []

    async def _click(sm_, a):
        clicks.append(a["selector"])
        return {"ok": True}

    monkeypatch.setattr(d, "_click", _click)

    sm = type(
        "SM",
        (),
        {
            "get_active_tab": lambda self: type(
                "T",
                (),
                {
                    "target": type("Tg", (), {"url": "https://example.com/"})(),
                    "sleep": AsyncMock(),
                    "send": AsyncMock(),
                },
            )(),
        },
    )()

    spec = {
        "kind": "rpa_flow",
        "schema_version": "rpa/1",
        "steps": [
            {"id": "init", "action": "set_var", "name": "rows", "value": ["a", "b"]},
            {
                "id": "loop",
                "action": "for_each",
                "over": "{{vars.rows}}",
                "as": "x",
                "do": [{"id": "hit", "action": "click", "selector": "{{vars.x}}"}],
            },
        ],
        "_ziniao_run_dir": str(tmp_path / "r2"),
    }
    out = await run_flow(sm, spec)
    assert out.get("ok") is True
    assert clicks == ["a", "b"]


def test_dry_run_plan_masks_secret_var() -> None:
    doc = {
        "kind": "rpa_flow",
        "schema_version": "rpa/1",
        "vars": {"token": {"type": "secret", "source": "env:TOK"}},
        "steps": [
            {
                "id": "ping",
                "action": "external_call",
                "kind": "http",
                "url": "https://example.com/hook",
                "method": "POST",
            },
            {"id": "py", "action": "code", "script": "return 1"},
        ],
    }
    validate_flow_document(doc)
    plan = dry_run_plan(doc)
    assert plan["vars_preview"]["token"]["preview"] == "<redacted>"
    assert any(x.get("action") == "external_call" for x in plan["step_outline"])


def test_dry_run_static_no_op_for_ui_only() -> None:
    doc = {"mode": "ui", "steps": [{"action": "wait", "selector": "body"}]}
    out = dry_run_static(doc)
    assert out["ok"] is True


@pytest.mark.asyncio
async def test_break_at_pauses_before_step(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(d, "_click", AsyncMock(return_value={"ok": True}))
    sm = type(
        "SM",
        (),
        {
            "get_active_tab": lambda self: type(
                "T",
                (),
                {
                    "target": type("Tg", (), {"url": "https://example.com/"})(),
                    "sleep": AsyncMock(),
                    "send": AsyncMock(),
                },
            )(),
        },
    )()
    out = await run_flow(
        sm,
        {
            "kind": "rpa_flow",
            "schema_version": "rpa/1",
            "steps": [{"id": "stop_here", "action": "click", "selector": "#x"}],
            "_ziniao_run_dir": str(tmp_path / "break"),
            "_ziniao_break_at": "stop_here",
        },
    )
    assert out["paused"]["step_id"] == "stop_here"
    assert d._click.await_count == 0


@pytest.mark.asyncio
async def test_resume_from_skips_previous_steps(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    clicks: list[str] = []

    async def _click(_sm, args):
        clicks.append(args["selector"])
        return {"ok": True}

    monkeypatch.setattr(d, "_click", _click)
    sm = type(
        "SM",
        (),
        {
            "get_active_tab": lambda self: type(
                "T",
                (),
                {
                    "target": type("Tg", (), {"url": "https://example.com/"})(),
                    "sleep": AsyncMock(),
                    "send": AsyncMock(),
                },
            )(),
        },
    )()
    out = await run_flow(
        sm,
        {
            "kind": "rpa_flow",
            "schema_version": "rpa/1",
            "steps": [
                {"id": "a", "action": "click", "selector": "#a"},
                {"id": "b", "action": "click", "selector": "#b"},
            ],
            "_ziniao_run_dir": str(tmp_path / "resume"),
            "_ziniao_resume_from": "b",
        },
    )
    assert out["ok"] is True
    assert clicks == ["#b"]


@pytest.mark.asyncio
async def test_resume_from_enters_nested_control_step(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    clicks: list[str] = []

    async def _click(_sm, args):
        clicks.append(args["selector"])
        return {"ok": True}

    monkeypatch.setattr(d, "_click", _click)
    sm = type(
        "SM",
        (),
        {
            "get_active_tab": lambda self: type(
                "T",
                (),
                {
                    "target": type("Tg", (), {"url": "https://example.com/"})(),
                    "sleep": AsyncMock(),
                    "send": AsyncMock(),
                },
            )(),
        },
    )()
    out = await run_flow(
        sm,
        {
            "kind": "rpa_flow",
            "schema_version": "rpa/1",
            "steps": [
                {"id": "a", "action": "click", "selector": "#a"},
                {
                    "id": "outer",
                    "action": "if",
                    "when": True,
                    "then": [
                        {"id": "inner_a", "action": "click", "selector": "#inner-a"},
                        {"id": "inner_b", "action": "click", "selector": "#inner-b"},
                    ],
                },
            ],
            "_ziniao_run_dir": str(tmp_path / "resume-nested"),
            "_ziniao_resume_from": "inner_b",
        },
    )
    assert out["ok"] is True
    assert clicks == ["#inner-b"]


@pytest.mark.asyncio
async def test_code_step_timeout_returns_without_waiting_for_thread(tmp_path: Path) -> None:
    class _BlockingSession:
        def block(self) -> None:
            time.sleep(5)

    out = await run_flow(
        _BlockingSession(),
        {
            "kind": "rpa_flow",
            "schema_version": "rpa/1",
            "policy": {"code_step": {"max_runtime_seconds": 0.01}},
            "steps": [{"id": "block", "action": "code", "script": "ctx.session.block()"}],
            "_ziniao_run_dir": str(tmp_path / "code-timeout"),
        },
    )
    assert out["ok"] is False
    assert "exceeded" in out["failures"][0]["error"]


@pytest.mark.asyncio
async def test_pure_data_sleep_does_not_require_browser(tmp_path: Path) -> None:
    class _NoBrowserSession:
        def get_active_tab(self):
            raise RuntimeError("no browser")

    out = await run_flow(
        _NoBrowserSession(),
        {
            "kind": "rpa_flow",
            "schema_version": "rpa/1",
            "steps": [{"id": "pause", "action": "sleep", "ms": 1}],
            "_ziniao_run_dir": str(tmp_path / "pure-sleep"),
        },
    )
    assert out["ok"] is True
    assert out["steps"]["pause"]["slept_ms"] == 1


@pytest.mark.asyncio
async def test_retry_success_discards_failed_attempt_failures(tmp_path: Path) -> None:
    out = await run_flow(
        object(),
        {
            "kind": "rpa_flow",
            "schema_version": "rpa/1",
            "on_error": {"screenshot": False, "snapshot": False},
            "steps": [
                {
                    "id": "retry_until_ready",
                    "action": "retry",
                    "max_attempts": 2,
                    "do": [
                        {
                            "id": "bump",
                            "action": "code",
                            "script": "ctx.vars['n'] = ctx.vars.get('n', 0) + 1",
                        },
                        {
                            "id": "ready",
                            "action": "assert",
                            "when": "{{ vars.n >= 2 }}",
                            "message": "not ready",
                        },
                    ],
                }
            ],
            "_ziniao_run_dir": str(tmp_path / "retry-clean"),
        },
    )
    assert out["ok"] is True
    assert out["failures"] == []
    assert out["steps"]["ready"]["asserted"] is True


@pytest.mark.asyncio
async def test_replay_strict_fails_when_wait_anchor_missing(tmp_path: Path) -> None:
    class _Tab:
        target = type("Tg", (), {"url": "https://example.com/page"})()

        async def evaluate(self, *_args, **_kwargs):
            return False

        async def sleep(self, *_args, **_kwargs):
            return None

        async def send(self, *_args, **_kwargs):
            return None

    sm = type("SM", (), {"get_active_tab": lambda self: _Tab()})()
    out = await run_flow(
        sm,
        {
            "kind": "rpa_flow",
            "schema_version": "rpa/1",
            "steps": [{"id": "c", "action": "click", "selector": "#x"}],
            "_ziniao_run_dir": str(tmp_path / "anchor"),
            "_ziniao_initial_ctx": {
                "session": {
                    "active_tab_url": "https://example.com/page",
                    "wait_anchors": ["#missing"],
                },
            },
            "_ziniao_strict": True,
        },
    )
    assert out["ok"] is False
    assert "wait_anchor" in out["error"]
