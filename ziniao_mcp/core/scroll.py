"""Shared core: scroll operations."""

from __future__ import annotations

import json as _json
from typing import Any


async def scroll(tab: Any, direction: str = "down", pixels: int = 300, selector: str = "") -> dict:
    scroll_map = {"up": (0, -pixels), "down": (0, pixels), "left": (-pixels, 0), "right": (pixels, 0)}
    dx, dy = scroll_map.get(direction, (0, pixels))

    if selector:
        await tab.evaluate(
            f"document.querySelector({_json.dumps(selector)})?.scrollBy({dx}, {dy})",
            return_by_value=True,
        )
    else:
        await tab.evaluate(f"window.scrollBy({dx}, {dy})", return_by_value=True)
    return {"ok": True, "direction": direction, "pixels": pixels}


async def scroll_into(tab: Any, selector: str) -> dict:
    found = await tab.evaluate(
        f"""(() => {{
            const el = document.querySelector({_json.dumps(selector)});
            if (!el) return false;
            el.scrollIntoView({{behavior: 'smooth', block: 'center'}});
            return true;
        }})()""",
        return_by_value=True,
    )
    if not found:
        return {"error": f"Element not found: {selector}"}
    return {"ok": True, "selector": selector}
