"""Multi-page fetch orchestration.

Two pagination strategies are built in:

- ``body_field``: the request body carries a page number; the first response
  exposes a total page count.
- ``offset``: the body carries ``offset``/``limit``; total record count
  determines how many pages to pull.

:func:`run_site_fetch` is the single entry point used by the CLI and the
``site/*`` MCP tool.  Plugins can override :meth:`SitePlugin.paginate` to
implement custom strategies entirely.
"""

from __future__ import annotations

import asyncio
import copy
import json
from typing import Any, Callable

from ._base import SitePlugin


def _get_nested(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if not part:
            continue
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _set_nested(obj: dict, path: str, value: Any) -> None:
    parts = [p for p in path.split(".") if p]
    if not parts:
        return
    cur: Any = obj
    for p in parts[:-1]:
        nxt = cur.get(p) if isinstance(cur, dict) else None
        if not isinstance(nxt, dict):
            cur[p] = {}
            nxt = cur[p]
        cur = nxt
    cur[parts[-1]] = value


def plugin_overrides_paginate(plugin: SitePlugin | None) -> bool:
    """True if *plugin* defines a custom ``paginate`` (not the base default)."""
    if plugin is None:
        return False
    return type(plugin).paginate is not SitePlugin.paginate


def _parse_body_dict(spec: dict) -> dict:
    b = spec.get("body")
    if isinstance(b, str):
        try:
            out = json.loads(b)
            return out if isinstance(out, dict) else {}
        except json.JSONDecodeError:
            return {}
    if isinstance(b, dict):
        return copy.deepcopy(b)
    return {}


def _spec_with_body_dict(spec: dict, body: dict) -> dict:
    s = copy.deepcopy(spec)
    s["body"] = json.dumps(body, ensure_ascii=False)
    return s


_CLI_ONLY_SPEC_KEYS = frozenset({"media_contract", "response_contract"})


def _spec_for_page_fetch(spec: dict) -> dict:
    """Deep-copy *spec* for ``page_fetch`` / daemon.

    Strips keys the daemon / JS fetch path never consumes:

    - ``_ziniao_*`` — internal flags (secret values, decode hints, …).
    - ``media_contract`` — declarative save rules used only client-side by
      the default :meth:`SitePlugin.media_contract`; shipping it to the
      daemon would just waste bytes.
    - ``response_contract`` — declarative body-parse / lift rules consumed
      only by :meth:`SitePlugin.after_fetch` after the response arrives.
    """
    out = copy.deepcopy(spec)
    for k in list(out.keys()):
        if k.startswith("_ziniao_") or k in _CLI_ONLY_SPEC_KEYS:
            out.pop(k, None)
    return out


def paginate_all_generic(
    spec: dict,
    pagination: dict,
    fetch_sync: Callable[[dict], dict],
) -> tuple[dict, int, int]:
    """Merge all pages using JSON ``pagination`` config.

    Returns ``(merged_response_dict, http_status_first_page, pages_fetched)``.
    """
    ptype = pagination.get("type", "none")
    if ptype == "body_field":
        return _paginate_body_field(spec, pagination, fetch_sync)
    if ptype == "offset":
        return _paginate_offset(spec, pagination, fetch_sync)
    raise ValueError(f"Unsupported pagination.type: {ptype}")


def _paginate_body_field(
    spec: dict,
    pag: dict,
    fetch_sync: Callable[[dict], dict],
) -> tuple[dict, int, int]:
    page_field = pag.get("page_field", "page")
    total_field = pag.get("total_field", "")
    start = int(pag.get("start", 1))
    max_pages = int(pag.get("max_pages", 500))
    merge_items_field = pag.get("merge_items_field", "")

    body = _parse_body_dict(spec)
    body[page_field] = start
    first = fetch_sync(_spec_for_page_fetch(_spec_with_body_dict(spec, body)))

    status = int(first.get("status", 200))
    if first.get("error") or status >= 400:
        try:
            merged = json.loads(first.get("body") or "{}")
        except (json.JSONDecodeError, TypeError):
            merged = {}
        return merged, status, 1

    text = first.get("body", "")
    try:
        first_data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {}, status, 1

    total = _get_nested(first_data, total_field) if total_field else 1
    try:
        total = int(total)
    except (TypeError, ValueError):
        total = 1
    total = max(1, min(total, max_pages))

    page_results = [first]
    for pnum in range(start + 1, total + 1):
        if pnum > max_pages:
            break
        b2 = _parse_body_dict(spec)
        b2[page_field] = pnum
        page_results.append(fetch_sync(_spec_for_page_fetch(_spec_with_body_dict(spec, b2))))

    merged = _merge_page_bodies(page_results, merge_items_field)
    return merged, status, len(page_results)


def _paginate_offset(
    spec: dict,
    pag: dict,
    fetch_sync: Callable[[dict], dict],
) -> tuple[dict, int, int]:
    offset_field = pag.get("offset_field", "offset")
    limit_field = pag.get("limit_field", "limit")
    limit = int(pag.get("limit", 50))
    start_offset = int(pag.get("start_offset", 0))
    total_field = pag.get("total_field", "")
    max_pages = int(pag.get("max_pages", 500))
    merge_items_field = pag.get("merge_items_field", "")

    body = _parse_body_dict(spec)
    body[offset_field] = start_offset
    body[limit_field] = limit
    first = fetch_sync(_spec_for_page_fetch(_spec_with_body_dict(spec, body)))
    status = int(first.get("status", 200))
    if first.get("error") or status >= 400:
        try:
            return json.loads(first.get("body") or "{}"), status, 1
        except (json.JSONDecodeError, TypeError):
            return {}, status, 1

    try:
        first_data = json.loads(first.get("body") or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}, status, 1

    total_count = _get_nested(first_data, total_field) if total_field else None
    try:
        total_count = int(total_count)
    except (TypeError, ValueError):
        total_count = limit

    num_pages = max(1, (total_count + limit - 1) // limit)
    num_pages = min(num_pages, max_pages)

    page_results = [first]
    for i in range(1, num_pages):
        off = start_offset + i * limit
        b2 = _parse_body_dict(spec)
        b2[offset_field] = off
        b2[limit_field] = limit
        page_results.append(fetch_sync(_spec_for_page_fetch(_spec_with_body_dict(spec, b2))))

    merged = _merge_page_bodies(page_results, merge_items_field)
    return merged, status, len(page_results)


def _merge_page_bodies(page_results: list[dict], merge_items_field: str) -> dict:
    if not page_results:
        return {}
    first_text = page_results[0].get("body", "") or "{}"
    try:
        first_data = json.loads(first_text)
    except (json.JSONDecodeError, TypeError):
        return {}

    if not merge_items_field or len(page_results) == 1:
        return first_data if isinstance(first_data, dict) else {}

    merged = json.loads(json.dumps(first_data))
    combined: list[Any] = []
    for pr in page_results:
        try:
            d = json.loads(pr.get("body") or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        chunk = _get_nested(d, merge_items_field)
        if isinstance(chunk, list):
            combined.extend(chunk)
    _set_nested(merged, merge_items_field, combined)
    return merged


async def _async_plugin_paginate_collect(
    plugin: SitePlugin,
    spec: dict,
    first_response: dict,
    fetch_sync: Callable[[dict], dict],
) -> dict:
    async def fetch_fn(s: dict) -> dict:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: fetch_sync(_spec_for_page_fetch(s)))

    pages: list[dict] = []
    async for p in plugin.paginate(fetch_fn, copy.deepcopy(spec), copy.deepcopy(first_response)):
        pages.append(p)

    if not pages:
        return {"ok": False, "error": "plugin paginate yielded no pages"}
    if len(pages) == 1:
        return pages[0]
    parsed_pages = []
    for p in pages:
        b = p.get("body", "")
        try:
            parsed_pages.append(json.loads(b) if b else {})
        except (json.JSONDecodeError, TypeError):
            parsed_pages.append({"raw": b})
    status = int(pages[0].get("status", 200))
    return {
        "ok": True,
        "status": status,
        "body": json.dumps({"pages": parsed_pages}, ensure_ascii=False),
    }


def run_site_fetch(
    spec: dict,
    plugin: SitePlugin | None,
    fetch_sync: Callable[[dict], dict],
    *,
    fetch_all: bool = False,
) -> dict:
    """Run one page or all pages.

    ``SitePlugin.after_fetch`` runs once at the end on every branch — the
    explicit *plugin* if provided, otherwise a bare :class:`SitePlugin`
    instance so a preset's declarative ``response_contract`` still applies
    even for JSON-only sites with no custom Python.
    """
    if not fetch_all:
        out = fetch_sync(_spec_for_page_fetch(spec))
        if "body" in out:
            out = (plugin or SitePlugin()).after_fetch(out, spec)
        return out

    if plugin_overrides_paginate(plugin):
        assert plugin is not None
        first = fetch_sync(_spec_for_page_fetch(spec))
        out = asyncio.run(_async_plugin_paginate_collect(plugin, spec, first, fetch_sync))
        if "body" in out:
            out = (plugin or SitePlugin()).after_fetch(out, spec)
        return out

    pagination = spec.get("pagination") or {}
    ptype = pagination.get("type", "none")
    if ptype in ("body_field", "offset"):
        try:
            merged_dict, status, pages_fetched = paginate_all_generic(spec, pagination, fetch_sync)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        out = {
            "ok": True,
            "status": status,
            "pages_fetched": pages_fetched,
            "body": json.dumps(merged_dict, ensure_ascii=False),
        }
        if "body" in out:
            out = (plugin or SitePlugin()).after_fetch(out, spec)
        return out

    out = fetch_sync(_spec_for_page_fetch(spec))
    if "body" in out:
        out = (plugin or SitePlugin()).after_fetch(out, spec)
    return out
