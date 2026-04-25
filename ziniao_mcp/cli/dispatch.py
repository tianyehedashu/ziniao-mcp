"""Command dispatch: map daemon requests to SessionManager / tool operations."""

from __future__ import annotations

import json
import logging
from typing import Any

from ziniao_mcp.sites import UI_ACTION_WHITELIST, coerce_page_fetch_eval_result
from ziniao_mcp.cli.actions import (
    navigate as _navigate,
    wait as _wait,
    back as _back,
    forward as _forward,
    reload as _reload,
    click as _click,
    fill as _fill,
    type_text as _type_text,
    insert_text as _insert_text,
    press_key as _press_key,
    hover as _hover,
    drag as _drag,
    dblclick as _dblclick,
    focus as _focus,
    select_option as _select_option,
    check as _check,
    uncheck as _uncheck,
    upload as _upload,
    upload_hijack as _upload_hijack,
    upload_react as _upload_react,
    clear_overlay as _clear_overlay,
    snapshot as _snapshot,
    screenshot as _screenshot,
    safe_eval_js as _safe_eval_js,
    run_js_in_context as _run_js_in_context,
    eval_js as _eval,
    console as _console,
    get_text as _get_text,
    get_html as _get_html,
    get_value as _get_value,
    get_attr as _get_attr,
    get_title as _get_title,
    get_url as _get_url,
    get_count as _get_count,
    find_nth as _find_nth,
    find_text as _find_text,
    find_role as _find_role,
    is_visible as _is_visible,
    is_enabled as _is_enabled,
    is_checked as _is_checked,
    scroll as _scroll,
    scroll_into as _scroll_into,
    keydown as _keydown,
    keyup as _keyup,
    mouse_move as _mouse_move,
    mouse_down as _mouse_down,
    mouse_up as _mouse_up,
    mouse_wheel as _mouse_wheel,
    clipboard as _clipboard,
)

_logger = logging.getLogger("ziniao-daemon")


def _is_cdp_disconnected_error(exc: BaseException) -> bool:
    """识别 nodriver / websockets 抛出的 CDP 链路断开类异常。

    覆盖三类来源：
    1. ``websockets.exceptions.ConnectionClosed*``（WS 正常/异常关闭）；
    2. 标准库 ``ConnectionResetError`` / ``BrokenPipeError``（底层 socket 被 RST/FIN）；
    3. nodriver 在连接失效后常见的 ``AttributeError: 'NoneType' ...`` /
       ``RuntimeError: connection is closed`` 等字符串兜底。
    我们只用异常类型优先，字符串匹配仅作补充，避免误杀正常业务错误。
    """
    if isinstance(exc, (ConnectionResetError, BrokenPipeError, ConnectionAbortedError)):
        return True
    try:
        from websockets.exceptions import ConnectionClosed  # pylint: disable=import-outside-toplevel
        if isinstance(exc, ConnectionClosed):
            return True
    except ImportError:
        pass
    msg = str(exc).lower()
    return (
        "connection is closed" in msg
        or "no close frame received" in msg
        or "websocket" in msg and "closed" in msg
    )


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
            return {
                "error": f"Session '{target}' not found. Use 'session list' to see available sessions."
            }
        sm._active_store_id = target

    try:
        result = await _execute(sm, command, args)
    except Exception as exc:
        if _is_cdp_disconnected_error(exc):
            # CDP WebSocket 已断：清理对应会话缓存，让下次命令走重建路径。
            # 不记 exception 级日志，避免每次都打整段 traceback。
            victim = target or sm.active_session_id
            _logger.warning(
                "命令 '%s' 遭遇 CDP 断开 (%s)，已清理会话 %s",
                command, type(exc).__name__, victim,
            )
            if victim:
                try:
                    sm.invalidate_session(victim)
                except Exception:  # noqa: BLE001
                    _logger.debug("invalidate_session 失败", exc_info=True)
            result = {
                "error": "CDP WebSocket 已断开，店铺/浏览器可能被关闭或紫鸟回收。"
                         "请重试命令以自动重建连接。",
                "code": "cdp_disconnected",
                "store_id": victim,
            }
        else:
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
        result.append(
            {
                "browserId": s.get("browserId"),
                "browserOauth": s.get("browserOauth"),
                "browserName": s.get("browserName"),
                "siteId": s.get("siteId"),
                "siteName": s.get("siteName"),
                "is_open": store_id in open_ids,
            }
        )
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


async def _open_store_passive(sm: Any, args: dict) -> dict:
    """Open store in passive mode (no attach, no stealth)."""
    store_id = args.get("store_id", "")
    if not store_id:
        return {"error": "store_id is required"}
    return await sm.open_store_passive(store_id)


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
    return {
        "active": sm.active_session_id,
        "sessions": sessions,
        "count": len(sessions),
    }


async def _session_switch(sm: Any, args: dict) -> dict:
    session_id = args.get("session_id", "")
    if not session_id:
        return {"error": "session_id is required"}
    s = sm.switch_session(session_id)
    return {
        "ok": True,
        "active": s.store_id,
        "name": s.store_name,
        "type": s.backend_type,
    }


async def _session_info(sm: Any, args: dict) -> dict:
    session_id = args.get("session_id", "")
    if not session_id:
        return {"error": "session_id is required"}
    return sm.get_session_info(session_id)


# ---------------------------------------------------------------------------
# Navigation commands
# ---------------------------------------------------------------------------


async def _tab(sm: Any, args: dict) -> dict:
    from ziniao_webdriver.cdp_tabs import filter_tabs as _filter_tabs  # pylint: disable=import-outside-toplevel

    action = args.get("action", "list")
    store = sm.get_active_session()

    if action == "list":
        store.tabs = _filter_tabs(store.browser.tabs)
        result = []
        for i, t in enumerate(store.tabs):
            result.append(
                {
                    "index": i,
                    "url": t.target.url,
                    "title": t.target.title or "",
                    "is_active": i == store.active_tab_index,
                }
            )
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
        return {
            "ok": True,
            "index": idx,
            "url": t.target.url,
            "title": t.target.title or "",
        }

    if action == "new":
        target_url = args.get("url", "") or "about:blank"
        new_tab = await store.browser.get(target_url, new_tab=True)
        store.tabs = _filter_tabs(store.browser.tabs)
        store.active_tab_index = len(store.tabs) - 1
        store.iframe_context = None
        await sm.setup_tab_listeners(store, new_tab)
        return {
            "ok": True,
            "index": store.active_tab_index,
            "url": new_tab.target.url,
            "total": len(store.tabs),
        }

    if action == "close":
        import asyncio  # pylint: disable=import-outside-toplevel

        store.tabs = _filter_tabs(store.browser.tabs)
        idx = (
            store.active_tab_index
            if args.get("page_index", -1) == -1
            else args.get("page_index", 0)
        )
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


async def _network(sm: Any, args: dict) -> dict:
    store = sm.get_active_session()
    request_id = args.get("request_id", 0)
    url_pattern = args.get("url_pattern", "")
    limit = args.get("limit", 50)

    if request_id:
        for req in store.network_requests:
            if req.id == request_id:
                return {
                    "id": req.id,
                    "url": req.url,
                    "method": req.method,
                    "status": req.status,
                    "status_text": req.status_text,
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
    return {
        "requests": [
            {
                "id": r.id,
                "method": r.method,
                "url": r.url[:200],
                "status": r.status,
                "resource_type": r.resource_type,
                "has_post_data": bool(getattr(r, "post_data", None)),
                "has_response_body": bool(getattr(r, "response_body", None)),
            }
            for r in list(reqs)[-limit:]
        ]
    }


async def _network_route(sm: Any, args: dict) -> dict:
    url_pattern = args.get("url_pattern", "")
    if not url_pattern:
        return {"error": "url_pattern is required"}
    from ..core.network import add_route  # pylint: disable=import-outside-toplevel

    return await add_route(
        sm.get_active_tab(),
        sm.get_active_session(),
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
        sm.get_active_tab(),
        sm.get_active_session(),
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
            sm,
            _inject,
            _nav_setup,
            engine=engine,
            scope=scope,
            max_tabs=max_tabs,
        )
        return json.loads(raw_result)
    if action == "stop":
        from ..recording.ir import parse_emit  # pylint: disable=import-outside-toplevel

        raw_result = await _do_stop(
            sm,
            name,
            _collect,
            _clear,
            force,
            emit=parse_emit(emit),
            record_secrets=record_secrets,
        )
        return json.loads(raw_result)
    if action == "replay":
        raw_result = await _do_replay(
            sm,
            name,
            actions_json,
            speed,
            reuse_tab=reuse_tab,
            auto_session=auto_session,
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
            return {
                "error": f"Unknown device: {device_name}",
                "available": sorted(DEVICE_PRESETS.keys()),
            }
        device = DEVICE_PRESETS[device_name]
        vp = device["viewport"]
        await tab.send(
            cdp.emulation.set_device_metrics_override(
                width=vp["width"],
                height=vp["height"],
                device_scale_factor=device.get("scale", 1),
                mobile=device.get("mobile", False),
            )
        )
        ua = device.get("user_agent", "")
        if ua and store.backend_type != "ziniao":
            await tab.send(cdp.emulation.set_user_agent_override(user_agent=ua))
        return {"ok": True, "device": device_name, "viewport": vp}

    if width > 0 and height > 0:
        await tab.send(
            cdp.emulation.set_device_metrics_override(
                width=width,
                height=height,
                device_scale_factor=1,
                mobile=False,
            )
        )
        return {"ok": True, "viewport": {"width": width, "height": height}}

    return {"error": "Provide device_name or width+height"}


# ---------------------------------------------------------------------------
# Get info commands
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
        return {
            "ok": True,
            "interactive_elements": elements,
            "count": len(elements) if elements else 0,
        }

    if store.iframe_context:
        from ..iframe import eval_in_frame  # pylint: disable=import-outside-toplevel

        html = await eval_in_frame(
            tab, store.iframe_context.context_id, "document.documentElement.outerHTML"
        )
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
        return {
            "ok": True,
            "cookies": [
                {
                    "name": c.name,
                    "value": c.value[:100],
                    "domain": c.domain,
                    "path": c.path,
                    "secure": c.secure,
                }
                for c in (cookies or [])
            ],
        }
    if action == "set":
        name = args.get("name", "")
        value = args.get("value", "")
        domain = args.get("domain", "")
        if not name:
            return {"error": "name is required"}
        await tab.send(
            cdp.network.set_cookie(name=name, value=value, domain=domain or None)
        )
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
            result = await tab.evaluate(
                f"{storage_obj}.getItem({json.dumps(key)})", return_by_value=True
            )
            return {"ok": True, "key": key, "value": result}
        result = await tab.evaluate(
            f"JSON.stringify(Object.fromEntries(Object.entries({storage_obj})))",
            return_by_value=True,
        )
        return {"ok": True, "storage": json.loads(result) if result else {}}
    if action == "set":
        if not key:
            return {"error": "key is required"}
        await tab.evaluate(
            f"{storage_obj}.setItem({json.dumps(key)}, {json.dumps(value)})",
            return_by_value=True,
        )
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
    return {
        "errors": [
            {"id": m.id, "text": m.text[:500], "timestamp": m.timestamp}
            for m in list(errors)[-limit:]
        ]
    }


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

def _resolve_body_file_refs(body: Any, resolve_fn: Any) -> Any:
    """Expand ``@@ZFILE@@`` tokens inside *body*.

    ``prepare_request`` may have JSON-serialised a ``dict`` body into a
    string.  This helper JSON-parses it first, resolves file references,
    then returns the resolved object (not re-serialised) so the caller
    can use it as ``body_obj_js`` directly.
    """
    if isinstance(body, str) and body:
        try:
            parsed = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            return resolve_fn(body)
        return resolve_fn(parsed)
    return resolve_fn(body)


async def _page_fetch(sm: Any, args: dict) -> dict:
    from ziniao_mcp.sites import _normalize_header_inject  # pylint: disable=import-outside-toplevel

    _normalize_header_inject(args)

    mode = args.get("mode", "fetch")
    navigate_url = args.get("navigate_url", "")
    tab = sm.get_active_tab()

    if navigate_url:
        force = bool(args.get("force_navigate"))
        current = tab.target.url or ""
        if force or not current.startswith(navigate_url.split("?")[0].split("#")[0]):
            from nodriver import cdp  # pylint: disable=import-outside-toplevel

            await tab.send(cdp.page.navigate(url=navigate_url))
            await tab.sleep(2.0)

    if mode == "js":
        return await _page_fetch_js(sm, args)
    return await _page_fetch_fetch(sm, args)


async def _page_fetch_fetch(sm: Any, args: dict) -> dict:
    from ..sites import resolve_file_refs  # pylint: disable=import-outside-toplevel

    tab = sm.get_active_tab()
    store = sm.get_active_session()

    url = args.get("url", "")
    if not url:
        return {"error": "url is required for fetch mode"}
    method = args.get("method", "GET")
    body = _resolve_body_file_refs(args.get("body", ""), resolve_file_refs)
    headers = args.get("headers") or {}
    injections = args.get("header_inject") or []

    headers_js = json.dumps(headers, ensure_ascii=False)
    body_js = json.dumps(body, ensure_ascii=False) if body else "null"
    url_js = json.dumps(url)
    inject_js = json.dumps(injections, ensure_ascii=False)

    js = f"""(async () => {{
  const h = {headers_js};
  const injections = {inject_js};
  for (const inj of injections) {{
    let val = null;
    if (inj.source === 'cookie') {{
      const m = document.cookie.match(new RegExp(inj.key + '=([^;]+)'));
      val = m ? decodeURIComponent(m[1]) : null;
    }} else if (inj.source === 'localStorage') {{
      val = localStorage.getItem(inj.key);
    }} else if (inj.source === 'sessionStorage') {{
      val = sessionStorage.getItem(inj.key);
    }} else if (inj.source === 'eval') {{
      try {{ val = await Promise.resolve(eval(inj.expression)); }} catch(e) {{}}
    }}
    if (val != null) {{
      h[inj.header] = inj.transform ? inj.transform.replace('${{value}}', val) : val;
    }}
  }}
  const opts = {{ method: {json.dumps(method)}, headers: h, credentials: 'include' }};
  const body = {body_js};
  if (body) opts.body = typeof body === 'string' ? body : JSON.stringify(body);
  const resp = await fetch({url_js}, opts);
  const ct = resp.headers.get('content-type') || '';
  const buf = await resp.arrayBuffer();
  const bytes = new Uint8Array(buf);
  const CHUNK = 0x8000;
  let bin = '';
  for (let i = 0; i < bytes.length; i += CHUNK) {{
    bin += String.fromCharCode.apply(null, bytes.subarray(i, Math.min(i + CHUNK, bytes.length)));
  }}
  return JSON.stringify({{ status: resp.status, statusText: resp.statusText, body_b64: btoa(bin), content_type: ct }});
}})()"""

    if store.iframe_context:
        from ..iframe import eval_in_frame  # pylint: disable=import-outside-toplevel

        result = await eval_in_frame(
            tab,
            store.iframe_context.context_id,
            js,
            await_promise=True,
            return_by_value=True,
        )
    else:
        result = await tab.evaluate(js, await_promise=True, return_by_value=True)
    return coerce_page_fetch_eval_result(result)


async def _page_fetch_js(sm: Any, args: dict) -> dict:
    from ..sites import resolve_file_refs  # pylint: disable=import-outside-toplevel

    tab = sm.get_active_tab()
    store = sm.get_active_session()

    script = args.get("script", "")
    if not script:
        return {"error": "script is required for js mode"}
    body = _resolve_body_file_refs(args.get("body", ""), resolve_file_refs)
    body_obj_js = json.dumps(body, ensure_ascii=False) if body else "null"
    body_str_js = json.dumps(json.dumps(body, ensure_ascii=False) if body else "")

    js = f"""(async () => {{
  const __BODY__ = {body_obj_js};
  const __BODY_STR__ = {body_str_js};
  let result = await ({script});
  if (result instanceof ArrayBuffer) {{
    result = new Uint8Array(result);
  }}
  if (result instanceof Uint8Array) {{
    const bytes = result;
    const CHUNK = 0x8000;
    let bin = '';
    for (let i = 0; i < bytes.length; i += CHUNK) {{
      bin += String.fromCharCode.apply(null, bytes.subarray(i, Math.min(i + CHUNK, bytes.length)));
    }}
    return JSON.stringify({{ status: 200, statusText: 'OK', body_b64: btoa(bin), content_type: 'application/octet-stream' }});
  }}
  if (typeof result !== 'string') result = JSON.stringify(result);
  return result;
}})()"""

    if store.iframe_context:
        from ..iframe import eval_in_frame  # pylint: disable=import-outside-toplevel

        result = await eval_in_frame(
            tab,
            store.iframe_context.context_id,
            js,
            await_promise=True,
            return_by_value=True,
        )
    else:
        result = await tab.evaluate(js, await_promise=True, return_by_value=True)
    return coerce_page_fetch_eval_result(result)


# ---------------------------------------------------------------------------
# UI flow runner (mode: ui presets)
# ---------------------------------------------------------------------------

_STEP_VAR_RE = __import__("re").compile(r"\{\{([A-Za-z0-9_][A-Za-z0-9_.]*)\}\}")

# Single source of truth: `ziniao_mcp.sites.UI_ACTION_WHITELIST` (imported
# at the top of the module).  Aliased locally to keep call sites short and
# prevent drift between the preset validator and this executor.
_FLOW_STEP_ACTIONS = UI_ACTION_WHITELIST

def _mask_secrets(text: str, secrets: list[str]) -> str:
    """Replace every secret occurrence in *text* with ``***``."""
    if not text or not secrets:
        return text
    masked = text
    for s in secrets:
        if s and s in masked:
            masked = masked.replace(s, "***")
    return masked


def _resolve_step_token(expr: str, ctx: dict) -> Any:
    """Resolve a ``steps.<id>.value`` / ``extracted.<name>`` / ``vars.<k>`` token."""
    parts = expr.split(".")
    head = parts[0]
    tail = parts[1:]
    if head == "steps":
        if not tail:
            return ctx.get("steps")
        sid = tail[0]
        step_result = ctx.get("steps", {}).get(sid)
        if step_result is None:
            return None
        cursor: Any = step_result
        for key in tail[1:]:
            if isinstance(cursor, dict):
                cursor = cursor.get(key)
            else:
                return None
        return cursor
    if head == "extracted":
        if not tail:
            return ctx.get("extracted")
        cursor = ctx.get("extracted", {})
        for key in tail:
            if isinstance(cursor, dict):
                cursor = cursor.get(key)
            else:
                return None
        return cursor
    if head == "vars":
        if not tail:
            return ctx.get("vars")
        return ctx.get("vars", {}).get(tail[0])
    return None


def _render_step_value(obj: Any, ctx: dict) -> Any:
    """Recursively substitute ``{{steps.X.value}}`` / ``{{extracted.Y}}`` tokens."""
    if isinstance(obj, str):
        match = _STEP_VAR_RE.fullmatch(obj)
        if match and (
            "." in match.group(1) or match.group(1) in ("steps", "extracted", "vars")
        ):
            resolved = _resolve_step_token(match.group(1), ctx)
            return resolved if resolved is not None else obj

        def _sub(m: Any) -> str:
            expr = m.group(1)
            if "." not in expr and expr not in ("steps", "extracted", "vars"):
                return m.group(0)
            val = _resolve_step_token(expr, ctx)
            if val is None:
                return m.group(0)
            return str(val) if not isinstance(val, str) else val

        return _STEP_VAR_RE.sub(_sub, obj)
    if isinstance(obj, dict):
        return {k: _render_step_value(v, ctx) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_render_step_value(v, ctx) for v in obj]
    return obj


async def _capture_failure_artifacts(
    sm: Any,
    step_id: str,
    error_msg: str,
    on_error: dict,
    seq: int = 0,
    *,
    secrets: list[str] | None = None,
) -> dict:
    """Write screenshot + snapshot HTML into ``exports/flow-errors/``.

    File names carry both millisecond-precision timestamps **and** a
    monotonic ``seq`` counter so multiple failures in the same second
    (e.g. cascading ``continue_on_error`` steps) never overwrite each
    other's artefacts.

    ``secrets`` (when supplied) is applied via :func:`_mask_secrets` to
    the **snapshot HTML** *and* the ``.err.txt`` payload before they hit
    disk.  This prevents leakage of resolved ``type: secret`` values into
    ``exports/flow-errors/*.html`` — the raw DOM would otherwise retain
    password-field ``value=``, reCAPTCHA tokens rendered via
    ``__NEXT_DATA__``, CSRF tokens embedded in hidden inputs, etc.  PNG
    screenshots cannot be masked at the pixel level, so callers should
    disable ``on_error.screenshot`` explicitly when the failing page is
    expected to render sensitive plaintext.
    """
    import base64 as _b64  # pylint: disable=import-outside-toplevel
    from datetime import datetime  # pylint: disable=import-outside-toplevel
    from pathlib import Path as _Path  # pylint: disable=import-outside-toplevel

    artefacts: dict = {}
    if not (on_error.get("screenshot", True) or on_error.get("snapshot", True)):
        return artefacts
    out_dir = _Path("exports") / "flow-errors"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]  # millisecond precision
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in step_id)[:40]
    base = out_dir / f"{stamp}-{seq:02d}-{safe_id}"

    if on_error.get("screenshot", True):
        try:
            shot = await _screenshot(sm, {"full_page": False})
            data = shot.get("data", "")
            if data.startswith("data:image/png;base64,"):
                png_path = base.with_suffix(".png")
                png_path.write_bytes(_b64.b64decode(data.split(",", 1)[1]))
                artefacts["screenshot_path"] = str(png_path.resolve())
        except Exception:  # noqa: BLE001
            pass

    if on_error.get("snapshot", True):
        try:
            snap = await _snapshot(sm, {})
            html = snap.get("html", "")
            if html:
                if secrets:
                    html = _mask_secrets(html, secrets)
                html_path = base.with_suffix(".html")
                html_path.write_text(html, encoding="utf-8")
                artefacts["snapshot_path"] = str(html_path.resolve())
        except Exception:  # noqa: BLE001
            pass

    if error_msg:
        safe_err = _mask_secrets(error_msg, secrets) if secrets else error_msg
        (base.with_suffix(".err.txt")).write_text(safe_err, encoding="utf-8")
    return artefacts


async def _extract_step(sm: Any, step: dict) -> dict:
    """Execute an ``action: extract`` step.

    Returns a dict with keys ``{"ok": True, "value": <scalar|list|dict>, "kind": ...}``
    or ``{"error": ...}``.  The caller stores ``value`` into
    ``ctx.extracted[step['as']]`` and the full dict into ``ctx.steps[step['id']]``.
    """
    tab = sm.get_active_tab()
    store = sm.get_active_session()
    kind = step.get("kind", "text")
    selector = step.get("selector", "")

    if kind == "eval":
        script = step.get("script", "") or step.get("expression", "")
        if not script:
            return {"error": "extract kind=eval requires 'script' or 'expression'."}
        try:
            value = await _run_js_in_context(
                tab,
                store,
                script,
                await_promise=step.get("await_promise", False),
            )
        except RuntimeError as exc:
            return {"error": str(exc)}
        return {"ok": True, "value": value, "kind": kind}

    if not selector:
        return {"error": f"extract kind={kind!r} requires 'selector'."}

    if kind == "text":
        js = f"(() => {{ const el = document.querySelector({json.dumps(selector)}); return el ? el.innerText || el.textContent || '' : null; }})()"
    elif kind == "html":
        js = f"(() => {{ const el = document.querySelector({json.dumps(selector)}); return el ? el.outerHTML : null; }})()"
    elif kind == "attribute":
        attr = step.get("attr") or step.get("attribute", "")
        if not attr:
            return {"error": "extract kind=attribute requires 'attr'."}
        js = (
            f"(() => {{ const el = document.querySelector({json.dumps(selector)}); "
            f"return el ? el.getAttribute({json.dumps(attr)}) : null; }})()"
        )
    elif kind == "querySelectorAll":
        inner = step.get("sub_attr") or "innerText"
        js = (
            f"(() => {{ return Array.from(document.querySelectorAll({json.dumps(selector)}))"
            f".map(el => el[{json.dumps(inner)}] || el.getAttribute({json.dumps(inner)}) || ''); }})()"
        )
    elif kind == "table":
        js = f"""(() => {{
  const tbl = document.querySelector({json.dumps(selector)});
  if (!tbl) return null;
  return Array.from(tbl.rows).map(r => Array.from(r.cells).map(c => c.innerText.trim()));
}})()"""
    else:
        return {
            "error": f"extract kind={kind!r} not supported (text/html/attribute/querySelectorAll/table/eval)."
        }

    try:
        value = await _run_js_in_context(tab, store, js)
    except RuntimeError as exc:
        return {"error": str(exc)}

    if kind in ("querySelectorAll", "table") and value is None:
        value = []
    return {"ok": True, "value": value, "kind": kind, "selector": selector}


async def _inline_fetch_step(sm: Any, step: dict) -> dict:
    """Execute a step-level ``action: fetch`` by delegating to ``_page_fetch_fetch``.

    Supports ``save_body_to`` to persist the (possibly binary) response body.
    """
    import base64 as _b64  # pylint: disable=import-outside-toplevel
    from pathlib import Path as _Path  # pylint: disable=import-outside-toplevel

    # `_page_fetch_fetch` already accepts dict/list bodies (via
    # `_resolve_body_file_refs` → `json.dumps`).  Pre-serialising here
    # forced a parse/re-serialise round-trip that broke non-JSON bodies
    # (plain text triggered a JSONDecodeError fallback) and needlessly
    # re-encoded non-ASCII payloads.  Pass the original value through.
    fetch_args = {
        "url": step.get("url", ""),
        "method": step.get("method", "GET"),
        "body": step.get("body", ""),
        "headers": step.get("headers") or {},
        "header_inject": step.get("header_inject") or [],
    }
    result = await _page_fetch_fetch(sm, fetch_args)

    save_body_to = step.get("save_body_to")
    if save_body_to and result.get("ok"):
        dest = _Path(save_body_to)
        dest.parent.mkdir(parents=True, exist_ok=True)
        body_b64 = result.get("body_b64")
        if body_b64:
            dest.write_bytes(_b64.b64decode(body_b64))
        else:
            dest.write_text(result.get("body", "") or "", encoding="utf-8")
        result["saved_path"] = str(dest.resolve())
    return result


async def _dispatch_flow_step(sm: Any, step: dict, ctx: dict) -> dict:
    """Route a single rendered step to the underlying primitive."""
    action = step.get("action")
    if action == "navigate":
        return await _navigate(sm, {"url": step.get("url", "")})
    if action == "wait":
        return await _wait(
            sm,
            {
                "selector": step.get("selector", ""),
                "state": step.get("state", "visible"),
                "timeout": int(step.get("timeout", 30)) * 1000
                if isinstance(step.get("timeout"), (int, float))
                else 30000,
            },
        )
    if action == "click":
        return await _click(sm, {"selector": step.get("selector", "")})
    if action == "fill":
        if step.get("fields_json"):
            return await _fill(sm, {"fields_json": step["fields_json"]})
        return await _fill(
            sm, {"selector": step.get("selector", ""), "value": step.get("value", "")}
        )
    if action == "type_text":
        return await _type_text(
            sm,
            {
                "selector": step.get("selector", ""),
                "text": step.get("text", step.get("value", "")),
            },
        )
    if action == "inject-file":
        _path = step.get("path", "")
        _var = step.get("var", "__injected_file")
        from pathlib import Path as _P2  # pylint: disable=import-outside-toplevel
        if not _P2(_path).is_file():
            return {"error": f"File not found: {_path}"}
        _content = _P2(_path).read_text(encoding="utf-8", errors="replace")
        _tab = sm.get_active_tab()
        _j = json.dumps(_content, ensure_ascii=False)
        await _safe_eval_js(_tab, f"window['{_var}'] = {_j};")
        return {"ok": True, "size": len(_content)}

    if action == "insert_text":
        return await _insert_text(
            sm,
            {
                "selector": step.get("selector", ""),
                "text": step.get("text", step.get("value", "")),
            },
        )
    if action == "press_key":
        return await _press_key(sm, {"key": step.get("key", "")})
    if action == "hover":
        return await _hover(sm, {"selector": step.get("selector", "")})
    if action == "dblclick":
        return await _dblclick(sm, {"selector": step.get("selector", "")})
    if action == "upload":
        return await _upload(
            sm,
            {
                "selector": step.get("selector", ""),
                "file_paths": step.get("file_paths")
                or ([step["file_path"]] if step.get("file_path") else []),
            },
        )
    if action == "upload-hijack":
        return await _upload_hijack(
            sm,
            {
                "file_paths": step.get("file_paths")
                or ([step["file_path"]] if step.get("file_path") else []),
                "trigger": step.get("trigger", ""),
                "wait_ms": step.get("wait_ms", 30000),
            },
        )
    if action == "upload-react":
        return await _upload_react(
            sm,
            {
                "file_paths": step.get("file_paths")
                or ([step["file_path"]] if step.get("file_path") else []),
                "trigger": step.get("trigger", ""),
            },
        )
    if action == "screenshot":
        return await _screenshot(
            sm,
            {
                "selector": step.get("selector", ""),
                "full_page": step.get("full_page", False),
            },
        )
    if action == "snapshot":
        return await _snapshot(sm, {})
    if action == "clear-overlay":
        return await _clear_overlay(sm, {})
    if action == "eval":
        return await _eval(
            sm,
            {
                "script": step.get("script", ""),
                "await_promise": step.get("await_promise", False),
            },
        )
    if action == "inject-vars":
        injected = await _inject_flow_vars(sm.get_active_tab(), ctx.get("vars") or {})
        return {"ok": True, "injected": injected}
    if action == "extract":
        result = await _extract_step(sm, step)
        if result.get("ok") and "as" in step:
            ctx.setdefault("extracted", {})[step["as"]] = result.get("value")
        return result
    if action == "fetch":
        return await _inline_fetch_step(sm, step)
    return {"error": f"Unsupported action: {action!r}"}


def _apply_output_contract(contract: dict, envelope: dict) -> dict:
    """Flatten ``extracted`` / ``steps`` into user-facing output keys.

    The contract maps output-key → JSONPath-like expression, e.g.::

        { "download_url": "$.extracted.download_url", "file": "$.steps.dl.saved_path" }

    Only the ``$.a.b.c`` dot-path dialect is supported (KISS).
    """
    out: dict = {}
    for key, expr in contract.items():
        if not isinstance(expr, str) or not expr.startswith("$."):
            continue
        cursor: Any = envelope
        for part in expr[2:].split("."):
            if isinstance(cursor, dict):
                cursor = cursor.get(part)
            else:
                cursor = None
                break
        out[key] = cursor
    return out


_FLOW_VARS_SMALL_MAX = 50_000


async def _inject_flow_vars(tab: Any, flow_vars: dict) -> list[str]:
    """Inject *flow_vars* into ``window.__flow_vars`` on *tab*.

    Strategy: small string values (< 50KB) are batched into a single eval so
    ``window.__flow_vars`` is always established as an object baseline; large
    values are assigned individually afterwards to dodge CDP eval size limits.
    Callers can rely on ``window.__flow_vars`` being a well-formed object
    after this function returns — even when every value is large.

    Returns the list of keys that were attempted (order preserves *flow_vars*).
    Failures in individual ``eval`` calls are swallowed: this matches the
    original best-effort contract used at flow startup, where a missing JS
    context should not abort the entire run.
    """
    keys = list(flow_vars.keys())
    if not flow_vars:
        return keys

    small = {
        k: v for k, v in flow_vars.items()
        if isinstance(v, str) and len(v) < _FLOW_VARS_SMALL_MAX
    }
    # Always write the baseline so large-value assignments below don't hit
    # "Cannot set properties of undefined" when no small values are present.
    baseline = json.dumps(small, ensure_ascii=False)
    try:
        await _safe_eval_js(tab, f"window.__flow_vars = {baseline};")
    except Exception:  # pylint: disable=broad-except
        pass

    for k, v in flow_vars.items():
        if isinstance(v, str) and len(v) >= _FLOW_VARS_SMALL_MAX:
            expr = (
                "window.__flow_vars["
                + json.dumps(k)
                + "] = "
                + json.dumps(v, ensure_ascii=False)
            )
            try:
                await _safe_eval_js(tab, expr)
            except Exception:  # pylint: disable=broad-except
                pass
    return keys


async def _flow_run(sm: Any, args: dict) -> dict:
    """Execute a ``mode: ui`` preset: step-by-step UI actions with extract/fetch.

    Contract:

    - Input ``args`` is the already-rendered spec (via ``render_vars``) plus
      optional ``_ziniao_secret_values`` carrying resolved secrets for masking.
    - On first hard failure the runner stops (unless ``step.continue_on_error``),
      writes screenshot / snapshot to ``exports/flow-errors/``, and returns
      ``{ok: False, failures: [...]}``.
    - On success returns ``{ok: True, steps, extracted, output, failures: []}``.
    """
    from nodriver import cdp  # pylint: disable=import-outside-toplevel

    steps = args.get("steps") or []
    navigate_url = args.get("navigate_url", "")
    secrets = list(args.get("_ziniao_secret_values") or [])
    on_error = dict(args.get("on_error") or {})
    output_contract = dict(args.get("output_contract") or {})
    flow_vars = dict(args.get("_ziniao_merged_vars") or {})

    if not isinstance(steps, list) or not steps:
        return {"error": "flow_run requires non-empty 'steps'."}

    tab = sm.get_active_tab()
    if navigate_url:
        force = bool(args.get("force_navigate"))
        current = tab.target.url or ""
        base = navigate_url.split("?")[0].split("#")[0]
        if force or not current.startswith(base):
            await tab.send(cdp.page.navigate(url=navigate_url))
            await tab.sleep(2.0)

    ctx: dict = {"steps": {}, "extracted": {}, "vars": flow_vars}
    failures: list[dict] = []

    # Inject flow vars AFTER navigate so eval steps can access window.__flow_vars.
    await _inject_flow_vars(tab, flow_vars)

    for idx, raw_step in enumerate(steps):
        sid = raw_step.get("id") or f"step_{idx}"
        action = raw_step.get("action")
        if action not in _FLOW_STEP_ACTIONS:
            return {
                "error": f"steps[{idx}] unsupported action {action!r}.",
                "steps": ctx["steps"],
                "extracted": ctx["extracted"],
                "failures": failures,
            }

        rendered = _render_step_value(raw_step, ctx)

        try:
            result = await _dispatch_flow_step(sm, rendered, ctx)
            if isinstance(result, dict) and result.get("error"):
                raise RuntimeError(result["error"])
            ctx["steps"][sid] = result
        except Exception as exc:  # noqa: BLE001
            err = _mask_secrets(str(exc), secrets)
            _logger.warning("flow_run step %s failed: %s", sid, err)
            artefacts = await _capture_failure_artifacts(
                sm,
                sid,
                err,
                on_error,
                seq=idx,
                secrets=secrets,
            )
            failures.append(
                {"step_id": sid, "error": err, "action": action, **artefacts}
            )
            if raw_step.get("continue_on_error"):
                ctx["steps"][sid] = {"error": err, **artefacts}
                continue
            return {
                "ok": False,
                "steps": ctx["steps"],
                "extracted": ctx["extracted"],
                "failures": failures,
            }

    envelope = {
        "ok": True,
        "steps": ctx["steps"],
        "extracted": ctx["extracted"],
        "failures": failures,
    }
    if output_contract:
        envelope_with_vars = {**envelope, "vars": ctx["vars"]}
        envelope["output"] = _apply_output_contract(output_contract, envelope_with_vars)
    return envelope


# ---------------------------------------------------------------------------
# Command registry
# ---------------------------------------------------------------------------

_COMMANDS: dict[str, Any] = {
    # Store
    "list_stores": _list_stores,
    "open_store": _open_store,
    "open_store_passive": _open_store_passive,
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
    "insert_text": _insert_text,
    "press_key": _press_key,
    "hover": _hover,
    "drag": _drag,
    "upload": _upload,
    "upload-hijack": _upload_hijack,
    "clear-overlay": _clear_overlay,
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
    # Page fetch
    "page_fetch": _page_fetch,
    # UI flow runner (mode: ui presets)
    "flow_run": _flow_run,
    # Douyin publish
}
