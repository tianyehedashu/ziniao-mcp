"""Upload action handlers: upload, upload_hijack, upload_react, clear_overlay."""

from __future__ import annotations

import json
import logging
from typing import Any

from .js import run_js_in_context, safe_eval_js

_logger = logging.getLogger("ziniao-daemon")


async def upload(sm: Any, args: dict) -> dict:
    from ...iframe import find_element  # pylint: disable=import-outside-toplevel

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


async def clear_overlay(sm: Any, args: dict) -> dict:
    """Remove transparent overlay divs that block user interaction.

    Common anti-automation pattern: position:fixed div with high z-index
    covering the viewport, with no visible content (empty or transparent).
    Works across React, Vue, Angular — purely DOM-based, framework agnostic.
    """
    js = """(() => {
        let removed = 0;
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        document.querySelectorAll('div').forEach(el => {
            try {
                const s = getComputedStyle(el);
                if (s.position !== 'fixed') return;
                const zI = parseInt(s.zIndex) || 0;
                if (zI < 1000) return;
                const w = el.offsetWidth;
                const h = el.offsetHeight;
                if (w < vw * 0.5 || h < vh * 0.5) return;
                const textLen = (el.innerText || '').trim().length;
                if (textLen > 20) return;
                if (el.children.length > 3) return;
                el.remove();
                removed++;
            } catch(e) {}
        });
        return removed;
    })()"""
    tab = sm.get_active_tab()
    store = sm.get_active_session()
    try:
        result = await run_js_in_context(tab, store, js, await_promise=False)
        return {"ok": True, "removed": result or 0}
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc)}


async def upload_hijack(sm: Any, args: dict) -> dict:
    """Upload files by hijacking Document.prototype.createElement.

    Works for sites that create ``<input type="file">`` programmatically
    and never append it to the DOM (e.g. Douyin, many React SPA uploaders).

    Chrome 147+ removed ``Page.handleFileChooser``, and CDP's
    ``DOM.setFileInputFiles`` requires the input to be in the DOM.
    This command bypasses both limitations by injecting a JS hook that
    intercepts ``createElement('input')``, hooks ``addEventListener('change')``
    and ``click()``, then dispatches the file via ``DataTransfer`` and calls
    the captured change handler directly.

    Files are read on the daemon side (not sent over TCP), so there is
    no size limit beyond Chrome's WebSocket frame budget.

    Args (from CLI):
        file_paths: list[str] — local file paths to upload
        trigger: str (optional) — CSS selector to click to trigger upload;
                if omitted, the caller clicks manually after hook install.
        object_id: str (optional) — CDP RemoteObject id of an existing <input type=file>;
                if provided, skips hook injection and trigger click, directly sets files
                via CDP DOM.setFileInputFiles. Useful when input is captured via
                createElement hook separately.
        wait_ms: int (optional, default 30000) — max wait for hook to fire.
    """
    import asyncio
    import base64 as _b64
    from pathlib import Path as _Path

    # Fast path: direct CDP setFileInputFiles via objectId (no hook needed)
    object_id: str = args.get("object_id", "")
    if object_id:
        file_paths = args.get("file_paths", [])
        if not file_paths:
            return {"error": "file_paths is required with object_id"}
        tab = sm.get_active_tab()
        try:
            from nodriver import cdp  # pylint: disable=import-outside-toplevel
            await tab.send(cdp.dom.set_file_input_files(file_paths, object_id=object_id))
        except Exception as exc:
            return {"ok": False, "error": f"DOM.setFileInputFiles failed: {exc}"}
        return {"ok": True, "method": "direct_cdp", "files": len(file_paths)}

    file_paths: list[str] = args.get("file_paths", [])
    trigger: str = args.get("trigger", "")
    wait_ms: int = int(args.get("wait_ms", 30000))

    if not file_paths:
        return {"error": "file_paths is required"}

    # Read files as base64 on the daemon side (avoids TCP size limits)
    file_entries: list[dict] = []
    for fp in file_paths:
        p = _Path(fp)
        if not p.is_file():
            return {"error": f"File not found: {fp}"}
        raw = p.read_bytes()
        if len(raw) > 50 * 1024 * 1024:
            return {"error": f"File too large ({len(raw)} bytes, limit 50MB): {fp}"}
        b64 = _b64.b64encode(raw).decode("ascii")
        ext = p.suffix.lower()
        mime = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp",
            ".pdf": "application/pdf", ".mp4": "video/mp4",
        }.get(ext, "application/octet-stream")
        file_entries.append({"b64": b64, "name": p.name, "mime": mime})

    tab = sm.get_active_tab()
    store = sm.get_active_session()

    # Build and inject the createElement hook
    files_js = json.dumps(file_entries, ensure_ascii=False)
    hook_script = """(() => {
        const files = __FILES__;
        window.__ziniao_upload_hijack = { fired: 0, done: false, error: null };
        const origCE = Document.prototype.createElement;
        Document.prototype.createElement = function(tag) {
            const el = origCE.call(this, tag);
            if (String(tag).toLowerCase() === 'input') {
                const origAEL = el.addEventListener.bind(el);
                el.addEventListener = function(type, fn, opts) {
                    if (type === 'change') {
                        const handler = fn;
                        const origClick = el.click.bind(el);
                        el.click = function() {
                            const dt = new DataTransfer();
                            for (const f of files) {
                                const bin = atob(f.b64);
                                const u = new Uint8Array(bin.length);
                                for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
                                dt.items.add(new File([new Blob([u], {type: f.mime})], f.name, {type: f.mime}));
                            }
                            this.files = dt.files;
                            window.__ziniao_upload_hijack.fired++;
                            const inp = this;
                            requestAnimationFrame(() => {
                                try {
                                    handler({target: inp, currentTarget: inp});
                                    window.__ziniao_upload_hijack.done = true;
                                } catch(e) {
                                    window.__ziniao_upload_hijack.error = e.message;
                                }
                            });
                        };
                    }
                    return origAEL(type, fn, opts);
                };
            }
            return el;
        };
        return 'hook_installed';
    })()""".replace("__FILES__", files_js)

    try:
        result = await run_js_in_context(tab, store, hook_script, await_promise=False)
    except RuntimeError as exc:
        return {"error": f"hook install failed: {exc}"}

    if result != "hook_installed":
        return {"error": f"hook install returned unexpected: {result}"}

    # If no trigger, return immediately — caller will click manually
    if not trigger:
        return {"ok": True, "hook": "installed", "files": len(file_entries)}

    # Auto-clear overlays before clicking trigger (common anti-automation pattern)
    if not args.get("no_auto_clear"):
        try:
            await clear_overlay(sm, {})
        except Exception:
            pass  # best-effort, don't block upload

    # Click the trigger element via click dispatch (reuses all existing logic)
    from .interaction import click as _click
    click_result = await _click(sm, {"selector": trigger})
    if click_result.get("error"):
        return click_result

    # Poll for hook to fire — but give fast feedback if nothing happens
    poll_js = "window.__ziniao_upload_hijack"
    loop = asyncio.get_event_loop()
    deadline = loop.time() + wait_ms / 1000
    early_deadline = loop.time() + 3.0  # check after 3s
    while loop.time() < deadline:
        await asyncio.sleep(0.5)
        try:
            status = await run_js_in_context(tab, store, poll_js, await_promise=False)
        except RuntimeError:
            continue
        if not status:
            continue
        if status.get("done"):
            return {"ok": True, "hijacked": status["fired"], "files": len(file_entries)}
        if status.get("error"):
            return {"ok": False, "hijacked": status["fired"], "error": status["error"]}
        # Early fallback if hook still not fired after 3s:
        # Use createElement hook + React onClick + CDP setFileInputFiles
        if not status.get("fired") and loop.time() >= early_deadline and early_deadline > 0:
            early_deadline = 0  # only attempt once
            if not args.get("no_auto_clear"):
                try:
                    await clear_overlay(sm, {})
                except Exception:
                    pass
            try:
                # Inject createElement hook + click React onClick
                inject_js = "(() => { window.__dp_inputs = []; const origCE = Document.prototype.createElement; Document.prototype.createElement = function(tag) { const el = origCE.call(this, tag); if (String(tag).toLowerCase() === 'input') window.__dp_inputs.push(el); return el; }; const a = document.querySelector(" + json.dumps(trigger) + "); if (!a) return 'not_found'; a.scrollIntoView({block:'center'}); const pk = Object.keys(a).find(k => k.startsWith('__reactProps')); if (pk && a[pk]?.onClick) { a[pk].onClick(); return 'created:' + window.__dp_inputs.length; } return 'no_react'; })()"
                inject_result = await run_js_in_context(tab, store, inject_js, await_promise=False)
                _logger.info("[upload-hijack] react fallback inject: %s", inject_result)
                if isinstance(inject_result, str) and "created:1" in inject_result:
                    # Got the input — use CDP to set files
                    await asyncio.sleep(0.5)
                    from nodriver import cdp as _cdp  # pylint: disable=import-outside-toplevel
                    obj_resp = await tab.send(_cdp.runtime.evaluate(
                        expression="window.__dp_inputs[0]",
                        return_by_value=False,
                    ))
                    if (obj_resp and hasattr(obj_resp, "result")
                            and obj_resp.result and obj_resp.result.object_id):
                        await tab.send(_cdp.dom.set_file_input_files(
                            [fp for fp in file_paths],
                            object_id=obj_resp.result.object_id,
                        ))
                        _logger.info("[upload-hijack] CDP setFileInputFiles OK")
                        return {"ok": True, "method": "react_fallback_cdp", "files": len(file_entries)}
            except Exception as exc:
                _logger.warning("[upload-hijack] react fallback failed: %s", exc)

    return {
        "ok": False,
        "hijacked": 0,
        "error": f"timeout after {wait_ms}ms — hook never fired (trigger click may be blocked by overlay; try clear-overlay first)",
    }


async def upload_react(sm: Any, args: dict) -> dict:
    """Upload files via CDP file chooser interception + real mouse click.

    1. Enable Page.setInterceptFileChooserDialog
    2. Register FileChooserOpened handler
    3. Get trigger element coordinates via JS
    4. Simulate real mouse click via CDP Input.dispatchMouseEvent
    5. React onClick fires, creates input, calls input.click()
    6. Chrome emits FileChooserOpened (intercepted)
    7. Respond with file paths via Page.handleFileChooser
    """
    import asyncio
    from pathlib import Path as _Path
    from nodriver import cdp as _cdp

    file_paths: list[str] = args.get("file_paths", [])
    trigger: str = args.get("trigger", "")

    if not file_paths:
        return {"error": "file_paths is required"}
    if not trigger:
        return {"error": "trigger is required"}

    for fp in file_paths:
        if not _Path(fp).is_file():
            return {"error": f"File not found: {fp}"}

    tab = sm.get_active_tab()
    store = sm.get_active_session()

    # Step 1: Enable file chooser interception
    await tab.send(_cdp.page.set_intercept_file_chooser_dialog(enabled=True))
    _logger.info("[upload-react] file chooser interception enabled")

    # Step 2: Register FileChooserOpened handler
    fc_future: asyncio.Future = asyncio.get_event_loop().create_future()

    def _on_fc(event: _cdp.page.FileChooserOpened):
        if not fc_future.done():
            fc_future.set_result(event)

    tab.add_handler(_cdp.page.FileChooserOpened, _on_fc)

    try:
        # Step 3: Get trigger element and click via nodriver (real user gesture)
        scroll_script = (
            '(function() {'
            + '  var a = document.querySelector(' + json.dumps(trigger) + ');'
            + '  if (!a) return "not_found";'
            + '  a.scrollIntoView({ block: "center" });'
            + '})();'
        )
        scroll_result = await run_js_in_context(tab, store, scroll_script, await_promise=False)
        if scroll_result == "not_found":
            # Page might be in stale state; try reloading
            _logger.warning("[upload-react] trigger not found, reloading page")
            current_url = await run_js_in_context(tab, store, "location.href")
            await tab.send(_cdp.page.navigate(url=current_url if current_url else ""))
            await asyncio.sleep(5)
            # Retry scroll
            scroll_result = await run_js_in_context(tab, store, scroll_script, await_promise=False)
            if scroll_result == "not_found":
                return {"ok": False, "error": f"trigger element not found after reload: {trigger}"}
        await asyncio.sleep(0.3)

        # Get element via nodriver's select
        elem = await tab.select(trigger, timeout=5)
        if not elem:
            return {"ok": False, "error": f"element not found: {trigger}"}

        _logger.info("[upload-react] clicking element: %s", trigger)

        # Step 4: Click the element (triggers React onClick -> input.click() -> file chooser)
        await elem.click()
        _logger.info("[upload-react] elem.click() done")

        # Step 5: Wait for FileChooserOpened
        try:
            event = await asyncio.wait_for(fc_future, timeout=15.0)
        except asyncio.TimeoutError:
            return {"ok": False, "error": "fileChooser timeout"}

        # Step 6: Set files on the input via DOM.setFileInputFiles using backend_node_id
        await tab.send(_cdp.dom.set_file_input_files(
            backend_node_id=event.backend_node_id,
            files=file_paths,
        ))
        _logger.info("[upload-react] set_file_input_files OK, backend_node_id=%s, %d files",
                     event.backend_node_id, len(file_paths))
        _logger.info("[upload-react] handleFileChooser OK, %d files", len(file_paths))

        # Wait for React to process the upload
        await asyncio.sleep(2.0)

        return {"ok": True, "method": "cdp_file_chooser", "files": len(file_paths)}

    finally:
        tab.remove_handler(_cdp.page.FileChooserOpened, _on_fc)
        try:
            await tab.send(_cdp.page.set_intercept_file_chooser_dialog(enabled=False))
        except Exception:
            pass
