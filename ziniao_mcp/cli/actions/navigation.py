"""Navigation action handlers: navigate, wait, back, forward, reload."""

from __future__ import annotations

from typing import Any


async def navigate(sm: Any, args: dict) -> dict:
    url = args.get("url", "")
    if not url:
        return {"error": "url is required"}
    from nodriver import cdp  # pylint: disable=import-outside-toplevel

    tab = sm.get_active_tab()
    await tab.send(cdp.page.navigate(url=url))
    await tab.sleep(1.0)
    return {"ok": True, "url": tab.target.url, "title": tab.target.title or ""}


async def wait(sm: Any, args: dict) -> dict:
    import asyncio  # pylint: disable=import-outside-toplevel
    from ...iframe import find_element  # pylint: disable=import-outside-toplevel

    selector = args.get("selector", "")
    state = args.get("state", "visible")
    timeout_ms = args.get("timeout", 30000)
    timeout_sec = timeout_ms / 1000
    tab = sm.get_active_tab()
    store = sm.get_active_session()

    if selector:
        if state in ("visible", "attached"):
            elem = await find_element(tab, selector, store, timeout=timeout_sec)
            if elem:
                return {"ok": True, "selector": selector, "state": state}
            return {"error": f"Timeout waiting for {selector}"}
        deadline = asyncio.get_event_loop().time() + timeout_sec
        while asyncio.get_event_loop().time() < deadline:
            try:
                elem = await find_element(tab, selector, store, timeout=0.5)
                if not elem:
                    return {"ok": True, "selector": selector, "state": state}
            except Exception:
                return {"ok": True, "selector": selector, "state": state}
            await asyncio.sleep(0.5)
        return {"error": f"Timeout waiting for {selector} to disappear"}
    await tab.sleep(min(timeout_sec, 5))
    return {"ok": True, "message": "Wait completed"}


# ---------------------------------------------------------------------------
# Navigation: back / forward / reload
# ---------------------------------------------------------------------------


def _parse_navigation_history(history: Any) -> tuple[list, int]:
    """Normalize CDP getNavigationHistory result (dict, tuple or object) to (entries, current_index)."""
    if hasattr(history, "current_index"):
        return (list(history.entries), int(history.current_index))
    if hasattr(history, "currentIndex"):
        return (list(history.entries), int(history.currentIndex))
    if isinstance(history, dict):
        entries = history.get("entries") or []
        idx = int(history.get("currentIndex", history.get("current_index", 0)))
        return (entries, idx)
    if isinstance(history, (tuple, list)) and len(history) >= 2:
        a, b = history[0], history[1]
        if isinstance(a, int) and isinstance(b, (list, tuple)):
            return (list(b), a)
        if isinstance(b, int) and isinstance(a, (list, tuple)):
            return (list(a), b)
    return ([], 0)


def _entry_id(entry: Any) -> int:
    """Get history entry id from object or dict."""
    if hasattr(entry, "id_"):
        return int(entry.id_)
    if hasattr(entry, "id"):
        return int(entry.id)
    if isinstance(entry, dict):
        return int(entry.get("id", entry.get("id_", 0)))
    return 0


async def back(sm: Any, args: dict) -> dict:
    from nodriver import cdp  # pylint: disable=import-outside-toplevel

    tab = sm.get_active_tab()
    raw = await tab.send(cdp.page.get_navigation_history())
    entries, current_index = _parse_navigation_history(raw)
    if current_index > 0:
        entry = entries[current_index - 1]
        await tab.send(cdp.page.navigate_to_history_entry(entry_id=_entry_id(entry)))
        await tab.sleep(0.5)
    return {"ok": True, "url": tab.target.url}


async def forward(sm: Any, args: dict) -> dict:
    from nodriver import cdp  # pylint: disable=import-outside-toplevel

    tab = sm.get_active_tab()
    raw = await tab.send(cdp.page.get_navigation_history())
    entries, current_index = _parse_navigation_history(raw)
    if current_index < len(entries) - 1:
        entry = entries[current_index + 1]
        await tab.send(cdp.page.navigate_to_history_entry(entry_id=_entry_id(entry)))
        await tab.sleep(0.5)
    return {"ok": True, "url": tab.target.url}


async def reload(sm: Any, args: dict) -> dict:
    from nodriver import cdp  # pylint: disable=import-outside-toplevel

    tab = sm.get_active_tab()
    ignore_cache = args.get("ignore_cache", False)
    await tab.send(cdp.page.reload(ignore_cache=ignore_cache))
    await tab.sleep(1.0)
    return {"ok": True, "url": tab.target.url}
