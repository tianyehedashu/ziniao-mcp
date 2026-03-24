"""Structured locators (v2) with CSS fallback for nodriver replay."""

from __future__ import annotations

import json
from typing import Any


def build_locator_dict(el_var: str = "el") -> str:
    """JS snippet: given element `el`, return locator object {strategy, ...}."""
    return f"""(function(el) {{
        if (!el || !el.tagName) return {{ strategy: 'css', value: 'html' }};
        var tag = el.tagName.toLowerCase();
        var tid = el.getAttribute('data-testid');
        if (tid) return {{ strategy: 'testid', value: tid }};
        var did = el.getAttribute('data-id') || el.getAttribute('data-qa');
        if (did) return {{ strategy: 'attr', attr: 'data-id', value: did }};
        var al = el.getAttribute('aria-label');
        if (al) return {{ strategy: 'aria', value: al }};
        var name = el.getAttribute('name');
        if (name && (tag === 'input' || tag === 'textarea' || tag === 'select'))
            return {{ strategy: 'attr', attr: 'name', value: name }};
        var role = el.getAttribute('role');
        if (role) {{
            var an = el.getAttribute('aria-label') || (el.innerText || '').trim().slice(0, 80);
            return {{ strategy: 'role', role: role, name: an || '' }};
        }}
        return null;
    }})({el_var})"""


def locator_to_css_selector(loc: dict[str, Any]) -> str:
    """Best-effort CSS for nodriver from structured locator."""
    if not loc or not isinstance(loc, dict):
        return ""
    strat = (loc.get("strategy") or "").lower()
    if strat == "testid":
        v = loc.get("value", "")
        return f'[data-testid={json.dumps(str(v))}]'
    if strat == "attr":
        attr = str(loc.get("attr", "name"))
        v = loc.get("value", "")
        if not attr:
            return ""
        return f"[{attr}={json.dumps(str(v))}]"
    if strat == "aria":
        v = loc.get("value", "")
        return f"[aria-label={json.dumps(str(v))}]"
    if strat == "role":
        role = str(loc.get("role", ""))
        name = str(loc.get("name", ""))
        if role and name:
            return f'[role={json.dumps(role)}][aria-label={json.dumps(name)}]'
        if role:
            return f"[role={json.dumps(role)}]"
        return "body"
    if strat == "css":
        return str(loc.get("value", ""))
    return str(loc.get("value", ""))


def normalize_action_for_replay(act: dict[str, Any]) -> dict[str, Any]:
    """Ensure `selector` is set for replay (v1 flat or v2 locator)."""
    out = dict(act)
    sel = (out.get("selector") or "").strip()
    if not sel:
        loc = out.get("locator")
        if isinstance(loc, dict):
            css = locator_to_css_selector(loc)
            if css:
                out["selector"] = css
    return out
