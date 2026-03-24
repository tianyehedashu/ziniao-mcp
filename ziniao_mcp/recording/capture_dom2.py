"""DOM2 recorder: Runtime.addBinding + buffer, multi-tab, frame-tree inject."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import TYPE_CHECKING, Any, Callable

from nodriver import cdp

from .buffer import RecordingBuffer
from .locator import build_locator_dict

if TYPE_CHECKING:
    from nodriver import Tab

    from ziniao_mcp.session import SessionManager, StoreSession

_logger = logging.getLogger("ziniao-mcp-debug")

def make_binding_name(store_id: str) -> str:
    """CDP binding must be a valid JS identifier fragment."""
    h = hashlib.sha256(str(store_id).encode()).hexdigest()[:12]
    return f"ziniaoRec{h}"


def _recorder_js_body(binding_name: str) -> str:
    loc_fn = build_locator_dict("el")
    return rf"""
(function() {{
    var BN = {json.dumps(binding_name)};
    var SYM = Symbol.for('__zin_rec_v2');
    if (window[SYM]) return;
    window[SYM] = true;

    function post(obj) {{
        try {{
            if (typeof window[BN] === 'function') window[BN](JSON.stringify(obj));
        }} catch (e) {{}}
    }}

    function getSelector(el) {{
        if (!el || el === document || el === document.documentElement) return 'html';
        if (el === document.body) return 'body';
        if (el.id && /^[a-zA-Z][\w-]*$/.test(el.id)) {{
            if (document.querySelectorAll('#' + CSS.escape(el.id)).length === 1)
                return '#' + CSS.escape(el.id);
        }}
        var attrCandidates = ['data-testid', 'data-id', 'data-qa', 'data-cy', 'name', 'aria-label'];
        for (var i = 0; i < attrCandidates.length; i++) {{
            var attr = attrCandidates[i];
            var val = el.getAttribute(attr);
            if (val) {{
                var sel = el.tagName.toLowerCase() + '[' + attr + '=' + JSON.stringify(val) + ']';
                try {{ if (document.querySelectorAll(sel).length === 1) return sel; }} catch(e) {{}}
            }}
        }}
        if (el.classList && el.classList.length > 0) {{
            var tag = el.tagName.toLowerCase();
            for (var j = 0; j < el.classList.length; j++) {{
                var cls = el.classList[j];
                if (/^[a-zA-Z][\w-]+$/.test(cls) && cls.length < 60) {{
                    var sel2 = tag + '.' + CSS.escape(cls);
                    try {{ if (document.querySelectorAll(sel2).length === 1) return sel2; }} catch(e) {{}}
                }}
            }}
        }}
        var parts = [];
        var cur = el;
        for (var d = 0; d < 5 && cur && cur !== document.body; d++) {{
            var seg = cur.tagName.toLowerCase();
            if (cur.id && /^[a-zA-Z][\w-]*$/.test(cur.id)) {{
                parts.unshift('#' + CSS.escape(cur.id));
                break;
            }}
            var parent = cur.parentElement;
            if (parent) {{
                var siblings = Array.from(parent.children).filter(function(c) {{
                    return c.tagName === cur.tagName;
                }});
                if (siblings.length > 1) {{
                    seg += ':nth-child(' + (Array.from(parent.children).indexOf(cur) + 1) + ')';
                }}
            }}
            parts.unshift(seg);
            cur = parent;
        }}
        return parts.join(' > ');
    }}

    function getLocator(el) {{
        var L = {loc_fn};
        return L || {{ strategy: 'css', value: getSelector(el) }};
    }}

    function record(obj) {{
        obj.timestamp = Date.now();
        obj.perfTs = performance.now();
        obj.frameUrl = location.href;
        post(obj);
    }}

    var inputTimers = {{}};

    document.addEventListener('click', function(e) {{
        var tgt = e.target;
        if (!tgt || !tgt.tagName) return;
        var tag = tgt.tagName.toLowerCase();
        if ((tag === 'input' || tag === 'textarea') &&
            !tgt.matches('[type=submit],[type=button],[type=reset],[type=checkbox],[type=radio]')) return;
        var loc = getLocator(tgt);
        if (!loc || !loc.strategy) loc = {{ strategy: 'css', value: getSelector(tgt) }};
        record({{ type: 'click', selector: getSelector(tgt), locator: loc }});
    }}, true);

    document.addEventListener('change', function(e) {{
        var tgt = e.target;
        if (!tgt) return;
        var tag = tgt.tagName.toLowerCase();
        if (tag === 'input' && (tgt.type === 'checkbox' || tgt.type === 'radio')) {{
            var loc = getLocator(tgt);
            record({{ type: 'click', selector: getSelector(tgt), locator: loc }});
            return;
        }}
        if (tag === 'select') {{
            var loc = getLocator(tgt);
            record({{ type: 'select', selector: getSelector(tgt), locator: loc, value: tgt.value }});
        }}
    }}, true);

    document.addEventListener('input', function(e) {{
        var tgt = e.target;
        if (!tgt) return;
        var tag = tgt.tagName.toLowerCase();
        if (tag !== 'input' && tag !== 'textarea') return;
        if (tgt.type === 'checkbox' || tgt.type === 'radio') return;
        var sel = getSelector(tgt);
        var loc = getLocator(tgt);
        if (inputTimers[sel]) clearTimeout(inputTimers[sel]);
        inputTimers[sel] = setTimeout(function() {{
            delete inputTimers[sel];
            record({{ type: 'fill', selector: sel, locator: loc, value: tgt.value }});
        }}, 500);
    }}, true);

    var SPECIAL_KEYS = {{
        'Enter': 'Enter', 'Tab': 'Tab', 'Escape': 'Escape',
        'Backspace': 'Backspace', 'Delete': 'Delete',
        'ArrowUp': 'ArrowUp', 'ArrowDown': 'ArrowDown',
        'ArrowLeft': 'ArrowLeft', 'ArrowRight': 'ArrowRight'
    }};
    document.addEventListener('keydown', function(e) {{
        var keyName = SPECIAL_KEYS[e.key];
        if (!keyName) return;
        var mods = '';
        if (e.ctrlKey) mods += 'Control+';
        if (e.altKey) mods += 'Alt+';
        if (e.shiftKey) mods += 'Shift+';
        if (e.metaKey) mods += 'Meta+';
        record({{ type: 'press_key', key: mods + keyName }});
    }}, true);

    window.addEventListener('popstate', function() {{
        record({{ type: 'navigate', url: location.href }});
    }});
    window.addEventListener('hashchange', function() {{
        record({{ type: 'navigate', url: location.href }});
    }});
}})();
"""


def _make_binding_handler(
    tab: "Tab",
    store: "StoreSession",
    binding_name: str,
) -> Callable[..., Any]:
    target_id = str(tab.target_id)

    async def _on_binding(event: cdp.runtime.BindingCalled) -> None:
        if event.name != binding_name:
            return
        if not store.recording or getattr(store, "recording_engine", "legacy") != "dom2":
            return
        buf = getattr(store, "recording_ring_buffer", None)
        if buf is None:
            return
        try:
            payload = json.loads(event.payload) if event.payload else {}
        except json.JSONDecodeError:
            return
        payload["target_id"] = target_id
        payload["seq"] = int(getattr(store, "recording_seq", 0))
        store.recording_seq = int(getattr(store, "recording_seq", 0)) + 1
        t0 = float(getattr(store, "recording_monotonic_t0", 0.0) or 0.0)
        payload["mono_ts"] = time.monotonic() - t0
        buf.append(payload)

    return _on_binding


async def _attach_dom2_to_tab(
    tab: "Tab",
    store: "StoreSession",
    binding_name: str,
    js: str,
) -> None:
    await tab.send(cdp.runtime.add_binding(name=binding_name))
    handler = _make_binding_handler(tab, store, binding_name)
    tab.add_handler(cdp.runtime.BindingCalled, handler)
    store.recording_dom2_handlers.append((tab, handler))

    sid = await tab.send(
        cdp.page.add_script_to_evaluate_on_new_document(
            source=js,
            run_immediately=True,
        ),
    )
    store.recording_script_entries.append((tab, sid))


def _tabs_to_attach(
    session: "SessionManager",
    store: "StoreSession",
    scope: str,
    max_tabs: int,
) -> list:
    from ziniao_mcp.session import _filter_tabs  # pylint: disable=import-outside-toplevel

    _ = session
    store.browser  # noqa: B018  # ensure exists
    tabs = _filter_tabs(list(store.browser.tabs))
    if not tabs:
        return []
    if scope == "all":
        if max_tabs > 0:
            return tabs[:max_tabs]
        return tabs
    # active: current index only
    idx = min(store.active_tab_index, len(tabs) - 1)
    if idx < 0:
        idx = 0
    return [tabs[idx]]


async def start_dom2_capture(
    session: "SessionManager",
    store: "StoreSession",
    scope: str,
    max_tabs: int,
) -> dict[str, Any]:
    from ziniao_mcp.session import _filter_tabs  # pylint: disable=import-outside-toplevel

    binding_name = make_binding_name(store.store_id)
    store.recording_binding_name = binding_name
    store.recording_ring_buffer = RecordingBuffer()
    store.recording_seq = 0
    store.recording_monotonic_t0 = time.monotonic()
    store.recording_dom2_handlers = []
    store.recording_script_entries = []
    store.recording_dropped_events = 0
    store.recording_scope = scope
    store.recording_max_tabs = max_tabs
    store.recording_attached_targets = set()

    js = _recorder_js_body(binding_name)
    attach_list = _tabs_to_attach(session, store, scope, max_tabs)

    for t in attach_list:
        tid = str(t.target_id)
        if tid in store.recording_attached_targets:
            continue
        try:
            await _attach_dom2_to_tab(t, store, binding_name, js)
            store.recording_attached_targets.add(tid)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            _logger.warning("dom2 attach tab failed: %s", exc)

    # Poll: new tabs / scope all missing tabs
    async def _poll() -> None:
        try:
            while store.recording and getattr(store, "recording_engine", "") == "dom2":
                await asyncio.sleep(1.5)
                try:
                    await store.browser.update_targets()
                except Exception:  # pylint: disable=broad-exception-caught
                    continue
                if not store.recording:
                    break
                tabs = _filter_tabs(list(store.browser.tabs))
                candidates: list = tabs if scope == "all" else (
                    [tabs[min(store.active_tab_index, len(tabs) - 1)]] if tabs else []
                )
                if max_tabs > 0 and scope == "all":
                    candidates = candidates[:max_tabs]
                for t in candidates:
                    tid = str(t.target_id)
                    if tid in store.recording_attached_targets:
                        continue
                    try:
                        await _attach_dom2_to_tab(t, store, binding_name, js)
                        store.recording_attached_targets.add(tid)
                    except Exception as exc:  # pylint: disable=broad-exception-caught
                        _logger.debug("poll attach: %s", exc)
        except asyncio.CancelledError:
            pass

    store.recording_poll_task = asyncio.create_task(_poll())
    start_tab = attach_list[0] if attach_list else None
    start_url = getattr(getattr(start_tab, "target", None), "url", "") or ""
    return {"binding": binding_name, "attached_targets": list(store.recording_attached_targets), "start_url": start_url}


async def stop_dom2_capture(store: "StoreSession") -> None:
    task = getattr(store, "recording_poll_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        store.recording_poll_task = None

    for tab, handler in list(getattr(store, "recording_dom2_handlers", []) or []):
        try:
            lst = tab.handlers.get(cdp.runtime.BindingCalled, [])
            if handler in lst:
                lst.remove(handler)
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        try:
            await tab.send(cdp.runtime.remove_binding(name=store.recording_binding_name))
        except Exception:  # pylint: disable=broad-exception-caught
            pass
    store.recording_dom2_handlers = []

    for tab, sid in list(getattr(store, "recording_script_entries", []) or []):
        try:
            await tab.send(cdp.page.remove_script_to_evaluate_on_new_document(identifier=sid))
        except Exception:  # pylint: disable=broad-exception-caught
            pass
    store.recording_script_entries = []

    buf = getattr(store, "recording_ring_buffer", None)
    if buf is not None:
        store.recording_dropped_events = int(getattr(buf, "dropped", 0) or 0)
    store.recording_ring_buffer = None
    store.recording_binding_name = ""
    store.recording_attached_targets = set()
