"""Small raw-CDP helpers for places where generated schema parsing is brittle."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib import request

import websockets


def normalize_cookie(cookie: dict[str, Any]) -> dict[str, Any]:
    """Normalize a raw CDP cookie JSON object into CookieVault snapshot shape."""
    return {
        "name": str(cookie.get("name") or ""),
        "value": str(cookie.get("value") or ""),
        "domain": str(cookie.get("domain") or ""),
        "path": str(cookie.get("path") or "/"),
        "secure": bool(cookie.get("secure", False)),
        "httpOnly": bool(cookie.get("httpOnly", cookie.get("http_only", False))),
        "sameSite": str(cookie.get("sameSite", cookie.get("same_site", "")) or ""),
    }


async def call(cdp_port: int, page_url: str, method: str, params: dict[str, Any], *, timeout: float = 5.0) -> dict:
    """Issue one bounded CDP call on a fresh page WebSocket connection."""

    def _load_targets() -> list[Any]:
        req = request.Request(f"http://127.0.0.1:{cdp_port}/json/list")
        with request.urlopen(req, timeout=timeout) as resp:  # nosec B310
            data = json.loads(resp.read().decode("utf-8"))
        return data if isinstance(data, list) else []

    targets = await asyncio.to_thread(_load_targets)
    page_targets = [t for t in targets if isinstance(t, dict) and t.get("type") == "page"]
    candidates = page_targets or [t for t in targets if isinstance(t, dict)]
    chosen = next((t for t in candidates if str(t.get("url") or "") == page_url), None)
    chosen = chosen or next((t for t in candidates if str(t.get("webSocketDebuggerUrl") or "")), None)
    ws_url = str((chosen or {}).get("webSocketDebuggerUrl") or "")
    if not ws_url:
        raise RuntimeError(f"No page webSocketDebuggerUrl on CDP port {cdp_port}")

    async with websockets.connect(ws_url, max_size=None) as ws:
        await ws.send(json.dumps({"id": 1, "method": method, "params": params}))
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(timeout, 0.1)
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError(f"raw CDP {method} timed out after {timeout}s")
            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            payload = json.loads(raw)
            if payload.get("id") != 1:
                continue
            if "error" in payload:
                raise RuntimeError(f"raw CDP {method} error: {payload['error']!r}")
            result = payload.get("result")
            return result if isinstance(result, dict) else {}


async def get_cookies_for_url(cdp_port: int, page_url: str, *, timeout: float = 10.0) -> list[dict[str, Any]]:
    """Read cookies as raw CDP JSON and normalize only the fields ziniao needs."""
    raw = await call(
        cdp_port,
        page_url,
        "Network.getCookies",
        {"urls": [page_url]} if page_url else {},
        timeout=timeout,
    )
    return [
        normalize_cookie(cookie)
        for cookie in (raw.get("cookies") or [])
        if isinstance(cookie, dict) and cookie.get("name")
    ]
