# 乐天 RMS 店铺评价 · 配套脚本

路径：`.cursor/skills/rakuten-reviews/`（`scripts/`、`references/`）。在 `ziniao rakuten reviews-csv -o …` 落盘后，用脚本生成**中文**汇总报告、**中低分全文清单**（可逐条查看全部低分）及可选 JSON/CSV。口径与业务解读以上级 `SKILL.md` 为准；说明由 `SKILL.md` **直接**链入本文即可，勿再叠套多级子文档。

## 脚本一览

| 脚本 | 作用 |
|------|------|
| `scripts/analyze_reviews_csv.py` | 读取 `reviews-csv` 导出的 UTF-8 CSV → `*_report_zh.md`（中文表头与章节）+ `*_lowscore_zh.md`（★1～3 或自定义区间**全部**正文，按楽天键分组）+ 可选 `*_summary.json`、`*_lowscore_zh.csv` |

## analyze_reviews_csv.py

**输入**：`reviews-csv` 标准列（`レビュータイプ`、`商品名`、`レビュー詳細URL`、`評価`、`投稿時間`、`タイトル`、`レビュー本文`、`注文番号` 等）。

**楽天商品键**：自商品评价 URL 解析 `/item/1/<店ID>_<商品ID>/`。

**默认中低分**：★1～3；可用 `--low-min` / `--low-max` 收窄为仅 ★1～2（须与 SKILL 口径声明一致）。

**主题标签**：对日文正文做轻量关键词映射，输出**中文**可行动标签（外箱破损、配送迟延、说明折叠困难等），供 C/E 对照；非 NLP 深度聚类，命中规则见脚本内 `THEME_RULES`。

### 常用命令（仓库根目录）

```powershell
# 最小：中文报告 + 中低分全文 Markdown（订单号默认脱敏）
python .cursor/skills/rakuten-reviews/scripts/analyze_reviews_csv.py exports/reviews_last30.csv

# 指定输出目录与主文件名前缀
python .cursor/skills/rakuten-reviews/scripts/analyze_reviews_csv.py exports/pettena/reviews_2026-03-01_2026-03-31.csv -o exports/pettena --stem reviews_2026-03-01_2026-03-31

# 同时：JSON 摘要 + Excel 友好 CSV（列名中文，UTF-8 BOM）
python .cursor/skills/rakuten-reviews/scripts/analyze_reviews_csv.py exports/reviews_last7.csv --write-json --lowscore-csv

# 仅差评 ★1～2 全文与统计
python .cursor/skills/rakuten-reviews/scripts/analyze_reviews_csv.py exports/reviews_last30.csv --low-max 2

# 内部分析需完整订单号时（勿对外粘贴）
python .cursor/skills/rakuten-reviews/scripts/analyze_reviews_csv.py exports/reviews_last30.csv --no-mask-order
```

### 参数简表

| 参数 | 说明 |
|------|------|
| `csv` | 必选，`reviews-csv` 导出路径 |
| `-o` / `--out-dir` | 输出目录，默认与 CSV 同目录 |
| `--stem` | 输出文件主名，默认与 CSV 同名（无扩展名） |
| `--low-min` / `--low-max` | 中低分星级闭区间，默认 1～3 |
| `--no-mask-order` | 订单号不脱敏（默认脱敏为 `店ID-****-****`） |
| `--no-lowscore-md` | 不生成中低分 Markdown 全文 |
| `--lowscore-csv` | 另存中低分表 CSV（含**完整正文**列） |
| `--write-json` | 写出 `<stem>_summary.json`（分布、按键汇总、主题命中等） |
| `--json <路径>` | 自定义 JSON 输出路径 |

### 产出文件（默认主名 = CSV stem）

| 文件 | 内容 |
|------|------|
| `<stem>_report_zh.md` | 店铺/商品概览、按键汇总表、中低分主题总览、星级分布（**中文**） |
| `<stem>_lowscore_zh.md` | 指定星级区间内**全部**评价，按楽天键分组，字段名中文 |
| `<stem>_lowscore_zh.csv` | 可选；同上数据，表格软件筛选 |
| `<stem>_summary.json` | 可选；机读摘要，供 Agent 或 BI |

## 与广告 Skill 脚本的对齐习惯

- **一批一档**：与 `reviews_*` CSV 同目录或 `exports/<店铺>/` 下放本批 `*_report_zh.md` / `*_lowscore_zh.md`，避免多期混读。  
- **Windows PowerShell**：多命令逐行或分号 `;` 串联；避免依赖 `&&`（5.1）。  
- **勿**在 `exports/` 堆叠一次性分析脚本；扩展逻辑改 `analyze_reviews_csv.py` 或在本 `scripts/` 下新增并记入本文。
