"""Apply AuthSnapshot to a browser tab and optional restore workflow (navigate, reload, verify)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from ziniao_mcp.cookie_vault import ensure_executable_snapshot, origin_of_url

_logger = logging.getLogger("ziniao-daemon")


async def apply_snapshot_to_tab(
    tab: Any,
    snap: dict[str, Any],
    *,
    tab_url: str,
    clear_cookies_first: bool,
    allow_origin_mismatch: bool,
    skip_executable_check: bool = False,
) -> dict[str, Any]:
    """Write snapshot cookies + storage into *tab*.

    Returns ``{"ok": True, ...counts}`` or ``{"error": "..."}``.
    """
    from nodriver import cdp  # pylint: disable=import-outside-toplevel

    if not skip_executable_check:
        try:
            ensure_executable_snapshot(snap)
        except ValueError as exc:
            return {"error": str(exc)}

    current_origin = origin_of_url(tab_url)
    snapshot_origin = origin_of_url(str(snap.get("page_url") or ""))
    if not allow_origin_mismatch and snapshot_origin and current_origin and current_origin != snapshot_origin:
        return {
            "error": (
                "snapshot origin does not match active tab; navigate to "
                f"{snapshot_origin} first or pass allow_origin_mismatch=true"
            ),
            "current_origin": current_origin,
            "snapshot_origin": snapshot_origin,
        }

    if clear_cookies_first:
        await tab.send(cdp.network.clear_browser_cookies())

    cookie_written = 0
    for c in snap.get("cookies") or []:
        if not isinstance(c, dict) or not c.get("name"):
            continue
        dom = str(c.get("domain") or "").strip() or None
        pth = str(c.get("path") or "/").strip() or None
        await tab.send(
            cdp.network.set_cookie(
                name=str(c["name"]),
                value=str(c.get("value", "")),
                domain=dom,
                path=pth,
                secure=bool(c["secure"]) if "secure" in c else None,
                http_only=bool(c.get("httpOnly")) if "httpOnly" in c else None,
            ),
        )
        cookie_written += 1

    loc = snap.get("local_storage") if isinstance(snap.get("local_storage"), dict) else {}
    ses = snap.get("session_storage") if isinstance(snap.get("session_storage"), dict) else {}
    for k, v in loc.items():
        await tab.evaluate(
            f"localStorage.setItem({json.dumps(str(k))}, {json.dumps(str(v))})",
            return_by_value=True,
        )
    for k, v in ses.items():
        await tab.evaluate(
            f"sessionStorage.setItem({json.dumps(str(k))}, {json.dumps(str(v))})",
            return_by_value=True,
        )

    return {
        "ok": True,
        "imported_cookies": cookie_written,
        "imported_local_storage_keys": len(loc),
        "imported_session_storage_keys": len(ses),
        "snapshot_origin": snapshot_origin,
        "current_origin": current_origin,
    }


async def wait_for_selector(tab: Any, selector: str, *, timeout_sec: float) -> bool:
    """Poll until ``document.querySelector(selector)`` is truthy or timeout."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(timeout_sec, 0.1)
    sel_js = json.dumps(selector)
    while loop.time() < deadline:
        found = await tab.evaluate(
            f"!!document.querySelector({sel_js})",
            return_by_value=True,
        )
        if found:
            return True
        await asyncio.sleep(0.2)
    return False


async def restore_tab_session(
    tab: Any,
    snap: dict[str, Any],
    *,
    navigate_url: str,
    default_snap_url: str,
    clear_cookies_first: bool,
    allow_origin_mismatch: bool,
    reload_after: bool,
    verify_selector: str,
    verify_timeout_sec: float,
    navigate_settle_sec: float = 2.0,
    reload_settle_sec: float = 1.0,
) -> dict[str, Any]:
    """Navigate (optional), import snapshot, reload (optional), verify selector (optional)."""
    from nodriver import cdp  # pylint: disable=import-outside-toplevel

    try:
        ensure_executable_snapshot(snap)
    except ValueError as exc:
        return {"ok": False, "restored": False, "verified": False, "error": str(exc)}

    target = (navigate_url or default_snap_url or "").strip()
    if target:
        _logger.info("cookie-vault restore: navigate to %s", target)
        try:
            await tab.send(cdp.page.navigate(url=target))
        except Exception as exc:  # pylint: disable=broad-except
            _logger.warning("cookie-vault restore: navigate failed: %s", exc)
            return {
                "ok": False,
                "restored": False,
                "verified": False,
                "error": f"navigate failed: {exc}",
                "phase": "navigate",
            }
        await tab.sleep(max(navigate_settle_sec, 0.0))

    tab_url = getattr(getattr(tab, "target", None), "url", "") or ""
    applied = await apply_snapshot_to_tab(
        tab,
        snap,
        tab_url=tab_url,
        clear_cookies_first=clear_cookies_first,
        allow_origin_mismatch=allow_origin_mismatch,
        skip_executable_check=True,
    )
    if applied.get("error"):
        return {
            "ok": False,
            "restored": False,
            "verified": False,
            "error": applied["error"],
            "current_origin": applied.get("current_origin"),
            "snapshot_origin": applied.get("snapshot_origin"),
        }

    if reload_after:
        try:
            await tab.send(cdp.page.reload())
        except Exception as exc:  # pylint: disable=broad-except
            _logger.warning("cookie-vault restore: reload failed: %s", exc)
            return {
                "ok": False,
                "restored": True,
                "verified": False,
                "error": f"reload failed: {exc}",
                "phase": "reload",
                "imported_cookies": applied["imported_cookies"],
                "imported_local_storage_keys": applied["imported_local_storage_keys"],
                "imported_session_storage_keys": applied["imported_session_storage_keys"],
            }
        await tab.sleep(max(reload_settle_sec, 0.0))

    verified = True
    verification: dict[str, Any] | None = None
    if verify_selector:
        ok = await wait_for_selector(tab, verify_selector, timeout_sec=verify_timeout_sec)
        verified = ok
        verification = {"type": "selector", "selector": verify_selector}
        if not ok:
            return {
                "ok": False,
                "restored": True,
                "verified": False,
                "error": "login verification failed",
                "verification": verification,
                "imported_cookies": applied["imported_cookies"],
                "imported_local_storage_keys": applied["imported_local_storage_keys"],
                "imported_session_storage_keys": applied["imported_session_storage_keys"],
            }

    return {
        "ok": True,
        "restored": True,
        "verified": verified,
        "verification": verification,
        "imported_cookies": applied["imported_cookies"],
        "imported_local_storage_keys": applied["imported_local_storage_keys"],
        "imported_session_storage_keys": applied["imported_session_storage_keys"],
        "snapshot_origin": applied.get("snapshot_origin"),
        "current_origin": applied.get("current_origin"),
    }
