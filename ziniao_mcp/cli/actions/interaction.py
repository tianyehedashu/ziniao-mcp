"""Interaction action handlers: click, fill, type_text, insert_text, press_key, hover, drag, dblclick, focus, select_option, check, uncheck."""

from __future__ import annotations

from typing import Any

from .js import run_js_in_context
from .upload import clear_overlay


async def click(sm: Any, args: dict) -> dict:
    from ...iframe import find_element  # pylint: disable=import-outside-toplevel
    from ..._interaction_helpers import dispatch_click  # pylint: disable=import-outside-toplevel

    selector = args.get("selector", "")
    if not selector:
        return {"error": "selector is required"}
    tab = sm.get_active_tab()
    store = sm.get_active_session()

    # Auto-clear overlays before clicking (unless disabled)
    if not args.get("no_auto_clear"):
        try:
            await clear_overlay(sm, {})
        except Exception:
            pass

    elem = await find_element(tab, selector, store, timeout=10)
    if not elem:
        return {"error": f"Element not found: {selector}"}
    await dispatch_click(tab, selector, elem, sm)
    return {"ok": True, "clicked": selector}


async def fill(sm: Any, args: dict) -> dict:
    import json  # pylint: disable=import-outside-toplevel
    from ...iframe import find_element  # pylint: disable=import-outside-toplevel
    from ..._interaction_helpers import dispatch_fill  # pylint: disable=import-outside-toplevel

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


async def type_text(sm: Any, args: dict) -> dict:
    from ...iframe import find_element  # pylint: disable=import-outside-toplevel
    from ..._interaction_helpers import dispatch_type  # pylint: disable=import-outside-toplevel

    text = args.get("text", "")
    selector = args.get("selector", "")
    tab = sm.get_active_tab()
    store = sm.get_active_session()
    elem = None
    if selector:
        elem = await find_element(tab, selector, store, timeout=10)
    await dispatch_type(tab, text, selector, elem, sm)
    return {"ok": True, "typed": text}


async def insert_text(sm: Any, args: dict) -> dict:
    """CDP Input.insertText — works with Slate/ProseMirror rich editors.

    When *selector* is provided it is treated as a **hard prerequisite**
    (focus target): if the element cannot be located we return an error
    rather than silently typing into whatever happens to hold focus —
    this matches ``click`` / ``fill`` / ``hover`` semantics and avoids
    leaking passwords / tokens into the wrong field.  Callers that do
    want to type into the currently-focused element should omit
    ``selector`` entirely.

    Stealth behaviour: when ``sm.stealth_config.human_behavior`` is on we
    route the focus click through :func:`dispatch_click` (bezier mouse
    movement) **and** split the text into several chunks with randomised
    inter-chunk delays so the payload doesn't land in the DOM
    instantaneously — otherwise ``insertText`` is trivially fingerprintable
    by behaviour-analytics detectors.  Chunking (rather than per-char
    ``dispatch_key_event("char")``) is required for Slate.js / ProseMirror
    editors which only observe ``beforeinput`` events.
    """
    import asyncio  # pylint: disable=import-outside-toplevel
    import random  # pylint: disable=import-outside-toplevel

    from nodriver import cdp  # pylint: disable=import-outside-toplevel

    from ..._interaction_helpers import _get_behavior_cfg, dispatch_click  # pylint: disable=import-outside-toplevel

    text = args.get("text", "")
    if not text:
        return {"error": "text is required"}
    selector = args.get("selector", "")
    tab = sm.get_active_tab()
    if selector:
        from ...iframe import find_element  # pylint: disable=import-outside-toplevel

        store = sm.get_active_session()
        elem = await find_element(tab, selector, store, timeout=10)
        if not elem:
            return {"error": f"Element not found: {selector}"}
        await dispatch_click(tab, selector, elem, sm)

    cfg = _get_behavior_cfg(sm)
    if cfg:
        from ...stealth import random_delay  # pylint: disable=import-outside-toplevel

        await random_delay(cfg=cfg)
        n = len(text)
        num_chunks = random.randint(3, 6) if n >= 4 else n
        chunk_size = max(1, -(-n // num_chunks))
        for i in range(0, n, chunk_size):
            await tab.send(cdp.input_.insert_text(text=text[i : i + chunk_size]))
            if i + chunk_size < n:
                await asyncio.sleep(random.uniform(0.05, 0.18))
    else:
        await tab.send(cdp.input_.insert_text(text=text))
    return {"ok": True, "inserted": text}


async def press_key(sm: Any, args: dict) -> dict:
    """Press a single key via CDP ``Input.dispatchKeyEvent``.

    With stealth enabled we add a pre-press *think* delay plus a realistic
    ~60ms hold time between ``rawKeyDown`` and ``keyUp``; without stealth
    we keep the original tight path to preserve test timing.
    """
    import asyncio  # pylint: disable=import-outside-toplevel
    import random  # pylint: disable=import-outside-toplevel

    from nodriver import cdp  # pylint: disable=import-outside-toplevel

    from ..._interaction_helpers import _get_behavior_cfg  # pylint: disable=import-outside-toplevel
    from ...tools._keys import parse_key  # pylint: disable=import-outside-toplevel

    key = args.get("key", "")
    if not key:
        return {"error": "key is required"}
    tab = sm.get_active_tab()
    actual_key, vk, modifiers = parse_key(key)

    cfg = _get_behavior_cfg(sm)
    if cfg:
        from ...stealth import random_delay  # pylint: disable=import-outside-toplevel

        await random_delay(cfg=cfg)
    await tab.send(
        cdp.input_.dispatch_key_event(
            "rawKeyDown",
            windows_virtual_key_code=vk,
            modifiers=modifiers,
            key=actual_key,
        )
    )
    if cfg:
        await asyncio.sleep(random.uniform(0.04, 0.12))
    await tab.send(
        cdp.input_.dispatch_key_event(
            "keyUp",
            windows_virtual_key_code=vk,
            modifiers=modifiers,
            key=actual_key,
        )
    )
    return {"ok": True, "pressed": key}


async def hover(sm: Any, args: dict) -> dict:
    from ...iframe import find_element  # pylint: disable=import-outside-toplevel
    from ..._interaction_helpers import dispatch_hover  # pylint: disable=import-outside-toplevel

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


async def drag(sm: Any, args: dict) -> dict:
    from ...iframe import find_element  # pylint: disable=import-outside-toplevel

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


async def dblclick(sm: Any, args: dict) -> dict:
    """Double-click via CDP mouse events.

    With stealth enabled we route the pointer via a bezier trajectory
    (:func:`_move_mouse_humanlike`) and add realistic down/up hold times
    plus an inter-click gap — flat "two simultaneous pressed events at
    the same (x, y)" is a strong automation signal otherwise.
    """
    import asyncio  # pylint: disable=import-outside-toplevel
    import random  # pylint: disable=import-outside-toplevel

    from nodriver import cdp  # pylint: disable=import-outside-toplevel

    from ..._interaction_helpers import _get_behavior_cfg  # pylint: disable=import-outside-toplevel
    from ...iframe import find_element  # pylint: disable=import-outside-toplevel

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
    cx, cy = pos.center

    cfg = _get_behavior_cfg(sm)
    button = cdp.input_.MouseButton("left")
    if cfg:
        from ...stealth import random_delay  # pylint: disable=import-outside-toplevel
        from ...stealth.human_behavior import _move_mouse_humanlike  # pylint: disable=import-outside-toplevel

        await _move_mouse_humanlike(tab, cx, cy, cfg=cfg)
        await random_delay(cfg=cfg)
        await tab.send(
            cdp.input_.dispatch_mouse_event(
                type_="mousePressed",
                x=cx,
                y=cy,
                button=button,
                click_count=1,
            )
        )
        await asyncio.sleep(random.uniform(0.03, 0.08))
        await tab.send(
            cdp.input_.dispatch_mouse_event(
                type_="mouseReleased",
                x=cx,
                y=cy,
                button=button,
                click_count=1,
            )
        )
        await asyncio.sleep(random.uniform(0.05, 0.12))
        await tab.send(
            cdp.input_.dispatch_mouse_event(
                type_="mousePressed",
                x=cx,
                y=cy,
                button=button,
                click_count=2,
            )
        )
        await asyncio.sleep(random.uniform(0.03, 0.08))
        await tab.send(
            cdp.input_.dispatch_mouse_event(
                type_="mouseReleased",
                x=cx,
                y=cy,
                button=button,
                click_count=2,
            )
        )
    else:
        await tab.send(
            cdp.input_.dispatch_mouse_event(
                type_="mouseMoved",
                x=cx,
                y=cy,
            )
        )
        await tab.send(
            cdp.input_.dispatch_mouse_event(
                type_="mousePressed",
                x=cx,
                y=cy,
                button=button,
                click_count=2,
            )
        )
        await tab.send(
            cdp.input_.dispatch_mouse_event(
                type_="mouseReleased",
                x=cx,
                y=cy,
                button=button,
                click_count=2,
            )
        )
    return {"ok": True, "double_clicked": selector}


async def focus(sm: Any, args: dict) -> dict:
    import json  # pylint: disable=import-outside-toplevel
    from ...iframe import find_element  # pylint: disable=import-outside-toplevel

    selector = args.get("selector", "")
    if not selector:
        return {"error": "selector is required"}
    tab = sm.get_active_tab()
    store = sm.get_active_session()
    elem = await find_element(tab, selector, store, timeout=10)
    if not elem:
        return {"error": f"Element not found: {selector}"}
    await tab.evaluate(
        f"document.querySelector({json.dumps(selector)})?.focus()", return_by_value=True
    )
    return {"ok": True, "focused": selector}


async def select_option(sm: Any, args: dict) -> dict:
    import json  # pylint: disable=import-outside-toplevel

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


async def check(sm: Any, args: dict) -> dict:
    import json  # pylint: disable=import-outside-toplevel

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


async def uncheck(sm: Any, args: dict) -> dict:
    import json  # pylint: disable=import-outside-toplevel

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
