"""Eval and console action handlers."""

from __future__ import annotations

from typing import Any

from .js import run_js_in_context


async def eval_js(sm: Any, args: dict) -> dict:
    script = args.get("script", "")
    if not script:
        return {"error": "script is required"}
    await_promise = args.get("await_promise", False)
    tab = sm.get_active_tab()
    store = sm.get_active_session()
    try:
        result = await run_js_in_context(
            tab,
            store,
            script,
            await_promise=await_promise,
        )
    except RuntimeError as exc:
        return {"error": str(exc)}
    return {"ok": True, "result": result}


async def console(sm: Any, args: dict) -> dict:
    store = sm.get_active_session()
    message_id = args.get("message_id", 0)
    level = args.get("level", "")
    limit = args.get("limit", 50)

    if message_id:
        for m in store.console_messages:
            if m.id == message_id:
                return {
                    "id": m.id,
                    "level": m.level,
                    "text": m.text,
                    "timestamp": m.timestamp,
                }
        return {"error": f"Message ID not found: {message_id}"}

    messages = store.console_messages
    if level:
        messages = [m for m in messages if m.level == level]
    return {
        "messages": [
            {"id": m.id, "level": m.level, "text": m.text[:500]}
            for m in list(messages)[-limit:]
        ]
    }
