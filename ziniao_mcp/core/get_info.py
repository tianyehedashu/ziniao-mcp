"""Shared core: get element/page information.

All readers route through :func:`ziniao_mcp.core._eval.safe_eval_js` so that
falsy JSON return values (``""``, ``0``, ``False``) round-trip correctly —
using ``tab.evaluate`` directly leaks raw ``RemoteObject`` instances on those
cases.  See ``core/_eval.py`` for the underlying nodriver bug.
"""

from __future__ import annotations

import json as _json
from typing import Any

from ._eval import safe_eval_js


async def get_text(tab: Any, selector: str) -> dict:
    text = await safe_eval_js(
        tab,
        f"document.querySelector({_json.dumps(selector)})?.textContent ?? ''",
    )
    return {"ok": True, "selector": selector, "text": text}


async def get_html(tab: Any, selector: str) -> dict:
    html = await safe_eval_js(
        tab,
        f"document.querySelector({_json.dumps(selector)})?.innerHTML ?? ''",
    )
    return {"ok": True, "selector": selector, "html": html}


async def get_value(tab: Any, selector: str) -> dict:
    value = await safe_eval_js(
        tab,
        f"document.querySelector({_json.dumps(selector)})?.value ?? ''",
    )
    return {"ok": True, "selector": selector, "value": value}


async def get_attr(tab: Any, selector: str, attribute: str) -> dict:
    value = await safe_eval_js(
        tab,
        f"document.querySelector({_json.dumps(selector)})?.getAttribute({_json.dumps(attribute)})",
    )
    return {"ok": True, "selector": selector, "attribute": attribute, "value": value}


async def get_title(tab: Any) -> dict:
    title = await safe_eval_js(tab, "document.title")
    return {"ok": True, "title": title}


async def get_url(tab: Any) -> dict:
    url = await safe_eval_js(tab, "location.href")
    return {"ok": True, "url": url}


async def get_count(tab: Any, selector: str) -> dict:
    count = await safe_eval_js(
        tab,
        f"document.querySelectorAll({_json.dumps(selector)}).length",
    )
    return {"ok": True, "selector": selector, "count": count}
