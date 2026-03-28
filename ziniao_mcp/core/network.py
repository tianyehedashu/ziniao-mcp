"""Shared core: network route interception & HAR recording.

Uses CDP Fetch domain for request interception and Network domain for HAR.
Both CLI dispatch and MCP tools call these functions.
"""

from __future__ import annotations

import base64
import json as _json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..session import StoreSession

_logger = logging.getLogger("ziniao-network")


# ---------------------------------------------------------------------------
# URL pattern matching (compatible with agent-browser's glob-like patterns)
# ---------------------------------------------------------------------------

def _url_matches(url: str, pattern: str) -> bool:
    if pattern == "*":
        return True
    if "*" not in pattern:
        return pattern in url
    parts = pattern.split("*")
    parts = [p for p in parts if p]
    if not parts:
        return True
    if not pattern.startswith("*") and not url.startswith(parts[0]):
        return False
    if not pattern.endswith("*") and not url.endswith(parts[-1]):
        return False
    idx = 0
    for part in parts:
        found = url.find(part, idx)
        if found == -1:
            return False
        idx = found + len(part)
    return True


# ---------------------------------------------------------------------------
# Route: add / remove / list / resolve
# ---------------------------------------------------------------------------

async def add_route(
    tab: Any,
    store: "StoreSession",
    url_pattern: str,
    abort: bool = False,
    response_status: int = 200,
    response_body: str = "",
    response_content_type: str = "text/plain",
    response_headers: dict | None = None,
) -> dict:
    """Add a request interception route and enable CDP Fetch if needed."""
    from nodriver import cdp  # pylint: disable=import-outside-toplevel
    from ..session import RouteEntry  # pylint: disable=import-outside-toplevel

    entry = RouteEntry(
        url_pattern=url_pattern,
        abort=abort,
        response_status=response_status,
        response_body=response_body,
        response_content_type=response_content_type,
        response_headers=response_headers or {},
    )
    store.routes.append(entry)

    tab_id = id(tab)
    if tab_id not in store._fetch_tab_ids:  # pylint: disable=protected-access
        await tab.send(cdp.fetch.enable(
            patterns=[cdp.fetch.RequestPattern(url_pattern="*")],
        ))
        store._fetch_tab_ids.add(tab_id)  # pylint: disable=protected-access
        store.fetch_enabled = True

        async def _on_fetch_paused(event: cdp.fetch.RequestPaused):
            await _resolve_fetch(tab, store, event)

        tab.add_handler(cdp.fetch.RequestPaused, _on_fetch_paused)

    return {
        "ok": True,
        "url_pattern": url_pattern,
        "abort": abort,
        "active_routes": len(store.routes),
    }


async def remove_route(tab: Any, store: "StoreSession", url_pattern: str = "") -> dict:
    """Remove route(s). If url_pattern is empty, remove all routes."""
    from nodriver import cdp  # pylint: disable=import-outside-toplevel

    if url_pattern:
        before = len(store.routes)
        store.routes = [r for r in store.routes if r.url_pattern != url_pattern]
        removed = before - len(store.routes)
    else:
        removed = len(store.routes)
        store.routes.clear()

    if not store.routes and store.fetch_enabled:
        try:
            await tab.send(cdp.fetch.disable())
        except Exception:  # pylint: disable=broad-exception-caught
            _logger.debug("Fetch.disable failed (may be already disabled)")
        store.fetch_enabled = False
        store._fetch_tab_ids.clear()  # pylint: disable=protected-access

    return {
        "ok": True,
        "removed": removed,
        "remaining_routes": len(store.routes),
    }


def list_routes(store: "StoreSession") -> dict:
    """List all active route rules."""
    routes = []
    for r in store.routes:
        entry: dict[str, Any] = {"url_pattern": r.url_pattern, "abort": r.abort}
        if not r.abort:
            entry["response_status"] = r.response_status
            if r.response_body:
                entry["response_body_preview"] = r.response_body[:200]
        routes.append(entry)
    return {"routes": routes, "count": len(routes), "fetch_enabled": store.fetch_enabled}


async def _resolve_fetch(tab: Any, store: "StoreSession", event: Any) -> None:
    """Handle a Fetch.requestPaused event by matching against active routes."""
    from nodriver import cdp  # pylint: disable=import-outside-toplevel

    request_id = event.request_id
    request_url = event.request.url if event.request else ""

    for route in store.routes:
        if not _url_matches(request_url, route.url_pattern):
            continue

        if route.abort:
            try:
                await tab.send(cdp.fetch.fail_request(
                    request_id=request_id,
                    error_reason=cdp.network.ErrorReason("Failed"),
                ))
            except Exception:  # pylint: disable=broad-exception-caught
                _logger.debug("fetch.fail_request error for %s", request_url)
            return

        body_b64 = base64.b64encode(route.response_body.encode()).decode() if route.response_body else ""
        headers = [
            cdp.fetch.HeaderEntry(name="Content-Type", value=route.response_content_type),
        ]
        for k, v in route.response_headers.items():
            headers.append(cdp.fetch.HeaderEntry(name=k, value=v))

        try:
            await tab.send(cdp.fetch.fulfill_request(
                request_id=request_id,
                response_code=route.response_status,
                response_headers=headers,
                body=body_b64 if body_b64 else None,
            ))
        except Exception:  # pylint: disable=broad-exception-caught
            _logger.debug("fetch.fulfill_request error for %s", request_url)
        return

    try:
        await tab.send(cdp.fetch.continue_request(request_id=request_id))
    except Exception:  # pylint: disable=broad-exception-caught
        _logger.debug("fetch.continue_request error for %s", request_url)


# ---------------------------------------------------------------------------
# HAR: start / stop / export
# ---------------------------------------------------------------------------

def har_start(store: "StoreSession") -> dict:
    """Start HAR recording. Uses existing network listeners to collect data."""
    if store.har_recording:
        return {"ok": True, "message": "HAR recording already active"}
    store.har_recording = True
    store.har_start_time = time.time()
    return {"ok": True, "message": "HAR recording started"}


def har_stop(store: "StoreSession", path: str = "") -> dict:
    """Stop HAR recording and export to file."""
    if not store.har_recording:
        return {"error": "HAR recording is not active"}

    store.har_recording = False
    entries = _build_har_entries(store)

    har = {
        "log": {
            "version": "1.2",
            "creator": {"name": "ziniao", "version": "1.0"},
            "entries": entries,
        }
    }

    if not path:
        har_dir = Path.home() / ".ziniao" / "har"
        har_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = str(har_dir / f"har-{ts}.har")

    with open(path, "w", encoding="utf-8") as f:
        _json.dump(har, f, ensure_ascii=False, indent=2)

    collected = [r for r in store.network_requests if r.timestamp >= store.har_start_time]
    store.har_start_time = 0.0

    return {
        "ok": True,
        "path": path,
        "entries": len(entries),
        "total_requests_in_period": len(collected),
    }


def _build_har_entries(store: "StoreSession") -> list[dict]:
    """Convert collected NetworkRequests into HAR 1.2 entries."""
    entries = []
    for req in store.network_requests:
        if req.timestamp < store.har_start_time:
            continue

        started = datetime.fromtimestamp(req.timestamp, tz=timezone.utc).isoformat()
        total_time = 0.0
        if req.finished_timestamp > 0:
            total_time = round((req.finished_timestamp - req.timestamp) * 1000, 2)

        req_headers = [{"name": k, "value": v} for k, v in req.request_headers.items()]
        resp_headers = [{"name": k, "value": v} for k, v in req.response_headers.items()]

        req_ct = ""
        for h in req_headers:
            if h.get("name", "").lower() == "content-type":
                req_ct = str(h.get("value") or "")
                break
        if not req_ct:
            req_ct = "application/octet-stream"

        req_obj: dict = {
            "method": req.method,
            "url": req.url,
            "httpVersion": "HTTP/1.1",
            "cookies": [],
            "headers": req_headers,
            "queryString": [],
            "headersSize": -1,
            "bodySize": -1,
        }
        if getattr(req, "post_data", None):
            req_obj["postData"] = {"mimeType": req_ct, "text": req.post_data}
            req_obj["bodySize"] = len(req.post_data.encode("utf-8", errors="replace"))

        resp_mime = req.response_headers.get("content-type", "")
        content_obj: dict = {
            "size": req.encoded_data_length,
            "mimeType": resp_mime,
        }
        if getattr(req, "response_body", None):
            content_obj["text"] = req.response_body

        entry = {
            "startedDateTime": started,
            "time": total_time,
            "request": req_obj,
            "response": {
                "status": req.status or 0,
                "statusText": req.status_text or "",
                "httpVersion": "HTTP/1.1",
                "cookies": [],
                "headers": resp_headers,
                "content": content_obj,
                "redirectURL": "",
                "headersSize": -1,
                "bodySize": req.encoded_data_length,
            },
            "cache": {},
            "timings": {
                "send": 0,
                "wait": total_time,
                "receive": 0,
            },
            "_resourceType": req.resource_type,
        }
        entries.append(entry)
    return entries
