"""Convert recording IR (``actions`` list) into ``kind: rpa_flow`` JSON drafts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _js_string_literal(val: str) -> str:
    return json.dumps(val, ensure_ascii=False)


def actions_to_flow_steps(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map dom2 / legacy recording actions to UI flow steps (best-effort)."""
    steps: list[dict[str, Any]] = []
    for i, a in enumerate(actions):
        t = str(a.get("type", ""))
        sid = f"rec_{i}_{t}"
        if t == "click":
            steps.append({"id": sid, "action": "click", "selector": a.get("selector") or "body"})
        elif t == "dblclick":
            steps.append({"id": sid, "action": "dblclick", "selector": a.get("selector") or "body"})
        elif t == "hover":
            steps.append({"id": sid, "action": "hover", "selector": a.get("selector") or "body"})
        elif t == "fill":
            steps.append(
                {
                    "id": sid,
                    "action": "fill",
                    "selector": a.get("selector") or "body",
                    "value": a.get("value", ""),
                },
            )
        elif t == "navigate":
            url = (a.get("url") or "").strip()
            if url:
                steps.append({"id": sid, "action": "navigate", "url": url})
        elif t == "press_key":
            steps.append({"id": sid, "action": "press_key", "key": a.get("key", "Enter")})
        elif t == "scroll":
            sx = int(a.get("scrollX", 0))
            sy = int(a.get("scrollY", 0))
            script = f"(() => {{ window.scrollTo({sx}, {sy}); return true; }})()"
            steps.append({"id": sid, "action": "eval", "script": script, "await_promise": False})
        elif t == "select":
            sel = _js_string_literal(str(a.get("selector") or "select"))
            val = _js_string_literal(str(a.get("value", "")))
            script = (
                "(() => { const el = document.querySelector(" + sel + ");"
                " if (!el) return null;"
                " el.value = " + val + ";"
                " el.dispatchEvent(new Event('change', { bubbles: true }));"
                " return true; })()"
            )
            steps.append({"id": sid, "action": "eval", "script": script, "await_promise": False})
        elif t == "upload":
            paths = a.get("fileNames") or []
            if isinstance(paths, list) and paths:
                steps.append(
                    {
                        "id": sid,
                        "action": "upload",
                        "selector": a.get("selector") or 'input[type="file"]',
                        "file_paths": [str(p) for p in paths],
                    },
                )
            else:
                steps.append(
                    {
                        "id": sid,
                        "action": "log",
                        "level": "warning",
                        "message": f"upload step {sid} has no fileNames; fix paths before run.",
                    },
                )
        elif t == "drag":
            steps.append(
                {
                    "id": sid,
                    "action": "log",
                    "level": "warning",
                    "message": "drag recorded; replace with explicit flow or eval.",
                },
            )
        elif t == "dialog":
            continue
        else:
            steps.append(
                {
                    "id": sid,
                    "action": "log",
                    "level": "info",
                    "message": f"skipped unsupported recording type {t!r}",
                },
            )
    return steps


def build_rpa_flow_draft(
    *,
    name: str,
    start_url: str,
    actions: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "kind": "rpa_flow",
        "schema_version": "rpa/1",
        "name": name,
        "navigate_url": start_url or "",
        "meta": {"draft": True, "source": "recording_emit_preset", "start_url": start_url},
        "vars": {},
        "steps": actions_to_flow_steps(actions),
    }


def write_preset_flow_draft(
    path: Path,
    *,
    name: str,
    start_url: str,
    actions: list[dict[str, Any]],
) -> None:
    """Write a draft ``rpa_flow`` JSON next to the recording."""
    doc = build_rpa_flow_draft(name=name, start_url=start_url, actions=actions)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
