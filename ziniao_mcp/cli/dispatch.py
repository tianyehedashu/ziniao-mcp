"""Command dispatch: map daemon requests to SessionManager / tool operations."""

from __future__ import annotations

import json
import logging
from typing import Any

_logger = logging.getLogger("ziniao-daemon")


async def dispatch(sm: Any, request: dict) -> dict:
    """Dispatch a CLI request to the appropriate SessionManager operation.

    The *request* dict has keys: ``command``, ``args``, and optionally
    ``target_session``.  When ``target_session`` is set, the dispatcher
    temporarily points the active session to that target for the duration
    of the command, then restores the original active session afterwards.
    """
    command = request.get("command", "")
    args: dict = request.get("args") or {}
    target = request.get("target_session")

    if command == "quit":
        return await _cmd_quit(sm)

    original_active = sm._active_store_id
    if target:
        if target not in sm._stores:
            return {"error": f"Session '{target}' not found. Use 'session list' to see available sessions."}
        sm._active_store_id = target

    try:
        result = await _execute(sm, command, args)
    except Exception as exc:
        _logger.exception("Command '%s' failed", command)
        result = {"error": str(exc)}
    finally:
        if target:
            sm._active_store_id = original_active

    return result


async def _cmd_quit(sm: Any) -> dict:
    """Graceful daemon shutdown."""
    try:
        await sm.cleanup()
    except Exception:
        _logger.exception("Error during quit cleanup")
    import asyncio  # pylint: disable=import-outside-toplevel
    loop = asyncio.get_running_loop()
    loop.call_soon(loop.stop)
    return {"ok": True, "message": "Daemon shutting down"}


async def _execute(sm: Any, command: str, args: dict) -> dict:  # noqa: C901, PLR0911, PLR0912
    handler = _COMMANDS.get(command)
    if handler:
        return await handler(sm, args)
    return {"error": f"Unknown command: {command}"}


# ---------------------------------------------------------------------------
# Store commands
# ---------------------------------------------------------------------------

async def _list_stores(sm: Any, args: dict) -> dict:
    from ..session import SessionManager  # pylint: disable=import-outside-toplevel
    opened_only = args.get("opened_only", False)
    open_stores = await SessionManager.get_persisted_stores()
    open_ids = {s["store_id"] for s in open_stores}

    if opened_only:
        return {"stores": open_stores, "count": len(open_stores)}

    try:
        all_stores = await sm.list_stores()
    except Exception as exc:
        return {"error": str(exc)}

    result = []
    for s in all_stores:
        store_id = s.get("browserOauth") or s.get("browserId") or ""
        result.append({
            "browserId": s.get("browserId"),
            "browserOauth": s.get("browserOauth"),
            "browserName": s.get("browserName"),
            "siteId": s.get("siteId"),
            "siteName": s.get("siteName"),
            "is_open": store_id in open_ids,
        })
    return {"stores": result, "count": len(result)}


async def _open_store(sm: Any, args: dict) -> dict:
    store_id = args.get("store_id", "")
    if not store_id:
        return {"error": "store_id is required"}
    ss = await sm.open_store(store_id)
    result: dict[str, Any] = {
        "ok": True,
        "store_id": ss.store_id,
        "store_name": ss.store_name,
        "cdp_port": ss.cdp_port,
        "tabs": len(ss.tabs),
    }
    if ss.launcher_page:
        result["launcher_page"] = ss.launcher_page
    return result


async def _close_store(sm: Any, args: dict) -> dict:
    store_id = args.get("store_id", "")
    if not store_id:
        return {"error": "store_id is required"}
    await sm.close_store(store_id)
    return {"ok": True, "store_id": store_id, "remaining": sm.get_open_store_ids()}


async def _start_client(sm: Any, args: dict) -> dict:
    msg = await sm.start_client()
    return {"ok": True, "message": msg}


async def _stop_client(sm: Any, args: dict) -> dict:
    await sm.stop_client()
    return {"ok": True, "message": "Ziniao client stopped"}


# ---------------------------------------------------------------------------
# Chrome commands
# ---------------------------------------------------------------------------

async def _launch_chrome(sm: Any, args: dict) -> dict:
    ss = await sm.launch_chrome(
        name=args.get("name", ""),
        executable_path=args.get("executable_path", ""),
        cdp_port=args.get("cdp_port", 0),
        user_data_dir=args.get("user_data_dir", ""),
        headless=args.get("headless", False),
        url=args.get("url", ""),
    )
    return {
        "ok": True,
        "session_id": ss.store_id,
        "name": ss.store_name,
        "cdp_port": ss.cdp_port,
        "tabs": len(ss.tabs),
    }


async def _connect_chrome(sm: Any, args: dict) -> dict:
    cdp_port = args.get("cdp_port", 0)
    if not cdp_port:
        return {"error": "cdp_port is required"}
    ss = await sm.connect_chrome(cdp_port=cdp_port, name=args.get("name", ""))
    return {
        "ok": True,
        "session_id": ss.store_id,
        "name": ss.store_name,
        "cdp_port": ss.cdp_port,
        "tabs": len(ss.tabs),
    }


async def _list_chrome(sm: Any, args: dict) -> dict:
    sessions = sm.list_chrome_sessions()
    return {"sessions": sessions, "count": len(sessions)}


async def _close_chrome(sm: Any, args: dict) -> dict:
    session_id = args.get("session_id", "")
    if not session_id:
        return {"error": "session_id is required"}
    await sm.close_chrome(session_id)
    return {"ok": True, "session_id": session_id}


# ---------------------------------------------------------------------------
# Session commands
# ---------------------------------------------------------------------------

async def _session_list(sm: Any, args: dict) -> dict:
    sessions = sm.list_all_sessions()
    return {"active": sm.active_session_id, "sessions": sessions, "count": len(sessions)}


async def _session_switch(sm: Any, args: dict) -> dict:
    session_id = args.get("session_id", "")
    if not session_id:
        return {"error": "session_id is required"}
    s = sm.switch_session(session_id)
    return {"ok": True, "active": s.store_id, "name": s.store_name, "type": s.backend_type}


async def _session_info(sm: Any, args: dict) -> dict:
    session_id = args.get("session_id", "")
    if not session_id:
        return {"error": "session_id is required"}
    return sm.get_session_info(session_id)


# ---------------------------------------------------------------------------
# Navigation commands
# ---------------------------------------------------------------------------

async def _navigate(sm: Any, args: dict) -> dict:
    url = args.get("url", "")
    if not url:
        return {"error": "url is required"}
    from nodriver import cdp  # pylint: disable=import-outside-toplevel
    tab = sm.get_active_tab()
    await tab.send(cdp.page.navigate(url=url))
    await tab.sleep(1.0)
    return {"ok": True, "url": tab.target.url, "title": tab.target.title or ""}


async def _tab(sm: Any, args: dict) -> dict:
    from ziniao_webdriver.cdp_tabs import filter_tabs as _filter_tabs  # pylint: disable=import-outside-toplevel
    action = args.get("action", "list")
    store = sm.get_active_session()

    if action == "list":
        store.tabs = _filter_tabs(store.browser.tabs)
        result = []
        for i, t in enumerate(store.tabs):
            result.append({
                "index": i, "url": t.target.url,
                "title": t.target.title or "", "is_active": i == store.active_tab_index,
            })
        return {"tabs": result, "count": len(result)}

    if action == "switch":
        store.tabs = _filter_tabs(store.browser.tabs)
        idx = args.get("page_index", -1)
        if idx < 0 or idx >= len(store.tabs):
            return {"error": f"Invalid tab index {idx}. Total: {len(store.tabs)}"}
        store.active_tab_index = idx
        store.iframe_context = None
        t = store.tabs[idx]
        await t.bring_to_front()
        await sm.setup_tab_listeners(store, t)
        return {"ok": True, "index": idx, "url": t.target.url, "title": t.target.title or ""}

    if action == "new":
        target_url = args.get("url", "") or "about:blank"
        new_tab = await store.browser.get(target_url, new_tab=True)
        store.tabs = _filter_tabs(store.browser.tabs)
        store.active_tab_index = len(store.tabs) - 1
        store.iframe_context = None
        await sm.setup_tab_listeners(store, new_tab)
        return {"ok": True, "index": store.active_tab_index, "url": new_tab.target.url, "total": len(store.tabs)}

    if action == "close":
        import asyncio  # pylint: disable=import-outside-toplevel
        store.tabs = _filter_tabs(store.browser.tabs)
        idx = store.active_tab_index if args.get("page_index", -1) == -1 else args.get("page_index", 0)
        if idx < 0 or idx >= len(store.tabs):
            return {"error": f"Invalid tab index {idx}"}
        closed_url = store.tabs[idx].target.url
        await store.tabs[idx].close()
        await asyncio.sleep(0.3)
        store.tabs = _filter_tabs(store.browser.tabs)
        if store.active_tab_index >= len(store.tabs):
            store.active_tab_index = max(0, len(store.tabs) - 1)
        store.iframe_context = None
        return {"ok": True, "closed_url": closed_url, "remaining": len(store.tabs)}

    return {"error": f"Unknown tab action: {action}"}


async def _frame(sm: Any, args: dict) -> dict:
    action = args.get("action", "list")
    tab = sm.get_active_tab()
    store = sm.get_active_session()

    if action == "list":
        from ..iframe import collect_frames  # pylint: disable=import-outside-toplevel
        frames = await collect_frames(tab)
        return {"frames": frames}
    if action == "switch":
        from ..iframe import switch_to_frame  # pylint: disable=import-outside-toplevel
        selector = args.get("selector", "")
        if not selector:
            return {"error": "selector is required for frame switch"}
        ctx = await switch_to_frame(tab, selector)
        store.iframe_context = ctx
        return {"ok": True, "frame_id": ctx.frame_id, "url": ctx.url}
    if action == "main":
        store.iframe_context = None
        return {"ok": True, "message": "Switched to main document"}
    return {"error": f"Unknown frame action: {action}"}


async def _wait(sm: Any, args: dict) -> dict:
    import asyncio  # pylint: disable=import-outside-toplevel
    from ..iframe import find_element  # pylint: disable=import-outside-toplevel
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
# Interaction commands
# ---------------------------------------------------------------------------

async def _click(sm: Any, args: dict) -> dict:
    from ..iframe import find_element  # pylint: disable=import-outside-toplevel
    from .._interaction_helpers import dispatch_click  # pylint: disable=import-outside-toplevel
    selector = args.get("selector", "")
    if not selector:
        return {"error": "selector is required"}
    tab = sm.get_active_tab()
    store = sm.get_active_session()
    elem = await find_element(tab, selector, store, timeout=10)
    if not elem:
        return {"error": f"Element not found: {selector}"}
    await dispatch_click(tab, selector, elem, sm)
    return {"ok": True, "clicked": selector}


async def _fill(sm: Any, args: dict) -> dict:
    from ..iframe import find_element  # pylint: disable=import-outside-toplevel
    from .._interaction_helpers import dispatch_fill  # pylint: disable=import-outside-toplevel
    selector = args.get("selector", "")
    value = args.get("value", "")
    fields_json = args.get("fields_json", "")

    tab = sm.get_active_tab()
    store = sm.get_active_session()

    if fields_json:
        fields = json.loads(fields_json)
    elif selector:
        fields = [{"selector": selector, "value": value}]
    else:
        return {"error": "selector+value or fields_json is required"}

    for f in fields:
        elem = await find_element(tab, f["selector"], store, timeout=10)
        if not elem:
            return {"error": f"Element not found: {f['selector']}"}
        await dispatch_fill(tab, f["selector"], f["value"], elem, sm)
    return {"ok": True, "filled": len(fields)}


async def _type_text(sm: Any, args: dict) -> dict:
    from ..iframe import find_element  # pylint: disable=import-outside-toplevel
    from .._interaction_helpers import dispatch_type  # pylint: disable=import-outside-toplevel
    text = args.get("text", "")
    selector = args.get("selector", "")
    tab = sm.get_active_tab()
    store = sm.get_active_session()
    elem = None
    if selector:
        elem = await find_element(tab, selector, store, timeout=10)
    await dispatch_type(tab, text, selector, elem, sm)
    return {"ok": True, "typed": text}


async def _press_key(sm: Any, args: dict) -> dict:
    from nodriver import cdp  # pylint: disable=import-outside-toplevel
    from ..tools._keys import parse_key  # pylint: disable=import-outside-toplevel
    key = args.get("key", "")
    if not key:
        return {"error": "key is required"}
    tab = sm.get_active_tab()
    actual_key, vk, modifiers = parse_key(key)
    await tab.send(cdp.input_.dispatch_key_event("rawKeyDown", windows_virtual_key_code=vk, modifiers=modifiers, key=actual_key))
    await tab.send(cdp.input_.dispatch_key_event("keyUp", windows_virtual_key_code=vk, modifiers=modifiers, key=actual_key))
    return {"ok": True, "pressed": key}


async def _hover(sm: Any, args: dict) -> dict:
    from ..iframe import find_element  # pylint: disable=import-outside-toplevel
    from .._interaction_helpers import dispatch_hover  # pylint: disable=import-outside-toplevel
    selector = args.get("selector", "")
    if not selector:
        return {"error": "selector is required"}
    tab = sm.get_active_tab()
    store = sm.get_active_session()
    elem = await find_element(tab, selector, store, timeout=10)
    if not elem:
        return {"error": f"Element not found: {selector}"}
    await dispatch_hover(tab, selector, elem, sm)
    return {"ok": True, "hovered": selector}


async def _drag(sm: Any, args: dict) -> dict:
    from ..iframe import find_element  # pylint: disable=import-outside-toplevel
    src_sel = args.get("source_selector", "")
    tgt_sel = args.get("target_selector", "")
    if not src_sel or not tgt_sel:
        return {"error": "source_selector and target_selector are required"}
    tab = sm.get_active_tab()
    store = sm.get_active_session()
    src = await find_element(tab, src_sel, store, timeout=10)
    tgt = await find_element(tab, tgt_sel, store, timeout=10)
    if not src or not tgt:
        return {"error": "Source or target element not found"}
    src_pos = await src.get_position()
    tgt_pos = await tgt.get_position()
    if not src_pos or not tgt_pos:
        return {"error": "Failed to get element positions"}
    await tab.mouse_drag(src_pos.center, tgt_pos.center)
    return {"ok": True, "dragged": f"{src_sel} -> {tgt_sel}"}


async def _upload(sm: Any, args: dict) -> dict:
    from ..iframe import find_element  # pylint: disable=import-outside-toplevel
    selector = args.get("selector", "")
    file_paths = args.get("file_paths", [])
    if not selector or not file_paths:
        return {"error": "selector and file_paths are required"}
    tab = sm.get_active_tab()
    store = sm.get_active_session()
    elem = await find_element(tab, selector, store, timeout=10)
    if not elem:
        return {"error": f"File input not found: {selector}"}
    await elem.send_file(*file_paths)
    return {"ok": True, "uploaded": len(file_paths)}


async def _handle_dialog(sm: Any, args: dict) -> dict:
    action = args.get("action", "accept")
    text = args.get("text", "")
    store = sm.get_active_session()
    store.dialog_action = action
    store.dialog_text = text
    return {"ok": True, "dialog_action": action}


# ---------------------------------------------------------------------------
# Info commands
# ---------------------------------------------------------------------------

async def _snapshot(sm: Any, args: dict) -> dict:
    tab = sm.get_active_tab()
    store = sm.get_active_session()
    if store.iframe_context:
        from ..iframe import eval_in_frame  # pylint: disable=import-outside-toplevel
        html = await eval_in_frame(tab, store.iframe_context.context_id, "document.documentElement.outerHTML")
        return {"ok": True, "html": html or ""}
    html = await tab.get_content()
    return {"ok": True, "html": html}


async def _screenshot(sm: Any, args: dict) -> dict:
    from nodriver import cdp  # pylint: disable=import-outside-toplevel
    selector = args.get("selector", "")
    full_page = args.get("full_page", False)
    tab = sm.get_active_tab()
    store = sm.get_active_session()

    if selector:
        from ..iframe import find_element  # pylint: disable=import-outside-toplevel
        elem = await find_element(tab, selector, store, timeout=10)
        if not elem:
            return {"error": f"Element not found: {selector}"}
        pos = await elem.get_position()
        if not pos:
            return {"error": f"Failed to get position: {selector}"}
        clip = cdp.page.Viewport(x=pos.x, y=pos.y, width=pos.width, height=pos.height, scale=1)
        data = await tab.send(cdp.page.capture_screenshot(format_="png", clip=clip))
    else:
        data = await tab.send(cdp.page.capture_screenshot(format_="png", capture_beyond_viewport=full_page))
    if not data:
        return {"error": "Screenshot failed"}
    return {"ok": True, "data": f"data:image/png;base64,{data}"}


async def _eval(sm: Any, args: dict) -> dict:
    script = args.get("script", "")
    if not script:
        return {"error": "script is required"}
    tab = sm.get_active_tab()
    store = sm.get_active_session()
    if store.iframe_context:
        from ..iframe import eval_in_frame  # pylint: disable=import-outside-toplevel
        result = await eval_in_frame(tab, store.iframe_context.context_id, script)
    else:
        result = await tab.evaluate(script, return_by_value=True)
    return {"ok": True, "result": result}


async def _console(sm: Any, args: dict) -> dict:
    store = sm.get_active_session()
    message_id = args.get("message_id", 0)
    level = args.get("level", "")
    limit = args.get("limit", 50)

    if message_id:
        for m in store.console_messages:
            if m.id == message_id:
                return {"id": m.id, "level": m.level, "text": m.text, "timestamp": m.timestamp}
        return {"error": f"Message ID not found: {message_id}"}

    messages = store.console_messages
    if level:
        messages = [m for m in messages if m.level == level]
    return {"messages": [{"id": m.id, "level": m.level, "text": m.text[:500]} for m in list(messages)[-limit:]]}


async def _network(sm: Any, args: dict) -> dict:
    store = sm.get_active_session()
    request_id = args.get("request_id", 0)
    url_pattern = args.get("url_pattern", "")
    limit = args.get("limit", 50)

    if request_id:
        for req in store.network_requests:
            if req.id == request_id:
                return {
                    "id": req.id, "url": req.url, "method": req.method,
                    "status": req.status, "status_text": req.status_text,
                    "resource_type": req.resource_type,
                    "request_headers": req.request_headers,
                    "response_headers": req.response_headers,
                    "post_data": getattr(req, "post_data", "") or "",
                    "response_body": getattr(req, "response_body", "") or "",
                }
        return {"error": f"Request ID not found: {request_id}"}

    reqs = store.network_requests
    if url_pattern:
        reqs = [r for r in reqs if url_pattern in r.url]
    return {"requests": [
        {
            "id": r.id, "method": r.method, "url": r.url[:200], "status": r.status,
            "resource_type": r.resource_type,
            "has_post_data": bool(getattr(r, "post_data", None)),
            "has_response_body": bool(getattr(r, "response_body", None)),
        }
        for r in list(reqs)[-limit:]
    ]}


async def _network_route(sm: Any, args: dict) -> dict:
    url_pattern = args.get("url_pattern", "")
    if not url_pattern:
        return {"error": "url_pattern is required"}
    from ..core.network import add_route  # pylint: disable=import-outside-toplevel
    return await add_route(
        sm.get_active_tab(), sm.get_active_session(),
        url_pattern=url_pattern,
        abort=args.get("abort", False),
        response_status=args.get("response_status", 200),
        response_body=args.get("response_body", ""),
        response_content_type=args.get("response_content_type", "text/plain"),
        response_headers=args.get("response_headers") or {},
    )


async def _network_unroute(sm: Any, args: dict) -> dict:
    from ..core.network import remove_route  # pylint: disable=import-outside-toplevel
    return await remove_route(
        sm.get_active_tab(), sm.get_active_session(),
        url_pattern=args.get("url_pattern", ""),
    )


async def _network_routes(sm: Any, args: dict) -> dict:
    from ..core.network import list_routes  # pylint: disable=import-outside-toplevel
    return list_routes(sm.get_active_session())


async def _har_start(sm: Any, args: dict) -> dict:
    from ..core.network import har_start  # pylint: disable=import-outside-toplevel
    return har_start(sm.get_active_session())


async def _har_stop(sm: Any, args: dict) -> dict:
    from ..core.network import har_stop  # pylint: disable=import-outside-toplevel
    return har_stop(sm.get_active_session(), path=args.get("path", ""))


# ---------------------------------------------------------------------------
# Recorder commands
# ---------------------------------------------------------------------------

async def _recorder(sm: Any, args: dict) -> dict:
    from ..tools.recorder import (  # pylint: disable=import-outside-toplevel
        _do_start,
        _do_stop,
        _do_replay,
        _do_list,
        _do_delete,
        _do_view,
        _do_status,
    )
    action = args.get("action", "start")
    name = args.get("name", "")
    actions_json = args.get("actions_json", "")
    speed = args.get("speed", 1.0)
    metadata_only = bool(args.get("metadata_only", False))
    force = bool(args.get("force", False))
    reuse_tab = bool(args.get("reuse_tab", False))
    auto_session = args.get("auto_session", True)
    if not isinstance(auto_session, bool):
        auto_session = bool(auto_session)
    engine = str(args.get("engine", "dom2") or "dom2")
    scope = str(args.get("scope", "active") or "active")
    try:
        max_tabs = int(args.get("max_tabs", 20))
    except (TypeError, ValueError):
        max_tabs = 20
    emit = str(args.get("emit", "nodriver") or "nodriver")
    record_secrets = args.get("record_secrets", True)
    if not isinstance(record_secrets, bool):
        record_secrets = bool(record_secrets)

    async def _inject(tab):
        from ..tools.recorder import _RECORDER_JS  # pylint: disable=import-outside-toplevel
        await tab.evaluate(_RECORDER_JS, await_promise=False)

    async def _collect(tab):
        from ..tools.recorder import _COLLECT_JS  # pylint: disable=import-outside-toplevel
        raw = await tab.evaluate(_COLLECT_JS, return_by_value=True)
        if isinstance(raw, str):
            return json.loads(raw)
        return []

    async def _clear(tab):
        from ..tools.recorder import _CLEAR_JS  # pylint: disable=import-outside-toplevel
        await tab.evaluate(_CLEAR_JS, await_promise=False)

    def _nav_setup(store, tab):
        from ..tools.recorder import _setup_navigation_reinjection  # pylint: disable=import-outside-toplevel

        _setup_navigation_reinjection(store, tab, _inject)

    if action == "start":
        raw_result = await _do_start(
            sm, _inject, _nav_setup,
            engine=engine, scope=scope, max_tabs=max_tabs,
        )
        return json.loads(raw_result)
    if action == "stop":
        from ..recording.ir import parse_emit  # pylint: disable=import-outside-toplevel

        raw_result = await _do_stop(
            sm, name, _collect, _clear, force,
            emit=parse_emit(emit),
            record_secrets=record_secrets,
        )
        return json.loads(raw_result)
    if action == "replay":
        raw_result = await _do_replay(
            sm, name, actions_json, speed,
            reuse_tab=reuse_tab, auto_session=auto_session,
        )
        return json.loads(raw_result)
    if action == "list":
        return json.loads(_do_list())
    if action == "delete":
        return json.loads(_do_delete(name))
    if action == "view":
        return json.loads(_do_view(name, metadata_only))
    if action == "status":
        return json.loads(_do_status(sm))
    return {"error": f"Unknown recorder action: {action}"}


# ---------------------------------------------------------------------------
# Emulation
# ---------------------------------------------------------------------------

async def _emulate(sm: Any, args: dict) -> dict:
    from nodriver import cdp  # pylint: disable=import-outside-toplevel
    from ..tools.emulation import DEVICE_PRESETS  # pylint: disable=import-outside-toplevel
    device_name = args.get("device_name", "")
    width = args.get("width", 0)
    height = args.get("height", 0)
    tab = sm.get_active_tab()
    store = sm.get_active_session()

    if device_name:
        if device_name not in DEVICE_PRESETS:
            return {"error": f"Unknown device: {device_name}", "available": sorted(DEVICE_PRESETS.keys())}
        device = DEVICE_PRESETS[device_name]
        vp = device["viewport"]
        await tab.send(cdp.emulation.set_device_metrics_override(
            width=vp["width"], height=vp["height"],
            device_scale_factor=device.get("scale", 1), mobile=device.get("mobile", False),
        ))
        ua = device.get("user_agent", "")
        if ua and store.backend_type != "ziniao":
            await tab.send(cdp.emulation.set_user_agent_override(user_agent=ua))
        return {"ok": True, "device": device_name, "viewport": vp}

    if width > 0 and height > 0:
        await tab.send(cdp.emulation.set_device_metrics_override(
            width=width, height=height, device_scale_factor=1, mobile=False,
        ))
        return {"ok": True, "viewport": {"width": width, "height": height}}

    return {"error": "Provide device_name or width+height"}


# ---------------------------------------------------------------------------
# Get info commands
# ---------------------------------------------------------------------------

async def _get_text(sm: Any, args: dict) -> dict:
    selector = args.get("selector", "")
    if not selector:
        return {"error": "selector is required"}
    from ..core.get_info import get_text  # pylint: disable=import-outside-toplevel
    return await get_text(sm.get_active_tab(), selector)


async def _get_html(sm: Any, args: dict) -> dict:
    selector = args.get("selector", "")
    if not selector:
        return {"error": "selector is required"}
    from ..core.get_info import get_html  # pylint: disable=import-outside-toplevel
    return await get_html(sm.get_active_tab(), selector)


async def _get_value(sm: Any, args: dict) -> dict:
    selector = args.get("selector", "")
    if not selector:
        return {"error": "selector is required"}
    from ..core.get_info import get_value  # pylint: disable=import-outside-toplevel
    return await get_value(sm.get_active_tab(), selector)


async def _get_attr(sm: Any, args: dict) -> dict:
    selector = args.get("selector", "")
    attribute = args.get("attribute", "")
    if not selector or not attribute:
        return {"error": "selector and attribute are required"}
    from ..core.get_info import get_attr  # pylint: disable=import-outside-toplevel
    return await get_attr(sm.get_active_tab(), selector, attribute)


async def _get_title(sm: Any, args: dict) -> dict:
    from ..core.get_info import get_title  # pylint: disable=import-outside-toplevel
    return await get_title(sm.get_active_tab())


async def _get_url(sm: Any, args: dict) -> dict:
    from ..core.get_info import get_url  # pylint: disable=import-outside-toplevel
    return await get_url(sm.get_active_tab())


async def _get_count(sm: Any, args: dict) -> dict:
    selector = args.get("selector", "")
    if not selector:
        return {"error": "selector is required"}
    from ..core.get_info import get_count  # pylint: disable=import-outside-toplevel
    return await get_count(sm.get_active_tab(), selector)


# ---------------------------------------------------------------------------
# Find/Nth commands
# ---------------------------------------------------------------------------

async def _find_nth(sm: Any, args: dict) -> dict:
    selector = args.get("selector", "")
    index = args.get("index", 0)
    action = args.get("action", "click")
    if not selector:
        return {"error": "selector is required"}
    from ..core.find import find_nth  # pylint: disable=import-outside-toplevel
    return await find_nth(sm.get_active_tab(), selector, index, action)


async def _find_text(sm: Any, args: dict) -> dict:
    text = args.get("text", "")
    action = args.get("action", "click")
    tag = args.get("tag", "")
    if not text:
        return {"error": "text is required"}
    from ..core.find import find_text  # pylint: disable=import-outside-toplevel
    return await find_text(sm.get_active_tab(), text, action, tag)


async def _find_role(sm: Any, args: dict) -> dict:
    role = args.get("role", "")
    action = args.get("action", "click")
    name = args.get("name", "")
    if not role:
        return {"error": "role is required"}
    from ..core.find import find_role  # pylint: disable=import-outside-toplevel
    return await find_role(sm.get_active_tab(), role, action, name)


# ---------------------------------------------------------------------------
# Check state commands
# ---------------------------------------------------------------------------

async def _is_visible(sm: Any, args: dict) -> dict:
    selector = args.get("selector", "")
    if not selector:
        return {"error": "selector is required"}
    from ..core.check import is_visible  # pylint: disable=import-outside-toplevel
    return await is_visible(sm.get_active_tab(), selector)


async def _is_enabled(sm: Any, args: dict) -> dict:
    selector = args.get("selector", "")
    if not selector:
        return {"error": "selector is required"}
    from ..core.check import is_enabled  # pylint: disable=import-outside-toplevel
    return await is_enabled(sm.get_active_tab(), selector)


async def _is_checked(sm: Any, args: dict) -> dict:
    selector = args.get("selector", "")
    if not selector:
        return {"error": "selector is required"}
    from ..core.check import is_checked  # pylint: disable=import-outside-toplevel
    return await is_checked(sm.get_active_tab(), selector)


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


async def _back(sm: Any, args: dict) -> dict:
    from nodriver import cdp  # pylint: disable=import-outside-toplevel
    tab = sm.get_active_tab()
    raw = await tab.send(cdp.page.get_navigation_history())
    entries, current_index = _parse_navigation_history(raw)
    if current_index > 0:
        entry = entries[current_index - 1]
        await tab.send(cdp.page.navigate_to_history_entry(entry_id=_entry_id(entry)))
        await tab.sleep(0.5)
    return {"ok": True, "url": tab.target.url}


async def _forward(sm: Any, args: dict) -> dict:
    from nodriver import cdp  # pylint: disable=import-outside-toplevel
    tab = sm.get_active_tab()
    raw = await tab.send(cdp.page.get_navigation_history())
    entries, current_index = _parse_navigation_history(raw)
    if current_index < len(entries) - 1:
        entry = entries[current_index + 1]
        await tab.send(cdp.page.navigate_to_history_entry(entry_id=_entry_id(entry)))
        await tab.sleep(0.5)
    return {"ok": True, "url": tab.target.url}


async def _reload(sm: Any, args: dict) -> dict:
    from nodriver import cdp  # pylint: disable=import-outside-toplevel
    tab = sm.get_active_tab()
    ignore_cache = args.get("ignore_cache", False)
    await tab.send(cdp.page.reload(ignore_cache=ignore_cache))
    await tab.sleep(1.0)
    return {"ok": True, "url": tab.target.url}


# ---------------------------------------------------------------------------
# Scroll commands
# ---------------------------------------------------------------------------

async def _scroll(sm: Any, args: dict) -> dict:
    from ..core.scroll import scroll  # pylint: disable=import-outside-toplevel
    return await scroll(
        sm.get_active_tab(),
        args.get("direction", "down"),
        args.get("pixels", 300),
        args.get("selector", ""),
    )


async def _scroll_into(sm: Any, args: dict) -> dict:
    selector = args.get("selector", "")
    if not selector:
        return {"error": "selector is required"}
    from ..core.scroll import scroll_into  # pylint: disable=import-outside-toplevel
    return await scroll_into(sm.get_active_tab(), selector)


# ---------------------------------------------------------------------------
# Interaction: dblclick, focus, select, check, uncheck, keydown, keyup
# ---------------------------------------------------------------------------

async def _dblclick(sm: Any, args: dict) -> dict:
    from ..iframe import find_element  # pylint: disable=import-outside-toplevel
    selector = args.get("selector", "")
    if not selector:
        return {"error": "selector is required"}
    tab = sm.get_active_tab()
    store = sm.get_active_session()
    elem = await find_element(tab, selector, store, timeout=10)
    if not elem:
        return {"error": f"Element not found: {selector}"}
    pos = await elem.get_position()
    if not pos:
        return {"error": f"Failed to get position: {selector}"}
    from nodriver import cdp  # pylint: disable=import-outside-toplevel
    cx, cy = pos.center
    await tab.send(cdp.input_.dispatch_mouse_event(
        type_="mouseMoved", x=cx, y=cy,
    ))
    await tab.send(cdp.input_.dispatch_mouse_event(
        type_="mousePressed", x=cx, y=cy, button=cdp.input_.MouseButton("left"),
        click_count=2,
    ))
    await tab.send(cdp.input_.dispatch_mouse_event(
        type_="mouseReleased", x=cx, y=cy, button=cdp.input_.MouseButton("left"),
        click_count=2,
    ))
    return {"ok": True, "double_clicked": selector}


async def _focus(sm: Any, args: dict) -> dict:
    from ..iframe import find_element  # pylint: disable=import-outside-toplevel
    selector = args.get("selector", "")
    if not selector:
        return {"error": "selector is required"}
    tab = sm.get_active_tab()
    store = sm.get_active_session()
    elem = await find_element(tab, selector, store, timeout=10)
    if not elem:
        return {"error": f"Element not found: {selector}"}
    await tab.evaluate(f"document.querySelector({json.dumps(selector)})?.focus()", return_by_value=True)
    return {"ok": True, "focused": selector}


async def _select_option(sm: Any, args: dict) -> dict:
    selector = args.get("selector", "")
    value = args.get("value", "")
    if not selector:
        return {"error": "selector is required"}
    tab = sm.get_active_tab()
    result = await tab.evaluate(
        f"""(() => {{
            const sel = document.querySelector({json.dumps(selector)});
            if (!sel) return null;
            sel.value = {json.dumps(value)};
            sel.dispatchEvent(new Event('change', {{bubbles: true}}));
            return sel.value;
        }})()""",
        return_by_value=True,
    )
    if result is None:
        return {"error": f"Select element not found: {selector}"}
    return {"ok": True, "selector": selector, "selected": result}


async def _check(sm: Any, args: dict) -> dict:
    selector = args.get("selector", "")
    if not selector:
        return {"error": "selector is required"}
    tab = sm.get_active_tab()
    await tab.evaluate(
        f"""(() => {{
            const el = document.querySelector({json.dumps(selector)});
            if (el && !el.checked) el.click();
        }})()""",
        return_by_value=True,
    )
    return {"ok": True, "checked": selector}


async def _uncheck(sm: Any, args: dict) -> dict:
    selector = args.get("selector", "")
    if not selector:
        return {"error": "selector is required"}
    tab = sm.get_active_tab()
    await tab.evaluate(
        f"""(() => {{
            const el = document.querySelector({json.dumps(selector)});
            if (el && el.checked) el.click();
        }})()""",
        return_by_value=True,
    )
    return {"ok": True, "unchecked": selector}


async def _keydown(sm: Any, args: dict) -> dict:
    from nodriver import cdp  # pylint: disable=import-outside-toplevel
    from ..tools._keys import parse_key  # pylint: disable=import-outside-toplevel
    key = args.get("key", "")
    if not key:
        return {"error": "key is required"}
    tab = sm.get_active_tab()
    actual_key, vk, modifiers = parse_key(key)
    await tab.send(cdp.input_.dispatch_key_event("rawKeyDown", windows_virtual_key_code=vk, modifiers=modifiers, key=actual_key))
    return {"ok": True, "keydown": key}


async def _keyup(sm: Any, args: dict) -> dict:
    from nodriver import cdp  # pylint: disable=import-outside-toplevel
    from ..tools._keys import parse_key  # pylint: disable=import-outside-toplevel
    key = args.get("key", "")
    if not key:
        return {"error": "key is required"}
    tab = sm.get_active_tab()
    actual_key, vk, modifiers = parse_key(key)
    await tab.send(cdp.input_.dispatch_key_event("keyUp", windows_virtual_key_code=vk, modifiers=modifiers, key=actual_key))
    return {"ok": True, "keyup": key}


# ---------------------------------------------------------------------------
# Mouse commands
# ---------------------------------------------------------------------------

async def _mouse_move(sm: Any, args: dict) -> dict:
    from nodriver import cdp  # pylint: disable=import-outside-toplevel
    x = args.get("x", 0)
    y = args.get("y", 0)
    tab = sm.get_active_tab()
    await tab.send(cdp.input_.dispatch_mouse_event(type_="mouseMoved", x=x, y=y))
    return {"ok": True, "x": x, "y": y}


async def _mouse_down(sm: Any, args: dict) -> dict:
    from nodriver import cdp  # pylint: disable=import-outside-toplevel
    button = args.get("button", "left")
    tab = sm.get_active_tab()
    await tab.send(cdp.input_.dispatch_mouse_event(
        type_="mousePressed", x=0, y=0, button=cdp.input_.MouseButton(button), click_count=1,
    ))
    return {"ok": True, "button": button, "action": "down"}


async def _mouse_up(sm: Any, args: dict) -> dict:
    from nodriver import cdp  # pylint: disable=import-outside-toplevel
    button = args.get("button", "left")
    tab = sm.get_active_tab()
    await tab.send(cdp.input_.dispatch_mouse_event(
        type_="mouseReleased", x=0, y=0, button=cdp.input_.MouseButton(button), click_count=1,
    ))
    return {"ok": True, "button": button, "action": "up"}


async def _mouse_wheel(sm: Any, args: dict) -> dict:
    from nodriver import cdp  # pylint: disable=import-outside-toplevel
    delta_x = args.get("delta_x", 0)
    delta_y = args.get("delta_y", 0)
    tab = sm.get_active_tab()
    await tab.send(cdp.input_.dispatch_mouse_event(
        type_="mouseWheel", x=0, y=0, delta_x=delta_x, delta_y=delta_y,
    ))
    return {"ok": True, "delta_x": delta_x, "delta_y": delta_y}


# ---------------------------------------------------------------------------
# Snapshot enhancements
# ---------------------------------------------------------------------------

async def _snapshot_enhanced(sm: Any, args: dict) -> dict:
    tab = sm.get_active_tab()
    store = sm.get_active_session()
    selector = args.get("selector", "")
    interactive = args.get("interactive", False)
    compact = args.get("compact", False)

    if selector:
        html = await tab.evaluate(
            f"document.querySelector({json.dumps(selector)})?.outerHTML ?? ''",
            return_by_value=True,
        )
        return {"ok": True, "html": html}

    if interactive:
        js = """(() => {
            const sels = 'a,button,input,select,textarea,[role="button"],[role="link"],[tabindex]';
            const els = document.querySelectorAll(sels);
            function pick(el, tag, id, name) {
                if (id) {
                    try { const s='#'+CSS.escape(id); if(document.querySelectorAll(s).length===1) return s; } catch(e){}
                }
                if (name) {
                    try { const s=tag+'[name='+JSON.stringify(name)+']'; if(document.querySelectorAll(s).length===1) return s; } catch(e){}
                }
                const al = el.getAttribute('aria-label');
                if (al) {
                    try { const s='[aria-label='+JSON.stringify(al)+']'; if(document.querySelectorAll(s).length===1) return s; } catch(e){}
                }
                if (id) { try { return '#'+CSS.escape(id); } catch(e){} }
                return '';
            }
            return Array.from(els).map((el, i) => {
                const tag = el.tagName.toLowerCase();
                const role = el.getAttribute('role') || '';
                const text = (el.textContent || '').trim().slice(0, 80);
                const type = el.getAttribute('type') || '';
                const name = el.getAttribute('name') || '';
                const href = el.getAttribute('href') || '';
                const id = el.id || '';
                const classes = (typeof el.className === 'string')
                    ? el.className.trim().replace(/\\s+/g, ' ').slice(0, 80)
                    : '';
                const selector = pick(el, tag, id, name);
                return {
                    ref: '@e' + i, tag, role, type, name, text, href: href.slice(0, 100),
                    id, classes, selector,
                };
            });
        })()"""
        elements = await tab.evaluate(js, return_by_value=True)
        return {"ok": True, "interactive_elements": elements, "count": len(elements) if elements else 0}

    if store.iframe_context:
        from ..iframe import eval_in_frame  # pylint: disable=import-outside-toplevel
        html = await eval_in_frame(tab, store.iframe_context.context_id, "document.documentElement.outerHTML")
        return {"ok": True, "html": html or ""}

    html = await tab.get_content()
    if compact:
        html = await tab.evaluate(
            """(() => {
                const clone = document.documentElement.cloneNode(true);
                clone.querySelectorAll('script,style,noscript,svg,link[rel=stylesheet]').forEach(e => e.remove());
                return clone.outerHTML;
            })()""",
            return_by_value=True,
        )
    return {"ok": True, "html": html}


# ---------------------------------------------------------------------------
# Cookies & Storage
# ---------------------------------------------------------------------------

async def _cookies(sm: Any, args: dict) -> dict:
    from nodriver import cdp  # pylint: disable=import-outside-toplevel
    action = args.get("action", "list")
    tab = sm.get_active_tab()

    if action == "list":
        cookies = await tab.send(cdp.network.get_cookies())
        return {"ok": True, "cookies": [
            {"name": c.name, "value": c.value[:100], "domain": c.domain, "path": c.path, "secure": c.secure}
            for c in (cookies or [])
        ]}
    if action == "set":
        name = args.get("name", "")
        value = args.get("value", "")
        domain = args.get("domain", "")
        if not name:
            return {"error": "name is required"}
        await tab.send(cdp.network.set_cookie(name=name, value=value, domain=domain or None))
        return {"ok": True, "set": name}
    if action == "clear":
        await tab.send(cdp.network.clear_browser_cookies())
        return {"ok": True, "message": "Cookies cleared"}
    return {"error": f"Unknown cookies action: {action}"}


async def _storage(sm: Any, args: dict) -> dict:
    storage_type = args.get("type", "local")
    action = args.get("action", "get")
    key = args.get("key", "")
    value = args.get("value", "")
    tab = sm.get_active_tab()
    storage_obj = "localStorage" if storage_type == "local" else "sessionStorage"

    if action == "get":
        if key:
            result = await tab.evaluate(f"{storage_obj}.getItem({json.dumps(key)})", return_by_value=True)
            return {"ok": True, "key": key, "value": result}
        result = await tab.evaluate(
            f"JSON.stringify(Object.fromEntries(Object.entries({storage_obj})))",
            return_by_value=True,
        )
        return {"ok": True, "storage": json.loads(result) if result else {}}
    if action == "set":
        if not key:
            return {"error": "key is required"}
        await tab.evaluate(f"{storage_obj}.setItem({json.dumps(key)}, {json.dumps(value)})", return_by_value=True)
        return {"ok": True, "key": key, "value": value}
    if action == "clear":
        await tab.evaluate(f"{storage_obj}.clear()", return_by_value=True)
        return {"ok": True, "message": f"{storage_obj} cleared"}
    return {"error": f"Unknown storage action: {action}"}


# ---------------------------------------------------------------------------
# Debug commands
# ---------------------------------------------------------------------------

async def _errors(sm: Any, args: dict) -> dict:
    store = sm.get_active_session()
    errors = [m for m in store.console_messages if m.level == "error"]
    limit = args.get("limit", 50)
    return {"errors": [{"id": m.id, "text": m.text[:500], "timestamp": m.timestamp} for m in list(errors)[-limit:]]}


async def _highlight(sm: Any, args: dict) -> dict:
    selector = args.get("selector", "")
    if not selector:
        return {"error": "selector is required"}
    tab = sm.get_active_tab()
    count = await tab.evaluate(
        f"""(() => {{
            const els = document.querySelectorAll({json.dumps(selector)});
            els.forEach(el => {{
                el.style.outline = '2px solid red';
                el.style.outlineOffset = '1px';
            }});
            return els.length;
        }})()""",
        return_by_value=True,
    )
    return {"ok": True, "selector": selector, "highlighted": count}


# ---------------------------------------------------------------------------
# Clipboard commands
# ---------------------------------------------------------------------------

async def _clipboard(sm: Any, args: dict) -> dict:
    action = args.get("action", "read")
    tab = sm.get_active_tab()

    if action == "read":
        text = await tab.evaluate("navigator.clipboard.readText()", await_promise=True, return_by_value=True)
        return {"ok": True, "text": text}
    if action == "write":
        text = args.get("text", "")
        await tab.evaluate(f"navigator.clipboard.writeText({json.dumps(text)})", await_promise=True, return_by_value=True)
        return {"ok": True, "written": len(text)}
    return {"error": f"Unknown clipboard action: {action}"}


# ---------------------------------------------------------------------------
# Command registry
# ---------------------------------------------------------------------------

_COMMANDS: dict[str, Any] = {
    # Store
    "list_stores": _list_stores,
    "open_store": _open_store,
    "close_store": _close_store,
    "start_client": _start_client,
    "stop_client": _stop_client,
    # Chrome
    "launch_chrome": _launch_chrome,
    "connect_chrome": _connect_chrome,
    "list_chrome": _list_chrome,
    "close_chrome": _close_chrome,
    # Session
    "session_list": _session_list,
    "session_switch": _session_switch,
    "session_info": _session_info,
    # Navigation
    "navigate": _navigate,
    "tab": _tab,
    "frame": _frame,
    "wait": _wait,
    "back": _back,
    "forward": _forward,
    "reload": _reload,
    # Interaction
    "click": _click,
    "fill": _fill,
    "type_text": _type_text,
    "press_key": _press_key,
    "hover": _hover,
    "drag": _drag,
    "upload": _upload,
    "handle_dialog": _handle_dialog,
    "dblclick": _dblclick,
    "focus": _focus,
    "select_option": _select_option,
    "check": _check,
    "uncheck": _uncheck,
    "keydown": _keydown,
    "keyup": _keyup,
    # Info
    "snapshot": _snapshot,
    "snapshot_enhanced": _snapshot_enhanced,
    "screenshot": _screenshot,
    "eval": _eval,
    "console": _console,
    "network": _network,
    # Get info
    "get_text": _get_text,
    "get_html": _get_html,
    "get_value": _get_value,
    "get_attr": _get_attr,
    "get_title": _get_title,
    "get_url": _get_url,
    "get_count": _get_count,
    # Find/Nth
    "find_nth": _find_nth,
    "find_text": _find_text,
    "find_role": _find_role,
    # Check state
    "is_visible": _is_visible,
    "is_enabled": _is_enabled,
    "is_checked": _is_checked,
    # Scroll
    "scroll": _scroll,
    "scroll_into": _scroll_into,
    # Mouse
    "mouse_move": _mouse_move,
    "mouse_down": _mouse_down,
    "mouse_up": _mouse_up,
    "mouse_wheel": _mouse_wheel,
    # Cookies & Storage
    "cookies": _cookies,
    "storage": _storage,
    # Debug
    "errors": _errors,
    "highlight": _highlight,
    # Clipboard
    "clipboard": _clipboard,
    # Network route / HAR
    "network_route": _network_route,
    "network_unroute": _network_unroute,
    "network_routes": _network_routes,
    "har_start": _har_start,
    "har_stop": _har_stop,
    # Recorder
    "recorder": _recorder,
    # Emulation
    "emulate": _emulate,
}
