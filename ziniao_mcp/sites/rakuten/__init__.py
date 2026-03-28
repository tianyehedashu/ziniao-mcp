"""Rakuten site plugin (optional post-processing)."""

from __future__ import annotations

import json

from .._base import SitePlugin


class RakutenPlugin(SitePlugin):
    site_id = "rakuten"

    def after_fetch(self, response: dict, request: dict) -> dict:
        body_text = response.get("body", "")
        if not body_text:
            return response
        try:
            data = json.loads(body_text)
        except (json.JSONDecodeError, TypeError):
            return response
        if data.get("status") == "SUCCESS" and "data" in data:
            response["parsed"] = data["data"]
        return response
