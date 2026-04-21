"""Shared core: scroll operations.

``scroll_into`` reads a bool return value, so it must go through
:func:`safe_eval_js` — ``tab.evaluate`` returns a raw ``RemoteObject`` on
``False`` (see ``core/_eval.py``) which would make "element not found" look
like "scrolled successfully".  ``scroll`` itself discards the return so either
path works; we still route it through the safe helper for consistency.
"""

from __future__ import annotations

import json as _json
from typing import Any

from ._eval import safe_eval_js


async def scroll(tab: Any, direction: str = "down", pixels: int = 300, selector: str = "") -> dict:
    scroll_map = {"up": (0, -pixels), "down": (0, pixels), "left": (-pixels, 0), "right": (pixels, 0)}
    dx, dy = scroll_map.get(direction, (0, pixels))

    if selector:
        await safe_eval_js(
            tab,
            f"document.querySelector({_json.dumps(selector)})?.scrollBy({dx}, {dy})",
        )
    else:
        await safe_eval_js(tab, f"window.scrollBy({dx}, {dy})")
    return {"ok": True, "direction": direction, "pixels": pixels}


async def scroll_into(tab: Any, selector: str) -> dict:
    found = await safe_eval_js(
        tab,
        f"""(() => {{
            const el = document.querySelector({_json.dumps(selector)});
            if (!el) return false;
            el.scrollIntoView({{behavior: 'smooth', block: 'center'}});
            return true;
        }})()""",
    )
    if not found:
        return {"error": f"Element not found: {selector}"}
    return {"ok": True, "selector": selector}
