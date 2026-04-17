"""Declarative response-transformation contract.

Sister of :mod:`save_media` for *non-media* post-processing: a preset JSON
may declare a ``response_contract`` block telling the framework how to
parse the raw response body and lift interesting fields up to the response
dict — without any site-specific Python code.

Schema (preset-side)::

    "response_contract": {
      "parse": "json",                      # only "json" is supported today
      "lift": [
        {
          "from":    "data",                # dotted path in the parsed tree
          "to":      "parsed",              # top-level key on the response
          "when_eq": { "status": "SUCCESS" } # optional, all keys must match
        }
      ]
    }

Runtime semantics are intentionally forgiving — any failure on a single
rule is swallowed so that a partial / malformed response does not crash
the CLI:

- body missing / ``parse`` not recognised / JSON decode error  → contract is a no-op
- a ``lift`` entry's ``from`` path is missing                   → that entry is skipped
- ``when_eq`` has a key that's missing or does not match        → that entry is skipped
- any unknown / unexpected top-level key                        → ignored

For conditional logic beyond literal equality (regex, numeric comparison,
boolean OR, etc.), override :meth:`SitePlugin.after_fetch` in Python —
this keeps the declarative surface small and predictable.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .save_media import _walk_dotted

log = logging.getLogger(__name__)


_SUPPORTED_PARSERS = frozenset({"json"})


def apply_response_contract(response: dict, contract: Any) -> dict:
    """Apply a declarative ``response_contract`` to *response* in place.

    Returns *response* (mutated) for call-chain convenience.  Safe to call
    with ``contract=None`` / ``contract={}`` / an invalid contract — in
    all error paths *response* is returned untouched.
    """
    if not isinstance(contract, dict) or not contract:
        return response
    if not isinstance(response, dict):
        return response

    parser = str(contract.get("parse") or "").strip().lower()
    if parser not in _SUPPORTED_PARSERS:
        return response

    body = response.get("body")
    if not isinstance(body, str) or not body:
        return response

    try:
        parsed_tree = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return response

    rules = contract.get("lift")
    if not isinstance(rules, list):
        return response

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        try:
            _apply_lift_rule(response, parsed_tree, rule)
        except Exception:  # noqa: BLE001 — declarative rules never crash the caller
            log.debug("response_contract lift rule failed: %r", rule, exc_info=True)
            continue
    return response


def _apply_lift_rule(response: dict, parsed_tree: Any, rule: dict) -> None:
    when = rule.get("when_eq")
    if when is not None and not _when_eq_matches(parsed_tree, when):
        return

    src = rule.get("from")
    if not isinstance(src, str) or not src:
        return
    value, path = _walk_dotted(parsed_tree, src)
    if not path:
        return

    dest = rule.get("to")
    if not isinstance(dest, str) or not dest or "." in dest:
        return
    response[dest] = value


def _when_eq_matches(parsed_tree: Any, when: Any) -> bool:
    if not isinstance(when, dict):
        return False
    for path, expected in when.items():
        if not isinstance(path, str) or not path:
            return False
        value, keys = _walk_dotted(parsed_tree, path)
        if not keys:
            return False
        if value != expected:
            return False
    return True


__all__ = ["apply_response_contract"]
