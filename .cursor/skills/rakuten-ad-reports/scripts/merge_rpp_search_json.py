#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Merge multiple ziniao Rakuten JSON exports that share `data.rppReports`.

Covers:

- `rpp-search` (daily or plan × day): split windows when a single request fails or exceeds limits.
- `rpp-search-item`: split by **natural month** when the requested range crosses calendar months.

Concatenates `data.rppReports` in file order. `aggregate_ad_exports.py` infers daily vs campaign vs item
from the first row shape (e.g. `itemUrl` → rpp_item).

  python merge_rpp_search_json.py -o merged.json slice1.json slice2.json
"""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: root must be object")
    return data


def merge_rpp_search(files: list[Path]) -> dict[str, Any]:
    if not files:
        raise ValueError("no input files")
    base = deepcopy(_load(files[0]))
    data = base.get("data")
    if not isinstance(data, dict):
        raise ValueError(f"{files[0]}: missing data object")
    reports = list(data.get("rppReports") or [])
    for p in files[1:]:
        other = _load(p)
        od = other.get("data")
        if not isinstance(od, dict):
            print(f"warn: skip {p} (no data)", file=sys.stderr)
            continue
        extra = od.get("rppReports")
        if isinstance(extra, list):
            reports.extend(extra)
        else:
            print(f"warn: skip rppReports in {p}", file=sys.stderr)
    data["rppReports"] = reports
    # Optional: align span labels from first+last slice if present
    if isinstance(data.get("startDate"), str) and len(files) > 1:
        last = _load(files[-1]).get("data") or {}
        if isinstance(last.get("endDate"), str):
            data["endDate"] = last["endDate"]
    base["data"] = data
    return base


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Merge rpp-search / rpp-search-item JSON exports (data.rppReports)."
    )
    ap.add_argument("inputs", nargs="+", type=Path, help="rpp-search JSON files in order")
    ap.add_argument("-o", "--output", type=Path, required=True, help="Output JSON path")
    args = ap.parse_args()
    try:
        merged = merge_rpp_search(args.inputs)
    except (OSError, json.JSONDecodeError, ValueError) as e:
        print(e, file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    n = len((merged.get("data") or {}).get("rppReports") or [])
    print(f"Wrote {args.output} ({n} rppReports rows)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
