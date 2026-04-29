"""Static validation for ``kind: rpa_flow`` JSON documents (schema_version rpa/1)."""

from __future__ import annotations

from typing import Any

RPA_SCHEMA_VERSION = "rpa/1"

# Leaf actions delegated to ``dispatch._dispatch_flow_step`` (must stay in sync
# with ``ziniao_mcp.sites.validation.UI_ACTION_WHITELIST``).
_UI_LEAF_ACTIONS = frozenset({
    "navigate", "wait", "click", "fill", "type_text", "insert_text",
    "press_key", "hover", "dblclick", "upload", "upload-hijack", "screenshot", "snapshot",
    "eval", "extract", "fetch", "clear-overlay", "upload-react", "inject-file", "inject-vars",
})

# Composite + RPA-only leaf steps handled by ``flows.runner``.
_RPA_CONTROL_ACTIONS = frozenset({
    "if", "for_each", "while", "for_range", "retry", "break", "continue", "return", "fail",
    "sleep", "assert", "set_var", "log", "code", "external_call", "call_preset", "call_flow",
    "read_csv", "write_csv", "read_json", "write_json", "read_text", "write_text",
})

RPA_ACTION_WHITELIST = _UI_LEAF_ACTIONS | _RPA_CONTROL_ACTIONS


def validate_rpa_flow_document(doc: dict[str, Any]) -> None:
    """Raise ``ValueError`` if *doc* is not a well-formed ``rpa_flow`` document."""
    if doc.get("kind") != "rpa_flow":
        raise ValueError("validate_rpa_flow_document expects kind: rpa_flow.")
    if doc.get("schema_version") != RPA_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported schema_version {doc.get('schema_version')!r}; "
            f"expected {RPA_SCHEMA_VERSION!r}."
        )
    steps = doc.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("rpa_flow requires non-empty 'steps' list.")
    seen: set[str] = set()
    _validate_steps_list(steps, seen, path="steps")


def _validate_steps_list(steps: list[Any], seen: set[str], *, path: str) -> None:
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError(f"{path}[{idx}] must be an object.")
        action = step.get("action")
        if action not in RPA_ACTION_WHITELIST:
            raise ValueError(
                f"{path}[{idx}] unsupported action {action!r}; "
                f"allowed: {sorted(RPA_ACTION_WHITELIST)}."
            )
        sid = step.get("id")
        if isinstance(sid, str) and sid:
            if sid in seen:
                raise ValueError(f"Duplicate step id: {sid!r}.")
            seen.add(sid)
        if action == "extract" and not step.get("as"):
            raise ValueError(f"{path}[{idx}] action=extract requires 'as'.")
        if action == "if":
            if "then" not in step:
                raise ValueError(f"{path}[{idx}] action=if requires 'then'.")
            _validate_steps_list(step["then"], seen, path=f"{path}[{idx}].then")
            if step.get("else"):
                _validate_steps_list(step["else"], seen, path=f"{path}[{idx}].else")
        elif action == "for_each":
            if "over" not in step or "do" not in step:
                raise ValueError(f"{path}[{idx}] action=for_each requires 'over' and 'do'.")
            _validate_steps_list(step["do"], seen, path=f"{path}[{idx}].do")
        elif action in ("while", "retry"):
            if "do" not in step:
                raise ValueError(f"{path}[{idx}] action={action} requires 'do'.")
            _validate_steps_list(step["do"], seen, path=f"{path}[{idx}].do")
        elif action == "for_range":
            if "do" not in step:
                raise ValueError(f"{path}[{idx}] action=for_range requires 'do'.")
            _validate_steps_list(step["do"], seen, path=f"{path}[{idx}].do")
        elif action == "call_flow":
            if not (step.get("path") or step.get("file")):
                raise ValueError(f"{path}[{idx}] action=call_flow requires 'path' or 'file'.")


def validate_flow_document(doc: dict[str, Any]) -> None:
    """Validate *doc* when it declares ``kind: rpa_flow``; no-op for other kinds."""
    kind = doc.get("kind")
    if kind == "rpa_flow":
        validate_rpa_flow_document(doc)
