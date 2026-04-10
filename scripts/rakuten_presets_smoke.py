#!/usr/bin/env python3
"""Smoke-test ziniao rakuten/* presets; prints TSV for docs. Run from repo root with daemon + logged-in tab.

  python scripts/rakuten_presets_smoke.py
  python scripts/rakuten_presets_smoke.py --save              # -> out/rakuten-preset-responses/
  python scripts/rakuten_presets_smoke.py --save path/to/dir  # full JSON per preset (--json --max-output 0)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Row:
    preset: str
    cmd: str
    outcome: str
    detail: str


def run(cmd: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return -1, "timeout"
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, out


def classify(text: str) -> tuple[str, str]:
    t = text.replace("\r", "")
    if "没有活动的浏览器会话" in t or "没有打开" in t:
        return "no_session", "需先 open_store / launch_chrome / connect_chrome"
    if "Error:" in t:
        m = re.search(r"Error:\s*(.+?)(?:\n|$)", t, re.S)
        msg = (m.group(1).strip().replace("\n", " ") if m else "error")[:180]
        return "cli_error", msg
    if "Failed to fetch" in t or "TypeError: Failed to fetch" in t:
        return "fetch_failed", "page fetch TypeError (wrong tab origin / CORS / network)"
    if re.search(r"\bstatus:\s*200\b", t, re.I):
        if "body:" in t.lower() and "<!DOCTYPE html>" in t:
            return "ok_200", "HTTP 200, HTML body"
        return "ok_200", "HTTP 200 (JSON or text)"
    m = re.search(r"\bstatus:\s*(\d{3})\b", t, re.I)
    if m:
        return f"http_{m.group(1)}", f"HTTP {m.group(1)}"
    if "OK" in t and "ExceptionDetails" in t:
        return "page_exception", "OK envelope but page script exception"
    if "OK" in t.splitlines()[0:3]:
        return "ok_unknown", "OK (parse status unclear)"
    return "unknown", t[:200].replace("\n", " ")


SHOP = "pettena-collections"  # from rpp-exp-merchant when session matches

TESTS: list[tuple[str, list[str]]] = [
    ("rpp-exp-merchant", []),
    ("rmail-reports", []),
    ("afl-report-pending", ["-V", "date=2026-03"]),
    ("cpa-reports-search", ["-V", "start_date=2026-03-01", "-V", "end_date=2026-03-07"]),
    (
        "cpnadv-performance-retrieve",
        ["-V", "start_date=2026-03-01", "-V", "end_date=2026-03-07"],
    ),
    (
        "datatool-deal-csv",
        ["-V", "start_date=20260301", "-V", "end_date=20260331", "-V", "period=daily"],
    ),
    (
        "rpp-exp-report",
        [
            "-V",
            "start_date=2026-03-01",
            "-V",
            "end_date=2026-03-07",
            "-V",
            f"shop_url={SHOP}",
        ],
    ),
    ("rpp-search", ["-V", "start_date=2026-03-01", "-V", "end_date=2026-03-07"]),
    ("shared-purchase-detail", ["-V", "target_month=2026-03"]),
    (
        "tda-exp-report",
        [
            "-V",
            "start_date=2026-03-01",
            "-V",
            "end_date=2026-03-07",
            "-V",
            f"shop_url={SHOP}",
        ],
    ),
    ("tda-reports-search", ["-V", "start_date=2026-03-01", "-V", "end_date=2026-03-07"]),
    ("reviews-csv", ["-V", "last_days=7"]),
]


def main() -> int:
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(description="Rakuten preset smoke test")
    ap.add_argument(
        "--save",
        nargs="?",
        const=str(Path("out") / "rakuten-preset-responses"),
        default=None,
        metavar="DIR",
        help="Save each response as JSON (uses: ziniao --json --max-output 0 ...). Default: out/rakuten-preset-responses",
    )
    args = ap.parse_args()
    save_dir: Path | None = Path(args.save).resolve() if args.save else None
    if save_dir is not None:
        save_dir.mkdir(parents=True, exist_ok=True)
        manifest: list[dict] = []

    rows: list[Row] = []
    for name, extra in TESTS:
        cmd = ["ziniao", "rakuten", name, *extra]
        code, out = run(cmd)
        kind, detail = classify(out)
        if code != 0 and kind == "unknown":
            detail = f"exit={code} {detail}"
        rows.append(Row(name, " ".join(cmd[2:]), kind, detail))

        if save_dir is not None:
            jcmd = ["ziniao", "--json", "--max-output", "0", "rakuten", name, *extra]
            jcode, jout = run(jcmd)
            out_path = save_dir / f"{name}.raw.txt"
            # CLI prints one JSON object per line or single blob — save as-is
            out_path.write_text(jout, encoding="utf-8")
            parsed_ok = False
            try:
                parsed = json.loads(jout.strip())
                (save_dir / f"{name}.json").write_text(
                    json.dumps(parsed, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                parsed_ok = True
            except (json.JSONDecodeError, ValueError):
                pass
            manifest.append(
                {
                    "preset": name,
                    "command": " ".join(jcmd),
                    "exit_code": jcode,
                    "tsv_outcome": kind,
                    "tsv_detail": detail,
                    "saved_raw": str(out_path.name),
                    "saved_pretty_json": f"{name}.json" if parsed_ok else None,
                }
            )

    print("preset\toutcome\tdetail\tcommand")
    for r in rows:
        print(f"{r.preset}\t{r.outcome}\t{r.detail}\t{r.cmd}")

    if save_dir is not None:
        (save_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"\nSaved under: {save_dir}", file=sys.stderr)
        print("  manifest.json, <preset>.json, <preset>.raw.txt", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
