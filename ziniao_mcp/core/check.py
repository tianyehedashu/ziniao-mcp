"""Shared core: element state checks.

Bool-returning probes MUST go through :func:`safe_eval_js` — a raw
``tab.evaluate`` with ``return_by_value=True`` returns a ``RemoteObject`` when
the JS result is ``False`` (see ``core/_eval.py``), and ``bool(RemoteObject)``
is ``True`` — i.e. every negative result would silently flip to positive.
"""

from __future__ import annotations

import json as _json
from typing import Any

from ._eval import safe_eval_js


async def is_visible(tab: Any, selector: str) -> dict:
    visible = await safe_eval_js(
        tab,
        f"""(() => {{
            const el = document.querySelector({_json.dumps(selector)});
            if (!el) return false;
            const style = window.getComputedStyle(el);
            return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0'
                && el.offsetWidth > 0 && el.offsetHeight > 0;
        }})()""",
    )
    return {"ok": True, "selector": selector, "visible": bool(visible)}


async def is_enabled(tab: Any, selector: str) -> dict:
    enabled = await safe_eval_js(
        tab,
        f"!document.querySelector({_json.dumps(selector)})?.disabled",
    )
    return {"ok": True, "selector": selector, "enabled": bool(enabled)}


async def is_checked(tab: Any, selector: str) -> dict:
    checked = await safe_eval_js(
        tab,
        f"!!document.querySelector({_json.dumps(selector)})?.checked",
    )
    return {"ok": True, "selector": selector, "checked": bool(checked)}
