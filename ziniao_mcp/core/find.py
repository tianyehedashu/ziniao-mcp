"""Shared core: find/nth semantic element location."""

from __future__ import annotations

import json as _json
from typing import Any


async def find_nth(tab: Any, selector: str, index: int, action: str = "click") -> dict:
    js = f"""(() => {{
        const els = document.querySelectorAll({_json.dumps(selector)});
        if (!els.length) return null;
        const idx = {index} < 0 ? els.length + {index} : {index};
        if (idx < 0 || idx >= els.length) return null;
        return idx;
    }})()"""
    resolved_idx = await tab.evaluate(js, return_by_value=True)
    if resolved_idx is None:
        return {"error": f"No element at index {index} for selector: {selector}"}

    if action == "text":
        text = await tab.evaluate(
            f"document.querySelectorAll({_json.dumps(selector)})[{resolved_idx}]?.textContent ?? ''",
            return_by_value=True,
        )
        return {"ok": True, "selector": selector, "index": resolved_idx, "text": text}
    if action == "html":
        html = await tab.evaluate(
            f"document.querySelectorAll({_json.dumps(selector)})[{resolved_idx}]?.innerHTML ?? ''",
            return_by_value=True,
        )
        return {"ok": True, "selector": selector, "index": resolved_idx, "html": html}
    if action == "value":
        value = await tab.evaluate(
            f"document.querySelectorAll({_json.dumps(selector)})[{resolved_idx}]?.value ?? ''",
            return_by_value=True,
        )
        return {"ok": True, "selector": selector, "index": resolved_idx, "value": value}

    await tab.evaluate(
        f"""(() => {{
            const el = document.querySelectorAll({_json.dumps(selector)})[{resolved_idx}];
            if (el) el.click();
        }})()""",
        return_by_value=True,
    )
    return {"ok": True, "selector": selector, "index": resolved_idx, "action": "click"}


async def find_text(tab: Any, text: str, action: str = "click", tag: str = "") -> dict:
    tag_filter = f" and local-name()='{tag}'" if tag else ""
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
    result = await tab.evaluate(js, return_by_value=True)
    if result is None:
        return {"error": f"No element found with text: {text}"}
    return {"ok": True, "text": text, "action": action, "result": result}


async def find_role(tab: Any, role: str, action: str = "click", name: str = "") -> dict:
    name_filter = f'[aria-label*="{name}"]' if name else ""
    selector = f'[role="{role}"]{name_filter}'
    js = f"""(() => {{
        const el = document.querySelector({_json.dumps(selector)});
        if (!el) return null;
        if ({_json.dumps(action)} === 'click') {{ el.click(); return 'clicked'; }}
        if ({_json.dumps(action)} === 'text') return el.textContent;
        if ({_json.dumps(action)} === 'html') return el.innerHTML;
        el.click(); return 'clicked';
    }})()"""
    result = await tab.evaluate(js, return_by_value=True)
    if result is None:
        return {"error": f"No element found with role={role}" + (f" name={name}" if name else "")}
    return {"ok": True, "role": role, "action": action, "result": result}
