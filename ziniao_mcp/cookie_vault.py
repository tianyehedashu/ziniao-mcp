"""Auth snapshot (cookie + storage + UA) export/import for CookieVault.

On-disk format is JSON with ``schema_version`` for forward compatibility.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


def _mask(s: str, keep: int = 6) -> str:
    if not s:
        return ""
    if len(s) <= keep:
        return "***"
    return s[:keep] + "***"


def redact_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    """Return a deep-copied snapshot safe for logs / sharing (truncated secrets)."""
    import copy

    out = copy.deepcopy(data)
    out["redacted"] = True
    cookies = out.get("cookies")
    if isinstance(cookies, list):
        for c in cookies:
            if isinstance(c, dict) and "value" in c:
                c["value"] = _mask(str(c.get("value", "")))
    for key in ("local_storage", "session_storage"):
        store = out.get(key)
        if isinstance(store, dict):
            for k, v in list(store.items()):
                if isinstance(v, str):
                    store[k] = _mask(v)
    return out


def load_auth_snapshot(path: Path) -> dict[str, Any]:
    """Load and validate an auth snapshot from disk."""
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("snapshot root must be a JSON object")
    ver = int(data.get("schema_version", 0))
    if ver != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {ver!r} (expected {SCHEMA_VERSION})")
    if "cookies" not in data or not isinstance(data["cookies"], list):
        raise ValueError("snapshot missing cookies array")
    return data


def ensure_executable_snapshot(data: dict[str, Any]) -> None:
    """Reject snapshots that are safe for sharing but invalid for replay."""
    if data.get("redacted") is True:
        raise ValueError("redacted snapshot cannot be imported or used for direct_http")


def save_auth_snapshot(path: Path, data: dict[str, Any]) -> None:
    """Write snapshot atomically (write temp + replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)


def build_empty_snapshot(
    *,
    profile_id: str = "",
    site: str = "",
    page_url: str = "",
    user_agent: str = "",
    backend_type: str = "",
    risk_level: str = "unknown",
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "profile_id": profile_id,
        "site": site,
        "captured_at": time.time(),
        "risk_level": risk_level,
        "page_url": page_url,
        "user_agent": user_agent,
        "cookies": [],
        "local_storage": {},
        "session_storage": {},
        "backend_type": backend_type,
    }


def _host_matches_cookie_domain(host: str, cookie_domain: str) -> bool:
    raw = cookie_domain or ""
    cd = raw.lstrip(".").lower()
    host = host.lower()
    if not cd:
        return True
    if raw.startswith("."):
        return host == cd or host.endswith("." + cd)
    # Chromium exposes host-only cookies without a leading dot; do not leak
    # them to sibling subdomains when replaying outside the browser.
    return host == cd


def _path_matches(cookie_path: str, req_path: str) -> bool:
    cp = cookie_path or "/"
    if not req_path.startswith("/"):
        req_path = "/" + req_path
    if cp == "/":
        return True
    if req_path == cp:
        return True
    if cp.endswith("/"):
        return req_path.startswith(cp)
    return req_path.startswith(cp + "/")


def cookie_header_for_url(url: str, cookies: list[dict[str, Any]]) -> str:
    """Build a ``Cookie`` request header value from snapshot cookies (best-effort RFC match)."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname or ""
    path = parsed.path or "/"
    scheme = parsed.scheme.lower()
    parts: list[str] = []
    for c in cookies:
        if not isinstance(c, dict):
            continue
        name = c.get("name")
        if not name:
            continue
        domain = str(c.get("domain", ""))
        cpath = str(c.get("path", "/"))
        if not _host_matches_cookie_domain(host, domain):
            continue
        if not _path_matches(cpath, path):
            continue
        if bool(c.get("secure")) and scheme not in ("https", "wss"):
            continue
        val = str(c.get("value", ""))
        parts.append(f"{name}={val}")
    return "; ".join(parts)


def apply_header_inject_from_snapshot(
    headers: dict[str, str],
    injections: list[dict[str, Any]],
    snapshot: dict[str, Any],
) -> dict[str, str]:
    """Apply ``header_inject`` using snapshot storage/cookie map (no ``eval`` — skipped)."""
    out = dict(headers)
    local = snapshot.get("local_storage") if isinstance(snapshot.get("local_storage"), dict) else {}
    session = snapshot.get("session_storage") if isinstance(snapshot.get("session_storage"), dict) else {}
    cookie_map: dict[str, str] = {}
    for c in snapshot.get("cookies") or []:
        if isinstance(c, dict) and c.get("name"):
            cookie_map[str(c["name"])] = str(c.get("value", ""))
    for inj in injections:
        if not isinstance(inj, dict):
            continue
        header = inj.get("header")
        if not header:
            continue
        source = inj.get("source", "")
        val: str | None = None
        if source == "cookie":
            key = inj.get("key", "")
            val = cookie_map.get(str(key))
        elif source == "localStorage":
            key = inj.get("key", "")
            v = local.get(str(key))
            val = None if v is None else str(v)
        elif source == "sessionStorage":
            key = inj.get("key", "")
            v = session.get(str(key))
            val = None if v is None else str(v)
        elif source == "eval":
            continue
        if val is None:
            continue
        transform = inj.get("transform")
        if transform and isinstance(transform, str):
            val = transform.replace("${value}", val)
        out[str(header)] = val
    return out
