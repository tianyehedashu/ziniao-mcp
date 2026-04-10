"""Rakuten site plugin (optional post-processing)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo

from .._base import SitePlugin

_JST = ZoneInfo("Asia/Tokyo")


def _int_from_vars(merged: dict, key: str, default: int) -> int:
    if key not in merged:
        return default
    raw = merged.get(key, "")
    if raw is None or str(raw).strip() == "":
        return default
    return int(str(raw).strip(), 10)


class RakutenPlugin(SitePlugin):
    site_id = "rakuten"

    def before_fetch(self, request: dict, *, tab=None, store=None) -> dict:  # noqa: ARG002
        if not request.pop("rakuten_review_csv", False):
            return request
        merged = request.pop("_ziniao_merged_vars", None)
        if not isinstance(merged, dict):
            merged = {}
        start_s = str(merged.get("start_date", "")).strip()
        end_s = str(merged.get("end_date", "")).strip()
        if start_s and end_s:
            try:
                ds = datetime.strptime(start_s, "%Y-%m-%d")
                de = datetime.strptime(end_s, "%Y-%m-%d")
            except ValueError as exc:
                raise ValueError("start_date / end_date must be YYYY-MM-DD") from exc
            if ds.date() > de.date():
                raise ValueError("start_date must be on or before end_date")
        elif start_s or end_s:
            raise ValueError("start_date and end_date must be used together, or omit both and use last_days")
        else:
            raw_ld = str(merged.get("last_days", "30")).strip() or "30"
            try:
                n = int(raw_ld, 10)
            except ValueError as exc:
                raise ValueError("last_days must be a positive integer") from exc
            if n < 1:
                raise ValueError("last_days must be >= 1")
            end_d = datetime.now(_JST).date()
            start_d = end_d - timedelta(days=n - 1)
            ds = datetime(start_d.year, start_d.month, start_d.day)
            de = datetime(end_d.year, end_d.month, end_d.day)
        sy, sm, sd = ds.year, ds.month, ds.day
        ey, em, ed = de.year, de.month, de.day
        sh = _int_from_vars(merged, "sh", 0)
        si = _int_from_vars(merged, "si", 0)
        eh = _int_from_vars(merged, "eh", 23)
        ei = _int_from_vars(merged, "ei", 59)
        ev = _int_from_vars(merged, "ev", 0)
        tc = _int_from_vars(merged, "tc", 0)
        st = _int_from_vars(merged, "st", 1)
        ao = str(merged.get("ao", "A") or "A").strip() or "A"
        kw = str(merged.get("kw", "") or "")
        request["url"] = (
            "https://review.rms.rakuten.co.jp/search/csv/"
            f"?sy={sy}&sm={sm}&sd={sd}&sh={sh}&si={si}"
            f"&ey={ey}&em={em}&ed={ed}&eh={eh}&ei={ei}"
            f"&ev={ev}&tc={tc}&kw={quote(kw, safe='')}&ao={quote(ao, safe='')}&st={st}"
        )
        return request

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


SITE_PLUGIN = RakutenPlugin
