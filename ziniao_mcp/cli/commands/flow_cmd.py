"""``ziniao flow`` — validate, dry-run, run, and inspect RPA flow documents / runs."""

from __future__ import annotations

import json
import sys
import csv
import re
from pathlib import Path
from typing import List, Optional

import typer
import yaml

from .. import get_json_mode, run_command, run_command_with_default_timeout
from ..help_epilog import GROUP_CLI_EPILOG
from ..output import print_result

app = typer.Typer(
    name="flow",
    help="RPA flow documents (kind: rpa_flow) and UI presets: validate, dry-run, run, list runs.",
    no_args_is_help=True,
    epilog=GROUP_CLI_EPILOG,
)

_CTX_REF_RE = re.compile(r"\b(vars|steps|extracted)\.([A-Za-z_][\w-]*(?:\.[A-Za-z_][\w-]*)*)")


def _parse_var_list(var: Optional[List[str]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for v in var or []:
        if "=" in v:
            k, val = v.split("=", 1)
            out[k.strip()] = val.strip()
    return out


def _load_vars_file(path: Path) -> dict[str, object]:
    suffix = path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    elif suffix == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as fh:
            data = {"rows": list(csv.DictReader(fh))}
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON/YAML object or CSV table.")
    return data


def _merge_native_vars(
    parsed: dict[str, str],
    native: dict[str, object],
    native_out: dict[str, object] | None = None,
) -> None:
    for key, val in native.items():
        if native_out is not None:
            native_out[str(key)] = val
        if isinstance(val, (dict, list)):
            parsed[str(key)] = json.dumps(val, ensure_ascii=False)
        else:
            parsed[str(key)] = str(val)


def _load_typed_var_value(vtype: str, raw: object) -> object:
    if not isinstance(raw, str) or not raw.startswith("file://"):
        return raw
    path = Path(raw[len("file://"):]).expanduser()
    if vtype == "csv":
        with path.open(encoding="utf-8-sig", newline="") as fh:
            return list(csv.DictReader(fh))
    if vtype == "yaml":
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    if vtype == "json":
        return json.loads(path.read_text(encoding="utf-8"))
    return raw


def _apply_typed_vars(spec: dict, native_values: dict[str, object]) -> None:
    defs = spec.get("vars") if isinstance(spec.get("vars"), dict) else {}
    merged = dict(spec.get("_ziniao_merged_vars") or {})
    for name, vdef in defs.items():
        if not isinstance(vdef, dict):
            continue
        vtype = str(vdef.get("type") or "")
        if vtype not in ("csv", "json", "yaml"):
            continue
        if name in native_values:
            merged[name] = native_values[name]
            continue
        raw = merged.get(name)
        try:
            merged[name] = _load_typed_var_value(vtype, raw)
        except (OSError, json.JSONDecodeError, yaml.YAMLError) as exc:
            raise ValueError(f"failed to load var {name!r}: {exc}") from exc
    if native_values:
        merged.update(native_values)
    if merged:
        spec["_ziniao_merged_vars"] = merged


def _read_replay_state(run_id: str) -> dict:
    p = Path.home() / ".ziniao" / "runs" / run_id / "state.json"
    if not p.is_file():
        raise FileNotFoundError(f"state.json not found for run {run_id!r}: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def _find_step(steps: list[dict], step_id: str) -> dict | None:
    for step in steps:
        if not isinstance(step, dict):
            continue
        if step.get("id") == step_id:
            return step
        for key in ("then", "else", "do"):
            child = step.get(key)
            if isinstance(child, list):
                found = _find_step(child, step_id)
                if found:
                    return found
    return None


def _resolve_dotted(root: dict, expr: str) -> object | None:
    cur: object = root
    for part in expr.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _iter_strings(value: object):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)


def _infer_step_inputs(step: dict) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for text in _iter_strings(step):
        for match in _CTX_REF_RE.finditer(text):
            expr = f"{match.group(1)}.{match.group(2)}"
            if expr not in seen:
                found.append(expr)
                seen.add(expr)
    return found


def _step_required_inputs(step: dict, *, include_inferred: bool = True) -> list[str]:
    required: list[str] = []
    seen: set[str] = set()
    for expr in list(step.get("inputs") or []):
        key = expr if isinstance(expr, str) else str(expr)
        if key not in seen:
            required.append(key)
            seen.add(key)
    if include_inferred:
        for expr in _infer_step_inputs(step):
            if expr not in seen:
                required.append(expr)
                seen.add(expr)
    return required


def _step_state_inputs(step: dict) -> list[str]:
    explicit = _step_required_inputs(step, include_inferred=False)
    inferred_state_refs = [
        expr for expr in _infer_step_inputs(step) if expr.startswith(("steps.", "extracted."))
    ]
    out: list[str] = []
    seen: set[str] = set()
    for expr in [*explicit, *inferred_state_refs]:
        if expr not in seen:
            out.append(expr)
            seen.add(expr)
    return out


def _validate_step_inputs(step: dict, state: dict) -> None:
    inputs = _step_required_inputs(step)
    if not inputs:
        return
    ctx = state.get("ctx") if isinstance(state.get("ctx"), dict) else {}
    root = {
        "vars": ctx.get("vars") or {},
        "steps": ctx.get("steps") or {},
        "extracted": ctx.get("extracted") or {},
    }
    missing = [expr for expr in inputs if not isinstance(expr, str) or _resolve_dotted(root, expr) is None]
    if missing:
        raise ValueError(f"state.json missing required inputs for step {step.get('id')!r}: {missing}")


def _emit_repro(run_id: str) -> Path:
    base = Path.home() / ".ziniao" / "runs" / run_id
    state_path = base / "state.json"
    report_path = base / "report.json"
    if not state_path.is_file():
        raise FileNotFoundError(f"state.json not found: {state_path}")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
    flow_path = Path(str(state.get("flow_path") or ""))
    flow_doc = {}
    if flow_path.is_file():
        try:
            flow_doc = json.loads(flow_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            flow_doc = {}
    repro = base / "repro.py"
    repro.write_text(
        "# Auto-generated by `ziniao flow diagnose --emit nodriver`.\n"
        "import asyncio\n"
        "import json\n\n"
        f"STATE = json.loads({json.dumps(json.dumps(state, ensure_ascii=False))!r})\n"
        f"REPORT = json.loads({json.dumps(json.dumps(report, ensure_ascii=False))!r})\n\n"
        f"FLOW = json.loads({json.dumps(json.dumps(flow_doc, ensure_ascii=False))!r})\n\n"
        "def find_step(steps, step_id):\n"
        "    for step in steps or []:\n"
        "        if not isinstance(step, dict):\n"
        "            continue\n"
        "        if step.get('id') == step_id:\n"
        "            return step\n"
        "        for key in ('then', 'else', 'do'):\n"
        "            found = find_step(step.get(key), step_id)\n"
        "            if found:\n"
        "                return found\n"
        "    return None\n\n"
        "async def run_step(tab, step):\n"
        "    action = step.get('action')\n"
        "    selector = step.get('selector') or 'body'\n"
        "    if action == 'click':\n"
        "        elem = await tab.select(selector, timeout=10)\n"
        "        if elem:\n"
        "            await elem.mouse_click()\n"
        "    elif action == 'fill':\n"
        "        elem = await tab.select(selector, timeout=10)\n"
        "        if elem:\n"
        "            await elem.mouse_click()\n"
        "            await elem.clear_input()\n"
        "            await elem.send_keys(str(step.get('value', '')))\n"
        "    elif action == 'eval':\n"
        "        print(await tab.evaluate(step.get('script') or 'undefined'))\n"
        "    elif action == 'extract':\n"
        "        js = \"(() => { const el = document.querySelector(\" + json.dumps(selector) + \"); return el ? (el.innerText || el.textContent || '') : null; })()\"\n"
        "        print('extract:', await tab.evaluate(js))\n"
        "    else:\n"
        "        print('No direct repro handler for action:', action, 'step:', step)\n\n"
        "async def main():\n"
        "    print('run_id:', STATE.get('run_id'))\n"
        "    print('current_step:', STATE.get('current_step'))\n"
        "    print('diagnostics:', REPORT.get('diagnostics'))\n"
        "    session = STATE.get('session') or {}\n"
        "    port = int(session.get('cdp_port') or 0)\n"
        "    if port <= 0:\n"
        "        print('No CDP port recorded; inspect STATE/REPORT manually.')\n"
        "        return\n"
        "    import nodriver\n"
        "    browser = await nodriver.Browser.create(host='127.0.0.1', port=port)\n"
        "    pages = getattr(browser, 'tabs', []) or []\n"
        "    print('connected_cdp_port:', port)\n"
        "    print('tab_count:', len(pages))\n"
        "    target_url = (session.get('active_tab_url') or '').split('?', 1)[0].split('#', 1)[0]\n"
        "    matched = None\n"
        "    for i, tab in enumerate(pages):\n"
        "        url = getattr(getattr(tab, 'target', None), 'url', '') or ''\n"
        "        print(f'[{i}]', url)\n"
        "        if target_url and url.startswith(target_url):\n"
        "            print('matched saved active_tab_url; set a breakpoint here to inspect tab')\n"
        "            matched = tab\n"
        "            break\n\n"
        "    if matched and FLOW:\n"
        "        failed = (REPORT.get('diagnostics') or {}).get('failed_step_id') or STATE.get('current_step')\n"
        "        step = find_step(FLOW.get('steps'), failed)\n"
        "        if step:\n"
        "            print('replaying step:', failed, step.get('action'))\n"
        "            await run_step(matched, step)\n"
        "if __name__ == '__main__':\n"
        "    asyncio.run(main())\n",
        encoding="utf-8",
    )
    return repro


@app.command("validate")
def validate_cmd(
    path: Path = typer.Argument(..., exists=True, readable=True, help="Path to flow JSON."),
) -> None:
    """Validate ``kind: rpa_flow`` schema (no-op for other kinds)."""
    from ziniao_mcp.flows import validate_flow_cli  # pylint: disable=import-outside-toplevel

    doc = json.loads(path.read_text(encoding="utf-8"))
    try:
        validate_flow_cli(doc)
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps({"ok": True, "path": str(path.resolve())}, ensure_ascii=False, indent=2))


@app.command("dry-run")
def dry_run_cmd(
    path: Path = typer.Argument(..., exists=True, readable=True, help="Path to flow JSON."),
    static: bool = typer.Option(False, "--static", help="Schema validation only (default when neither flag set)."),
    plan: bool = typer.Option(False, "--plan", help="Structured explain: outline + external calls + code previews."),
) -> None:
    """Offline dry-run: ``--static`` or ``--plan`` (no browser)."""
    from ziniao_mcp.flows.runner import dry_run_plan, dry_run_static  # pylint: disable=import-outside-toplevel

    doc = json.loads(path.read_text(encoding="utf-8"))
    try:
        if plan:
            out = dry_run_plan(doc)
        else:
            out = dry_run_static(doc)
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(out, ensure_ascii=False, indent=2))


@app.command("run")
def run_cmd(
    path: Path = typer.Argument(..., exists=True, readable=True, help="Path to preset or rpa_flow JSON."),
    var: Optional[List[str]] = typer.Option(None, "--var", help='Variable "key=value" (repeatable).'),
    vars_from: Optional[List[Path]] = typer.Option(
        None,
        "--vars-from",
        help="Read variables from JSON/YAML object or CSV table (CSV becomes rows=[...]). Repeatable.",
    ),
    vars_stdin: bool = typer.Option(
        False,
        "--vars-stdin",
        help="Read a JSON object from stdin and merge into CLI vars (stdin wins on duplicate keys).",
    ),
    run_dir: Optional[str] = typer.Option(
        None,
        "--run-dir",
        help="Directory for state.json / report.json / failure artefacts (default: ~/.ziniao/runs/<id>).",
    ),
    allow_private: bool = typer.Option(
        False,
        "--allow-private-network",
        help="Allow external_call http to private / loopback URLs (dev only).",
    ),
    allow_mcp: bool = typer.Option(False, "--allow-mcp", help="Allow all MCP tools for this run only."),
    policy: Optional[Path] = typer.Option(None, "--policy", exists=True, readable=True, help="Policy YAML path."),
    break_at: Optional[str] = typer.Option(None, "--break-at", help="Pause before this step id."),
    on_fail: str = typer.Option("none", "--on-fail", help="Failure debug mode: none, pdb, repl."),
    resume_from: Optional[str] = typer.Option(None, "--resume-from", help="Skip steps before this step id."),
    replay: Optional[str] = typer.Option(None, "--replay", help="Load state.json from a previous run id."),
    auto_resync: bool = typer.Option(False, "--auto-resync", help="On replay URL mismatch, navigate to saved URL."),
    strict: bool = typer.Option(False, "--strict", help="On replay URL mismatch, fail instead of warning."),
) -> None:
    """Execute flow via daemon (``flow_run``). Uses ``prepare_request`` when ``vars`` are defined."""
    from ziniao_mcp.sites import prepare_request  # pylint: disable=import-outside-toplevel

    parsed = _parse_var_list(var)
    native_values: dict[str, object] = {}
    try:
        for vf in vars_from or []:
            _merge_native_vars(parsed, _load_vars_file(vf), native_values)
    except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    if vars_stdin:
        blob = json.load(sys.stdin)
        if not isinstance(blob, dict):
            typer.echo("Error: --vars-stdin expects a JSON object on stdin.", err=True)
            raise typer.Exit(1)
        _merge_native_vars(parsed, blob, native_values)
    try:
        spec, _plugin = prepare_request(file=str(path), var_values=parsed)
        _apply_typed_vars(spec, native_values)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    if run_dir:
        spec["_ziniao_run_dir"] = run_dir
    spec["_ziniao_flow_base_dir"] = str(path.parent.resolve())
    spec["_ziniao_flow_path"] = str(path.resolve())
    if allow_private:
        spec["_ziniao_allow_private_network"] = True
    if allow_mcp:
        spec["_ziniao_allow_mcp"] = True
    if policy:
        spec["_ziniao_policy_path"] = str(policy.resolve())
    if break_at:
        spec["_ziniao_break_at"] = break_at
    if on_fail not in ("none", "pdb", "repl"):
        typer.echo("Error: --on-fail must be one of: none, pdb, repl.", err=True)
        raise typer.Exit(1)
    spec["_ziniao_on_fail"] = on_fail
    if resume_from:
        spec["_ziniao_resume_from"] = resume_from
    if replay:
        try:
            spec["_ziniao_initial_ctx"] = _read_replay_state(replay)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc
    if auto_resync:
        spec["_ziniao_auto_resync"] = True
    if strict:
        spec["_ziniao_strict"] = True

    preset_timeout_ms = spec.get("default_timeout_ms") or 0
    try:
        preset_timeout_s = float(preset_timeout_ms) / 1000.0
    except (TypeError, ValueError):
        preset_timeout_s = 0.0

    if preset_timeout_s > 0:
        result = run_command_with_default_timeout("flow_run", spec, preset_timeout_s)
    else:
        result = run_command("flow_run", spec)
    print_result(result, json_mode=get_json_mode())


@app.command("list")
def list_runs(
    limit: int = typer.Option(20, "--limit", "-n", help="Max directories to show."),
) -> None:
    """List recent run directories under ``~/.ziniao/runs/``."""
    root = Path.home() / ".ziniao" / "runs"
    if not root.is_dir():
        typer.echo(json.dumps({"runs": [], "root": str(root)}, ensure_ascii=False, indent=2))
        return
    dirs = sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)[
        : max(1, limit)
    ]
    rows = [{"id": p.name, "path": str(p.resolve()), "mtime": int(p.stat().st_mtime)} for p in dirs]
    typer.echo(json.dumps({"runs": rows, "root": str(root.resolve())}, ensure_ascii=False, indent=2))


@app.command("show")
def show_run(
    run_id: str = typer.Argument(..., help="Run directory name under ~/.ziniao/runs/."),
) -> None:
    """Print ``report.json`` for a run id."""
    p = Path.home() / ".ziniao" / "runs" / run_id / "report.json"
    if not p.is_file():
        typer.echo(f"Error: no report at {p}", err=True)
        raise typer.Exit(1)
    typer.echo(p.read_text(encoding="utf-8"))


@app.command("diagnose")
def diagnose_run(
    run_id: str = typer.Argument(..., help="Run directory name under ~/.ziniao/runs/."),
    emit: Optional[str] = typer.Option(None, "--emit", help="Optional emitter: nodriver."),
) -> None:
    """Summarise ``report.json`` + ``state.json`` paths for Agent tooling."""
    base = Path.home() / ".ziniao" / "runs" / run_id
    rep = base / "report.json"
    st = base / "state.json"
    payload = {
        "run_id": run_id,
        "artifacts_dir": str(base.resolve()),
        "report_json": str(rep) if rep.is_file() else None,
        "state_json": str(st) if st.is_file() else None,
    }
    if rep.is_file():
        try:
            doc = json.loads(rep.read_text(encoding="utf-8"))
            payload["ok"] = doc.get("ok")
            payload["diagnostics"] = doc.get("diagnostics")
            payload["failure_count"] = len(doc.get("failures") or [])
        except json.JSONDecodeError:
            payload["report_parse_error"] = True
    if emit:
        if emit != "nodriver":
            typer.echo("Error: --emit currently supports only 'nodriver'.", err=True)
            raise typer.Exit(1)
        try:
            payload["repro_py"] = str(_emit_repro(run_id))
        except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@app.command("step")
def step_cmd(
    path: Path = typer.Argument(..., exists=True, readable=True, help="Path to rpa_flow JSON."),
    step_id: str = typer.Argument(..., help="Step id to run in isolation."),
    state: Optional[str] = typer.Option(None, "--state", help="Run id whose state.json seeds ctx."),
) -> None:
    """Run one step using an optional previous ``state.json`` as context."""
    from ziniao_mcp.sites import prepare_request  # pylint: disable=import-outside-toplevel

    try:
        spec, _plugin = prepare_request(file=str(path), var_values={})
        step = _find_step(list(spec.get("steps") or []), step_id)
        if not step:
            raise ValueError(f"step id not found: {step_id}")
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    spec["steps"] = [step]
    spec["_ziniao_flow_base_dir"] = str(path.parent.resolve())
    spec["_ziniao_flow_path"] = str(path.resolve())
    if state:
        try:
            loaded_state = _read_replay_state(state)
            _validate_step_inputs(step, loaded_state)
            spec["_ziniao_initial_ctx"] = loaded_state
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc
        except ValueError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc
    else:
        state_inputs = _step_state_inputs(step)
        if state_inputs:
            typer.echo(
                (
                    f"Error: step {step_id!r} depends on prior flow state {state_inputs}; "
                    "pass --state <run_id> from a previous run, or remove/override the dependency."
                ),
                err=True,
            )
            raise typer.Exit(1)
    result = run_command("flow_run", spec)
    print_result(result, json_mode=get_json_mode())


def register_top_level(parent: typer.Typer) -> None:
    parent.add_typer(app, name="flow", help="RPA flows: validate, dry-run, run, list/show/diagnose runs.")
