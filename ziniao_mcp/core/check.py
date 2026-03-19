"""Shared core: element state checks."""

from __future__ import annotations

import json as _json
from typing import Any


async def is_visible(tab: Any, selector: str) -> dict:
    visible = await tab.evaluate(
        f"""(() => {{
            const el = document.querySelector({_json.dumps(selector)});
            if (!el) return false;
            const style = window.getComputedStyle(el);
            return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0'
                && el.offsetWidth > 0 && el.offsetHeight > 0;
        }})()""",
        return_by_value=True,
    )
    return {"ok": True, "selector": selector, "visible": bool(visible)}


async def is_enabled(tab: Any, selector: str) -> dict:
    enabled = await tab.evaluate(
        f"!document.querySelector({_json.dumps(selector)})?.disabled",
        return_by_value=True,
    )
    return {"ok": True, "selector": selector, "enabled": bool(enabled)}


async def is_checked(tab: Any, selector: str) -> dict:
    checked = await tab.evaluate(
        f"!!document.querySelector({_json.dumps(selector)})?.checked",
        return_by_value=True,
    )
    return {"ok": True, "selector": selector, "checked": bool(checked)}
