#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Summarize ziniao Rakuten ad JSON exports (RPP, TDA, cpnadv shop/item, CPA).

Typical usage (from repo root or any cwd):

  python .cursor/skills/rakuten-ad-reports/scripts/aggregate_ad_exports.py -d exports
  python .cursor/skills/rakuten-ad-reports/scripts/aggregate_ad_exports.py rpp_item.json tda_item.json

Directory scan skips filenames starting with ``_`` (e.g. ``_sample_*.json``).

字段口径与合并流程见同技能目录下 ``references/SCRIPTS.md``。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def _load(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _report_dtos_have_item(rows: list[Any]) -> bool:
    for r in rows:
        if not isinstance(r, dict):
            continue
        if r.get("itemMngId") is not None and str(r.get("itemMngId")).strip() != "":
            return True
    return False


def _detect_kind(data: Any) -> str:
    if not isinstance(data, dict):
        return "unknown"
    if data == {}:
        return "empty"
    # cpnadv: top-level reportDtos（店铺日汇总 vs 按商品分页）
    if "reportDtos" in data and isinstance(data["reportDtos"], list):
        rows = data["reportDtos"]
        if _report_dtos_have_item(rows):
            return "cpnadv_item"
        return "cpnadv_shop"
    d = data.get("data")
    if not isinstance(d, dict):
        return "unknown"
    if "billingReports" in d and isinstance(d["billingReports"], list):
        return "cpa_billing"
    if "rppReports" in d and isinstance(d["rppReports"], list):
        rows = d["rppReports"]
        if not rows:
            return "rpp_empty"
        r0 = rows[0]
        if isinstance(r0, dict) and r0.get("itemUrl"):
            return "rpp_item"
        if isinstance(r0, dict) and (
            r0.get("campaignName") or r0.get("rppCampaignId") is not None
        ):
            return "rpp_campaignish"
        if isinstance(r0, dict) and r0.get("effectDate"):
            return "rpp_daily"
        return "rpp_other"
    if "tdaReports" in d and isinstance(d["tdaReports"], list):
        return "tda_item"
    return "unknown"


def _eff_ratio(gms: float, spend: float) -> float | None:
    if spend <= 0:
        return None
    return gms / spend


def summarize_rpp_item(rows: list[dict[str, Any]], top_n: int = 12) -> dict[str, Any]:
    skus: list[dict[str, Any]] = []
    for r in rows:
        tu = r.get("totalUsersReport") or {}
        t720 = tu.get("type720H") or {}
        sp = float(tu.get("adSalesBeforeDiscount") or 0)
        gms = float(t720.get("gms") or 0)
        skus.append(
            {
                "sku": r.get("itemUrl") or "",
                "clicks": int(tu.get("clicksValid") or 0),
                "spend": sp,
                "gms720": gms,
                "cv720": int(t720.get("cv") or 0),
                "ratio720": _eff_ratio(gms, sp),
                "ctr": r.get("ctr"),
            }
        )
    by_spend = sorted(skus, key=lambda x: x["spend"], reverse=True)[:top_n]
    min_spend = 15000.0
    rated = [s for s in skus if s["spend"] >= min_spend and s["ratio720"] is not None]
    tail = sorted(rated, key=lambda x: x["ratio720"] or 0)[:8]
    head = sorted(rated, key=lambda x: x["ratio720"] or 0, reverse=True)[:8]
    tot_spend = sum(s["spend"] for s in skus)
    tot_gms = sum(s["gms720"] for s in skus)
    tot_clicks = sum(s["clicks"] for s in skus)
    tot_cv = sum(s["cv720"] for s in skus)
    return {
        "sku_count": len(skus),
        "totals": {
            "spend": tot_spend,
            "clicks": tot_clicks,
            "gms720": tot_gms,
            "cv720": tot_cv,
            "blended_ratio720": _eff_ratio(tot_gms, tot_spend),
        },
        "top_by_spend": by_spend,
        "low_ratio_spend_ge": {"threshold": min_spend, "skus": tail},
        "high_ratio_spend_ge": {"threshold": min_spend, "skus": head},
    }


def summarize_rpp_daily(rows: list[dict[str, Any]], top_days: int = 5) -> dict[str, Any]:
    tot_clicks = tot_spend = tot_gms = tot_cv = 0
    daily: list[tuple[str, float, float | None]] = []
    for r in rows:
        tu = r.get("totalUsersReport") or {}
        t720 = tu.get("type720H") or {}
        c = int(tu.get("clicksValid") or 0)
        sp = float(tu.get("adSalesBeforeDiscount") or 0)
        gms = float(t720.get("gms") or 0)
        cv = int(t720.get("cv") or 0)
        tot_clicks += c
        tot_spend += sp
        tot_gms += gms
        tot_cv += cv
        day = str(r.get("effectDate") or "")
        daily.append((day, sp, _eff_ratio(gms, sp)))
    daily.sort(key=lambda x: x[1], reverse=True)
    return {
        "day_count": len(rows),
        "totals": {
            "clicks": tot_clicks,
            "spend": tot_spend,
            "gms720": tot_gms,
            "cv720": tot_cv,
            "blended_ratio720": _eff_ratio(tot_gms, tot_spend),
        },
        "top_spend_days": [{"date": d, "spend": sp, "ratio720": rt} for d, sp, rt in daily[:top_days]],
    }


def summarize_rpp_campaign(rows: list[dict[str, Any]], top_n: int = 15) -> dict[str, Any]:
    """RPP selection_type=2：按计划名聚合多日明细。"""
    by_c: dict[str, dict[str, float]] = defaultdict(
        lambda: {"spend": 0.0, "clicks": 0.0, "gms720": 0.0, "cv720": 0.0, "row_days": 0.0}
    )
    for r in rows:
        name = str(r.get("campaignName") or "unknown")
        tu = r.get("totalUsersReport") or {}
        t720 = tu.get("type720H") or {}
        by_c[name]["spend"] += float(tu.get("adSalesBeforeDiscount") or 0)
        by_c[name]["clicks"] += float(tu.get("clicksValid") or 0)
        by_c[name]["gms720"] += float(t720.get("gms") or 0)
        by_c[name]["cv720"] += float(t720.get("cv") or 0)
        by_c[name]["row_days"] += 1.0
    campaigns = []
    for name, v in by_c.items():
        sp = v["spend"]
        g = v["gms720"]
        campaigns.append(
            {
                "campaignName": name,
                **v,
                "ratio720": _eff_ratio(g, sp),
            }
        )
    campaigns.sort(key=lambda x: x["spend"], reverse=True)
    return {
        "row_count": len(rows),
        "plan_count": len(campaigns),
        "totals": {
            "spend": sum(c["spend"] for c in campaigns),
            "clicks": sum(c["clicks"] for c in campaigns),
            "gms720": sum(c["gms720"] for c in campaigns),
            "cv720": sum(c["cv720"] for c in campaigns),
        },
        "top_by_spend": campaigns[:top_n],
    }


def summarize_tda(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_c: dict[str, dict[str, float]] = defaultdict(
        lambda: {"spend": 0.0, "gms": 0.0, "cv": 0.0, "imp": 0.0, "clk": 0.0}
    )
    for r in rows:
        name = str(r.get("campaignName") or "unknown")
        by_c[name]["spend"] += float(r.get("spendingBudget") or 0)
        by_c[name]["gms"] += float(r.get("vtCvAmount") or 0)
        by_c[name]["cv"] += float(r.get("vtCvNum") or 0)
        by_c[name]["imp"] += float(r.get("viewableImpNum") or 0)
        by_c[name]["clk"] += float(r.get("ctNum") or 0)
    campaigns = []
    for name, v in by_c.items():
        sp = v["spend"]
        g = v["gms"]
        campaigns.append(
            {
                "campaignName": name,
                **v,
                "ratio_vt": _eff_ratio(g, sp),
            }
        )
    campaigns.sort(key=lambda x: x["spend"], reverse=True)
    return {"row_count": len(rows), "by_campaign": campaigns}


def summarize_cpnadv_shop(report_dtos: list[dict[str, Any]]) -> dict[str, Any]:
    fee = sum(float(r.get("adFee") or 0) for r in report_dtos)
    use = sum(int(r.get("useCount") or 0) for r in report_dtos)
    acquired = sum(int(r.get("couponAcquired") or 0) for r in report_dtos)
    return {
        "row_count": len(report_dtos),
        "ad_fee_sum": fee,
        "use_count_sum": use,
        "coupon_acquired_sum": acquired,
    }


def summarize_cpnadv_item(report_dtos: list[dict[str, Any]], top_n: int = 15) -> dict[str, Any]:
    by_sku: dict[str, dict[str, float]] = defaultdict(
        lambda: {
            "ad_fee": 0.0,
            "use_count": 0.0,
            "gms720": 0.0,
            "cv720": 0.0,
            "coupon_acquired": 0.0,
            "rows": 0.0,
        }
    )
    for r in report_dtos:
        if not isinstance(r, dict):
            continue
        sku = str(r.get("itemMngId") or "").strip() or "unknown"
        by_sku[sku]["ad_fee"] += float(r.get("adFee") or 0)
        by_sku[sku]["use_count"] += float(r.get("useCount") or 0)
        by_sku[sku]["gms720"] += float(r.get("gmsShopXDevice720h") or 0)
        by_sku[sku]["cv720"] += float(r.get("cvShopXDevice720h") or 0)
        by_sku[sku]["coupon_acquired"] += float(r.get("couponAcquired") or 0)
        by_sku[sku]["rows"] += 1.0
    items = []
    for sku, v in by_sku.items():
        fee = v["ad_fee"]
        g = v["gms720"]
        items.append(
            {
                "itemMngId": sku,
                **v,
                "ratio_gms720_per_fee": _eff_ratio(g, fee),
            }
        )
    items.sort(key=lambda x: x["ad_fee"], reverse=True)
    tot_fee = sum(x["ad_fee"] for x in items)
    tot_gms = sum(x["gms720"] for x in items)
    return {
        "sku_count": len(items),
        "row_count": len(report_dtos),
        "totals": {
            "ad_fee": tot_fee,
            "gms720": tot_gms,
            "use_count": sum(x["use_count"] for x in items),
            "cv720": sum(x["cv720"] for x in items),
            "blended_ratio_gms_per_fee": _eff_ratio(tot_gms, tot_fee),
        },
        "top_by_ad_fee": items[:top_n],
    }


def summarize_cpa_billing(rows: list[dict[str, Any]]) -> dict[str, Any]:
    fees = sum(float(r.get("advertisingFees") or 0) for r in rows)
    sales = sum(float(r.get("sales") or 0) for r in rows)
    return {
        "row_count": len(rows),
        "advertising_fees_sum": fees,
        "attributed_sales_sum": sales,
        "sales_per_fee": _eff_ratio(sales, fees),
    }


def _print_summary(label: str, payload: dict[str, Any]) -> None:
    print(f"\n=== {label} ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def run(paths: list[Path], out_json: Path | None) -> int:
    bundle: dict[str, Any] = {"files": {}}
    for p in paths:
        if not p.is_file():
            print(f"skip missing: {p}", file=sys.stderr)
            continue
        try:
            raw = _load(p)
        except (OSError, json.JSONDecodeError) as e:
            print(f"skip bad json {p}: {e}", file=sys.stderr)
            continue
        kind = _detect_kind(raw)
        key = str(p)
        entry: dict[str, Any] = {"kind": kind}
        if kind == "empty":
            entry["summary"] = {"note": "empty object {}"}
        elif kind == "cpnadv_shop":
            rows = raw.get("reportDtos") or []
            s = summarize_cpnadv_shop(rows)
            entry["summary"] = s
            _print_summary(f"{p.name} [cpnadv_shop]", s)
        elif kind == "cpnadv_item":
            rows = raw.get("reportDtos") or []
            s = summarize_cpnadv_item(rows)
            entry["summary"] = s
            _print_summary(f"{p.name} [cpnadv_item]", s)
        elif kind == "cpa_billing":
            rows = (raw.get("data") or {}).get("billingReports") or []
            s = summarize_cpa_billing(rows)
            entry["summary"] = s
            _print_summary(f"{p.name} [cpa_billing]", s)
        elif kind == "rpp_item":
            rows = (raw.get("data") or {}).get("rppReports") or []
            s = summarize_rpp_item(rows)
            entry["summary"] = s
            _print_summary(f"{p.name} [rpp_item]", s)
        elif kind == "rpp_daily":
            rows = (raw.get("data") or {}).get("rppReports") or []
            s = summarize_rpp_daily(rows)
            entry["summary"] = s
            _print_summary(f"{p.name} [rpp_daily]", s)
        elif kind == "rpp_campaignish":
            rows = (raw.get("data") or {}).get("rppReports") or []
            if rows:
                s = summarize_rpp_campaign(rows)
            else:
                s = {"row_count": 0, "note": "empty rppReports"}
            entry["summary"] = s
            _print_summary(f"{p.name} [rpp_campaign]", s)
        elif kind in ("rpp_other", "rpp_empty"):
            rows = (raw.get("data") or {}).get("rppReports") or []
            entry["summary"] = {"row_count": len(rows), "note": f"kind={kind}; use merge_rpp_search_json for chunks"}
            _print_summary(f"{p.name} [{kind}]", entry["summary"])
        elif kind == "tda_item":
            rows = (raw.get("data") or {}).get("tdaReports") or []
            s = summarize_tda(rows)
            entry["summary"] = s
            _print_summary(f"{p.name} [tda_item]", s)
        else:
            entry["summary"] = {"note": "unknown structure"}
            _print_summary(f"{p.name} [unknown]", entry["summary"])
        bundle["files"][key] = entry

    if out_json:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        with out_json.open("w", encoding="utf-8") as f:
            json.dump(bundle, f, ensure_ascii=False, indent=2)
        print(f"\nWrote {out_json}", file=sys.stderr)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Aggregate Rakuten ad export JSON files.")
    ap.add_argument("paths", nargs="*", type=Path, help="JSON files to scan")
    ap.add_argument("-d", "--dir", type=Path, help="Directory: all *.json non-recursive")
    ap.add_argument("-o", "--output", type=Path, help="Write combined summary JSON")
    args = ap.parse_args()
    files: list[Path] = []
    if args.dir:
        if not args.dir.is_dir():
            print(f"not a directory: {args.dir}", file=sys.stderr)
            return 1
        for f in sorted(args.dir.glob("*.json")):
            if f.name.startswith("_"):
                continue
            files.append(f)
    files.extend(args.paths)
    if not files:
        ap.print_help()
        return 1
    return run(files, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
