"""HTTP transport for site fetch: browser_fetch (via dispatch) vs direct_http from AuthSnapshot."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

import httpx

from ziniao_mcp.cookie_vault import apply_header_inject_from_snapshot, cookie_header_for_url
from ziniao_mcp.sites.request import decode_body_bytes

_logger = logging.getLogger("ziniao-mcp")

_SAFE_PROBE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def can_auto_probe_method(method: str) -> bool:
    """Whether ``transport:auto`` may try the actual request before fallback."""
    return method.upper() in _SAFE_PROBE_METHODS


def _has_header(headers: dict[str, str], name: str) -> bool:
    needle = name.lower()
    return any(k.lower() == needle for k in headers)


def direct_http_response_looks_successful(result: dict[str, Any]) -> bool:
    """Heuristic for ``transport: auto`` — conservative when unsure."""
    if result.get("error"):
        return False
    if not result.get("ok"):
        return False
    status = result.get("status")
    try:
        code = int(status) if status is not None else 0
    except (TypeError, ValueError):
        return False
    if code < 200 or code >= 400:
        return False
    ct = str(result.get("content_type", "")).lower()
    body = str(result.get("body", ""))[:4000].lower()
    if "text/html" in ct and ("<html" in body or "login" in body or "sign in" in body):
        return False
    return True


async def direct_http_fetch(
    args: dict[str, Any],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Perform the same logical request as ``_page_fetch_fetch`` using httpx + snapshot.

    * ``eval`` header_inject entries are ignored (browser-only).
    * ``Cookie`` header is merged from snapshot unless caller already set ``Cookie``.
    """
    url = args.get("url", "")
    if not url:
        return {"ok": False, "error": "url is required for fetch mode"}
    try:
        from ziniao_mcp.cookie_vault import ensure_executable_snapshot

        ensure_executable_snapshot(snapshot)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    method = str(args.get("method", "GET")).upper()
    raw_headers = args.get("headers") or {}
    if not isinstance(raw_headers, dict):
        return {"ok": False, "error": "headers must be a dict"}
    headers: dict[str, str] = {str(k): str(v) for k, v in raw_headers.items()}
    injections = args.get("header_inject") or []
    if not isinstance(injections, list):
        injections = []

    ua = str(snapshot.get("user_agent") or "").strip()
    if ua and "User-Agent" not in headers and "user-agent" not in {k.lower() for k in headers}:
        headers["User-Agent"] = ua

    cookies = snapshot.get("cookies") if isinstance(snapshot.get("cookies"), list) else []
    ch = cookie_header_for_url(url, [c for c in cookies if isinstance(c, dict)])
    if ch and "Cookie" not in headers and "cookie" not in {k.lower() for k in headers}:
        headers["Cookie"] = ch

    headers = apply_header_inject_from_snapshot(headers, injections, snapshot)

    body = args.get("body", "")
    content: str | bytes | None = None
    if body not in (None, "", b""):
        if isinstance(body, (dict, list)):
            content = json.dumps(body, ensure_ascii=False)
            if not _has_header(headers, "Content-Type"):
                headers["Content-Type"] = "application/json; charset=utf-8"
        else:
            content = str(body)

    timeout = float(args.get("_ziniao_direct_http_timeout") or 60.0)
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            resp = await client.request(method, url, headers=headers, content=content)
    except (httpx.HTTPError, OSError) as exc:
        _logger.debug("direct_http fetch failed: %s", exc)
        return {"ok": False, "error": f"direct_http: {exc}"}

    raw_bytes = resp.content
    ct = resp.headers.get("content-type", "") or ""
    body_str = decode_body_bytes(raw_bytes, ct)
    b64 = base64.b64encode(raw_bytes).decode("ascii")
    return {
        "ok": True,
        "status": resp.status_code,
        "statusText": resp.reason_phrase,
        "body": body_str,
        "body_b64": b64,
        "content_type": ct,
        "transport_used": "direct_http",
        "network_context_warning": (
            "direct_http does not reuse the browser/Ziniao network context "
            "unless the caller supplies an equivalent proxy/network layer."
        ),
    }
