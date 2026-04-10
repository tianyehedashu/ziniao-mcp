#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
解析 ziniao `reviews-csv` 导出（UTF-8）：中文汇总报告 + 中低分评价全文清单 + 可选 JSON 摘要。

楽天 URL 键：.../item/1/<店ID>_<商品ID>/...
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ITEM_KEY_RE = re.compile(r"/item/1/(\d+_\d+)/")

# 日文/常用表达 → 中文可行动标签（命中即计入，可多标签）
THEME_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("外箱破损/包装", ("ダンボール", "箱", "破れ", "破損", "穴", "つぶれ", "汚れ", "袋", "突き出し", "裸")),
    ("配送迟延", ("遅い", "遅延", "日かか", "届かな", "ようやく", "まだ届")),
    ("说明/折叠困难", ("説明書", "畳め", "折り畳", "ストレス", "コツ", "分からない")),
    ("错发/漏发/配件", ("入っていなかった", "欠品", "同梱", "オプション", "クッションが", "特典", "送ってもらえ")),
    ("品质/做工/异味", ("キツい", "匂い", "傷", "不良", "シミ", "ホコリ", "汚れ", "スムーズにいかない")),
    ("尺寸/适配", ("大きい", "小さい", "幅", "合わず", "合わない", "サイズ")),
    ("客服/沟通不满", ("問い合わせ", "対応", "返信", "キャンセル", "不信")),
    ("描述不符/预期差", ("思っていた", "イマイチ", "違う", "間違え")),
]


def mask_order_id(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    parts = s.split("-")
    if len(parts) == 3 and parts[0].isdigit():
        return f"{parts[0]}-****-****"
    return "（已脱敏）"


def parse_star(val: str) -> int | None:
    try:
        return int((val or "").strip())
    except ValueError:
        return None


def item_key_from_url(url: str) -> str | None:
    m = ITEM_KEY_RE.search(url or "")
    return m.group(1) if m else None


def theme_tags(text: str, max_tags: int = 3) -> list[str]:
    if not text:
        return []
    found: list[str] = []
    for label, kws in THEME_RULES:
        if any(k in text for k in kws):
            found.append(label)
        if len(found) >= max_tags:
            break
    return found


@dataclass
class ReviewRow:
    typ: str
    name: str
    url: str
    star: int
    posted: str
    title: str
    body: str
    order_id: str
    item_key: str | None = None


def load_reviews(path: Path) -> list[ReviewRow]:
    out: list[ReviewRow] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            star = parse_star(row.get("評価", ""))
            if star is None:
                continue
            typ = (row.get("レビュータイプ") or "").strip()
            url = (row.get("レビュー詳細URL") or "").strip()
            out.append(
                ReviewRow(
                    typ=typ,
                    name=(row.get("商品名") or "").strip(),
                    url=url,
                    star=star,
                    posted=(row.get("投稿時間") or "").strip(),
                    title=(row.get("タイトル") or "").strip(),
                    body=(row.get("レビュー本文") or "").strip(),
                    order_id=(row.get("注文番号") or "").strip(),
                    item_key=item_key_from_url(url) if typ == "商品レビュー" else None,
                )
            )
    return out


def star_distribution(rows: list[ReviewRow], typ: str) -> dict[int, int]:
    c: Counter[int] = Counter()
    for r in rows:
        if r.typ != typ:
            continue
        c[r.star] += 1
    return {s: c.get(s, 0) for s in range(1, 6)}


def aggregate_products(rows: list[ReviewRow], low_min: int, low_max: int) -> dict[str, dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "name": "",
            "total": 0,
            "low_n": 0,
            "l12": 0,
            "theme_counter": Counter(),
        }
    )
    for r in rows:
        if r.typ != "商品レビュー":
            continue
        key = r.item_key or "（无法解析URL键）"
        b = by_key[key]
        if not b["name"] and r.name:
            b["name"] = r.name
        b["total"] += 1
        if low_min <= r.star <= low_max:
            b["low_n"] += 1
            for t in theme_tags(r.title + "\n" + r.body):
                b["theme_counter"][t] += 1
        if 1 <= r.star <= 2:
            b["l12"] += 1
    return dict(by_key)


def build_lowscore_rows(rows: list[ReviewRow], low_min: int, low_max: int) -> list[ReviewRow]:
    return [r for r in rows if low_min <= r.star <= low_max]


def write_report_zh(
    path_out: Path,
    src_csv: Path,
    rows: list[ReviewRow],
    low_min: int,
    low_max: int,
    by_product: dict[str, dict[str, Any]],
) -> None:
    shop_rows = [r for r in rows if r.typ == "ショップレビュー"]
    prod_rows = [r for r in rows if r.typ == "商品レビュー"]
    shop_dist = star_distribution(rows, "ショップレビュー")
    prod_dist = star_distribution(rows, "商品レビュー")

    shop_low = sum(1 for r in shop_rows if low_min <= r.star <= low_max)
    shop_12 = sum(1 for r in shop_rows if 1 <= r.star <= 2)
    prod_low = sum(1 for r in prod_rows if low_min <= r.star <= low_max)
    prod_12 = sum(1 for r in prod_rows if 1 <= r.star <= 2)

    lines: list[str] = [
        "# 乐天评价解析报告（中文）",
        "",
        f"- **源文件**：`{src_csv.as_posix()}`",
        f"- **总记录数**：{len(rows)}（店铺评价 {len(shop_rows)} / 商品评价 {len(prod_rows)}）",
        f"- **中低分口径**：★{low_min}～{low_max}（条数见下表「中低分条数」）",
    ]
    if prod_rows:
        lines.append(
            f"- **商品评价**：中低分 **{prod_low}** / {len(prod_rows)}（{100 * prod_low / len(prod_rows):.1f}%），其中 ★1～2：**{prod_12}**"
        )
    lines.extend(
        [
            "",
            "## 一、店铺评价（ショップレビュー）概览",
            "",
            f"- 总条数：**{len(shop_rows)}**",
            (
                f"- 中低分（★{low_min}～{low_max}）：**{shop_low}**（占店铺评价 {shop_low / len(shop_rows) * 100:.1f}%）"
                if shop_rows
                else "- （无店铺评价）"
            ),
        ]
    )
    if shop_rows:
        lines.append(f"- 其中 ★1～2：**{shop_12}**")
    lines.extend(["", "| 星级 | 条数 | 占店铺评价比例(%) |", "|------|------|-------------------|"])
    stotal = len(shop_rows) or 1
    for s in range(5, 0, -1):
        n = shop_dist.get(s, 0)
        lines.append(f"| ★{s} | {n} | {100 * n / stotal:.1f} |")
    lines.extend(["", "## 二、商品评价按楽天键汇总（店ID_商品ID）", "", "| 楽天商品键 | 代表商品名(缩) | 商品评论数 | 中低分条数 | 中低分率(%) | 其中★1～2 | 主要问题线索(中文) |", "|------------|----------------|------------|------------|-------------|-----------|-------------------|"])

    items = []
    for key, v in by_product.items():
        t = v["total"]
        if t == 0:
            continue
        l_low = v["low_n"]
        l12 = v["l12"]
        rate = 100 * l_low / t
        top_themes = v["theme_counter"].most_common(3)
        theme_str = "、".join(f"{n}({c})" for n, c in top_themes) if top_themes else "—"
        name = (v["name"] or "")[:40] + ("…" if len(v["name"] or "") > 40 else "")
        items.append((l_low, rate, key, name, t, l12, theme_str))
    items.sort(key=lambda x: (-x[0], -x[1]))
    for l_low, rate, key, name, t, l12, theme_str in items:
        lines.append(f"| `{key}` | {name} | {t} | {l_low} | {rate:.1f} | {l12} | {theme_str} |")

    prod_low_rows = [r for r in prod_rows if low_min <= r.star <= low_max]
    theme_all: Counter[str] = Counter()
    for r in prod_low_rows:
        for t in theme_tags(r.title + "\n" + r.body, max_tags=5):
            theme_all[t] += 1
    if theme_all:
        lines.extend(
            [
                "",
                "## 二（附）商品评价·中低分主题命中汇总（中文标签）",
                "",
                "说明：同一条评价可命中多个标签；以下为命中次数总览，供 E 类主题挖掘对照。",
                "",
                "| 主题标签（中文） | 命中次数 |",
                "|------------------|----------|",
            ]
        )
        for label, cnt in theme_all.most_common():
            lines.append(f"| {label} | {cnt} |")

    lines.extend(["", "## 三、商品评价星级分布", "", "| 星级 | 条数 | 占商品评价比例(%) |", "|------|------|-------------------|"])
    ptotal = len(prod_rows) or 1
    for s in range(5, 0, -1):
        n = prod_dist.get(s, 0)
        lines.append(f"| ★{s} | {n} | {100 * n / ptotal:.1f} |")

    lines.extend(
        [
            "",
            "## 四、输出文件说明",
            "",
            "- **本报告（Markdown）**：汇总表、星级分布、主题命中总览。",
            "- **中低分全文清单**：同目录 `*_lowscore_zh.md`，含全部 ★{}～{} 顾客原文，按楽天键分组；订单号默认脱敏。".format(low_min, low_max),
            "- **可选**：脚本加 `--lowscore-csv` 可另存 `*_lowscore_zh.csv`（UTF-8 BOM，列名中文）；`--write-json` 产出结构化 `*_summary.json` 供二次透视。",
            "",
        ]
    )
    path_out.write_text("\n".join(lines), encoding="utf-8")


def write_lowscore_zh(
    path_out: Path,
    rows: list[ReviewRow],
    low_min: int,
    low_max: int,
    mask_order: bool,
) -> None:
    low_rows = build_lowscore_rows(rows, low_min, low_max)
    low_rows.sort(key=lambda r: (r.typ, r.item_key or "", r.posted))

    lines: list[str] = [
        f"# 中低分评价全文清单（★{low_min}～{low_max}）",
        "",
        f"- **总条数**：{len(low_rows)}（含店铺评价 + 商品评价）",
        "- **说明**：正文为顾客原文（日语等）；小节标题与字段名为中文。",
        "",
    ]

    # 先商品（按键分组）
    prod_low = [r for r in low_rows if r.typ == "商品レビュー"]
    shop_low = [r for r in low_rows if r.typ == "ショップレビュー"]

    by_key: dict[str, list[ReviewRow]] = defaultdict(list)
    for r in prod_low:
        by_key[r.item_key or "（无法解析URL键）"].append(r)

    lines.extend(["## 商品评价（按楽天商品键分组）", ""])
    for key in sorted(by_key.keys(), key=lambda k: (-len(by_key[k]), k)):
        rs = by_key[key]
        lines.extend([f"### `{key}`（共 {len(rs)} 条）", ""])
        for i, r in enumerate(rs, 1):
            oid = mask_order_id(r.order_id) if mask_order else (r.order_id or "—")
            tags = "、".join(theme_tags(r.title + "\n" + r.body)) or "—"
            lines.extend(
                [
                    f"#### 第 {i} 条 · ★{r.star} · {r.posted}",
                    f"- **问题线索**：{tags}",
                    f"- **商品名**：{r.name or '—'}",
                    f"- **标题**：{r.title or '（无）'}",
                    "- **正文**：",
                    "",
                    r.body or "（无）",
                    "",
                    f"- **详情链接**：{r.url or '—'}",
                    f"- **订单号**：{oid}",
                    "",
                    "---",
                    "",
                ]
            )

    lines.extend(["## 店铺评价（ショップレビュー）中低分", ""])
    if not shop_low:
        lines.extend(["（本窗口内无店铺中低分评价）", ""])
    else:
        for i, r in enumerate(shop_low, 1):
            oid = mask_order_id(r.order_id) if mask_order else (r.order_id or "—")
            tags = "、".join(theme_tags(r.title + "\n" + r.body)) or "—"
            lines.extend(
                [
                    f"### 第 {i} 条 · ★{r.star} · {r.posted}",
                    f"- **问题线索**：{tags}",
                    f"- **标题**：{r.title or '（无）'}",
                    "- **正文**：",
                    "",
                    r.body or "（无）",
                    "",
                    f"- **详情链接**：{r.url or '—'}",
                    f"- **订单号**：{oid}",
                    "",
                    "---",
                    "",
                ]
            )

    path_out.write_text("\n".join(lines), encoding="utf-8")


def write_lowscore_csv(
    path_out: Path,
    rows: list[ReviewRow],
    low_min: int,
    low_max: int,
    mask_order: bool,
) -> None:
    low_rows = build_lowscore_rows(rows, low_min, low_max)
    low_rows.sort(key=lambda r: (r.typ, r.item_key or "", r.posted))
    fieldnames = [
        "评价类型",
        "楽天商品键",
        "星级",
        "投稿时间",
        "商品名",
        "标题",
        "正文全文",
        "问题线索_中文",
        "详情链接",
        "订单号",
    ]
    with path_out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in low_rows:
            key = r.item_key if r.typ == "商品レビュー" else "—"
            oid = mask_order_id(r.order_id) if mask_order else (r.order_id or "")
            tags = "、".join(theme_tags(r.title + "\n" + r.body, max_tags=8))
            w.writerow(
                {
                    "评价类型": "商品评价" if r.typ == "商品レビュー" else "店铺评价",
                    "楽天商品键": key or "—",
                    "星级": r.star,
                    "投稿时间": r.posted,
                    "商品名": r.name,
                    "标题": r.title,
                    "正文全文": r.body,
                    "问题线索_中文": tags or "—",
                    "详情链接": r.url,
                    "订单号": oid or "—",
                }
            )


def write_summary_json(
    path_out: Path,
    src_csv: Path,
    rows: list[ReviewRow],
    low_min: int,
    low_max: int,
    by_product: dict[str, dict[str, Any]],
) -> None:
    shop_rows = [r for r in rows if r.typ == "ショップレビュー"]
    prod_rows = [r for r in rows if r.typ == "商品レビュー"]
    low_count = len(build_lowscore_rows(rows, low_min, low_max))

    prod_summary = []
    for key, v in sorted(by_product.items(), key=lambda kv: -kv[1]["total"]):
        t = v["total"]
        l_low = v["low_n"]
        l12 = v["l12"]
        prod_summary.append(
            {
                "rakuten_item_key": key,
                "sample_name": (v["name"] or "")[:80],
                "product_review_count": t,
                "low_star_count": l_low,
                "low_star_rate_pct": round(100 * l_low / t, 2) if t else 0,
                "star_1_2_count": l12,
                "top_themes_zh": [x[0] for x in v["theme_counter"].most_common(5)],
            }
        )
    prod_summary.sort(key=lambda x: (-x["low_star_count"], -x["low_star_rate_pct"]))

    prod_low = [r for r in prod_rows if low_min <= r.star <= low_max]
    theme_all: Counter[str] = Counter()
    for r in prod_low:
        for t in theme_tags(r.title + "\n" + r.body, max_tags=5):
            theme_all[t] += 1

    payload = {
        "source_csv": str(src_csv),
        "low_star_range": [low_min, low_max],
        "counts": {
            "total_rows": len(rows),
            "shop_reviews": len(shop_rows),
            "product_reviews": len(prod_rows),
            "low_star_total": low_count,
        },
        "shop_star_distribution": star_distribution(rows, "ショップレビュー"),
        "product_star_distribution": star_distribution(rows, "商品レビュー"),
        "low_star_theme_hits_zh": dict(theme_all.most_common()),
        "product_keys_sorted_by_low_star": prod_summary,
    }
    path_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="解析乐天 reviews-csv 导出 → 中文报告 + 中低分全文")
    ap.add_argument("csv", type=Path, help="reviews-csv 导出的 UTF-8 CSV 路径")
    ap.add_argument(
        "-o",
        "--out-dir",
        type=Path,
        default=None,
        help="输出目录（默认与 CSV 同目录）",
    )
    ap.add_argument("--stem", type=str, default=None, help="输出文件主名（默认与 CSV 同名不含扩展名）")
    ap.add_argument("--low-min", type=int, default=1, help="中低分下限星级（默认 1）")
    ap.add_argument("--low-max", type=int, default=3, help="中低分上限星级（默认 3；若只看差评可设 2）")
    ap.add_argument("--no-mask-order", action="store_true", help="订单号不脱敏（默认脱敏）")
    ap.add_argument("--no-lowscore-md", action="store_true", help="不写中低分全文 Markdown")
    ap.add_argument(
        "--lowscore-csv",
        action="store_true",
        help="另写中低分全文表 CSV（UTF-8 BOM，Excel 友好；列名为中文）",
    )
    ap.add_argument("--json", type=Path, default=None, help="另写 JSON 摘要到此路径（默认同目录 <stem>_summary.json 若指定 --write-json）")
    ap.add_argument("--write-json", action="store_true", help="在同目录写出 <stem>_summary.json")

    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    csv_path: Path = args.csv.resolve()
    if not csv_path.is_file():
        raise SystemExit(f"找不到文件: {csv_path}")

    out_dir = (args.out_dir or csv_path.parent).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.stem or csv_path.stem

    rows = load_reviews(csv_path)
    by_product = aggregate_products(rows, args.low_min, args.low_max)

    report_path = out_dir / f"{stem}_report_zh.md"
    write_report_zh(report_path, csv_path, rows, args.low_min, args.low_max, by_product)

    mask = not args.no_mask_order
    if not args.no_lowscore_md:
        low_path = out_dir / f"{stem}_lowscore_zh.md"
        write_lowscore_zh(low_path, rows, args.low_min, args.low_max, mask_order=mask)
    if args.lowscore_csv:
        csv_path = out_dir / f"{stem}_lowscore_zh.csv"
        write_lowscore_csv(csv_path, rows, args.low_min, args.low_max, mask_order=mask)

    json_path = args.json
    if args.write_json and json_path is None:
        json_path = out_dir / f"{stem}_summary.json"
    if json_path is not None:
        write_summary_json(json_path.resolve(), csv_path, rows, args.low_min, args.low_max, by_product)

    print(f"报告: {report_path}")
    if not args.no_lowscore_md:
        print(f"中低分全文: {out_dir / f'{stem}_lowscore_zh.md'}")
    if args.lowscore_csv:
        print(f"中低分CSV: {out_dir / f'{stem}_lowscore_zh.csv'}")
    if json_path is not None:
        print(f"JSON: {json_path.resolve()}")


if __name__ == "__main__":
    main()
