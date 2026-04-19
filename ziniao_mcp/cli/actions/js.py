"""Shared JS evaluation helpers used across multiple action modules."""

from __future__ import annotations

from typing import Any


async def safe_eval_js(tab: Any, script: str, *, await_promise: bool = False) -> Any:
    """Evaluate JS in ``tab`` and return a JSON-serializable Python value.

    Worked around issue: ``nodriver.Tab.evaluate`` builds a ``SerializationOptions``
    with ``serialization="deep"`` while also passing ``returnByValue=True`` to
    Chrome. Depending on the result shape, Chrome may populate
    ``remote_object.deep_serialized_value`` but leave ``remote_object.value`` as
    ``None``; nodriver's final branch uses ``if remote_object.value:`` (a truthy
    check) and falls through to ``return remote_object``. Callers then receive
    the raw ``RemoteObject`` which cannot be JSON-serialized, producing
    ``repr(RemoteObject(...))`` in CLI output.

    This helper bypasses ``Tab.evaluate`` and calls ``cdp.runtime.evaluate``
    directly with no ``serialization_options`` (Chrome defaults to standard
    JSON), and explicitly checks ``value is not None`` so falsy JSON values
    (``0``, ``""``, ``False``, ``[]``) round-trip correctly. Unserializable
    primitives (``NaN``, ``Infinity``) are returned as their string form.

    Raises :class:`RuntimeError` when the script throws, so step executors can
    surface the message into ``on_error`` artefacts.
    """
    from nodriver import cdp  # pylint: disable=import-outside-toplevel
    from ...iframe import _format_cdp_exception  # pylint: disable=import-outside-toplevel

    remote_object, errors = await tab.send(
        cdp.runtime.evaluate(
            expression=script,
            user_gesture=True,
            await_promise=await_promise,
            return_by_value=True,
            allow_unsafe_eval_blocked_by_csp=True,
        )
    )
    if errors:
        raise RuntimeError(f"eval failed: {_format_cdp_exception(errors)}")

    if remote_object is None:
        return None
    if remote_object.value is not None:
        return remote_object.value
    if getattr(remote_object, "unserializable_value", None) is not None:
        return str(remote_object.unserializable_value)
    return None


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
