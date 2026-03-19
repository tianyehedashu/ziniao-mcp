"""Shared core: get element/page information."""

from __future__ import annotations

import json as _json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


async def get_text(tab: Any, selector: str) -> dict:
    text = await tab.evaluate(
        f"document.querySelector({_json.dumps(selector)})?.textContent ?? ''",
        return_by_value=True,
    )
    return {"ok": True, "selector": selector, "text": text}


async def get_html(tab: Any, selector: str) -> dict:
    html = await tab.evaluate(
        f"document.querySelector({_json.dumps(selector)})?.innerHTML ?? ''",
        return_by_value=True,
    )
    return {"ok": True, "selector": selector, "html": html}


async def get_value(tab: Any, selector: str) -> dict:
    value = await tab.evaluate(
        f"document.querySelector({_json.dumps(selector)})?.value ?? ''",
        return_by_value=True,
    )
    return {"ok": True, "selector": selector, "value": value}


async def get_attr(tab: Any, selector: str, attribute: str) -> dict:
    value = await tab.evaluate(
        f"document.querySelector({_json.dumps(selector)})?.getAttribute({_json.dumps(attribute)})",
        return_by_value=True,
    )
    return {"ok": True, "selector": selector, "attribute": attribute, "value": value}


async def get_title(tab: Any) -> dict:
    title = await tab.evaluate("document.title", return_by_value=True)
    return {"ok": True, "title": title}


async def get_url(tab: Any) -> dict:
    url = await tab.evaluate("location.href", return_by_value=True)
    return {"ok": True, "url": url}


async def get_count(tab: Any, selector: str) -> dict:
    count = await tab.evaluate(
        f"document.querySelectorAll({_json.dumps(selector)}).length",
        return_by_value=True,
    )
    return {"ok": True, "selector": selector, "count": count}
