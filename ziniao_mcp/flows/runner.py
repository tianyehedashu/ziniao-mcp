"""RPA / UI flow execution (``flow_run`` daemon command implementation).

``ziniao_mcp.cli.dispatch._flow_run`` delegates here so this module can grow
control-flow, ``kind: rpa_flow`` validation, run directories, and diagnostics
without further bloating ``dispatch.py``.
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import queue
import threading
import textwrap
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2.nativetypes import NativeEnvironment

from ziniao_mcp.flows import policy as flow_policy
from ziniao_mcp.flows.schema import validate_flow_document

_logger = logging.getLogger(__name__)
_JINJA = NativeEnvironment(autoescape=False, enable_async=False)

_MAX_CALL_DEPTH = 4
_MAX_FOR_EACH = 10_000
_MAX_WHILE = 100
_MAX_NEST = 8
_MAX_STEPS = 100_000
_JINJA_TIMEOUT_SEC = 0.10


class FlowBreak(Exception):
    """Propagates ``break`` out of the innermost ``for_each`` / ``while``."""

    pass


class FlowContinue(Exception):
    """Propagates ``continue`` to the innermost loop."""

    pass


class _NoopTab:
    target = type("Target", (), {"url": ""})()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    async def send(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    async def evaluate(self, *_args: Any, **_kwargs: Any) -> Any:
        return None


def _now_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]


async def _jinja_render_bool(
    template_str: str, *, steps: Any, vars_: Any, extracted: Any, run: Any
) -> bool:
    when = template_str.strip()
    if not when:
        return False

    def _sync() -> bool:
        try:
            val = _JINJA.from_string(when).render(
                steps=steps, vars=vars_, extracted=extracted, run=run
            )
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Jinja when/template error: {exc}") from exc
        return bool(val)

    try:
        return await asyncio.wait_for(asyncio.to_thread(_sync), timeout=_JINJA_TIMEOUT_SEC)
    except asyncio.TimeoutError:
        raise ValueError("Jinja expression exceeded timeout.") from None


async def _jinja_render_any(
    template_str: str, *, steps: Any, vars_: Any, extracted: Any, run: Any
) -> Any:
    def _sync() -> Any:
        try:
            return _JINJA.from_string(template_str).render(
                steps=steps, vars=vars_, extracted=extracted, run=run
            )
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Jinja render error: {exc}") from exc

    try:
        return await asyncio.wait_for(asyncio.to_thread(_sync), timeout=_JINJA_TIMEOUT_SEC)
    except asyncio.TimeoutError:
        raise ValueError("Jinja expression exceeded timeout.") from None


def _classify_failure(message: str, action: str | None) -> dict[str, Any]:
    low = message.lower()
    cat = "unknown"
    if "not found" in low or "selector" in low or "element" in low:
        cat = "selector_missing"
    elif "timeout" in low or "timed out" in low:
        cat = "wait_timeout"
    elif "policy" in low or "not allowed" in low or "allowlist" in low:
        cat = "policy_denied"
    elif "max depth" in low or "call depth" in low:
        cat = "call_depth_exceeded"
    elif "iteration" in low or "max_iterations" in low:
        cat = "iteration_limit_exceeded"
    elif "jinja" in low or "template" in low:
        cat = "expression_error"
    return {
        "category": cat,
        "suggestions": [{"kind": "inspect_step", "detail": f"action={action!r}"}],
    }


def _persist_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _mask_for_state(value: Any, secrets: list[str]) -> Any:
    if isinstance(value, str):
        out = value
        for secret in secrets:
            if secret:
                out = out.replace(secret, "***")
        return out
    if isinstance(value, dict):
        return {k: _mask_for_state(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [_mask_for_state(v, secrets) for v in value]
    return value


def _policy_view(policy: dict[str, Any]) -> dict[str, Any]:
    ext = policy.get("external_call") or {}
    http = ext.get("http") or {}
    mcp = ext.get("mcp") or {}
    return {
        "external_call.http.enabled": bool(http.get("enabled", True)),
        "external_call.http.allow_private_network": bool(http.get("allow_private_network", False)),
        "external_call.mcp.enabled": bool(mcp.get("enabled", False)),
        "code_step.enabled": bool((policy.get("code_step") or {}).get("enabled", True)),
    }


def _action_needs_browser(action: str | None) -> bool:
    rpa_no_browser = {
        "set_var",
        "log",
        "assert",
        "code",
        "external_call",
        "read_csv",
        "write_csv",
        "read_json",
        "write_json",
        "read_text",
        "write_text",
        "sleep",
        "break",
        "continue",
        "return",
        "fail",
    }
    return action not in rpa_no_browser


def _steps_need_browser(steps: Any) -> bool:
    if not isinstance(steps, list):
        return False
    for step in steps:
        if not isinstance(step, dict):
            continue
        action = step.get("action")
        if action == "if":
            if _steps_need_browser(step.get("then")) or _steps_need_browser(step.get("else")):
                return True
        elif action in ("for_each", "while", "for_range", "retry"):
            if _steps_need_browser(step.get("do")):
                return True
        elif _action_needs_browser(action):
            return True
    return False


def _step_tree_contains_id(step: dict[str, Any], step_id: str) -> bool:
    if step.get("id") == step_id:
        return True
    for key in ("then", "else", "do"):
        child = step.get(key)
        if isinstance(child, list):
            for nested in child:
                if isinstance(nested, dict) and _step_tree_contains_id(nested, step_id):
                    return True
    return False


def _state_payload(
    *,
    sm: Any,
    args: dict[str, Any],
    ctx: dict[str, Any],
    run_id: str,
    sid: str,
    secrets: list[str],
    policy: dict[str, Any],
) -> dict[str, Any]:
    selector = ctx.get("_last_selector") or ""
    session = _session_stub(sm)
    if selector:
        session["wait_anchors"] = [selector]
    return {
        "run_id": run_id,
        "flow_id": str(args.get("name") or args.get("_ziniao_flow_id") or "flow"),
        "flow_path": str(args.get("_ziniao_flow_path") or ""),
        "current_step": sid,
        "last_ok_step": sid,
        "ctx": {
            "vars": _mask_for_state(ctx["vars"], secrets),
            "extracted": _mask_for_state(ctx["extracted"], secrets),
            "steps": _mask_for_state(
                {k: v for k, v in ctx["steps"].items() if not str(k).startswith("_")},
                secrets,
            ),
        },
        "session": session,
        "policy_view": _policy_view(policy),
        "capabilities_used": list(args.get("_capabilities_used") or []),
    }


async def _handle_rpa_leaf(
    sm: Any,
    step: dict[str, Any],
    ctx: dict[str, Any],
    *,
    policy: dict[str, Any],
    allow_private: bool,
) -> dict[str, Any]:
    """Execute RPA-only leaf steps (not passed to ``_dispatch_flow_step``)."""
    action = step.get("action")
    if action == "sleep":
        ms = int(step.get("ms", step.get("milliseconds", 0)))
        await asyncio.sleep(ms / 1000.0)
        return {"ok": True, "slept_ms": ms}
    if action == "set_var":
        name = step.get("name", "")
        if not name:
            return {"error": "set_var requires 'name'."}
        ctx["vars"][name] = step.get("value")
        return {"ok": True, "name": name}
    if action == "log":
        msg = str(step.get("message", ""))
        lvl = str(step.get("level", "info")).lower()
        log_fn = getattr(_logger, lvl, _logger.info)
        log_fn("[flow] %s", msg)
        return {"ok": True, "logged": True}
    if action == "assert":
        when = step.get("when", "")
        if not when:
            return {"error": "assert requires 'when' (Jinja string)."}
        if isinstance(when, str):
            ok = await _jinja_render_bool(
                when,
                steps=ctx["steps"],
                vars_=ctx["vars"],
                extracted=ctx["extracted"],
                run=ctx.get("_run_meta") or {},
            )
        else:
            ok = bool(when)
        if not ok:
            return {"error": step.get("message") or "assertion failed"}
        return {"ok": True, "asserted": True}
    if action == "code":
        cfg = (policy.get("code_step") or {})
        if not cfg.get("enabled", True):
            return {"error": "code_step disabled by policy."}
        lang = step.get("language", "python")
        if lang not in (cfg.get("language_allowlist") or ["python"]):
            return {"error": f"code language {lang!r} not allowed."}
        script = step.get("script") or ""
        if not script and step.get("script_file"):
            sf = Path(str(step["script_file"]))
            if not flow_policy.allows_local_io_path(sf, policy):
                return {"error": "code script_file path denied by policy."}
            if not sf.is_file():
                return {"error": f"code script_file not found: {sf}"}
            script = sf.read_text(encoding=str(step.get("encoding") or "utf-8"))
        if not script.strip():
            return {"error": "code step requires non-empty 'script'."}
        max_sec = float(cfg.get("max_runtime_seconds", 5))
        max_out = int(cfg.get("max_output_kb", 64)) * 1024

        class _CtxView:
            def __init__(self) -> None:
                self.vars = ctx["vars"]
                self.steps = ctx["steps"]
                self.extracted = ctx["extracted"]
                self.session = sm

            @property
            def tab(self) -> Any:
                return sm.get_active_tab()

        ctx_view = _CtxView()
        builtins_safe = {
            "len": len,
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "dict": dict,
            "list": list,
            "tuple": tuple,
            "set": set,
            "range": range,
            "enumerate": enumerate,
            "isinstance": isinstance,
            "min": min,
            "max": max,
            "sum": sum,
            "any": any,
            "all": all,
            "abs": abs,
            "round": round,
        }
        wrapped = "def __flow_code():\n" + textwrap.indent(script.rstrip(), "    ")
        wrapped += "\n    return None\n__flow_result__ = __flow_code()\n"
        g: dict[str, Any] = {"__builtins__": builtins_safe, "ctx": ctx_view}

        def _run() -> Any:
            loc: dict[str, Any] = {}
            exec(compile(wrapped, "<flow_code>", "exec"), g, loc)  # noqa: S102
            return loc.get("__flow_result__")

        q: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)

        def _target() -> None:
            try:
                q.put(("ok", _run()), block=False)
            except BaseException as exc:  # noqa: BLE001
                q.put(("err", exc), block=False)

        th = threading.Thread(target=_target, name="ziniao-flow-code-step", daemon=True)
        th.start()
        try:
            status, payload = await asyncio.to_thread(q.get, True, max_sec)
        except queue.Empty:
            return {"error": f"code step exceeded {max_sec}s timeout."}
        if status == "err":
            raise payload
        out = payload
        if out is not None:
            ser = json.dumps(out, ensure_ascii=False, default=str)
            if len(ser) > max_out:
                return {"error": "code step output exceeds max_output_kb."}
        return {"ok": True, "value": out}
    if action == "external_call" and step.get("kind") == "http":
        url = str(step.get("url", ""))
        if not flow_policy.allows_http_url(policy, url, allow_private_override=allow_private):
            return {"error": "external_call http blocked by policy or SSRF rules."}
        import httpx  # pylint: disable=import-outside-toplevel

        method = str(step.get("method", "GET")).upper()
        timeout = float(step.get("timeout", 30))
        headers = step.get("headers") or {}
        body = step.get("json") if step.get("json") is not None else step.get("body")
        req_kw: dict[str, Any] = {}
        if isinstance(body, (dict, list)):
            req_kw["json"] = body
        elif body is not None:
            req_kw["content"] = body
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(method, url, headers=headers, **req_kw)
        return {"ok": True, "status": resp.status_code, "text": resp.text[:8192]}
    if action == "external_call" and step.get("kind") == "mcp":
        from ziniao_mcp.flows.mcp_invoke import invoke_mcp_tool  # noqa: PLC0415

        server = str(step.get("server") or "").strip()
        tool = str(step.get("tool") or "").strip()
        arguments = dict(step.get("arguments") or {})
        if not server or not tool:
            return {"error": "external_call mcp requires 'server' and 'tool'."}
        if not flow_policy.allows_mcp_tool(policy, server, tool):
            return {"error": "external_call mcp denied by policy or tool_allowlist."}
        timeout = float(step.get("timeout", 60))
        out = await invoke_mcp_tool(
            policy=policy, server=server, tool=tool, arguments=arguments, timeout=timeout
        )
        if out.get("error"):
            return {"error": str(out["error"])}
        return {"ok": bool(out.get("ok")), **{k: v for k, v in out.items() if k != "error"}}
    if action == "read_json":
        ip = Path(str(step.get("path", "")))
        if not flow_policy.allows_local_io_path(ip, policy):
            return {"error": "read_json path denied by policy."}
        if not ip.is_file():
            return {"error": f"read_json: file not found: {ip}"}
        enc = str(step.get("encoding") or "utf-8")
        try:
            data = json.loads(ip.read_text(encoding=enc))
        except json.JSONDecodeError as exc:
            return {"error": f"read_json invalid JSON: {exc}"}
        return {"ok": True, "value": data}
    if action == "write_json":
        ip = Path(str(step.get("path", "")))
        if not flow_policy.allows_local_io_path(ip, policy):
            return {"error": "write_json path denied by policy."}
        payload = step.get("value")
        if payload is None and step.get("from_var"):
            payload = ctx["vars"].get(step["from_var"])
        if isinstance(payload, str) and payload.lstrip().startswith(("{", "[")):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                pass
        ip.parent.mkdir(parents=True, exist_ok=True)
        ip.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "saved_path": str(ip.resolve())}
    if action == "read_text":
        ip = Path(str(step.get("path", "")))
        if not flow_policy.allows_local_io_path(ip, policy):
            return {"error": "read_text path denied by policy."}
        if not ip.is_file():
            return {"error": f"read_text: file not found: {ip}"}
        enc = str(step.get("encoding") or "utf-8")
        return {"ok": True, "value": ip.read_text(encoding=enc)}
    if action == "write_text":
        ip = Path(str(step.get("path", "")))
        if not flow_policy.allows_local_io_path(ip, policy):
            return {"error": "write_text path denied by policy."}
        text = step.get("text")
        if text is None and step.get("from_var") is not None:
            text = ctx["vars"].get(step["from_var"], "")
        ip.parent.mkdir(parents=True, exist_ok=True)
        ip.write_text(str(text), encoding=str(step.get("encoding") or "utf-8"))
        return {"ok": True, "saved_path": str(ip.resolve())}
    if action == "read_csv":
        path = Path(str(step.get("path", "")))
        if not flow_policy.allows_local_io_path(path, policy):
            return {"error": "read_csv path denied by policy."}
        if not path.is_file():
            return {"error": f"read_csv: file not found: {path}"}
        with path.open(encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        return {"ok": True, "value": rows, "rows": len(rows)}
    if action == "write_csv":
        path = Path(str(step.get("path", "")))
        if not flow_policy.allows_local_io_path(path, policy):
            return {"error": "write_csv path denied by policy."}
        rows = step.get("rows") or ctx["vars"].get(step.get("from_var", ""))
        if not isinstance(rows, list):
            return {"error": "write_csv requires 'rows' list or from_var in ctx.vars."}
        fieldnames = step.get("fieldnames")
        if not fieldnames and rows and isinstance(rows[0], dict):
            fieldnames = list(rows[0].keys())
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(fieldnames or []))
            w.writeheader()
            for r in rows:
                if isinstance(r, dict):
                    w.writerow(r)
        return {"ok": True, "saved_path": str(path.resolve())}
    return {"error": f"unsupported RPA leaf action: {action!r}"}


async def _execute_leaf(
    sm: Any,
    raw_step: dict[str, Any],
    rendered: dict[str, Any],
    ctx: dict[str, Any],
    *,
    policy: dict[str, Any],
    allow_private: bool,
) -> dict[str, Any]:
    from ziniao_mcp.cli.dispatch import _dispatch_flow_step, _FLOW_STEP_ACTIONS  # noqa: PLC0415

    action = rendered.get("action")
    if action in (
        "sleep",
        "set_var",
        "log",
        "assert",
        "code",
        "external_call",
        "read_csv",
        "write_csv",
        "read_json",
        "write_json",
        "read_text",
        "write_text",
    ):
        return await _handle_rpa_leaf(sm, rendered, ctx, policy=policy, allow_private=allow_private)
    if action not in _FLOW_STEP_ACTIONS:
        return {"error": f"unsupported action {action!r}"}
    return await _dispatch_flow_step(sm, rendered, ctx)


async def _run_block(  # noqa: PLR0912, PLR0915
    sm: Any,
    block_steps: list[dict[str, Any]],
    ctx: dict[str, Any],
    args: dict[str, Any],
    *,
    failures: list[dict[str, Any]],
    secrets: list[str],
    on_error: dict[str, Any],
    output_contract: dict[str, Any],
    run_dir: Path,
    run_id: str,
    seq_state: dict[str, int],
    nest: int,
    policy: dict[str, Any],
    allow_private: bool,
) -> bool:
    """Execute a linear block with composite nesting. Return False on hard failure."""
    from ziniao_mcp.cli.dispatch import (  # noqa: PLC0415
        _capture_failure_artifacts,
        _FLOW_STEP_ACTIONS,
        _mask_secrets,
        _render_step_value,
    )

    idx = 0
    while idx < len(block_steps):
        if nest > _MAX_NEST:
            raise ValueError("control-flow nesting exceeds max depth")
        raw_step = block_steps[idx]
        idx += 1
        sid = raw_step.get("id") or f"step_{idx}"
        action = raw_step.get("action")
        seq_state["total"] = seq_state.get("total", 0) + 1
        if seq_state["total"] > _MAX_STEPS:
            raise RuntimeError("flow exceeded max step count")

        resume_from = args.get("_ziniao_resume_from")
        if resume_from and not ctx.get("_resume_active"):
            if sid == resume_from:
                ctx["_resume_active"] = True
            elif _step_tree_contains_id(raw_step, str(resume_from)):
                pass
            else:
                continue

        if args.get("_ziniao_break_at") == sid:
            ctx["_paused"] = {"step_id": sid, "action": action}
            _persist_state(
                run_dir / "state.json",
                _state_payload(
                    sm=sm,
                    args=args,
                    ctx=ctx,
                    run_id=run_id,
                    sid=sid,
                    secrets=secrets,
                    policy=policy,
                ),
            )
            return True

        if action == "break":
            raise FlowBreak
        if action == "continue":
            raise FlowContinue
        if action == "fail":
            raise RuntimeError(raw_step.get("message") or "fail step")
        if action == "return":
            val = raw_step.get("value")
            ctx["_early_return"] = _render_step_value(val, ctx) if val is not None else None
            return True

        if action == "if":
            when = str(raw_step.get("when", ""))
            then_steps = list(raw_step.get("then") or [])
            else_steps = list(raw_step.get("else") or [])
            ok_when = await _jinja_render_bool(
                when,
                steps=ctx["steps"],
                vars_=ctx["vars"],
                extracted=ctx["extracted"],
                run=ctx.get("_run_meta") or {},
            )
            branch = then_steps if ok_when else else_steps
            sub_ok = await _run_block(
                sm,
                branch,
                ctx,
                args,
                failures=failures,
                secrets=secrets,
                on_error=on_error,
                output_contract=output_contract,
                run_dir=run_dir,
                run_id=run_id,
                seq_state=seq_state,
                nest=nest + 1,
                policy=policy,
                allow_private=allow_private,
            )
            if not sub_ok:
                return False
            continue

        if action == "for_each":
            over_t = str(raw_step.get("over", ""))
            items_any = await _jinja_render_any(
                over_t,
                steps=ctx["steps"],
                vars_=ctx["vars"],
                extracted=ctx["extracted"],
                run=ctx.get("_run_meta") or {},
            )
            if not isinstance(items_any, list):
                raise TypeError("for_each 'over' must render to a list")
            items: list[Any] = items_any
            var_name = str(raw_step.get("as", "item"))
            do_steps = list(raw_step.get("do") or [])
            max_it = int(raw_step.get("max_iterations", _MAX_FOR_EACH))
            cont_err = bool(raw_step.get("continue_on_error"))
            for i, item in enumerate(items[:max_it]):
                ctx["vars"][var_name] = item
                try:
                    sub_ok = await _run_block(
                        sm,
                        do_steps,
                        ctx,
                        args,
                        failures=failures,
                        secrets=secrets,
                        on_error=on_error,
                        output_contract=output_contract,
                        run_dir=run_dir,
                        run_id=run_id,
                        seq_state=seq_state,
                        nest=nest + 1,
                        policy=policy,
                        allow_private=allow_private,
                    )
                except FlowContinue:
                    continue
                except FlowBreak:
                    break
                if not sub_ok:
                    if cont_err:
                        continue
                    return False
            continue

        if action == "while":
            when = str(raw_step.get("when", ""))
            do_steps = list(raw_step.get("do") or [])
            max_it = int(raw_step.get("max_iterations", _MAX_WHILE))
            for _ in range(max_it):
                if not await _jinja_render_bool(
                    when,
                    steps=ctx["steps"],
                    vars_=ctx["vars"],
                    extracted=ctx["extracted"],
                    run=ctx.get("_run_meta") or {},
                ):
                    break
                try:
                    sub_ok = await _run_block(
                        sm,
                        do_steps,
                        ctx,
                        args,
                        failures=failures,
                        secrets=secrets,
                        on_error=on_error,
                        output_contract=output_contract,
                        run_dir=run_dir,
                        run_id=run_id,
                        seq_state=seq_state,
                        nest=nest + 1,
                        policy=policy,
                        allow_private=allow_private,
                    )
                except FlowContinue:
                    continue
                except FlowBreak:
                    break
                if not sub_ok:
                    return False
            else:
                raise RuntimeError("while exceeded max_iterations")
            continue

        if action == "for_range":
            start = int(raw_step.get("from", 0))
            end = int(raw_step.get("to", 0))
            inclusive = bool(raw_step.get("inclusive_to"))
            var_name = str(raw_step.get("as", "i"))
            do_steps = list(raw_step.get("do") or [])
            max_span = int(raw_step.get("max_span", _MAX_FOR_EACH))
            if inclusive:
                if end >= start:
                    span = end - start + 1
                    rng = range(start, end + 1)
                else:
                    span = start - end + 1
                    rng = range(start, end - 1, -1)
            elif end >= start:
                span = end - start
                rng = range(start, end)
            else:
                span = start - end
                rng = range(start, end, -1)
            if span > max_span:
                raise RuntimeError(f"for_range span {span} exceeds max_span={max_span}")
            max_it = int(raw_step.get("max_iterations", _MAX_FOR_EACH))
            cont_err = bool(raw_step.get("continue_on_error"))
            for i, val in enumerate(list(rng)[:max_it]):
                ctx["vars"][var_name] = val
                try:
                    sub_ok = await _run_block(
                        sm,
                        do_steps,
                        ctx,
                        args,
                        failures=failures,
                        secrets=secrets,
                        on_error=on_error,
                        output_contract=output_contract,
                        run_dir=run_dir,
                        run_id=run_id,
                        seq_state=seq_state,
                        nest=nest + 1,
                        policy=policy,
                        allow_private=allow_private,
                    )
                except FlowContinue:
                    continue
                except FlowBreak:
                    break
                if not sub_ok:
                    if cont_err:
                        continue
                    return False
            continue

        if action == "retry":
            do_steps = list(raw_step.get("do") or [])
            max_attempts = max(1, int(raw_step.get("max_attempts", 3)))
            delay_ms = int(raw_step.get("delay_ms", 0))
            backoff = str(raw_step.get("backoff", "none")).lower()
            retry_on = set(raw_step.get("on") or [])
            last_ok = False
            attempt_failures: list[dict[str, Any]] = []
            for attempt in range(max_attempts):
                before_failures = len(failures)
                sub_ok = await _run_block(
                    sm,
                    do_steps,
                    ctx,
                    args,
                    failures=failures,
                    secrets=secrets,
                    on_error=on_error,
                    output_contract=output_contract,
                    run_dir=run_dir,
                    run_id=run_id,
                    seq_state=seq_state,
                    nest=nest + 1,
                    policy=policy,
                    allow_private=allow_private,
                )
                new_failures = failures[before_failures:]
                del failures[before_failures:]
                if sub_ok:
                    last_ok = True
                    break
                attempt_failures = new_failures
                diag = ctx.get("_last_diagnostics") or {}
                if retry_on and diag.get("category") not in retry_on:
                    break
                if attempt < max_attempts - 1 and delay_ms > 0:
                    mult = (2**attempt) if backoff == "exponential" else 1
                    await asyncio.sleep(min(delay_ms * mult, 60_000) / 1000.0)
            if not last_ok:
                failures.extend(attempt_failures)
                return False
            continue

        if action == "call_flow":
            depth = int(args.get("_ziniao_call_depth") or 0)
            if depth >= _MAX_CALL_DEPTH:
                raise RuntimeError("call_flow max depth exceeded")
            from ziniao_mcp.sites import prepare_request  # noqa: PLC0415

            raw_path = raw_step.get("path") or raw_step.get("file")
            if not raw_path:
                raise ValueError("call_flow requires 'path' or 'file'")
            rp = _render_step_value(raw_path, ctx)
            base_dir = Path(str(args.get("_ziniao_flow_base_dir") or Path.cwd()))
            pth = Path(str(rp))
            if not pth.is_absolute():
                pth = (base_dir / pth).resolve()
            else:
                pth = pth.resolve()
            if not pth.is_file():
                raise FileNotFoundError(f"call_flow file not found: {pth}")
            with_map = dict(raw_step.get("with") or {})
            rendered_with = _render_step_value(with_map, ctx)
            if not isinstance(rendered_with, dict):
                raise TypeError("call_flow 'with' must be a dict")
            str_with = {k: str(v) for k, v in rendered_with.items()}
            child_spec, _plugin = prepare_request(file=str(pth), var_values=str_with)
            child_args = dict(child_spec)
            child_args["_ziniao_call_depth"] = depth + 1
            child_args["_ziniao_run_id"] = run_id
            child_args["_ziniao_run_dir"] = str(run_dir)
            child_args.setdefault("_ziniao_secret_values", secrets)
            child_args["_ziniao_flow_base_dir"] = str(pth.parent)
            child_envelope = await run_flow(sm, child_args)
            flow_tag = str(pth)
            for f in child_envelope.get("failures") or []:
                merged = dict(f)
                merged.setdefault("call_flow", flow_tag)
                failures.append(merged)
            save_as = raw_step.get("save_as")
            if save_as:
                ctx["steps"][str(save_as)] = {"ok": child_envelope.get("ok"), "value": child_envelope}
            ctx["steps"][sid] = {"ok": child_envelope.get("ok", True), "value": child_envelope}
            if child_envelope.get("ok") is False and not raw_step.get("continue_on_error"):
                return False
            continue

        if action == "call_preset":
            depth = int(args.get("_ziniao_call_depth") or 0)
            if depth >= _MAX_CALL_DEPTH:
                raise RuntimeError("call_preset max depth exceeded")
            from ziniao_mcp.sites import prepare_request  # noqa: PLC0415

            preset_id = str(raw_step.get("preset", ""))
            if not preset_id:
                raise ValueError("call_preset requires 'preset'")
            with_map = dict(raw_step.get("with") or {})
            rendered_with = _render_step_value(with_map, ctx)
            if not isinstance(rendered_with, dict):
                raise TypeError("call_preset 'with' must be a dict")
            str_with = {k: str(v) for k, v in rendered_with.items()}
            child_spec, _plugin = prepare_request(preset=preset_id, var_values=str_with)
            child_args = dict(child_spec)
            child_args["_ziniao_call_depth"] = depth + 1
            child_args["_ziniao_run_id"] = run_id
            child_args["_ziniao_run_dir"] = str(run_dir)
            child_args.setdefault("_ziniao_secret_values", secrets)
            child_args.setdefault("_ziniao_flow_base_dir", args.get("_ziniao_flow_base_dir"))
            child_envelope = await run_flow(sm, child_args)
            for f in child_envelope.get("failures") or []:
                merged = dict(f)
                merged.setdefault("call_preset", preset_id)
                failures.append(merged)
            save_as = raw_step.get("save_as")
            if save_as:
                ctx["steps"][str(save_as)] = {"ok": child_envelope.get("ok"), "value": child_envelope}
            ctx["steps"][sid] = {"ok": child_envelope.get("ok", True), "value": child_envelope}
            if child_envelope.get("ok") is False and not raw_step.get("continue_on_error"):
                return False
            continue

        if action not in _FLOW_STEP_ACTIONS and action not in (
            "sleep",
            "set_var",
            "log",
            "assert",
            "code",
            "external_call",
            "read_csv",
            "write_csv",
            "read_json",
            "write_json",
            "read_text",
            "write_text",
            "call_flow",
        ):
            ctx["steps"][sid] = {"error": f"unsupported action {action!r}"}
            return False

        rendered = _render_step_value(raw_step, ctx)
        if isinstance(rendered, dict) and rendered.get("selector"):
            ctx["_last_selector"] = rendered.get("selector")
        seq_state["n"] = seq_state.get("n", 0) + 1
        retry_cfg = raw_step.get("retry") if isinstance(raw_step.get("retry"), dict) else None
        max_attempts = max(1, int((retry_cfg or {}).get("max_attempts", 1)))
        delay_ms = int((retry_cfg or {}).get("delay_ms", 0))
        backoff = str((retry_cfg or {}).get("backoff", "none")).lower()
        retry_on = set((retry_cfg or {}).get("on") or [])
        last_err: BaseException | None = None
        result: dict[str, Any] | None = None
        for attempt in range(max_attempts):
            try:
                result = await _execute_leaf(
                    sm, raw_step, rendered, ctx, policy=policy, allow_private=allow_private
                )
                if isinstance(result, dict) and result.get("error"):
                    raise RuntimeError(result["error"])
                last_err = None
                break
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                diag = _classify_failure(str(exc), action)
                if retry_on and diag.get("category") not in retry_on:
                    break
                if attempt < max_attempts - 1:
                    if delay_ms > 0:
                        mult = (2**attempt) if backoff == "exponential" else 1
                        await sm.get_active_tab().sleep(min(delay_ms * mult, 60_000) / 1000.0)
                    continue
        if last_err is not None:
            exc = last_err
            err = _mask_secrets(str(exc), secrets)
            _logger.warning("flow_run step %s failed: %s", sid, err)
            artefacts = await _capture_failure_artifacts(
                sm,
                sid,
                err,
                on_error,
                seq=seq_state["n"],
                secrets=secrets,
                artifacts_dir=run_dir,
            )
            failures.append({"step_id": sid, "error": err, "action": action, **artefacts})
            if raw_step.get("continue_on_error"):
                ctx["steps"][sid] = {"error": err, **artefacts}
                continue
            diag = _classify_failure(err, action)
            ctx["_last_diagnostics"] = {**diag, "failed_step_id": sid, "failed_action": action}
            if args.get("_ziniao_on_fail") in ("pdb", "repl"):
                ctx["_last_diagnostics"]["debug_mode"] = args["_ziniao_on_fail"]
                ctx["_last_diagnostics"]["debug_note"] = (
                    "Interactive debugger is represented in RunReport; "
                    "daemon mode does not block on stdin."
                )
            return False

        if result is None:
            return False
        ctx["steps"][sid] = result
        if raw_step.get("save_as"):
            ctx["steps"][str(raw_step["save_as"])] = result
        if action == "extract" and raw_step.get("as"):
            ctx["extracted"][raw_step["as"]] = result.get("value")

        _persist_state(
            run_dir / "state.json",
            _state_payload(
                sm=sm,
                args=args,
                ctx=ctx,
                run_id=run_id,
                sid=sid,
                secrets=secrets,
                policy=policy,
            ),
        )

    return True


def _session_stub(sm: Any) -> dict[str, Any]:
    try:
        tab = sm.get_active_tab()
        url = getattr(getattr(tab, "target", None), "url", "") or ""
    except Exception:  # noqa: BLE001
        url = ""
    try:
        sess = sm.get_active_session()
        kind = getattr(sess, "backend_type", "unknown") or "unknown"
        store_id = getattr(sess, "store_id", "") or ""
        cdp_port = int(getattr(sess, "cdp_port", 0) or 0)
    except Exception:  # noqa: BLE001
        kind = "unknown"
        store_id = ""
        cdp_port = 0
    return {
        "kind": kind,
        "store_id": store_id,
        "cdp_port": cdp_port,
        "active_tab_url": url,
        "active_tab_title": "",
        "wait_anchors": [],
    }


def _same_url_base(left: str, right: str) -> bool:
    return left.split("?", 1)[0].split("#", 1)[0] == right.split("?", 1)[0].split("#", 1)[0]


async def run_flow(sm: Any, args: dict[str, Any]) -> dict[str, Any]:
    """Main entry: same contract as legacy ``dispatch._flow_run``."""
    from nodriver import cdp  # pylint: disable=import-outside-toplevel

    from ziniao_mcp.cli.dispatch import (  # noqa: PLC0415
        _apply_output_contract,
        _inject_flow_vars,
    )

    validate_flow_document(args)
    started_at = datetime.now(timezone.utc)

    steps = args.get("steps") or []
    navigate_url = args.get("navigate_url", "")
    secrets = list(args.get("_ziniao_secret_values") or [])
    on_error = dict(args.get("on_error") or {})
    output_contract = dict(args.get("output_contract") or {})
    flow_vars = dict(args.get("_ziniao_merged_vars") or {})

    if not isinstance(steps, list) or not steps:
        ended_at = datetime.now(timezone.utc)
        duration_ms = int((ended_at - started_at).total_seconds() * 1000)
        return {
            "error": "flow_run requires non-empty 'steps'.",
            "started_at": started_at.isoformat(),
            "ended_at": ended_at.isoformat(),
            "duration_ms": duration_ms,
        }

    run_id = str(args.get("_ziniao_run_id") or _now_run_id())
    run_dir = Path(str(args.get("_ziniao_run_dir") or (Path.home() / ".ziniao" / "runs" / run_id)))
    run_dir.mkdir(parents=True, exist_ok=True)
    policy_path = Path(str(args["_ziniao_policy_path"])) if args.get("_ziniao_policy_path") else None
    policy = flow_policy.load_policy(policy_path)
    policy = flow_policy.merge_policy(policy, args.get("policy") if isinstance(args.get("policy"), dict) else None)
    policy = flow_policy.merge_policy(policy, args.get("_ziniao_policy_override"))
    allow_private = bool(args.get("_ziniao_allow_private_network"))
    if args.get("_ziniao_allow_mcp"):
        policy = flow_policy.merge_policy(
            policy,
            {"external_call": {"mcp": {"enabled": True, "tool_allowlist": ["*"]}}},
        )

    initial_ctx = args.get("_ziniao_initial_ctx") if isinstance(args.get("_ziniao_initial_ctx"), dict) else {}
    replay_session = initial_ctx.get("session") if isinstance(initial_ctx.get("session"), dict) else {}
    if replay_session and hasattr(sm, "attach_from_recording_context"):
        try:
            from ziniao_mcp.recording_context import RecordingBrowserContext  # noqa: PLC0415

            kind = str(replay_session.get("kind") or replay_session.get("backend_type") or "").lower()
            store_id = str(replay_session.get("store_id") or replay_session.get("session_id") or "")
            cdp_port = int(replay_session.get("cdp_port") or 0)
            if kind in ("chrome", "ziniao") and (store_id or cdp_port):
                await sm.attach_from_recording_context(
                    RecordingBrowserContext(
                        session_id=store_id or f"chrome-{cdp_port}",
                        backend_type=kind,
                        cdp_port=cdp_port,
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            if args.get("_ziniao_strict"):
                return {"ok": False, "error": f"resume reconnect failed: {exc}"}
            _logger.warning("resume reconnect failed: %s", exc)
    needs_browser = bool(navigate_url) or _steps_need_browser(steps)
    tab = sm.get_active_tab() if needs_browser else _NoopTab()
    replay_url = str(replay_session.get("active_tab_url") or "")
    if replay_url and needs_browser:
        current_url = getattr(getattr(tab, "target", None), "url", "") or ""
        if current_url and not _same_url_base(current_url, replay_url):
            if args.get("_ziniao_strict"):
                return {
                    "ok": False,
                    "error": "resume URL mismatch",
                    "expected_url": replay_url,
                    "current_url": current_url,
                }
            if args.get("_ziniao_auto_resync"):
                await tab.send(cdp.page.navigate(url=replay_url))
                await tab.sleep(1.0)
        for anchor in list(replay_session.get("wait_anchors") or []):
            if not anchor:
                continue
            try:
                found = await tab.evaluate(
                    "document.querySelector(" + json.dumps(str(anchor)) + ") !== null",
                    return_by_value=True,
                )
                if found is False and args.get("_ziniao_strict"):
                    return {"ok": False, "error": f"resume wait_anchor not found: {anchor}"}
            except Exception as exc:  # noqa: BLE001
                if args.get("_ziniao_strict"):
                    return {"ok": False, "error": f"resume wait_anchor failed: {anchor}: {exc}"}
    if navigate_url:
        force = bool(args.get("force_navigate"))
        current = tab.target.url or ""
        base = navigate_url.split("?")[0].split("#")[0]
        if force or not current.startswith(base):
            await tab.send(cdp.page.navigate(url=navigate_url))
            await tab.sleep(2.0)

    ctx: dict[str, Any] = {
        "steps": dict(((initial_ctx.get("ctx") or {}).get("steps") or {}) if isinstance(initial_ctx.get("ctx"), dict) else {}),
        "extracted": dict(((initial_ctx.get("ctx") or {}).get("extracted") or {}) if isinstance(initial_ctx.get("ctx"), dict) else {}),
        "vars": {**dict(((initial_ctx.get("ctx") or {}).get("vars") or {}) if isinstance(initial_ctx.get("ctx"), dict) else {}), **flow_vars},
        "_run_meta": {"id": run_id, "run_dir": str(run_dir)},
    }
    failures: list[dict[str, Any]] = []

    if needs_browser:
        await _inject_flow_vars(tab, flow_vars)

    seq_state: dict[str, int] = {"n": 0}
    nest = 0
    try:
        ok = await _run_block(
            sm,
            list(steps),
            ctx,
            args,
            failures=failures,
            secrets=secrets,
            on_error=on_error,
            output_contract=output_contract,
            run_dir=run_dir,
            run_id=run_id,
            seq_state=seq_state,
            nest=nest,
            policy=policy,
            allow_private=allow_private,
        )
    except FlowBreak as exc:
        raise RuntimeError("break used outside of a loop") from exc
    except FlowContinue as exc:
        raise RuntimeError("continue used outside of a loop") from exc
    except Exception as exc:  # noqa: BLE001
        ok = False
        err = str(exc)
        failures.append({"step_id": "<flow>", "error": err, "action": "flow"})
        diag = _classify_failure(err, "flow")
        ctx["_last_diagnostics"] = {**diag, "failed_step_id": "<flow>", "failed_action": "flow"}

    ended_at = datetime.now(timezone.utc)
    duration_ms = int((ended_at - started_at).total_seconds() * 1000)
    timing_fields = {
        "started_at": started_at.isoformat(),
        "ended_at": ended_at.isoformat(),
        "duration_ms": duration_ms,
    }

    if not ok:
        rep = {
            "ok": False,
            "steps": ctx["steps"],
            "extracted": ctx["extracted"],
            "failures": failures,
            "run_id": run_id,
            "artifacts_dir": str(run_dir),
            **timing_fields,
        }
        if ctx.get("_last_diagnostics"):
            rep["diagnostics"] = ctx["_last_diagnostics"]
        _persist_state(
            run_dir / "report.json",
            {
                "ok": rep["ok"],
                "run_id": run_id,
                "failures": failures,
                "diagnostics": rep.get("diagnostics"),
                "artifacts_dir": str(run_dir),
                "artifacts": {
                    "dir": str(run_dir),
                    "report_json": str((run_dir / "report.json").resolve()),
                    "state_json": str((run_dir / "state.json").resolve()),
                },
                **timing_fields,
            },
        )
        return rep

    envelope: dict[str, Any] = {
        "ok": True,
        "steps": ctx["steps"],
        "extracted": ctx["extracted"],
        "failures": failures,
        "run_id": run_id,
        "artifacts_dir": str(run_dir),
        **timing_fields,
    }
    if ctx.get("_paused"):
        envelope["paused"] = ctx["_paused"]
    if ctx.get("_early_return") is not None:
        envelope["early_return"] = ctx["_early_return"]
    if output_contract:
        envelope_with_vars = {**envelope, "vars": ctx["vars"]}
        envelope["output"] = _apply_output_contract(output_contract, envelope_with_vars)
    _persist_state(
        run_dir / "report.json",
        {
            **{k: envelope[k] for k in ("ok", "steps", "extracted", "failures", "run_id") if k in envelope},
            "output": envelope.get("output"),
            "artifacts_dir": str(run_dir),
            "artifacts": {
                "dir": str(run_dir),
                "report_json": str((run_dir / "report.json").resolve()),
                "state_json": str((run_dir / "state.json").resolve()),
            },
            **{k: envelope[k] for k in ("started_at", "ended_at", "duration_ms") if k in envelope},
        },
    )
    return envelope


def dry_run_static(doc: dict[str, Any]) -> dict[str, Any]:
    """Validate *doc* without a browser (schema only)."""
    validate_flow_document(doc)
    return {"ok": True, "mode": "dry_run_static", "validated": True}


def _mask_var_schema(vars_block: Any) -> dict[str, Any]:
    """Summarise ``vars`` for explain output (secrets redacted)."""
    if not isinstance(vars_block, dict):
        return {}
    out: dict[str, Any] = {}
    for name, spec in vars_block.items():
        if isinstance(spec, dict) and spec.get("type") == "secret":
            out[str(name)] = {"type": "secret", "preview": "<redacted>"}
        elif isinstance(spec, dict):
            out[str(name)] = {"type": spec.get("type", "any")}
        else:
            out[str(name)] = {"type": "inline"}
    return out


def _plan_walk_steps(
    steps: Any,
    *,
    path: str,
    linear: list[dict[str, Any]],
    external_calls: list[dict[str, Any]],
    code_steps: list[dict[str, Any]],
    call_presets: list[dict[str, Any]],
) -> None:
    if not isinstance(steps, list):
        return
    for idx, raw in enumerate(steps):
        if not isinstance(raw, dict):
            continue
        action = raw.get("action")
        sid = raw.get("id") or f"{action}@{path}[{idx}]"
        p = f"{path}/{idx}:{action}"
        if action in ("if",):
            linear.append({"path": p, "id": sid, "action": "if", "note": "branch (then/else not flattened)"})
            _plan_walk_steps(raw.get("then"), path=p + ".then", linear=linear, external_calls=external_calls, code_steps=code_steps, call_presets=call_presets)
            _plan_walk_steps(raw.get("else"), path=p + ".else", linear=linear, external_calls=external_calls, code_steps=code_steps, call_presets=call_presets)
        elif action in ("for_each", "while", "for_range", "retry"):
            linear.append({"path": p, "id": sid, "action": action, "note": "composite loop"})
            do = raw.get("do")
            if isinstance(do, list):
                _plan_walk_steps(do, path=p + ".do", linear=linear, external_calls=external_calls, code_steps=code_steps, call_presets=call_presets)
        elif action == "external_call" and raw.get("kind") == "http":
            url = str(raw.get("url", ""))
            external_calls.append({"path": p, "id": sid, "method": raw.get("method", "GET"), "url": url[:500]})
            linear.append({"path": p, "id": sid, "action": "external_call", "kind": "http"})
        elif action == "external_call" and raw.get("kind") == "mcp":
            external_calls.append(
                {
                    "path": p,
                    "id": sid,
                    "kind": "mcp",
                    "server": raw.get("server"),
                    "tool": raw.get("tool"),
                },
            )
            linear.append({"path": p, "id": sid, "action": "external_call", "kind": "mcp"})
        elif action == "call_flow":
            linear.append(
                {
                    "path": p,
                    "id": sid,
                    "action": "call_flow",
                    "file": raw.get("path") or raw.get("file"),
                },
            )
        elif action == "code":
            preview = str(raw.get("script", ""))[:120].replace("\n", " ")
            code_steps.append({"path": p, "id": sid, "script_preview": preview + ("…" if len(str(raw.get("script", ""))) > 120 else "")})
            linear.append({"path": p, "id": sid, "action": "code"})
        elif action == "call_preset":
            call_presets.append({"path": p, "id": sid, "preset": raw.get("preset", "")})
            linear.append({"path": p, "id": sid, "action": "call_preset", "preset": raw.get("preset")})
        else:
            linear.append({"path": p, "id": sid, "action": action})


def dry_run_plan(doc: dict[str, Any]) -> dict[str, Any]:
    """Structured explain plan: no browser, secrets masked, lists external/code/preset usage."""
    validate_flow_document(doc)
    linear: list[dict[str, Any]] = []
    external_calls: list[dict[str, Any]] = []
    code_steps: list[dict[str, Any]] = []
    call_presets: list[dict[str, Any]] = []
    _plan_walk_steps(
        doc.get("steps"),
        path="steps",
        linear=linear,
        external_calls=external_calls,
        code_steps=code_steps,
        call_presets=call_presets,
    )
    return {
        "ok": True,
        "mode": "dry_run_plan",
        "kind": doc.get("kind"),
        "schema_version": doc.get("schema_version"),
        "vars_preview": _mask_var_schema(doc.get("vars")),
        "step_outline": linear,
        "external_calls": external_calls,
        "code_steps": code_steps,
        "call_presets": call_presets,
    }


def validate_flow_cli(doc: dict[str, Any]) -> None:
    """CLI helper: raise ``ValueError`` on invalid ``rpa_flow`` documents."""
    validate_flow_document(doc)
