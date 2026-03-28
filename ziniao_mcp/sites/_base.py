"""Base class for site plugins.

Subclass ``SitePlugin`` in ``ziniao_mcp/sites/<site>/__init__.py`` (or a
third-party ``ziniao-site-*`` package) to add custom auth logic, response
parsing, or auto-pagination for a specific website.

Simple sites that only need a JSON template do NOT need a Python plugin.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Callable, Awaitable


class SitePlugin:
    """Site plugin base class.  Override hooks as needed."""

    site_id: str = ""

    def before_fetch(self, request: dict, *, tab: Any = None, store: Any = None) -> dict:
        """Called before the fetch JS is built.

        Modify *request* dict in-place or return a new one.  Useful for
        injecting dynamic tokens read from the page, rewriting URLs, etc.
        """
        return request

    def after_fetch(self, response: dict, request: dict) -> dict:
        """Called after the raw response is received.

        *response* has ``status``, ``statusText``, ``body`` (raw text).
        You can parse ``body`` and attach ``parsed`` or any extra keys.
        """
        return response

    async def paginate(
        self,
        fetch_fn: Callable[[dict], Awaitable[dict]],
        request: dict,
        first_response: dict,
    ) -> AsyncIterator[dict]:
        """Yield pages of data.  Default: single page (no pagination)."""
        yield first_response
