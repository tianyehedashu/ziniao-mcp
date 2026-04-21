"""Canonical CDP ``Runtime.evaluate`` helpers shared by core / CLI / tools.

Why this module exists
----------------------
``nodriver.Tab.evaluate`` builds a ``SerializationOptions(serialization="deep")``
while also passing ``return_by_value=True`` to Chrome.  Depending on the result
shape Chrome may populate ``remote_object.deep_serialized_value`` but leave
``remote_object.value`` as ``None``; nodriver's final branch uses
``if remote_object.value:`` (a truthy check) and falls through to
``return remote_object``.  Callers then receive the raw ``RemoteObject`` —
which fails JSON serialisation and surfaces as ``repr(RemoteObject(...))`` in
CLI output.  This bites every *falsy* JSON scalar: ``""``, ``0``, ``False``,
``[]``, ``{}``.

Worse, bool-returning probes (``is_visible`` / ``is_enabled`` / ``is_checked``)
silently flip their answer because ``bool(RemoteObject(...))`` is ``True`` —
so a real ``False`` round-trips as ``True``.

:func:`safe_eval_js` bypasses ``Tab.evaluate`` and calls ``cdp.runtime.evaluate``
directly with no ``serialization_options`` (Chrome defaults to standard JSON),
and explicitly checks ``value is not None`` so falsy JSON values round-trip
correctly.  Unserializable primitives (``NaN`` / ``Infinity``) are returned as
their string form.  JS exceptions are raised as :class:`RuntimeError` so
callers can funnel them into ``on_error`` artefacts.
"""

from __future__ import annotations

from typing import Any


def format_cdp_exception(exc: Any) -> str:
    """Render a ``cdp.runtime.ExceptionDetails`` into a human-readable string.

    Only reads string-typed fields (``text``, ``exception.description``); the
    ``exception`` field itself is a ``RemoteObject`` so it must never be used
    as the message directly or callers will see ``repr(RemoteObject(...))``.
    """
    text = getattr(exc, "text", "") or ""
    exc_obj = getattr(exc, "exception", None)
    desc = getattr(exc_obj, "description", None) if exc_obj is not None else None
    parts = [p for p in (text, desc) if p]
    return ": ".join(parts) or "unknown error"


async def safe_eval_js(
    tab: Any,
    script: str,
    *,
    await_promise: bool = False,
) -> Any:
    """Evaluate JS in ``tab`` and return a JSON-serialisable Python value.

    See module docstring for the underlying nodriver bug this works around.

    Raises :class:`RuntimeError` when the script throws, so step executors can
    surface the message into ``on_error`` artefacts.
    """
    from nodriver import cdp  # pylint: disable=import-outside-toplevel

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
        raise RuntimeError(f"eval failed: {format_cdp_exception(errors)}")

    if remote_object is None:
        return None
    if remote_object.value is not None:
        return remote_object.value
    if getattr(remote_object, "unserializable_value", None) is not None:
        return str(remote_object.unserializable_value)
    return None
