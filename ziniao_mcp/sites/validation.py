"""Preset-level static validation.

Two validators live here:

- :func:`_validate_ui_preset` — UI flow (``mode: ui``) pre-render check:
  steps whitelist, duplicate IDs, secret leakage guards, output_contract
  safety.
- :func:`_normalize_header_inject` — runtime normaliser for the
  ``header_inject`` list used by ``mode: fetch`` presets.
"""

from __future__ import annotations

from typing import Any

UI_ACTION_WHITELIST = frozenset({
    "navigate", "wait", "click", "fill", "type_text", "insert_text",
    "press_key", "hover", "dblclick", "upload", "upload-hijack", "screenshot", "snapshot",
    "eval", "extract", "fetch",
})

_VALID_INJECT_SOURCES = frozenset({"cookie", "localStorage", "sessionStorage", "eval"})

# Fields where a `{{secret}}` placeholder is legitimate (posted as body /
# typed into a password input / sent as a header value).  Any *other* field
# -- including selectors, URLs, scripts, extract `attr` -- must NOT carry
# secret values, because:
#   * selectors are logged/echoed by CDP and may end up in daemon logs;
#   * URLs appear in `navigate` history, browser address bar, and network
#     panels;
#   * `eval` scripts get snapshotted on error.
_SECRET_ALLOWED_STEP_FIELDS = frozenset({"value", "text", "headers", "body", "fields_json"})


def _walk_strings(obj: Any):
    """Yield every string leaf in *obj* (recurses into dict/list)."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_strings(v)


def _validate_ui_preset(spec: dict) -> None:
    """Validate a ``mode: ui`` preset *before* rendering.

    Enforces:

    - ``steps`` present, non-empty, list of dicts.
    - Each step has an ``action`` in :data:`UI_ACTION_WHITELIST`.
    - ``action: extract`` requires ``as`` (where to store the result).
    - ``secret`` vars may only appear in the whitelist
      :data:`_SECRET_ALLOWED_STEP_FIELDS`.  Any other step field
      (``selector``, ``url``, ``script``, ``attr``, …) must NOT carry
      ``{{secret}}`` tokens, even nested inside dict/list values.
    - ``output_contract`` must not export ``$.vars.<secret>`` — flow output
      is user-facing and often logged / stored.

    Raises :class:`ValueError` on the first violation.
    """
    if spec.get("mode") != "ui":
        return

    steps = spec.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("mode: ui preset requires non-empty 'steps' list.")

    secret_names = {
        k for k, v in (spec.get("vars") or {}).items()
        if isinstance(v, dict) and v.get("type") == "secret"
    }

    def _contains_secret_token(node: Any) -> str | None:
        for leaf in _walk_strings(node):
            for sname in secret_names:
                if "{{" + sname + "}}" in leaf:
                    return sname
        return None

    seen_ids: set[str] = set()
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError(f"steps[{idx}] must be an object, got {type(step).__name__}.")
        action = step.get("action")
        if action not in UI_ACTION_WHITELIST:
            raise ValueError(
                f"steps[{idx}] action={action!r} not in whitelist "
                f"{sorted(UI_ACTION_WHITELIST)}."
            )
        sid = step.get("id")
        if sid:
            if sid in seen_ids:
                raise ValueError(f"Duplicate step id: {sid!r}.")
            seen_ids.add(sid)
        if action == "extract" and not step.get("as"):
            raise ValueError(f"steps[{idx}] action=extract requires 'as' (target key).")

        if secret_names:
            for key, val in step.items():
                if key in _SECRET_ALLOWED_STEP_FIELDS:
                    continue
                leaked = _contains_secret_token(val)
                if leaked is not None:
                    raise ValueError(
                        f"steps[{idx}].{key} references secret var {leaked!r}; "
                        f"secrets may only appear in {sorted(_SECRET_ALLOWED_STEP_FIELDS)}."
                    )

    contract = spec.get("output_contract") or {}
    if isinstance(contract, dict) and secret_names:
        for out_key, expr in contract.items():
            if not isinstance(expr, str) or not expr.startswith("$.vars."):
                continue
            var_name = expr[len("$.vars."):].split(".", 1)[0]
            if var_name in secret_names:
                raise ValueError(
                    f"output_contract[{out_key!r}] exports secret var "
                    f"{var_name!r}; secrets must never appear in flow output."
                )


def _normalize_header_inject(spec: dict) -> None:
    """Validate and clean the ``header_inject`` list in *spec*.

    Each entry must have ``header`` (str) and ``source`` (one of cookie /
    localStorage / sessionStorage / eval).  Invalid or incomplete entries are
    silently dropped.  If the resulting list is empty the key is removed.

    Invoked from ``dispatch._page_fetch`` (single choke point for CLI + MCP);
    ``prepare_request`` does not call this.
    """
    raw = spec.get("header_inject")
    if not isinstance(raw, list):
        spec.pop("header_inject", None)
        return
    cleaned: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        header = str(item.get("header") or "").strip()
        source = str(item.get("source") or "").strip()
        if not header or source not in _VALID_INJECT_SOURCES:
            continue
        entry: dict = {"header": header, "source": source}
        if source == "eval":
            expr = str(item.get("expression") or "").strip()
            if not expr:
                continue
            entry["expression"] = expr
        else:
            key = str(item.get("key") or "").strip()
            if not key:
                continue
            entry["key"] = key
        transform = str(item.get("transform") or "").strip()
        if transform:
            entry["transform"] = transform
        cleaned.append(entry)
    if cleaned:
        spec["header_inject"] = cleaned
    else:
        spec.pop("header_inject", None)
