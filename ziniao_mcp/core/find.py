"""Shared core: find/nth semantic element location.

Routes JS evaluation through :func:`safe_eval_js` so that falsy return values
(``null`` → ``None``; index ``0`` → ``0``; empty text ``""`` → ``""``) do not
leak raw ``RemoteObject`` instances and thereby confuse downstream
``is None`` / ``if result`` sentinel checks.  See ``core/_eval.py``.
"""

from __future__ import annotations

import json as _json
from typing import Any

from ._eval import safe_eval_js


async def find_nth(tab: Any, selector: str, index: int, action: str = "click") -> dict:
    js = f"""(() => {{
        const els = document.querySelectorAll({_json.dumps(selector)});
        if (!els.length) return null;
        const idx = {index} < 0 ? els.length + {index} : {index};
        if (idx < 0 || idx >= els.length) return null;
        return idx;
    }})()"""
    resolved_idx = await safe_eval_js(tab, js)
    if resolved_idx is None:
        return {"error": f"No element at index {index} for selector: {selector}"}

    if action == "text":
        text = await safe_eval_js(
            tab,
            f"document.querySelectorAll({_json.dumps(selector)})[{resolved_idx}]?.textContent ?? ''",
        )
        return {"ok": True, "selector": selector, "index": resolved_idx, "text": text}
    if action == "html":
        html = await safe_eval_js(
            tab,
            f"document.querySelectorAll({_json.dumps(selector)})[{resolved_idx}]?.innerHTML ?? ''",
        )
        return {"ok": True, "selector": selector, "index": resolved_idx, "html": html}
    if action == "value":
        value = await safe_eval_js(
            tab,
            f"document.querySelectorAll({_json.dumps(selector)})[{resolved_idx}]?.value ?? ''",
        )
        return {"ok": True, "selector": selector, "index": resolved_idx, "value": value}

    await safe_eval_js(
        tab,
        f"""(() => {{
            const el = document.querySelectorAll({_json.dumps(selector)})[{resolved_idx}];
            if (el) el.click();
        }})()""",
    )
    return {"ok": True, "selector": selector, "index": resolved_idx, "action": "click"}


async def find_text(tab: Any, text: str, action: str = "click", tag: str = "") -> dict:
    tag_filter = f" and local-name()={_json.dumps(tag)}" if tag else ""
    xpath = f"//*[contains(text(), {_json.dumps(text)}){tag_filter}]"
    js = f"""(() => {{
        const result = document.evaluate({_json.dumps(xpath)}, document, null,
            XPathResult.FIRST_ORDERED_NODE_TYPE, null);
        const el = result.singleNodeValue;
        if (!el) return null;
        if ({_json.dumps(action)} === 'click') {{ el.click(); return 'clicked'; }}
        if ({_json.dumps(action)} === 'text') return el.textContent;
        if ({_json.dumps(action)} === 'html') return el.innerHTML;
        el.click(); return 'clicked';
    }})()"""
    result = await safe_eval_js(tab, js)
    if result is None:
        return {"error": f"No element found with text: {text}"}
    return {"ok": True, "text": text, "action": action, "result": result}


async def find_role(tab: Any, role: str, action: str = "click", name: str = "") -> dict:
    css_role = role.replace("\\", "\\\\").replace('"', '\\"')
    selector = f'[role="{css_role}"]'
    if name:
        css_name = name.replace("\\", "\\\\").replace('"', '\\"')
        selector += f'[aria-label*="{css_name}"]'
    js = f"""(() => {{
        const el = document.querySelector({_json.dumps(selector)});
        if (!el) return null;
        if ({_json.dumps(action)} === 'click') {{ el.click(); return 'clicked'; }}
        if ({_json.dumps(action)} === 'text') return el.textContent;
        if ({_json.dumps(action)} === 'html') return el.innerHTML;
        el.click(); return 'clicked';
    }})()"""
    result = await safe_eval_js(tab, js)
    if result is None:
        return {"error": f"No element found with role={role}" + (f" name={name}" if name else "")}
    return {"ok": True, "role": role, "action": action, "result": result}
