"""Unit tests for the UI flow runner (``dispatch._flow_run`` and helpers).

Execution tests focus on pure helpers (``_render_step_value``,
``_apply_output_contract``, ``_mask_secrets``) and the validator /
schema wiring.  Full browser-backed E2E belongs in
``tests/integration_test.py`` or the demo preset.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from ziniao_mcp.cli.dispatch import (  # type: ignore[attr-defined]
    _apply_output_contract,
    _mask_secrets,
    _render_step_value,
    _resolve_step_token,
)


# ---------------------------------------------------------------------------
# _mask_secrets
# ---------------------------------------------------------------------------


def test_mask_secrets_replaces_every_occurrence() -> None:
    out = _mask_secrets("oops pw=hunter2; token=abc", ["hunter2", "abc"])
    assert out == "oops pw=***; token=***"


def test_mask_secrets_noop_when_empty() -> None:
    assert _mask_secrets("plain text", []) == "plain text"
    assert _mask_secrets("", ["x"]) == ""


# ---------------------------------------------------------------------------
# _resolve_step_token + _render_step_value
# ---------------------------------------------------------------------------


def test_resolve_step_token_steps_dot_path() -> None:
    ctx = {"steps": {"grab": {"value": "https://dl", "kind": "attribute"}}}
    assert _resolve_step_token("steps.grab.value", ctx) == "https://dl"
    assert _resolve_step_token("steps.grab.kind", ctx) == "attribute"
    assert _resolve_step_token("steps.missing.value", ctx) is None


def test_resolve_step_token_extracted() -> None:
    ctx = {"extracted": {"title": "Hi"}}
    assert _resolve_step_token("extracted.title", ctx) == "Hi"
    assert _resolve_step_token("extracted.absent", ctx) is None


def test_render_step_value_full_match_returns_native_type() -> None:
    ctx = {"steps": {"count": {"value": 42}}, "extracted": {}, "vars": {}}
    out = _render_step_value({"action": "click", "n": "{{steps.count.value}}"}, ctx)
    assert out["n"] == 42


def test_render_step_value_interpolation() -> None:
    ctx = {"extracted": {"id": "X-123"}, "steps": {}, "vars": {}}
    out = _render_step_value("/api/items/{{extracted.id}}/detail", ctx)
    assert out == "/api/items/X-123/detail"


def test_render_step_value_unknown_token_preserved() -> None:
    ctx = {"steps": {}, "extracted": {}, "vars": {}}
    out = _render_step_value("hi {{vars.unknown}} there", ctx)
    assert out == "hi {{vars.unknown}} there"


def test_render_step_value_preserves_simple_var_tokens() -> None:
    """Bare ``{{x}}`` without a dot must NOT be rewritten — those are vars
    handled upstream in ``render_vars``, not here.
    """
    ctx = {"steps": {}, "extracted": {}, "vars": {}}
    out = _render_step_value("hello {{user}}", ctx)
    assert out == "hello {{user}}"


# ---------------------------------------------------------------------------
# _apply_output_contract
# ---------------------------------------------------------------------------


def test_apply_output_contract_flattens_paths() -> None:
    envelope = {
        "extracted": {"download_url": "https://dl"},
        "steps": {"dl": {"saved_path": "/tmp/report.csv"}},
    }
    out = _apply_output_contract(
        {"url": "$.extracted.download_url", "file": "$.steps.dl.saved_path"},
        envelope,
    )
    assert out == {"url": "https://dl", "file": "/tmp/report.csv"}


def test_apply_output_contract_missing_path_returns_none() -> None:
    envelope = {"extracted": {}, "steps": {}}
    out = _apply_output_contract({"x": "$.extracted.not_here"}, envelope)
    assert out == {"x": None}


# ---------------------------------------------------------------------------
# Validator integration via prepare_request (end-to-end schema wiring)
# ---------------------------------------------------------------------------


def test_prepare_request_rejects_invalid_ui_preset(tmp_path: Path) -> None:
    """A ``mode: ui`` preset with a bad action must fail at prepare_request."""
    from ziniao_mcp.sites import prepare_request  # pylint: disable=import-outside-toplevel

    bad = {
        "mode": "ui",
        "vars": {"q": {"type": "str", "required": True}},
        "steps": [{"action": "launch_missiles", "selector": "#x"}],
    }
    pf = tmp_path / "bad.json"
    pf.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="whitelist"):
        prepare_request(file=str(pf), var_values={"q": "v"})


def test_prepare_request_accepts_valid_ui_preset(tmp_path: Path) -> None:
    from ziniao_mcp.sites import prepare_request  # pylint: disable=import-outside-toplevel

    ok = {
        "mode": "ui",
        "vars": {"q": {"type": "str", "required": True}},
        "steps": [
            {"action": "fill", "selector": "#q", "value": "{{q}}"},
            {"action": "extract", "as": "title", "selector": "title", "kind": "text"},
        ],
    }
    pf = tmp_path / "ok.json"
    pf.write_text(json.dumps(ok), encoding="utf-8")
    spec, _plugin = prepare_request(file=str(pf), var_values={"q": "abc"})
    assert spec["mode"] == "ui"
    assert spec["steps"][0]["value"] == "abc"


# ---------------------------------------------------------------------------
# _flow_run — end-to-end with mocked primitives
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flow_run_happy_path_with_extract_and_fetch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Run click → extract → fetch, feeding the extracted URL into the fetch step."""
    from ziniao_mcp.cli import dispatch as d  # pylint: disable=import-outside-toplevel

    clicks: list[str] = []

    async def fake_click(_sm, args):
        clicks.append(args["selector"])
        return {"ok": True, "clicked": args["selector"]}

    async def fake_extract(_sm, step):
        return {"ok": True, "value": "https://dl.example/file.csv", "kind": "attribute"}

    async def fake_inline_fetch(_sm, step):
        out = tmp_path / "report.csv"
        out.write_bytes(b"a,b,c\n")
        return {
            "ok": True,
            "status": 200,
            "body": "a,b,c\n",
            "saved_path": str(out),
        }

    async def fake_navigate(_sm, _args):
        return {"ok": True, "url": "https://site", "title": ""}

    monkeypatch.setattr(d, "_click", fake_click)
    monkeypatch.setattr(d, "_extract_step", fake_extract)
    monkeypatch.setattr(d, "_inline_fetch_step", fake_inline_fetch)
    monkeypatch.setattr(d, "_navigate", fake_navigate)

    sm = type(
        "SM",
        (),
        {
            "get_active_tab": lambda self: type(
                "T",
                (),
                {
                    "target": type("Tg", (), {"url": "about:blank"})(),
                    "sleep": AsyncMock(),
                    "send": AsyncMock(),
                },
            )(),
        },
    )()

    spec = {
        "mode": "ui",
        "steps": [
            {"id": "go", "action": "click", "selector": "button#export"},
            {
                "id": "grab",
                "action": "extract",
                "as": "url",
                "selector": "a.download",
                "kind": "attribute",
                "attr": "href",
            },
            {
                "id": "dl",
                "action": "fetch",
                "url": "{{extracted.url}}",
                "method": "GET",
                "save_body_to": str(tmp_path / "report.csv"),
            },
        ],
        "output_contract": {
            "url": "$.extracted.url",
            "file": "$.steps.dl.saved_path",
        },
    }

    result = await d._flow_run(sm, spec)
    assert result["ok"] is True
    assert clicks == ["button#export"]
    assert result["extracted"]["url"] == "https://dl.example/file.csv"
    assert result["output"]["url"] == "https://dl.example/file.csv"
    assert result["output"]["file"].endswith("report.csv")


@pytest.mark.asyncio
async def test_flow_run_failure_captures_artefacts_and_masks_secrets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from ziniao_mcp.cli import dispatch as d  # pylint: disable=import-outside-toplevel

    async def fake_click(_sm, args):
        return {
            "error": f"Element not found: pw-was-supersecret in DOM {args['selector']}"
        }

    async def fake_screenshot(_sm, _args):
        return {"ok": True, "data": "data:image/png;base64,iVBORw0KGgo="}

    async def fake_snapshot(_sm, _args):
        return {"ok": True, "html": "<html>pw=supersecret</html>"}

    monkeypatch.setattr(d, "_click", fake_click)
    monkeypatch.setattr(d, "_screenshot", fake_screenshot)
    monkeypatch.setattr(d, "_snapshot", fake_snapshot)
    monkeypatch.chdir(tmp_path)

    sm = type(
        "SM",
        (),
        {
            "get_active_tab": lambda self: type(
                "T",
                (),
                {
                    "target": type("Tg", (), {"url": "about:blank"})(),
                    "sleep": AsyncMock(),
                    "send": AsyncMock(),
                },
            )(),
        },
    )()

    spec = {
        "mode": "ui",
        "steps": [{"id": "miss", "action": "click", "selector": "#does-not-exist"}],
        "_ziniao_secret_values": ["supersecret"],
    }
    result = await d._flow_run(sm, spec)

    assert result["ok"] is False
    assert len(result["failures"]) == 1
    failure = result["failures"][0]
    assert failure["step_id"] == "miss"
    assert "supersecret" not in failure["error"]
    assert "***" in failure["error"]
    errors_dir = tmp_path / "exports" / "flow-errors"
    assert errors_dir.exists()
    artefacts = list(errors_dir.iterdir())
    assert any(a.suffix == ".png" for a in artefacts)
    assert any(a.suffix == ".html" for a in artefacts)


@pytest.mark.asyncio
async def test_flow_run_continue_on_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from ziniao_mcp.cli import dispatch as d  # pylint: disable=import-outside-toplevel

    call_count: dict[str, int] = {"click": 0}

    async def fake_click(_sm, _args):
        call_count["click"] += 1
        if call_count["click"] == 1:
            return {"error": "flaky first"}
        return {"ok": True, "clicked": "second"}

    async def fake_screenshot(_sm, _args):
        return {"ok": True, "data": "data:image/png;base64,iVBORw0KGgo="}

    async def fake_snapshot(_sm, _args):
        return {"ok": True, "html": "<html/>"}

    monkeypatch.setattr(d, "_click", fake_click)
    monkeypatch.setattr(d, "_screenshot", fake_screenshot)
    monkeypatch.setattr(d, "_snapshot", fake_snapshot)
    monkeypatch.chdir(tmp_path)

    sm = type(
        "SM",
        (),
        {
            "get_active_tab": lambda self: type(
                "T",
                (),
                {
                    "target": type("Tg", (), {"url": "about:blank"})(),
                    "sleep": AsyncMock(),
                    "send": AsyncMock(),
                },
            )(),
        },
    )()

    spec = {
        "mode": "ui",
        "steps": [
            {
                "id": "a",
                "action": "click",
                "selector": "#first",
                "continue_on_error": True,
            },
            {"id": "b", "action": "click", "selector": "#second"},
        ],
    }
    result = await d._flow_run(sm, spec)
    assert result["ok"] is True
    assert len(result["failures"]) == 1
    assert result["failures"][0]["step_id"] == "a"
    assert result["steps"]["b"].get("clicked") == "second"


# ---------------------------------------------------------------------------
# _insert_text — selector is a *focus prerequisite*; a missing element must
# NOT silently insert text into whatever currently holds focus (regression
# guard: previously the code did `if elem: click` and fell through to CDP
# insertText even when the element was not found).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_insert_text_errors_when_selector_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ziniao_mcp.cli import dispatch as d  # pylint: disable=import-outside-toplevel
    from ziniao_mcp import iframe  # pylint: disable=import-outside-toplevel

    async def fake_find(*_args, **_kwargs):
        return None

    monkeypatch.setattr(iframe, "find_element", fake_find)

    send_mock = AsyncMock()
    tab = type("T", (), {"send": send_mock})()
    sm = type(
        "SM",
        (),
        {
            "get_active_tab": lambda self: tab,
            "get_active_session": lambda self: type("S", (), {})(),
        },
    )()

    result = await d._insert_text(sm, {"text": "s3cret-token", "selector": "#missing"})
    assert "error" in result
    assert "#missing" in result["error"]
    send_mock.assert_not_called()


class _StealthOff:
    """Minimal stand-in for ``SessionManager.stealth_config`` with stealth disabled."""

    enabled = False
    human_behavior = False

    def to_behavior_config(self):  # pragma: no cover - never hit when disabled
        return None


class _StealthOn:
    """Minimal stand-in with ``human_behavior`` enabled."""

    enabled = True
    human_behavior = True

    def to_behavior_config(self):
        from ziniao_mcp.stealth.human_behavior import BehaviorConfig  # pylint: disable=import-outside-toplevel

        return BehaviorConfig()


@pytest.mark.asyncio
async def test_insert_text_without_selector_sends_cdp() -> None:
    """No selector + stealth off = single CDP insertText with full payload."""
    from ziniao_mcp.cli import dispatch as d  # pylint: disable=import-outside-toplevel

    send_mock = AsyncMock()
    tab = type("T", (), {"send": send_mock})()
    sm = type(
        "SM",
        (),
        {
            "get_active_tab": lambda self: tab,
            "stealth_config": _StealthOff(),
        },
    )()

    result = await d._insert_text(sm, {"text": "hello"})
    assert result == {"ok": True, "inserted": "hello"}
    send_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_insert_text_stealth_chunks_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stealth ON: text MUST be split into >=2 ``Input.insertText`` calls so
    the whole secret doesn't land in the DOM in a single frame (behaviour
    analytics red flag).  Exact chunk count is randomised; we only assert
    ``n_calls >= 2`` and that payloads reassemble the input."""
    from ziniao_mcp.cli import dispatch as d  # pylint: disable=import-outside-toplevel

    call_count = {"n": 0}

    async def fake_send(*_args, **_kw):
        call_count["n"] += 1

    tab = type("T", (), {"send": fake_send})()
    sm = type(
        "SM",
        (),
        {
            "get_active_tab": lambda self: tab,
            "stealth_config": _StealthOn(),
        },
    )()

    async def _fast_sleep(_s):
        return None

    monkeypatch.setattr("asyncio.sleep", _fast_sleep)

    payload = "ThisIsALongerPayloadForChunkCheck"
    result = await d._insert_text(sm, {"text": payload})
    assert result["ok"] is True
    assert call_count["n"] >= 2, (
        f"expected chunked insertText (>=2 CDP sends), got {call_count['n']}"
    )
    assert result["inserted"] == payload


# ---------------------------------------------------------------------------
# _capture_failure_artifacts — snapshot HTML must be masked when secrets
# are passed (regression guard: previously only the error message string
# went through _mask_secrets, so resolved password / token values leaked
# into exports/flow-errors/*.html via the raw DOM snapshot).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_capture_failure_artifacts_masks_html_and_err(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from ziniao_mcp.cli import dispatch as d  # pylint: disable=import-outside-toplevel

    secret_val = "pw-leak-xyz-42"

    async def fake_screenshot(_sm, _args):
        return {"ok": True, "data": "data:image/png;base64,iVBORw0KGgo="}

    async def fake_snapshot(_sm, _args):
        html = (
            "<html><body>"
            f"<input type='password' value='{secret_val}'/>"
            "<meta name='csrf' content='x'/>"
            "</body></html>"
        )
        return {"ok": True, "html": html}

    monkeypatch.setattr(d, "_screenshot", fake_screenshot)
    monkeypatch.setattr(d, "_snapshot", fake_snapshot)
    monkeypatch.chdir(tmp_path)

    artefacts = await d._capture_failure_artifacts(
        sm=object(),
        step_id="login",
        error_msg=f"auth failed with {secret_val}",
        on_error={"screenshot": True, "snapshot": True},
        seq=0,
        secrets=[secret_val],
    )

    html_text = Path(artefacts["snapshot_path"]).read_text(encoding="utf-8")
    assert secret_val not in html_text
    assert "***" in html_text

    err_path = Path(artefacts["snapshot_path"]).with_suffix(".err.txt")
    err_text = err_path.read_text(encoding="utf-8")
    assert secret_val not in err_text
    assert "***" in err_text


@pytest.mark.asyncio
async def test_capture_failure_artifacts_no_secrets_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """When no secrets are provided, HTML is written verbatim (back-compat)."""
    from ziniao_mcp.cli import dispatch as d  # pylint: disable=import-outside-toplevel

    async def fake_snapshot(_sm, _args):
        return {"ok": True, "html": "<html><body>hello</body></html>"}

    monkeypatch.setattr(d, "_snapshot", fake_snapshot)
    monkeypatch.chdir(tmp_path)

    artefacts = await d._capture_failure_artifacts(
        sm=object(),
        step_id="s",
        error_msg="oops",
        on_error={"screenshot": False, "snapshot": True},
        seq=0,
    )
    html_text = Path(artefacts["snapshot_path"]).read_text(encoding="utf-8")
    assert html_text == "<html><body>hello</body></html>"


# ---------------------------------------------------------------------------
# _safe_eval_js — regression for nodriver Tab.evaluate leaking raw RemoteObject
#   Bug: nodriver builds ``SerializationOptions(serialization="deep")`` while
#   also passing ``return_by_value=True`` to Chrome. Depending on result shape,
#   Chrome populates ``deep_serialized_value`` but leaves ``value=None``; the
#   library's final branch uses ``if remote_object.value:`` (truthy check) and
#   falls through to ``return remote_object``. Downstream JSON serialisation
#   then crashes or produces ``repr(RemoteObject(...))``.
#
#   These tests exercise the helper in isolation by mocking ``tab.send`` so
#   we don't need a real Chrome. The contract is simple: for any falsy JSON
#   value (``0``, ``""``, ``[]``, ``False``, ``None``) and for deeply nested
#   objects/arrays, the helper MUST return the Python value, never the
#   ``RemoteObject`` wrapper.
# ---------------------------------------------------------------------------


def _make_remote_object(value=None, unserializable=None):
    """Build a stand-in for ``cdp.runtime.RemoteObject`` with just the fields
    ``_safe_eval_js`` reads. Avoids importing the dataclass and accidentally
    coupling the test to nodriver's internal layout."""

    class _RO:
        pass

    ro = _RO()
    ro.value = value
    ro.unserializable_value = unserializable
    return ro


def _tab_with_send(send_coro):
    """Build a minimal tab object whose ``.send`` is bound at instance level,
    avoiding the ``self`` injection that happens when ``async def`` funcs are
    attached via ``type("T", (), {...})``."""
    tab = type("T", (), {})()
    tab.send = send_coro
    return tab


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "returned_value",
    [0, "", False, [], {}, [1, 2, 3], {"quotes": [{"t": "x"}]}, None],
)
async def test_safe_eval_js_returns_value_including_falsy(returned_value) -> None:
    """Falsy JSON scalars / empty collections must survive the round-trip.
    Previously nodriver.Tab.evaluate returned RemoteObject for these cases."""
    from ziniao_mcp.cli import dispatch as d  # pylint: disable=import-outside-toplevel

    ro = _make_remote_object(value=returned_value)

    async def fake_send(_cmd):
        return (ro, None)

    out = await d._safe_eval_js(_tab_with_send(fake_send), "anything")
    assert out == returned_value


@pytest.mark.asyncio
async def test_safe_eval_js_unserializable_fallback() -> None:
    from ziniao_mcp.cli import dispatch as d  # pylint: disable=import-outside-toplevel

    ro = _make_remote_object(value=None, unserializable="NaN")

    async def fake_send(_cmd):
        return (ro, None)

    out = await d._safe_eval_js(_tab_with_send(fake_send), "NaN")
    assert out == "NaN"


@pytest.mark.asyncio
async def test_safe_eval_js_raises_on_exception() -> None:
    from ziniao_mcp.cli import dispatch as d  # pylint: disable=import-outside-toplevel

    class _Err:
        text = "Uncaught ReferenceError: foo is not defined"
        exception = None

    async def fake_send(_cmd):
        return (None, _Err())

    with pytest.raises(RuntimeError) as exc_info:
        await d._safe_eval_js(_tab_with_send(fake_send), "foo")
    assert "ReferenceError" in str(exc_info.value)


@pytest.mark.asyncio
async def test_safe_eval_js_error_never_stringifies_remote_object() -> None:
    """Regression: previously the error branch did
    ``getattr(errors, "exception", "") or str(errors)``, so when
    ``errors.text`` was empty but ``errors.exception`` was a RemoteObject,
    the RemoteObject leaked into the f-string and produced
    ``repr(RemoteObject(...))`` in the message.

    Guard: the raised message MUST NOT contain ``RemoteObject``; the
    ``description`` field of the exception object is the only acceptable
    source of detail, joined with ``text`` via ``": "``.
    """
    from ziniao_mcp.cli import dispatch as d  # pylint: disable=import-outside-toplevel

    class _RemoteObj:
        """Minimal stand-in for cdp.runtime.RemoteObject with a description."""

        description = "TypeError: Cannot read properties of null"

        def __repr__(self) -> str:  # pragma: no cover - fail loud if stringified
            return "RemoteObject(type_='object', subtype='error', ...)"

    class _Err:
        text = ""  # Chrome sometimes leaves this empty for throw-new-Error
        exception = _RemoteObj()

    async def fake_send(_cmd):
        return (None, _Err())

    with pytest.raises(RuntimeError) as exc_info:
        await d._safe_eval_js(_tab_with_send(fake_send), "throw new TypeError(...)")
    msg = str(exc_info.value)
    assert "RemoteObject" not in msg, f"RemoteObject leaked into error: {msg!r}"
    assert "TypeError" in msg


@pytest.mark.asyncio
async def test_run_js_in_context_iframe_is_strict() -> None:
    """``_run_js_in_context`` must raise when an iframe-bound script throws,
    so ``_extract_step`` / ``_eval`` produce the same ``{"error": ...}`` shape
    regardless of whether the realm is the main document or an iframe.

    Regression guard: the original ``eval_in_frame(...)`` silently returned
    None on exception, masking failures from step-level ``on_error``.
    """
    from ziniao_mcp.cli import dispatch as d  # pylint: disable=import-outside-toplevel
    from ziniao_mcp import iframe as iframe_mod  # pylint: disable=import-outside-toplevel

    called = {"strict": None}

    async def fake_eval_in_frame(
        _tab,
        _ctx_id,
        _expr,
        *,
        await_promise=False,
        strict=False,
        **_kw,
    ):
        called["strict"] = strict
        if strict:
            raise RuntimeError("iframe eval failed: TypeError: boom")
        return None

    iframe_ctx = type("IC", (), {"context_id": 42})()
    store = type("S", (), {"iframe_context": iframe_ctx})()
    tab = object()

    import unittest.mock as _mock

    with _mock.patch.object(iframe_mod, "eval_in_frame", fake_eval_in_frame):
        with pytest.raises(RuntimeError) as exc_info:
            await d._run_js_in_context(tab, store, "throw 1")
        assert called["strict"] is True
        assert "TypeError" in str(exc_info.value)


@pytest.mark.asyncio
async def test_extract_eval_step_iframe_failure_becomes_error_dict() -> None:
    """In iframe context, a throwing ``extract kind=eval`` must surface as
    ``{"error": ...}`` (previously: silent ``{"ok": True, "value": None}``)."""
    from ziniao_mcp.cli import dispatch as d  # pylint: disable=import-outside-toplevel
    from ziniao_mcp import iframe as iframe_mod  # pylint: disable=import-outside-toplevel

    async def fake_eval_in_frame(*_a, strict=False, **_kw):
        assert strict is True
        raise RuntimeError("iframe eval failed: boom")

    iframe_ctx = type("IC", (), {"context_id": 1})()
    session = type("S", (), {"iframe_context": iframe_ctx})()
    sm = type(
        "SM",
        (),
        {
            "get_active_tab": lambda self: object(),
            "get_active_session": lambda self: session,
        },
    )()

    import unittest.mock as _mock

    with _mock.patch.object(iframe_mod, "eval_in_frame", fake_eval_in_frame):
        result = await d._extract_step(
            sm,
            {
                "id": "e",
                "action": "extract",
                "kind": "eval",
                "script": "nope",
            },
        )
    assert "error" in result
    assert "boom" in result["error"]


@pytest.mark.asyncio
async def test_extract_eval_step_unwraps_list_of_objects() -> None:
    """End-to-end: ``action: extract kind: eval`` must surface a real Python
    list-of-dicts, not ``repr(RemoteObject(...))``. This is the exact failure
    the user hit on the ``quotes-scrape`` demo before the fix."""
    from ziniao_mcp.cli import dispatch as d  # pylint: disable=import-outside-toplevel

    payload = [
        {"text": "q1", "author": "a1", "tags": ["t1"]},
        {"text": "q2", "author": "a2", "tags": []},
    ]
    ro = _make_remote_object(value=payload)

    async def fake_send(_cmd):
        return (ro, None)

    tab = _tab_with_send(fake_send)
    session = type("S", (), {"iframe_context": None})()
    sm = type(
        "SM",
        (),
        {
            "get_active_tab": lambda self: tab,
            "get_active_session": lambda self: session,
        },
    )()

    result = await d._extract_step(
        sm,
        {
            "id": "quotes",
            "action": "extract",
            "kind": "eval",
            "script": "Array.from(document.querySelectorAll('div.quote'))",
        },
    )
    assert result["ok"] is True
    assert result["value"] == payload
    # sanity: serialisable as JSON (the original bug broke exactly here)
    json.dumps(result["value"])


# ---------------------------------------------------------------------------
# _move_mouse_humanlike — must NOT call tab.evaluate (regression for the
# daemon-hang reported on `ziniao click`/`ziniao hover` against launched
# Chrome). Mouse position is now cached on ``tab._ziniao_last_mouse``.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_move_mouse_humanlike_no_evaluate_roundtrips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ziniao_mcp.stealth import human_behavior as hb  # pylint: disable=import-outside-toplevel

    evaluate_calls = {"n": 0}
    send_calls = {"n": 0}

    async def fake_evaluate(*_a, **_kw):  # pragma: no cover - asserted not called
        evaluate_calls["n"] += 1
        return None

    async def fake_send(_cmd):
        send_calls["n"] += 1

    # Use a non-slotted real class so weakref works (the stealth module caches
    # the last position in a WeakKeyDictionary).
    class _Tab:
        pass

    tab = _Tab()
    tab.evaluate = fake_evaluate
    tab.send = fake_send

    async def _fast_sleep(_s):
        return None

    monkeypatch.setattr("asyncio.sleep", _fast_sleep)

    await hb._move_mouse_humanlike(tab, 100, 200)

    assert evaluate_calls["n"] == 0, (
        "regression: _move_mouse_humanlike must not invoke tab.evaluate — "
        "those calls were the root cause of the daemon hang on launched Chrome."
    )
    assert send_calls["n"] >= 1
    assert hb._MOUSE_POS_CACHE.get(tab) == (100, 200)
    # Regression: must not touch nodriver's Tab attribute namespace
    assert not hasattr(tab, "_ziniao_last_mouse")

    send_calls["n"] = 0
    await hb._move_mouse_humanlike(tab, 300, 400)
    assert hb._MOUSE_POS_CACHE.get(tab) == (300, 400)


def test_mouse_pos_cache_entry_released_when_tab_collected() -> None:
    """Weakref cache must drop entries automatically so long-running daemons
    don't leak one tuple per ever-opened tab."""
    import gc
    from ziniao_mcp.stealth import human_behavior as hb  # pylint: disable=import-outside-toplevel

    class _Tab:
        pass

    tab = _Tab()
    hb._MOUSE_POS_CACHE[tab] = (10.0, 20.0)
    assert hb._MOUSE_POS_CACHE.get(tab) == (10.0, 20.0)

    tab_id = id(tab)
    del tab
    gc.collect()
    # After GC, the weakref should have been cleared.
    assert not any(id(k) == tab_id for k in hb._MOUSE_POS_CACHE.keys())
