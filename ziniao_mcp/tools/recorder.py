"""Browser action recording and code generation tool."""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from collections.abc import Awaitable, Callable
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from ..recording.capture_dom2 import start_dom2_capture, stop_dom2_capture
from ..recording.emit_nodriver import generate_nodriver_script
from ..recording.emit_playwright import generate_playwright_typescript
from ..recording.ir import (
    RECORDING_SCHEMA_VERSION,
    actions_for_disk,
    parse_emit,
)
from ..recording.locator import normalize_action_for_replay
from ..recording_context import resolve_recording_browser_context
from ..session import SessionManager, _read_state_file

_logger = logging.getLogger("ziniao-mcp-debug")

_RECORDINGS_DIR = Path.home() / ".ziniao" / "recordings"

# ---------------------------------------------------------------------------
# JS recorder injected into page to capture user interactions
# ---------------------------------------------------------------------------

_RECORDER_JS = r"""
(function() {
    /* Anti-detection: use non-enumerable Symbol-keyed storage on window
       so the recorder state is invisible to Object.keys / for-in / JSON.stringify */
    var SYM_ACTIVE = Symbol.for('__ev_a');
    var SYM_DATA   = Symbol.for('__ev_d');

    if (window[SYM_ACTIVE]) return;
    Object.defineProperty(window, SYM_ACTIVE, {
        value: true, configurable: true, enumerable: false, writable: true
    });
    if (!window[SYM_DATA]) {
        Object.defineProperty(window, SYM_DATA, {
            value: [], configurable: true, enumerable: false, writable: true
        });
    }

    var actions = window[SYM_DATA];
    var inputTimers = {};
    var scrollTimer = null;
    var hoverTimer = null;
    var lastHoverSel = '';
    var dragSource = null;

    function getSelector(el) {
        if (!el || el === document || el === document.documentElement) return 'html';
        if (el === document.body) return 'body';

        // 1) id
        if (el.id && /^[a-zA-Z][\w-]*$/.test(el.id)) {
            if (document.querySelectorAll('#' + CSS.escape(el.id)).length === 1) {
                return '#' + CSS.escape(el.id);
            }
        }

        // 2) data-testid / data-id / data-qa / name / aria-label
        var attrCandidates = ['data-testid', 'data-id', 'data-qa', 'data-cy', 'name', 'aria-label'];
        for (var i = 0; i < attrCandidates.length; i++) {
            var attr = attrCandidates[i];
            var val = el.getAttribute(attr);
            if (val) {
                var sel = el.tagName.toLowerCase() + '[' + attr + '=' + JSON.stringify(val) + ']';
                try { if (document.querySelectorAll(sel).length === 1) return sel; } catch(e) {}
            }
        }

        // 3) tag + unique class combo
        if (el.classList && el.classList.length > 0) {
            var tag = el.tagName.toLowerCase();
            for (var j = 0; j < el.classList.length; j++) {
                var cls = el.classList[j];
                if (/^[a-zA-Z][\w-]+$/.test(cls) && cls.length < 60) {
                    var sel2 = tag + '.' + CSS.escape(cls);
                    try { if (document.querySelectorAll(sel2).length === 1) return sel2; } catch(e) {}
                }
            }
        }

        // 4) build path via nth-child (max depth 5)
        var parts = [];
        var cur = el;
        for (var d = 0; d < 5 && cur && cur !== document.body; d++) {
            var seg = cur.tagName.toLowerCase();
            if (cur.id && /^[a-zA-Z][\w-]*$/.test(cur.id)) {
                parts.unshift('#' + CSS.escape(cur.id));
                break;
            }
            var parent = cur.parentElement;
            if (parent) {
                var siblings = Array.from(parent.children).filter(function(c) {
                    return c.tagName === cur.tagName;
                });
                if (siblings.length > 1) {
                    seg += ':nth-child(' + (Array.from(parent.children).indexOf(cur) + 1) + ')';
                }
            }
            parts.unshift(seg);
            cur = parent;
        }
        return parts.join(' > ');
    }

    function record(obj) {
        obj.timestamp = Date.now();
        actions.push(obj);
    }

    document.addEventListener('click', function(e) {
        var tgt = e.target;
        if (!tgt || !tgt.tagName) return;
        var tag = tgt.tagName.toLowerCase();
        if ((tag === 'input' || tag === 'textarea') && !tgt.matches('[type=submit],[type=button],[type=reset],[type=checkbox],[type=radio]')) return;
        record({ type: 'click', selector: getSelector(tgt) });
    }, true);

    document.addEventListener('dblclick', function(e) {
        var tgt = e.target;
        if (!tgt || !tgt.tagName) return;
        record({ type: 'dblclick', selector: getSelector(tgt) });
    }, true);

    document.addEventListener('mouseover', function(e) {
        var tgt = e.target;
        if (!tgt || !tgt.tagName) return;
        var sel = getSelector(tgt);
        if (sel === lastHoverSel || sel === 'html' || sel === 'body') return;
        if (hoverTimer) clearTimeout(hoverTimer);
        hoverTimer = setTimeout(function() {
            hoverTimer = null;
            lastHoverSel = sel;
            var tag = tgt.tagName.toLowerCase();
            var ok = (tag === 'a' || tag === 'button' || tag === 'li' || tag === 'summary' || tag === 'details');
            if (!ok) {
                try { ok = tgt.matches('[role],[aria-haspopup],[data-toggle],[data-hover],.menu-item,.nav-item,.dropdown-toggle'); } catch(ex) {}
            }
            if (!ok) return;
            record({ type: 'hover', selector: sel });
        }, 300);
    }, true);

    document.addEventListener('change', function(e) {
        var tgt = e.target;
        if (!tgt) return;
        var tag = tgt.tagName.toLowerCase();
        if (tag === 'input' && tgt.type === 'file') {
            var files = Array.from(tgt.files || []).map(function(f) { return f.name; });
            record({ type: 'upload', selector: getSelector(tgt), fileNames: files });
            return;
        }
        if (tag === 'input' && (tgt.type === 'checkbox' || tgt.type === 'radio')) {
            record({ type: 'click', selector: getSelector(tgt) });
            return;
        }
        if (tag === 'select') {
            record({ type: 'select', selector: getSelector(tgt), value: tgt.value });
            return;
        }
    }, true);

    document.addEventListener('input', function(e) {
        var tgt = e.target;
        if (!tgt) return;
        var tag = tgt.tagName.toLowerCase();
        var isEditable = (tag === 'input' || tag === 'textarea');
        if (!isEditable && tgt.isContentEditable) isEditable = true;
        if (!isEditable) return;
        if (tgt.type === 'checkbox' || tgt.type === 'radio') return;

        var sel = getSelector(tgt);
        if (inputTimers[sel]) clearTimeout(inputTimers[sel]);
        inputTimers[sel] = setTimeout(function() {
            delete inputTimers[sel];
            var val = (tag === 'input' || tag === 'textarea') ? tgt.value : (tgt.innerText || '');
            var last = actions[actions.length - 1];
            if (last && last.type === 'fill' && last.selector === sel) {
                last.value = val;
                last.timestamp = Date.now();
            } else {
                record({ type: 'fill', selector: sel, value: val });
            }
        }, 500);
    }, true);

    var SPECIAL_KEYS = {
        'Enter': 'Enter', 'Tab': 'Tab', 'Escape': 'Escape',
        'Backspace': 'Backspace', 'Delete': 'Delete',
        'ArrowUp': 'ArrowUp', 'ArrowDown': 'ArrowDown',
        'ArrowLeft': 'ArrowLeft', 'ArrowRight': 'ArrowRight',
        ' ': 'Space', 'Home': 'Home', 'End': 'End',
        'PageUp': 'PageUp', 'PageDown': 'PageDown',
        'F1': 'F1', 'F2': 'F2', 'F3': 'F3', 'F4': 'F4',
        'F5': 'F5', 'F6': 'F6', 'F7': 'F7', 'F8': 'F8',
        'F9': 'F9', 'F10': 'F10', 'F11': 'F11', 'F12': 'F12'
    };
    document.addEventListener('keydown', function(e) {
        var mods = '';
        if (e.ctrlKey) mods += 'Control+';
        if (e.altKey) mods += 'Alt+';
        if (e.shiftKey) mods += 'Shift+';
        if (e.metaKey) mods += 'Meta+';
        var keyName = SPECIAL_KEYS[e.key];
        if (keyName) {
            record({ type: 'press_key', key: mods + keyName });
            return;
        }
        if (mods && e.key.length === 1) {
            record({ type: 'press_key', key: mods + e.key });
        }
    }, true);

    document.addEventListener('scroll', function() {
        if (scrollTimer) clearTimeout(scrollTimer);
        scrollTimer = setTimeout(function() {
            scrollTimer = null;
            record({ type: 'scroll', scrollX: Math.round(window.scrollX), scrollY: Math.round(window.scrollY) });
        }, 500);
    }, true);

    document.addEventListener('dragstart', function(e) {
        if (e.target) dragSource = { selector: getSelector(e.target) };
    }, true);
    document.addEventListener('drop', function(e) {
        if (!dragSource || !e.target) return;
        record({ type: 'drag', sourceSelector: dragSource.selector, targetSelector: getSelector(e.target) });
        dragSource = null;
    }, true);

    var origAlert = window.alert;
    var origConfirm = window.confirm;
    var origPrompt = window.prompt;
    window.alert = function(msg) {
        record({ type: 'dialog', dialogType: 'alert', message: String(msg || '') });
        return origAlert.apply(this, arguments);
    };
    window.confirm = function(msg) {
        var result = origConfirm.apply(this, arguments);
        record({ type: 'dialog', dialogType: 'confirm', message: String(msg || ''), accepted: result });
        return result;
    };
    window.prompt = function(msg, def) {
        var result = origPrompt.apply(this, arguments);
        record({ type: 'dialog', dialogType: 'prompt', message: String(msg || ''), response: result });
        return result;
    };

    window.addEventListener('popstate', function() {
        record({ type: 'navigate', url: location.href });
    });
    window.addEventListener('hashchange', function() {
        record({ type: 'navigate', url: location.href });
    });
})();
"""

# JS expressions used by Python side for collect/clear (Symbol.for keys)
_COLLECT_JS = "JSON.stringify(window[Symbol.for('__ev_d')] || [])"
_CLEAR_JS = "window[Symbol.for('__ev_a')] = false; window[Symbol.for('__ev_d')] = [];"
_NAV_PUSH_JS = (
    "window[Symbol.for('__ev_d')].push("
    "{{type:'navigate',url:{url},timestamp:Date.now()}})"
)


def _setup_navigation_reinjection(
    store: Any,
    tab: Any,
    inject_fn: Callable[[Any], Awaitable[None]],
) -> None:
    """Reinject recorder JS after top-frame navigation and record navigate."""
    from nodriver import cdp  # pylint: disable=import-outside-toplevel

    handler_key = f"_recorder_nav_{id(tab)}"
    if getattr(store, handler_key, False):
        return
    setattr(store, handler_key, True)

    async def _on_frame_navigated(event: cdp.page.FrameNavigated) -> None:
        if not store.recording:
            return
        if event.frame.parent_id:
            return
        url = event.frame.url or ""
        _logger.debug("Detected navigation during recording: %s", url)
        await asyncio.sleep(1)
        try:
            await inject_fn(tab)
            push_js = _NAV_PUSH_JS.format(url=json.dumps(url))
            await tab.evaluate(push_js, await_promise=False)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            _logger.warning("Failed to re-inject recorder after navigation: %s", exc)

    tab.add_handler(cdp.page.FrameNavigated, _on_frame_navigated)


# ---------------------------------------------------------------------------
# Recording file I/O
# ---------------------------------------------------------------------------

def _schema_version_for_engine(engine: str) -> int:
    return RECORDING_SCHEMA_VERSION if engine == "dom2" else 1


def _ensure_recordings_dir() -> Path:
    _RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    return _RECORDINGS_DIR


def _save_recording(
    name: str,
    actions: list[dict],
    cdp_port: int,
    start_url: str,
    *,
    session_id: str = "",
    backend_type: str = "ziniao",
    store_name: str = "",
    schema_version: int = 1,
    emit: Optional[list[str]] = None,
    record_secrets: bool = True,
    recording_engine: str = "legacy",
) -> dict[str, str]:
    """Save JSON metadata and optional nodriver / Playwright emitters."""
    d = _ensure_recordings_dir()
    emit = emit or ["nodriver"]
    disk_actions = actions_for_disk(
        list(actions),
        record_secrets=record_secrets,
    )

    meta = {
        "name": name,
        "schema_version": schema_version,
        "recording_engine": recording_engine,
        "created_at": datetime.now().isoformat(),
        "start_url": start_url,
        "cdp_port": cdp_port,
        "session_id": session_id,
        "backend_type": backend_type,
        "store_name": store_name,
        "action_count": len(disk_actions),
        "actions": disk_actions,
    }
    json_path = d / f"{name}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    paths: dict[str, str] = {"json": str(json_path)}
    if "nodriver" in emit:
        py_code = generate_nodriver_script(
            disk_actions, cdp_port, start_url, name,
            session_id=session_id,
            backend_type=backend_type,
            store_name=store_name,
        )
        py_path = d / f"{name}.py"
        with open(py_path, "w", encoding="utf-8") as f:
            f.write(py_code)
        paths["py"] = str(py_path)
    if "playwright" in emit:
        ts_code = generate_playwright_typescript(disk_actions, start_url, name=name)
        ts_path = d / f"{name}.spec.ts"
        with open(ts_path, "w", encoding="utf-8") as f:
            f.write(ts_code)
        paths["ts"] = str(ts_path)
    return paths


def _load_recording(name: str) -> dict[str, Any]:
    json_path = _RECORDINGS_DIR / f"{name}.json"
    if not json_path.exists():
        raise RuntimeError(f"Recording '{name}' does not exist: {json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _list_recordings() -> list[dict[str, Any]]:
    d = _ensure_recordings_dir()
    result = []
    for p in sorted(d.glob("*.json")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                meta = json.load(f)
            stem = meta.get("name", p.stem)
            py_path = p.with_suffix(".py")
            ts_path = d / f"{p.stem}.spec.ts"
            result.append({
                "name": stem,
                "created_at": meta.get("created_at", ""),
                "start_url": meta.get("start_url", ""),
                "session_id": meta.get("session_id", ""),
                "backend_type": meta.get("backend_type", ""),
                "action_count": meta.get("action_count", 0),
                "schema_version": meta.get("schema_version", 1),
                "py_file": str(py_path) if py_path.exists() else "",
                "ts_file": str(ts_path) if ts_path.exists() else "",
            })
        except (json.JSONDecodeError, OSError):
            continue
    return result


def _delete_recording(name: str) -> None:
    d = _RECORDINGS_DIR
    for suffix in (".json", ".py", ".spec.ts"):
        path = d / f"{name}{suffix}"
        if path.exists():
            path.unlink()


# ---------------------------------------------------------------------------
# MCP tool registration
# ---------------------------------------------------------------------------


def register_tools(mcp: FastMCP, session: SessionManager) -> None:

    async def _inject_recorder(tab) -> None:
        """Inject recorder JS into tab (idempotent)."""
        await tab.evaluate(_RECORDER_JS, await_promise=False)

    async def _collect_actions(tab) -> list[dict]:
        """Collect recorded actions from page via non-enumerable Symbol key."""
        raw = await tab.evaluate(_COLLECT_JS, return_by_value=True)
        if isinstance(raw, str):
            return json.loads(raw)
        return []

    async def _clear_recorder(tab) -> None:
        """Clear recorder state from page."""
        await tab.evaluate(_CLEAR_JS, await_promise=False)

    def _nav_setup(store, tab) -> None:
        _setup_navigation_reinjection(store, tab, _inject_recorder)

    @mcp.tool()
    async def recorder(
        action: str = "start",
        name: str = "",
        actions_json: str = "",
        speed: float = 1.0,
        metadata_only: bool = False,
        force: bool = False,
        reuse_tab: bool = False,
        auto_session: bool = True,
        engine: str = "dom2",
        scope: str = "active",
        max_tabs: int = 20,
        emit: str = "nodriver",
        record_secrets: bool = True,
    ) -> str:
        """Record browser actions and replay saved recordings.

        This tool records interactions such as click, dblclick, hover, fill,
        select, key press, scroll, navigation, file upload, dialog, and
        drag-and-drop. On stop, it saves JSON metadata and generates a
        standalone Python script based on nodriver. Recording defaults to
        engine dom2; replay accepts both schema v1 (legacy) and v2 (dom2)
        action lists.

        Args:
            action: The recorder action ("start" | "stop" | "replay" |
                "list" | "delete" | "view" | "status").
            name: Optional recording name. Used when saving (stop) or targeting
                replay/delete/view.
            actions_json: Optional JSON action list for replay. If provided, it
                takes priority over name.
            speed: Replay speed multiplier. Default is 1.0.
            metadata_only: For action "view", omit the actions array when True.
            force: For action "stop", when name is set and the JSON file already
                exists, overwrite if True; otherwise return an error.
            reuse_tab: For action "replay", use the current active tab instead of
                opening a new tab. Default False (always new tab for replay).
            auto_session: For action "replay", when no daemon session exists, try to
                connect using session_id/backend_type saved in the recording (default True).
            engine: For "start": "dom2" (CDP binding + buffer, default) or "legacy" (page Symbol buffer).
            scope: For "start" with dom2: "active" (current tab + poll new) or "all" (cap max_tabs).
            max_tabs: For dom2 scope=all, max pages to instrument (0 = unlimited).
            emit: For "stop": comma-separated "nodriver" and/or "playwright".
            record_secrets: For "stop": when False, redact fill values in JSON on disk.
        """
        if action == "start":
            return await _do_start(
                session, _inject_recorder, _nav_setup,
                engine=engine, scope=scope, max_tabs=max_tabs,
            )
        if action == "stop":
            return await _do_stop(
                session, name, _collect_actions, _clear_recorder, force,
                emit=parse_emit(emit),
                record_secrets=record_secrets,
            )
        if action == "replay":
            return await _do_replay(
                session, name, actions_json, speed,
                reuse_tab=reuse_tab, auto_session=auto_session,
            )
        if action == "list":
            return _do_list()
        if action == "delete":
            return _do_delete(name)
        if action == "view":
            return _do_view(name, metadata_only)
        if action == "status":
            return _do_status(session)
        raise RuntimeError(
            f"Unknown action: {action}. Supported: start, stop, replay, list, delete, view, status.",
        )


async def _do_start(
    session,
    inject_fn,
    nav_setup_fn,
    *,
    engine: str = "dom2",
    scope: str = "active",
    max_tabs: int = 20,
) -> str:
    store = session.get_active_session()
    if store.recording:
        return json.dumps({"status": "already_recording", "message": "Recording is already in progress."}, ensure_ascii=False)

    eng = (engine or "dom2").strip().lower()
    sc = (scope or "active").strip().lower()
    if sc not in ("active", "all"):
        sc = "active"
    try:
        mt = int(max_tabs)
    except (TypeError, ValueError):
        mt = 20

    if eng == "dom2":
        try:
            await session.ensure_active_regular_tab("")
            store.recording = True
            store.recording_engine = "dom2"
            store.recording_scope = sc
            store.recording_max_tabs = mt
            info = await start_dom2_capture(session, store, sc, mt)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            store.recording = False
            store.recording_engine = "legacy"
            return json.dumps({
                "status": "error",
                "message": f"dom2 recorder failed to start: {exc}",
            }, ensure_ascii=False)
        start_url = info.get("start_url", "") or ""
        store.recording_start_url = start_url
        return json.dumps({
            "status": "recording",
            "message": "Recording started (dom2). Perform actions in the browser, then call recorder(action='stop').",
            "start_url": start_url,
            "engine": "dom2",
            "scope": sc,
            "max_tabs": mt,
            "attached_targets": info.get("attached_targets", []),
        }, ensure_ascii=False)

    tab = await session.ensure_active_regular_tab("")
    start_url = getattr(getattr(tab, "target", None), "url", "") or ""
    store.recording = True
    store.recording_engine = "legacy"
    store.recording_start_url = start_url

    await inject_fn(tab)
    nav_setup_fn(store, tab)

    return json.dumps({
        "status": "recording",
        "message": "Recording started. Perform actions in the browser, then call recorder(action='stop').",
        "start_url": start_url,
        "engine": "legacy",
    }, ensure_ascii=False)


async def _do_stop(
    session,
    name,
    collect_fn,
    clear_fn,
    force: bool = False,
    *,
    emit: Optional[list[str]] = None,
    record_secrets: bool = True,
) -> str:
    store = session.get_active_session()
    if not store.recording:
        return json.dumps({"status": "error", "message": "No active recording."}, ensure_ascii=False)

    eng = getattr(store, "recording_engine", "legacy") or "legacy"
    emit = emit or ["nodriver"]

    if eng == "dom2":
        buf = getattr(store, "recording_ring_buffer", None)
        dropped = 0
        if buf is not None:
            actions, dropped = buf.drain_keep_stats()
        else:
            actions = []
        store.recording_dropped_events = int(dropped)
        await stop_dom2_capture(store)
        actions.sort(key=lambda x: int(x.get("seq", 0)))
    else:
        tab = await session.ensure_active_regular_tab("")
        actions = await collect_fn(tab)
        await clear_fn(tab)

    store.recording = False
    store.recording_engine = "legacy"

    if not actions:
        return json.dumps({"status": "empty", "message": "No actions were recorded."}, ensure_ascii=False)

    rec_name = (name or "").strip() or datetime.now().strftime("rec_%Y%m%d_%H%M%S")
    json_path = _RECORDINGS_DIR / f"{rec_name}.json"
    if (name or "").strip() and json_path.exists() and not force:
        return json.dumps({
            "status": "error",
            "message": (
                f"Recording '{rec_name}' already exists. Use another --name or pass force=true to overwrite."
            ),
        }, ensure_ascii=False)

    paths = _save_recording(
        rec_name,
        actions,
        store.cdp_port,
        store.recording_start_url,
        session_id=store.store_id,
        backend_type=store.backend_type,
        store_name=store.store_name,
        schema_version=_schema_version_for_engine(eng),
        emit=emit,
        record_secrets=record_secrets,
        recording_engine=eng,
    )

    msg_parts = [f"Recorded {len(actions)} actions."]
    if "py" in paths:
        msg_parts.append(f"Python: {paths['py']}")
    if "ts" in paths:
        msg_parts.append(f"Playwright TS: {paths['ts']}")
    if eng == "dom2" and getattr(store, "recording_dropped_events", 0):
        msg_parts.append(f"(dropped_overflow={store.recording_dropped_events})")

    return json.dumps({
        "status": "saved",
        "name": rec_name,
        "action_count": len(actions),
        "schema_version": _schema_version_for_engine(eng),
        "files": paths,
        "message": " ".join(msg_parts),
    }, ensure_ascii=False)


async def _scroll_to(tab: Any, selector: str) -> None:
    """Scroll element into view before interaction."""
    try:
        await tab.evaluate(
            f"document.querySelector({json.dumps(selector)})"
            f"?.scrollIntoView({{block:'center',behavior:'instant'}})",
        )
        await asyncio.sleep(0.15)
    except Exception:  # pylint: disable=broad-exception-caught
        pass


async def _do_replay(
    session,
    name,
    actions_json,
    speed,
    reuse_tab: bool = False,
    auto_session: bool = True,
) -> str:
    meta: dict[str, Any] = {}
    start_url = ""
    if actions_json:
        actions = json.loads(actions_json)
    elif name:
        meta = _load_recording(name)
        actions = meta.get("actions", [])
        start_url = (meta.get("start_url") or "").strip()
    else:
        raise RuntimeError(
            "Replay requires a recording `name` (saved file) or `actions_json` (inline JSON array).",
        )

    if not actions:
        return json.dumps({"status": "empty", "message": "Action list is empty."}, ensure_ascii=False)

    if auto_session and meta and not session.has_active_session():
        ctx = resolve_recording_browser_context(meta, _read_state_file())
        if ctx is not None:
            await session.attach_from_recording_context(ctx)

    from ..iframe import find_element  # pylint: disable=import-outside-toplevel
    from ..stealth.human_behavior import (  # pylint: disable=import-outside-toplevel
        human_click as _hclick,
        human_fill as _hfill,
    )
    from nodriver import cdp as _cdp  # pylint: disable=import-outside-toplevel

    if reuse_tab:
        try:
            tab = session.get_active_tab()
        except RuntimeError:
            tab = await session.ensure_active_regular_tab(start_url)
    else:
        tab = await session.open_replay_tab(start_url)
    store = session.get_active_session()
    is_ziniao = store.backend_type == "ziniao"
    cfg = None
    sc = session.stealth_config
    if sc.enabled and sc.human_behavior:
        cfg = sc.to_behavior_config()
    speed = max(0.1, speed)
    replayed = 0

    # Pre-collect dialog responses so the CDP handler can use them in order
    dialog_responses = [a for a in actions if a.get("type") == "dialog"]
    _dialog_idx = [0]

    async def _on_dialog(event: _cdp.page.JavascriptDialogOpening) -> None:
        accept = True
        prompt_text = ""
        if _dialog_idx[0] < len(dialog_responses):
            dr = dialog_responses[_dialog_idx[0]]
            accept = dr.get("accepted", True)
            prompt_text = str(dr.get("response") or "")
            _dialog_idx[0] += 1
        try:
            await tab.send(_cdp.page.handle_java_script_dialog(
                accept=accept, prompt_text=prompt_text,
            ))
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    tab.add_handler(_cdp.page.JavascriptDialogOpening, _on_dialog)

    # Multi-tab: map recorded target_id -> replay tab
    tab_map: dict[str, Any] = {}
    current_target_id: str | None = None

    for act in actions:
        act = normalize_action_for_replay(act)
        delay_ms = act.get("delay_ms", 0)
        if delay_ms > 100:
            await asyncio.sleep(delay_ms / 1000 / speed)

        # Switch tab when target_id changes
        rec_tid = act.get("target_id")
        if rec_tid and rec_tid != current_target_id:
            if current_target_id is None:
                tab_map[rec_tid] = tab
            elif rec_tid in tab_map:
                tab = tab_map[rec_tid]
            else:
                try:
                    from ..session import _filter_tabs  # pylint: disable=import-outside-toplevel
                    all_tabs = _filter_tabs(list(store.browser.tabs))
                    known_ids = {id(t) for t in tab_map.values()}
                    for t in all_tabs:
                        if id(t) not in known_ids:
                            tab_map[rec_tid] = t
                            tab = t
                            break
                except Exception:  # pylint: disable=broad-exception-caught
                    pass
            current_target_id = rec_tid

        act_type = act.get("type", "")
        try:
            if act_type == "click":
                sel = act.get("selector") or "body"
                await _scroll_to(tab, sel)
                elem = await find_element(tab, sel, store, timeout=10)
                if elem:
                    if cfg or is_ziniao:
                        await _hclick(tab, sel, cfg=cfg, element=elem)
                    else:
                        await elem.click()

            elif act_type == "dblclick":
                sel = act.get("selector") or "body"
                await _scroll_to(tab, sel)
                await tab.evaluate(
                    f"document.querySelector({json.dumps(sel)})"
                    f"?.dispatchEvent(new MouseEvent('dblclick',{{bubbles:true}}))",
                )

            elif act_type == "hover":
                sel = act.get("selector") or "body"
                await _scroll_to(tab, sel)
                await tab.evaluate(
                    f"(function(){{var el=document.querySelector({json.dumps(sel)});"
                    f"if(!el)return;"
                    f"el.dispatchEvent(new MouseEvent('mouseover',{{bubbles:true}}));"
                    f"el.dispatchEvent(new MouseEvent('mouseenter',{{bubbles:false}}))}})()",
                )
                await asyncio.sleep(0.15)

            elif act_type == "fill":
                sel = act.get("selector") or "body"
                await _scroll_to(tab, sel)
                elem = await find_element(tab, sel, store, timeout=10)
                if elem:
                    if cfg or is_ziniao:
                        await _hfill(tab, sel, act.get("value", ""), cfg=cfg, element=elem)
                    else:
                        await elem.clear_input()
                        await elem.send_keys(act.get("value", ""))

            elif act_type == "select":
                sel = act.get("selector") or "select"
                val = act.get("value", "")
                await _scroll_to(tab, sel)
                await tab.evaluate(
                    f"document.querySelector({json.dumps(sel)}).value = {json.dumps(val)};"
                    f"document.querySelector({json.dumps(sel)}).dispatchEvent(new Event('change'))",
                )

            elif act_type == "press_key":
                from ._keys import parse_key as _parse  # pylint: disable=import-outside-toplevel
                key = act.get("key", "Enter")
                actual_key, vk, modifiers = _parse(key)
                await tab.send(_cdp.input_.dispatch_key_event(
                    "rawKeyDown", windows_virtual_key_code=vk, modifiers=modifiers, key=actual_key,
                ))
                await tab.send(_cdp.input_.dispatch_key_event(
                    "keyUp", windows_virtual_key_code=vk, modifiers=modifiers, key=actual_key,
                ))

            elif act_type == "scroll":
                sx = int(act.get("scrollX", 0))
                sy = int(act.get("scrollY", 0))
                await tab.evaluate(f"window.scrollTo({sx},{sy})")
                await asyncio.sleep(0.2)

            elif act_type == "navigate":
                url = act.get("url", "")
                if url:
                    await tab.send(_cdp.page.navigate(url=url))
                    await tab.sleep(1)

            elif act_type == "upload":
                sel = act.get("selector") or "input[type=file]"
                file_names = act.get("fileNames") or []
                _logger.info(
                    "Upload action: selector=%s, fileNames=%s (provide actual file paths for replay)",
                    sel, file_names,
                )

            elif act_type == "dialog":
                pass  # handled by _on_dialog CDP handler

            elif act_type == "drag":
                src_sel = act.get("sourceSelector") or "body"
                tgt_sel = act.get("targetSelector") or "body"
                await _scroll_to(tab, src_sel)
                await tab.evaluate(
                    f"(function(){{var s=document.querySelector({json.dumps(src_sel)}),"
                    f"t=document.querySelector({json.dumps(tgt_sel)});"
                    f"if(!s||!t)return;"
                    f"var d=new DataTransfer();"
                    f"s.dispatchEvent(new DragEvent('dragstart',{{bubbles:true,dataTransfer:d}}));"
                    f"t.dispatchEvent(new DragEvent('dragover',{{bubbles:true,dataTransfer:d}}));"
                    f"t.dispatchEvent(new DragEvent('drop',{{bubbles:true,dataTransfer:d}}));"
                    f"s.dispatchEvent(new DragEvent('dragend',{{bubbles:true,dataTransfer:d}}))}})()",
                )

            replayed += 1
        except Exception as exc:  # pylint: disable=broad-exception-caught
            _logger.warning("Replay step %d (%s) failed: %s", replayed + 1, act_type, exc)

    # Clean up dialog handler
    try:
        lst = tab.handlers.get(_cdp.page.JavascriptDialogOpening, [])
        if _on_dialog in lst:
            lst.remove(_on_dialog)
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    return json.dumps({
        "status": "done",
        "replayed": replayed,
        "total": len(actions),
        "message": f"Replayed {replayed}/{len(actions)} actions.",
    }, ensure_ascii=False)


def _do_list() -> str:
    recordings = _list_recordings()
    return json.dumps({
        "recordings": recordings,
        "count": len(recordings),
    }, ensure_ascii=False, indent=2)


def _do_delete(name: str) -> str:
    if not name:
        raise RuntimeError("Delete requires the name parameter.")
    _delete_recording(name)
    return json.dumps({
        "status": "deleted",
        "name": name,
    }, ensure_ascii=False)


def _do_view(name: str, metadata_only: bool = False) -> str:
    n = (name or "").strip()
    if not n:
        raise RuntimeError("View requires the name parameter.")
    meta = _load_recording(n)
    path = (_RECORDINGS_DIR / f"{n}.json").resolve()
    recording: dict[str, Any] = dict(meta)
    if metadata_only:
        recording.pop("actions", None)
    return json.dumps({
        "status": "ok",
        "path": str(path),
        "recording": recording,
        "metadata_only": metadata_only,
    }, ensure_ascii=False, indent=2)


def _do_status(session) -> str:
    store = session.get_active_session()
    buf = getattr(store, "recording_ring_buffer", None)
    pending = len(buf) if buf is not None else 0
    return json.dumps({
        "status": "ok",
        "recording_active": store.recording,
        "recording_start_url": getattr(store, "recording_start_url", "") or "",
        "engine": getattr(store, "recording_engine", "legacy") or "legacy",
        "scope": getattr(store, "recording_scope", "") or "",
        "max_tabs": int(getattr(store, "recording_max_tabs", 0) or 0),
        "buffered_events": pending,
        "attached_targets": list(getattr(store, "recording_attached_targets", set()) or []),
        "dropped_events": int(getattr(store, "recording_dropped_events", 0) or 0),
    }, ensure_ascii=False)
