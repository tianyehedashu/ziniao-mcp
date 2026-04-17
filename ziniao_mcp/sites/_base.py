"""Base class for site plugins.

Subclass ``SitePlugin`` in ``ziniao_mcp/sites/<site>/__init__.py`` (or a
third-party ``ziniao-site-*`` package) to add custom auth logic, response
parsing, or auto-pagination for a specific website.

Simple sites that only need a JSON template do NOT need a Python plugin.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Awaitable, Callable

from .response_contract import apply_response_contract
from .save_media import compile_media_contract


class SitePlugin:
    """Site plugin base class.  Override hooks as needed."""

    site_id: str = ""

    def before_fetch(self, request: dict, *, tab: Any = None, store: Any = None) -> dict:
        """Called before the fetch JS is built.

        Modify *request* dict in-place or return a new one.  Useful for
        injecting dynamic tokens read from the page, rewriting URLs, etc.
        """
        return request

    def after_fetch(self, response: dict, spec: dict) -> dict:
        """Called after the raw response is received.

        *response* carries ``status`` / ``statusText`` / ``body`` (raw text);
        *spec* is the fully-rendered preset that produced the request.

        Sites have **three** ways to extend this hook — pick the simplest
        that fits (symmetric with :meth:`media_contract`):

        1. **Python plugin override** (this method) — full flexibility:
           branch on status codes, do regex / numeric comparisons, run
           async enrichment, etc.  Call ``super().after_fetch(response, spec)``
           first if you still want declarative rules to apply.

        2. **Declarative preset JSON** — add a top-level
           ``response_contract`` block to the preset.  The default
           implementation here dispatches to
           :func:`~ziniao_mcp.sites.response_contract.apply_response_contract`
           which supports JSON parsing + dotted-path "lift" rules with
           optional ``when_eq`` equality guards.

        3. **None** — the preset has no ``response_contract`` and no
           plugin overrides this method; *response* is returned unchanged.
        """
        return apply_response_contract(response, spec.get("response_contract"))

    async def paginate(
        self,
        fetch_fn: Callable[[dict], Awaitable[dict]],
        request: dict,
        first_response: dict,
    ) -> AsyncIterator[dict]:
        """Yield pages of data.  Default: single page (no pagination)."""
        yield first_response

    def media_contract(self, result: dict, spec: dict) -> list[dict]:
        """Declare which fields in *result* are media to persist to disk.

        Sites have **three** ways to extend ``--save-images`` — pick the
        simplest that fits:

        1. **Python plugin override** (this method) — full flexibility:
           conditionally synthesize items, compute derived file names,
           branch on status codes, etc.  Receives *result* (response body
           parsed) and *spec* (the rendered preset).

        2. **Declarative preset JSON** — add a top-level ``media_contract``
           list to the preset (no Python code required).  The default
           implementation here compiles those rules via
           :func:`~ziniao_mcp.sites.save_media.compile_media_contract`.
           Supported rule shapes::

              { "items_at": "<dotted>",                    # list path
                "fields": [ {"key": "...", "source": "base64"|"url"} ],
                "stem_suffix": "-{idx}" }
              { "at": "<dotted>", "source": "base64"|"url",
                "stem_suffix": "-logo" }

        3. **None** — return ``[]`` (the framework default when the preset
           declares no rules and no plugin overrides this method).

        Each returned "save item" is a dict with:

        - ``source``: ``"base64"`` or ``"url"``
        - ``value``: the base64 payload or the URL
        - ``stem_suffix``: filename suffix (e.g. ``"-0"``, ``"-front"``)
          appended to the user-supplied ``--save-images <prefix>``.
        - ``path``: list of dict-keys / list-indices pointing to the
          original field; :func:`apply_media_contract` replaces it with a
          short ``"[saved: <filename>]"`` note after writing.
        """
        return compile_media_contract(spec.get("media_contract"), result)
