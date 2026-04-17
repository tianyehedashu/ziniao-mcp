"""Preset variable rendering.

:func:`render_vars` substitutes ``{{var}}`` placeholders inside preset
``url`` / ``body`` / ``headers`` / ``script`` / ``steps`` / ``navigate_url``
fields, coercing each value to the type declared in the preset's ``vars``
block.  Secret / file / file_list resolution is delegated to
:mod:`ziniao_mcp.sites.variables`.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .variables import _read_file_as_base64, _read_file_list_as_refs, _resolve_secret

_VAR_RE = re.compile(r"\{\{(\w+)\}\}")


def render_vars(template: dict, var_values: dict[str, str]) -> dict:
    """Replace ``{{var}}`` placeholders in *template* with *var_values*.

    - String values: simple replacement.
    - When ``"{{var}}"`` is the sole content of a JSON value and the var
      definition declares ``type: int/float/bool/file/file_list/secret``,
      the value is coerced via :func:`_coerce`.
    - Resolved ``secret`` values are collected into
      ``result['_ziniao_secret_values']`` so the UI flow executor can mask
      them in logs / failure artefacts.  ``steps`` (used by ``mode: ui``)
      is traversed alongside the fetch/js keys.
    """
    var_defs: dict = template.get("vars") or {}
    defaults = {k: v["default"] for k, v in var_defs.items() if "default" in v}
    merged = {**defaults, **var_values}

    for k, vdef in var_defs.items():
        if vdef.get("required") and k not in merged:
            if vdef.get("type") == "secret" and vdef.get("source"):
                continue
            raise ValueError(f"Required variable missing: {k}")

    result = json.loads(json.dumps(template))
    result.pop("vars", None)

    resolved_cache: dict[str, Any] = {}
    secret_values: list[str] = []

    def _resolve(var_name: str) -> Any:
        if var_name in resolved_cache:
            return resolved_cache[var_name]
        vdef = dict(var_defs.get(var_name) or {})
        vdef.setdefault("_name", var_name)
        coerced = _coerce(merged.get(var_name, ""), vdef)
        resolved_cache[var_name] = coerced
        if vdef.get("type") == "secret" and isinstance(coerced, str) and coerced:
            secret_values.append(coerced)
        return coerced

    def _replace(obj: Any) -> Any:
        if isinstance(obj, str):
            match = _VAR_RE.fullmatch(obj)
            if match:
                var_name = match.group(1)
                if var_name in merged or var_name in var_defs:
                    return _resolve(var_name)
                return obj

            def _sub(m: Any) -> str:
                name = m.group(1)
                if name in merged or name in var_defs:
                    val = _resolve(name)
                    return str(val) if not isinstance(val, str) else val
                return m.group(0)

            return _VAR_RE.sub(_sub, obj)
        if isinstance(obj, dict):
            return {k: _replace(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_replace(v) for v in obj]
        return obj

    for key in ("url", "body", "headers", "script", "steps", "navigate_url"):
        if key in result:
            result[key] = _replace(result[key])

    if secret_values:
        result["_ziniao_secret_values"] = secret_values
    return result


def _coerce(value: Any, var_def: dict) -> Any:
    """Coerce a string value to the type declared in the var definition."""
    vtype = var_def.get("type", "str")
    if vtype == "int":
        try:
            return int(value)
        except (ValueError, TypeError):
            return value
    if vtype == "float":
        try:
            return float(value)
        except (ValueError, TypeError):
            return value
    if vtype == "bool":
        if isinstance(value, bool):
            return value
        return str(value).lower() in ("true", "1", "yes")
    if vtype == "file":
        return _read_file_as_base64(str(value), var_def)
    if vtype == "file_list":
        return _read_file_list_as_refs(value, var_def)
    if vtype == "secret":
        return _resolve_secret(value, var_def)
    return value
