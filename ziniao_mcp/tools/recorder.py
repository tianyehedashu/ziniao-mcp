"""Browser action recording and code generation tool."""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..session import SessionManager

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

    // --- click ---
    document.addEventListener('click', function(e) {
        var tgt = e.target;
        if (!tgt || !tgt.tagName) return;
        var tag = tgt.tagName.toLowerCase();
        if ((tag === 'input' || tag === 'textarea') && !tgt.matches('[type=submit],[type=button],[type=reset],[type=checkbox],[type=radio]')) return;
        record({ type: 'click', selector: getSelector(tgt) });
    }, true);

    // --- checkbox / radio ---
    document.addEventListener('change', function(e) {
        var tgt = e.target;
        if (!tgt) return;
        var tag = tgt.tagName.toLowerCase();
        if (tag === 'input' && (tgt.type === 'checkbox' || tgt.type === 'radio')) {
            record({ type: 'click', selector: getSelector(tgt) });
            return;
        }
        if (tag === 'select') {
            record({ type: 'select', selector: getSelector(tgt), value: tgt.value });
            return;
        }
    }, true);

    // --- input (debounced fill) ---
    document.addEventListener('input', function(e) {
        var tgt = e.target;
        if (!tgt) return;
        var tag = tgt.tagName.toLowerCase();
        if (tag !== 'input' && tag !== 'textarea') return;
        if (tgt.type === 'checkbox' || tgt.type === 'radio') return;

        var sel = getSelector(tgt);
        if (inputTimers[sel]) clearTimeout(inputTimers[sel]);
        inputTimers[sel] = setTimeout(function() {
            delete inputTimers[sel];
            var last = actions[actions.length - 1];
            if (last && last.type === 'fill' && last.selector === sel) {
                last.value = tgt.value;
                last.timestamp = Date.now();
            } else {
                record({ type: 'fill', selector: sel, value: tgt.value });
            }
        }, 500);
    }, true);

    // --- special keys ---
    var SPECIAL_KEYS = {
        'Enter': 'Enter', 'Tab': 'Tab', 'Escape': 'Escape',
        'Backspace': 'Backspace', 'Delete': 'Delete',
        'ArrowUp': 'ArrowUp', 'ArrowDown': 'ArrowDown',
        'ArrowLeft': 'ArrowLeft', 'ArrowRight': 'ArrowRight'
    };
    document.addEventListener('keydown', function(e) {
        var keyName = SPECIAL_KEYS[e.key];
        if (!keyName) return;
        var mods = '';
        if (e.ctrlKey) mods += 'Control+';
        if (e.altKey) mods += 'Alt+';
        if (e.shiftKey) mods += 'Shift+';
        if (e.metaKey) mods += 'Meta+';
        record({ type: 'press_key', key: mods + keyName });
    }, true);

    // --- navigation (popstate / hashchange) ---
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

# ---------------------------------------------------------------------------
# Python code generator
# ---------------------------------------------------------------------------


def _generate_python_script(
    actions: list[dict[str, Any]],
    cdp_port: int,
    start_url: str,
    name: str = "",
) -> str:
    """Convert JSON action list to a standalone nodriver Python script."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = name or "recording"

    lines: list[str] = []
    lines.append(f'"""Auto-generated by ziniao-mcp recorder - {now_str} recording: {title}"""')
    lines.append("")
    lines.append("import argparse")
    lines.append("import asyncio")
    lines.append("import random")
    lines.append("")
    lines.append("import nodriver")
    lines.append("from nodriver import cdp")
    lines.append("")
    lines.append("")
    lines.append("async def main(port: int) -> None:")
    lines.append('    browser = await nodriver.Browser.create(host="127.0.0.1", port=port)')
    lines.append("    tab = browser.tabs[0]")
    lines.append("")

    if start_url:
        lines.append("    # Navigate to start URL")
        lines.append(f"    await tab.get({start_url!r})")
        lines.append("    await tab.sleep(1)")
        lines.append("")

    step = 0
    prev_ts = actions[0]["timestamp"] if actions else 0

    for act in actions:
        step += 1
        act_type = act.get("type", "")
        ts = act.get("timestamp", prev_ts)
        delay = max(0, ts - prev_ts) / 1000
        prev_ts = ts

        if delay > 0.2 and step > 1:
            lines.append(f"    await tab.sleep({round(delay, 1)})")

        if act_type == "click":
            sel = act["selector"]
            lines.append(f"    # {step}. Click {sel}")
            lines.append(f"    elem = await tab.select({sel!r}, timeout=10)")
            lines.append("    if elem:")
            lines.append("        pos = await elem.get_position()")
            lines.append("        if pos:")
            lines.append("            cx, cy = pos.center")
            lines.append("            await tab.mouse_click(cx, cy)")
            lines.append("        else:")
            lines.append("            await elem.mouse_click()")

        elif act_type == "fill":
            sel = act["selector"]
            val = act.get("value", "")
            lines.append(f"    # {step}. Fill {sel}")
            lines.append(f"    elem = await tab.select({sel!r}, timeout=10)")
            lines.append("    if elem:")
            lines.append("        pos = await elem.get_position()")
            lines.append("        if pos:")
            lines.append("            await tab.mouse_click(*pos.center)")
            lines.append("        else:")
            lines.append("            await elem.mouse_click()")
            lines.append("        await asyncio.sleep(random.uniform(0.1, 0.3))")
            lines.append("        await tab.send(cdp.input_.dispatch_key_event('rawKeyDown', windows_virtual_key_code=65, modifiers=2))")
            lines.append("        await tab.send(cdp.input_.dispatch_key_event('keyUp', windows_virtual_key_code=65, modifiers=2))")
            lines.append("        await asyncio.sleep(0.05)")
            lines.append("        await tab.send(cdp.input_.dispatch_key_event('rawKeyDown', windows_virtual_key_code=8))")
            lines.append("        await tab.send(cdp.input_.dispatch_key_event('keyUp', windows_virtual_key_code=8))")
            lines.append(f"        for char in {val!r}:")
            lines.append("            await tab.send(cdp.input_.dispatch_key_event('char', text=char))")
            lines.append("            await asyncio.sleep(random.uniform(0.05, 0.15))")

        elif act_type == "select":
            sel = act["selector"]
            val = act.get("value", "")
            lines.append(f"    # {step}. Select {sel} = {val}")
            js_code = (
                f"document.querySelector({json.dumps(sel)}).value = {json.dumps(val)}; "
                f"document.querySelector({json.dumps(sel)}).dispatchEvent(new Event('change'))"
            )
            lines.append(f"    await tab.evaluate({js_code!r})")

        elif act_type == "press_key":
            key = act.get("key", "Enter")
            lines.append(f"    # {step}. Press key {key}")
            _append_press_key_code(lines, key)

        elif act_type == "navigate":
            url = act.get("url", "")
            lines.append(f"    # {step}. Navigate to {url}")
            lines.append(f"    await tab.get({url!r})")
            lines.append("    await tab.sleep(1)")

        else:
            lines.append(f"    # {step}. Unknown action: {act_type}")

        lines.append("")

    lines.append("")
    lines.append('if __name__ == "__main__":')
    lines.append('    parser = argparse.ArgumentParser(description="Replay a ziniao-mcp recording")')
    lines.append(f'    parser.add_argument("--port", type=int, default={cdp_port}, help="CDP port")')
    lines.append("    args = parser.parse_args()")
    lines.append("    asyncio.run(main(args.port))")
    lines.append("")

    return "\n".join(lines)


def _append_press_key_code(lines: list[str], key: str) -> None:
    """Append nodriver CDP code for a press_key action."""
    from ._keys import parse_key as _parse  # pylint: disable=import-outside-toplevel

    actual_key, vk, modifiers = _parse(key)

    lines.append("    from nodriver import cdp")
    lines.append("    await tab.send(cdp.input_.dispatch_key_event(")
    lines.append(f"        \"rawKeyDown\", windows_virtual_key_code={vk}, modifiers={modifiers}, key={actual_key!r}")
    lines.append("    ))")
    lines.append("    await tab.send(cdp.input_.dispatch_key_event(")
    lines.append(f"        \"keyUp\", windows_virtual_key_code={vk}, modifiers={modifiers}, key={actual_key!r}")
    lines.append("    ))")


# ---------------------------------------------------------------------------
# Recording file I/O
# ---------------------------------------------------------------------------


def _ensure_recordings_dir() -> Path:
    _RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    return _RECORDINGS_DIR


def _save_recording(
    name: str,
    actions: list[dict],
    cdp_port: int,
    start_url: str,
) -> dict[str, str]:
    """Save JSON metadata and generated Python script, then return file paths."""
    d = _ensure_recordings_dir()

    meta = {
        "name": name,
        "created_at": datetime.now().isoformat(),
        "start_url": start_url,
        "cdp_port": cdp_port,
        "action_count": len(actions),
        "actions": actions,
    }
    json_path = d / f"{name}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    py_code = _generate_python_script(actions, cdp_port, start_url, name)
    py_path = d / f"{name}.py"
    with open(py_path, "w", encoding="utf-8") as f:
        f.write(py_code)

    return {"json": str(json_path), "py": str(py_path)}


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
            result.append({
                "name": meta.get("name", p.stem),
                "created_at": meta.get("created_at", ""),
                "start_url": meta.get("start_url", ""),
                "action_count": meta.get("action_count", 0),
                "py_file": str(p.with_suffix(".py")),
            })
        except (json.JSONDecodeError, OSError):
            continue
    return result


def _delete_recording(name: str) -> None:
    d = _RECORDINGS_DIR
    for suffix in (".json", ".py"):
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

    def _setup_navigation_reinjection(store, tab) -> None:
        """Reinject recorder JS after top-frame navigation and record navigate."""
        from nodriver import cdp  # pylint: disable=import-outside-toplevel

        handler_key = f"_recorder_nav_{id(tab)}"
        if getattr(store, handler_key, False):
            return
        setattr(store, handler_key, True)

        async def _on_frame_navigated(event: cdp.page.FrameNavigated):
            if not store.recording:
                return
            if event.frame.parent_id:
                return
            url = event.frame.url or ""
            _logger.debug("Detected navigation during recording: %s", url)
            await asyncio.sleep(1)
            try:
                await _inject_recorder(tab)
                push_js = _NAV_PUSH_JS.format(url=json.dumps(url))
                await tab.evaluate(push_js, await_promise=False)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                _logger.warning("Failed to re-inject recorder after navigation: %s", exc)

        tab.add_handler(cdp.page.FrameNavigated, _on_frame_navigated)

    @mcp.tool()
    async def recorder(
        action: str = "start",
        name: str = "",
        actions_json: str = "",
        speed: float = 1.0,
    ) -> str:
        """Record browser actions and replay saved recordings.

        This tool records interactions such as click, fill, key press, and
        navigation. On stop, it saves JSON metadata and generates a standalone
        Python script based on nodriver.

        Args:
            action: The recorder action ("start" | "stop" | "replay" |
                "list" | "delete").
            name: Optional recording name. Used when saving (stop) or targeting
                replay/delete.
            actions_json: Optional JSON action list for replay. If provided, it
                takes priority over name.
            speed: Replay speed multiplier. Default is 1.0.
        """
        if action == "start":
            return await _do_start(session, _inject_recorder, _setup_navigation_reinjection)
        if action == "stop":
            return await _do_stop(session, name, _collect_actions, _clear_recorder)
        if action == "replay":
            return await _do_replay(session, name, actions_json, speed)
        if action == "list":
            return _do_list()
        if action == "delete":
            return _do_delete(name)
        raise RuntimeError(f"Unknown action: {action}. Supported: start, stop, replay, list, delete.")


async def _do_start(session, inject_fn, nav_setup_fn) -> str:
    store = session.get_active_session()
    if store.recording:
        return json.dumps({"status": "already_recording", "message": "Recording is already in progress."}, ensure_ascii=False)

    tab = session.get_active_tab()
    start_url = getattr(getattr(tab, "target", None), "url", "") or ""
    store.recording = True
    store.recording_start_url = start_url

    await inject_fn(tab)
    nav_setup_fn(store, tab)

    return json.dumps({
        "status": "recording",
        "message": "Recording started. Perform actions in the browser, then call recorder(action='stop').",
        "start_url": start_url,
    }, ensure_ascii=False)


async def _do_stop(session, name, collect_fn, clear_fn) -> str:
    store = session.get_active_session()
    if not store.recording:
        return json.dumps({"status": "error", "message": "No active recording."}, ensure_ascii=False)

    tab = session.get_active_tab()
    actions = await collect_fn(tab)

    # Calculate delay_ms between adjacent actions
    for i in range(len(actions) - 1, 0, -1):
        actions[i]["delay_ms"] = max(0, actions[i].get("timestamp", 0) - actions[i - 1].get("timestamp", 0))
    if actions:
        actions[0]["delay_ms"] = 0

    await clear_fn(tab)
    store.recording = False

    if not actions:
        return json.dumps({"status": "empty", "message": "No actions were recorded."}, ensure_ascii=False)

    rec_name = name or datetime.now().strftime("rec_%Y%m%d_%H%M%S")
    paths = _save_recording(rec_name, actions, store.cdp_port, store.recording_start_url)

    return json.dumps({
        "status": "saved",
        "name": rec_name,
        "action_count": len(actions),
        "files": paths,
        "message": f"Recorded {len(actions)} actions. Python script generated: {paths['py']}",
    }, ensure_ascii=False)


async def _do_replay(session, name, actions_json, speed) -> str:
    if actions_json:
        actions = json.loads(actions_json)
    elif name:
        meta = _load_recording(name)
        actions = meta.get("actions", [])
    else:
        raise RuntimeError("Replay requires name or actions_json.")

    if not actions:
        return json.dumps({"status": "empty", "message": "Action list is empty."}, ensure_ascii=False)

    from ..iframe import find_element  # pylint: disable=import-outside-toplevel
    from ..stealth.human_behavior import (  # pylint: disable=import-outside-toplevel
        human_click as _hclick,
        human_fill as _hfill,
    )

    tab = session.get_active_tab()
    store = session.get_active_session()
    is_ziniao = store.backend_type == "ziniao"
    cfg = None
    sc = session.stealth_config
    if sc.enabled and sc.human_behavior:
        cfg = sc.to_behavior_config()
    speed = max(0.1, speed)
    replayed = 0

    for act in actions:
        delay_ms = act.get("delay_ms", 0)
        if delay_ms > 100:
            await asyncio.sleep(delay_ms / 1000 / speed)

        act_type = act.get("type", "")
        try:
            if act_type == "click":
                elem = await find_element(tab, act["selector"], store, timeout=10)
                if elem:
                    if cfg or is_ziniao:
                        await _hclick(tab, act["selector"], cfg=cfg, element=elem)
                    else:
                        await elem.click()

            elif act_type == "fill":
                elem = await find_element(tab, act["selector"], store, timeout=10)
                if elem:
                    if cfg or is_ziniao:
                        await _hfill(tab, act["selector"], act.get("value", ""), cfg=cfg, element=elem)
                    else:
                        await elem.clear_input()
                        await elem.send_keys(act.get("value", ""))

            elif act_type == "select":
                sel = act["selector"]
                val = act.get("value", "")
                await tab.evaluate(
                    f"document.querySelector({json.dumps(sel)}).value = {json.dumps(val)};"
                    f"document.querySelector({json.dumps(sel)}).dispatchEvent(new Event('change'))",
                )

            elif act_type == "press_key":
                from nodriver import cdp  # pylint: disable=import-outside-toplevel
                from ._keys import parse_key as _parse  # pylint: disable=import-outside-toplevel
                key = act.get("key", "Enter")
                actual_key, vk, modifiers = _parse(key)
                await tab.send(cdp.input_.dispatch_key_event(
                    "rawKeyDown", windows_virtual_key_code=vk, modifiers=modifiers, key=actual_key,
                ))
                await tab.send(cdp.input_.dispatch_key_event(
                    "keyUp", windows_virtual_key_code=vk, modifiers=modifiers, key=actual_key,
                ))

            elif act_type == "navigate":
                from nodriver import cdp as _cdp  # pylint: disable=import-outside-toplevel
                url = act.get("url", "")
                if url:
                    await tab.send(_cdp.page.navigate(url=url))
                    await tab.sleep(1)

            replayed += 1
        except Exception as exc:  # pylint: disable=broad-exception-caught
            _logger.warning("Replay step %d (%s) failed: %s", replayed + 1, act_type, exc)

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
