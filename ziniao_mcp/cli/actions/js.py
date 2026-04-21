"""JS evaluation helpers for the CLI/daemon layer.

The low-level ``safe_eval_js`` is owned by :mod:`ziniao_mcp.core._eval` (so
that the ``core/`` layer itself — which must not reverse-depend on ``cli/`` —
can use it).  We re-export it here to keep existing import sites stable, and
add :func:`run_js_in_context` which fans out to the iframe realm when the
session has an iframe context bound.
"""

from __future__ import annotations

from typing import Any

from ...core._eval import safe_eval_js

__all__ = ["safe_eval_js", "run_js_in_context"]


async def run_js_in_context(
    tab: Any,
    store: Any,
    script: str,
    *,
    await_promise: bool = False,
) -> Any:
    """Route JS evaluation to the main document or the bound iframe context.

    Both paths propagate exceptions as :class:`RuntimeError` so callers can
    produce a single ``{"error": ...}`` branch regardless of which realm the
    script ran in.  Centralising the branch also guarantees the falsy-value
    unwrapping rules stay in lockstep between main / iframe paths.
    """
    if store.iframe_context:
        from ...iframe import eval_in_frame  # pylint: disable=import-outside-toplevel

        return await eval_in_frame(
            tab,
            store.iframe_context.context_id,
            script,
            await_promise=await_promise,
            strict=True,
        )
    return await safe_eval_js(tab, script, await_promise=await_promise)
