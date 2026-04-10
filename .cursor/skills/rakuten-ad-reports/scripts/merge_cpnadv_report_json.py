#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Merge `cpnadv-performance-retrieve-item` pages (concat top-level `reportDtos`).

ziniao 的 item 变体常需手工递增 `-V page=`；将每页 `-o` 的 JSON 按顺序传入本脚本即可。

  python merge_cpnadv_report_json.py -o cpnadv_item_merged.json page0.json page1.json
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


def merge(files: list[Path]) -> dict[str, Any]:
    if not files:
        raise ValueError("no input files")
    base = deepcopy(_load(files[0]))
    merged: list[Any] = []
    max_total = 0
    for p in files:
        raw = _load(p)
        chunk = raw.get("reportDtos")
        if not isinstance(chunk, list):
            print(f"warn: {p} has no reportDtos list", file=sys.stderr)
            continue
        merged.extend(chunk)
        tc = raw.get("totalCount")
        if isinstance(tc, int):
            max_total = max(max_total, tc)
    base["reportDtos"] = merged
    if max_total > 0:
        base["totalCount"] = max_total
    else:
        base["totalCount"] = len(merged)
    return base


def main() -> int:
    ap = argparse.ArgumentParser(description="Merge cpnadv JSON pages (reportDtos).")
    ap.add_argument("inputs", nargs="+", type=Path, help="JSON files in page order")
    ap.add_argument("-o", "--output", type=Path, required=True, help="Output JSON path")
    args = ap.parse_args()
    try:
        out = merge(args.inputs)
    except (OSError, json.JSONDecodeError, ValueError) as e:
        print(e, file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    n = len(out.get("reportDtos") or [])
    print(f"Wrote {args.output} ({n} reportDtos rows)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
