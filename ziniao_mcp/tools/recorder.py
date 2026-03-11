"""浏览器操作录制与代码生成工具（类 Playwright Codegen）"""

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
# JS 录制器 —— 注入浏览器页面，捕获用户交互
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

# Python 侧提取/清理时使用的 JS 表达式（通过 Symbol.for 匹配注入侧的 key）
_COLLECT_JS = "JSON.stringify(window[Symbol.for('__ev_d')] || [])"
_CLEAR_JS = "window[Symbol.for('__ev_a')] = false; window[Symbol.for('__ev_d')] = [];"
_NAV_PUSH_JS = (
    "window[Symbol.for('__ev_d')].push("
    "{{type:'navigate',url:{url},timestamp:Date.now()}})"
)

# ---------------------------------------------------------------------------
# Python 代码生成器
# ---------------------------------------------------------------------------


def _generate_python_script(
    actions: list[dict[str, Any]],
    cdp_port: int,
    start_url: str,
    name: str = "",
) -> str:
    """将 JSON 动作序列转为可独立运行的 nodriver Python 脚本。"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = name or "recording"

    lines: list[str] = []
    lines.append(f'"""由 ziniao-mcp recorder 自动生成 — {now_str} 录制: {title}"""')
    lines.append("")
    lines.append("import argparse")
    lines.append("import asyncio")
    lines.append("")
    lines.append("import nodriver")
    lines.append("")
    lines.append("")
    lines.append("async def main(port: int) -> None:")
    lines.append('    browser = await nodriver.Browser.create(host="127.0.0.1", port=port)')
    lines.append("    tab = browser.tabs[0]")
    lines.append("")

    if start_url:
        lines.append("    # 导航到起始页")
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
            lines.append(f"    # {step}. 点击 {sel}")
            lines.append(f"    elem = await tab.select({sel!r}, timeout=10)")
            lines.append("    if elem:")
            lines.append("        await elem.click()")

        elif act_type == "fill":
            sel = act["selector"]
            val = act.get("value", "")
            lines.append(f"    # {step}. 填写 {sel}")
            lines.append(f"    elem = await tab.select({sel!r}, timeout=10)")
            lines.append("    if elem:")
            lines.append("        await elem.clear_input()")
            lines.append(f"        await elem.send_keys({val!r})")

        elif act_type == "select":
            sel = act["selector"]
            val = act.get("value", "")
            lines.append(f"    # {step}. 选择 {sel} = {val}")
            js_code = (
                f"document.querySelector({json.dumps(sel)}).value = {json.dumps(val)}; "
                f"document.querySelector({json.dumps(sel)}).dispatchEvent(new Event('change'))"
            )
            lines.append(f"    await tab.evaluate({js_code!r})")

        elif act_type == "press_key":
            key = act.get("key", "Enter")
            lines.append(f"    # {step}. 按键 {key}")
            _append_press_key_code(lines, key)

        elif act_type == "navigate":
            url = act.get("url", "")
            lines.append(f"    # {step}. 导航到 {url}")
            lines.append(f"    await tab.get({url!r})")
            lines.append("    await tab.sleep(1)")

        else:
            lines.append(f"    # {step}. 未知操作: {act_type}")

        lines.append("")

    lines.append("")
    lines.append('if __name__ == "__main__":')
    lines.append('    parser = argparse.ArgumentParser(description="ziniao-mcp 录制脚本回放")')
    lines.append(f'    parser.add_argument("--port", type=int, default={cdp_port}, help="CDP 端口")')
    lines.append("    args = parser.parse_args()")
    lines.append("    asyncio.run(main(args.port))")
    lines.append("")

    return "\n".join(lines)


def _append_press_key_code(lines: list[str], key: str) -> None:
    """生成 press_key 对应的 nodriver CDP 代码。"""
    key_map = {
        "Enter": 13, "Tab": 9, "Escape": 27, "Backspace": 8,
        "Delete": 46, "ArrowUp": 38, "ArrowDown": 40,
        "ArrowLeft": 37, "ArrowRight": 39,
    }

    modifiers = 0
    actual_key = key
    if "+" in key:
        parts = key.split("+")
        for mod in parts[:-1]:
            m = mod.strip().lower()
            if m in ("control", "ctrl"):
                modifiers |= 2
            elif m == "alt":
                modifiers |= 1
            elif m in ("meta", "command"):
                modifiers |= 4
            elif m == "shift":
                modifiers |= 8
        actual_key = parts[-1].strip()

    vk = key_map.get(actual_key, ord(actual_key.upper()) if len(actual_key) == 1 else 0)

    lines.append("    from nodriver import cdp")
    lines.append("    await tab.send(cdp.input_.dispatch_key_event(")
    lines.append(f"        \"rawKeyDown\", windows_virtual_key_code={vk}, modifiers={modifiers}, key={actual_key!r}")
    lines.append("    ))")
    lines.append("    await tab.send(cdp.input_.dispatch_key_event(")
    lines.append(f"        \"keyUp\", windows_virtual_key_code={vk}, modifiers={modifiers}, key={actual_key!r}")
    lines.append("    ))")


# ---------------------------------------------------------------------------
# 录制文件 I/O
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
    """保存 JSON 元数据 + 生成 Python 脚本，返回文件路径。"""
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
        raise RuntimeError(f"录制 '{name}' 不存在: {json_path}")
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
# MCP 工具注册
# ---------------------------------------------------------------------------


def register_tools(mcp: FastMCP, session: SessionManager) -> None:

    async def _inject_recorder(tab) -> None:
        """向 tab 注入录制 JS（幂等）。"""
        await tab.evaluate(_RECORDER_JS, await_promise=False)

    async def _collect_actions(tab) -> list[dict]:
        """从页面提取已录制的动作列表（通过 Symbol key 访问，不可枚举）。"""
        raw = await tab.evaluate(_COLLECT_JS, return_by_value=True)
        if isinstance(raw, str):
            return json.loads(raw)
        return []

    async def _clear_recorder(tab) -> None:
        """清除页面上的录制状态。"""
        await tab.evaluate(_CLEAR_JS, await_promise=False)

    def _setup_navigation_reinjection(store, tab) -> None:
        """绑定 CDP Page.frameNavigated 事件，导航后自动重注入 JS 并记录 navigate。"""
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
            _logger.debug("录制中检测到导航: %s", url)
            await asyncio.sleep(1)
            try:
                await _inject_recorder(tab)
                push_js = _NAV_PUSH_JS.format(url=json.dumps(url))
                await tab.evaluate(push_js, await_promise=False)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                _logger.warning("导航后重注入录制器失败: %s", exc)

        tab.add_handler(cdp.page.FrameNavigated, _on_frame_navigated)

    @mcp.tool()
    async def recorder(
        action: str = "start",
        name: str = "",
        actions_json: str = "",
        speed: float = 1.0,
    ) -> str:
        """浏览器操作录制与代码生成（类 Playwright Codegen）。

        录制用户在浏览器中的交互操作（点击、输入、按键、导航），
        停止后生成可独立运行的 Python 脚本（基于 nodriver），也可在 MCP 内回放。

        Args:
            action: 操作类型
                - "start": 开始录制（注入 JS 监听器）
                - "stop": 停止录制并生成脚本（name 可选，默认按时间戳命名）
                - "replay": 回放录制（通过 name 加载或传入 actions_json）
                - "list": 列出所有已保存的录制
                - "delete": 删除指定录制
            name: 录制名称（stop 时保存用，replay/delete 时指定目标）
            actions_json: 回放时可直接传入 JSON 动作列表（优先级高于 name）
            speed: 回放速度倍率，默认 1.0，2.0 表示双倍速
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
        raise RuntimeError(f"未知 action: {action}，可选值: start, stop, replay, list, delete")


async def _do_start(session, inject_fn, nav_setup_fn) -> str:
    store = session.get_active_session()
    if store.recording:
        return json.dumps({"status": "already_recording", "message": "已在录制中"}, ensure_ascii=False)

    tab = session.get_active_tab()
    start_url = getattr(getattr(tab, "target", None), "url", "") or ""
    store.recording = True
    store.recording_start_url = start_url

    await inject_fn(tab)
    nav_setup_fn(store, tab)

    return json.dumps({
        "status": "recording",
        "message": "录制已开始，请在浏览器中操作。完成后调用 recorder(action='stop') 停止。",
        "start_url": start_url,
    }, ensure_ascii=False)


async def _do_stop(session, name, collect_fn, clear_fn) -> str:
    store = session.get_active_session()
    if not store.recording:
        return json.dumps({"status": "error", "message": "当前未在录制"}, ensure_ascii=False)

    tab = session.get_active_tab()
    actions = await collect_fn(tab)

    # 计算相邻动作间 delay_ms
    for i in range(len(actions) - 1, 0, -1):
        actions[i]["delay_ms"] = max(0, actions[i].get("timestamp", 0) - actions[i - 1].get("timestamp", 0))
    if actions:
        actions[0]["delay_ms"] = 0

    await clear_fn(tab)
    store.recording = False

    if not actions:
        return json.dumps({"status": "empty", "message": "未录制到任何操作"}, ensure_ascii=False)

    rec_name = name or datetime.now().strftime("rec_%Y%m%d_%H%M%S")
    paths = _save_recording(rec_name, actions, store.cdp_port, store.recording_start_url)

    return json.dumps({
        "status": "saved",
        "name": rec_name,
        "action_count": len(actions),
        "files": paths,
        "message": f"已录制 {len(actions)} 个操作，Python 脚本已生成: {paths['py']}",
    }, ensure_ascii=False)


async def _do_replay(session, name, actions_json, speed) -> str:
    if actions_json:
        actions = json.loads(actions_json)
    elif name:
        meta = _load_recording(name)
        actions = meta.get("actions", [])
    else:
        raise RuntimeError("replay 需要提供 name 或 actions_json")

    if not actions:
        return json.dumps({"status": "empty", "message": "动作列表为空"}, ensure_ascii=False)

    from ..iframe import find_element  # pylint: disable=import-outside-toplevel

    tab = session.get_active_tab()
    store = session.get_active_session()
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
                    await elem.click()

            elif act_type == "fill":
                elem = await find_element(tab, act["selector"], store, timeout=10)
                if elem:
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
                key = act.get("key", "Enter")
                key_map = {
                    "Enter": 13, "Tab": 9, "Escape": 27, "Backspace": 8,
                    "Delete": 46, "ArrowUp": 38, "ArrowDown": 40,
                    "ArrowLeft": 37, "ArrowRight": 39,
                }
                modifiers = 0
                actual_key = key
                if "+" in key:
                    parts = key.split("+")
                    for mod in parts[:-1]:
                        m = mod.strip().lower()
                        if m in ("control", "ctrl"):
                            modifiers |= 2
                        elif m == "alt":
                            modifiers |= 1
                        elif m in ("meta", "command"):
                            modifiers |= 4
                        elif m == "shift":
                            modifiers |= 8
                    actual_key = parts[-1].strip()
                vk = key_map.get(actual_key, ord(actual_key.upper()) if len(actual_key) == 1 else 0)
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
            _logger.warning("回放步骤 %d (%s) 失败: %s", replayed + 1, act_type, exc)

    return json.dumps({
        "status": "done",
        "replayed": replayed,
        "total": len(actions),
        "message": f"已回放 {replayed}/{len(actions)} 个操作",
    }, ensure_ascii=False)


def _do_list() -> str:
    recordings = _list_recordings()
    return json.dumps({
        "recordings": recordings,
        "count": len(recordings),
    }, ensure_ascii=False, indent=2)


def _do_delete(name: str) -> str:
    if not name:
        raise RuntimeError("delete 需要提供 name 参数")
    _delete_recording(name)
    return json.dumps({
        "status": "deleted",
        "name": name,
    }, ensure_ascii=False)
