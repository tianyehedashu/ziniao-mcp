# 乐天 RMS 广告报表 · 配套脚本

路径：`.cursor/skills/rakuten-ad-reports/`（`scripts/`、`references/`）。在 `ziniao rakuten … -o` 落盘后，用脚本做 JSON **合并**与**汇总**，口径与业务解读以 `SKILL.md` 为准。说明文档由 `SKILL.md` **直接**链入本文即可，**勿**再在 `references/` 下叠套多级子文档。

## 接口集計期間（ziniao 实测样例，乐天变更后请复测）

| 子命令 | 限制 | 说明 |
|--------|------|------|
| `rpp-search` | 終了は開始から **3ヶ月以内** | 例：`2026-01-01`～`2026-03-31` ✓，`～2026-04-01` ✗。可跨自然月，只要不超出「自 `start_date` 起连续三个月」窗口。超窗 → 分段拉取 + `merge_rpp_search_json.py`。 |
| `rpp-search` | **`end_date` ≠ JST 当日**；区间勿含**未来日** | 否则常见 `集計期間の条件を正しく指定してください。` |
| `rpp-search-item` | 終了は開始から **1ヶ月以内**（不跨自然月） | 例：`2026-01-01`～`2026-01-31` ✓，`～2026-02-01` ✗。跨月区间见下节 **标准流程**（按月切段 + `merge_rpp_search_json.py`）。 |
| `tda-reports-search-item` | 終了は開始から **3ヶ月以内** | 与 `rpp-search` 同级，**非** item 的一个月。 |

### `rpp-search-item` 跨自然月：标准流程（滚动区间与 `Last30`）

乐天要求 **按商品** 报表的起止须落在**同一自然月**内。若业务要 **滚动近 30 日**、**自定义起止**等导致**跨月**（例如 `2026-03-12`～`2026-04-09`），按下面顺序执行即可，无需另找专用合并脚本。

1. **按月切段拉取**：对每个自然月各执行一次 `ziniao rakuten rpp-search-item`，`-V start_date` / `end_date` 分别取该月内与目标区间相交的片段（上一月尾段 + 下一月首段等）。每段仍可用 `--all` 分页。  
2. **合并 JSON**：使用 **`merge_rpp_search_json.py`**，按**时间顺序**传入各段文件。该脚本与 `rpp-search`（按日/按计划）共用同一结构：拼接根对象下的 **`data.rppReports`**，因此**同样适用于 `rpp-search-item` 的落盘文件**。  
3. **汇总**：将合并产物（建议命名如 `rpp_item_merged.json`）放入本批 **`batch_<起>_<止>/`** 目录；若目录内同时保留未合并的分段文件，请将分段文件改名为 **`_` 前缀**（如 `_rpp_item_mar.json`），避免 `aggregate_ad_exports.py -d` 对同一批 **重复统计**。亦可仅用 **显式文件列表**调用 aggregate，只列入合并后的一个 `rpp_item` 文件。  
4. **解读 `summary`**：`aggregate_ad_exports.py` 对 `rpp_item` 按 **行**汇总：合并后 **全表合计**（总花费、总 720H GMS 等）与跨月业务区间一致。若同一 SKU 在两个月各有一行，**Top/头尾榜单**中可能出现**同一标识多行**（分段各一行）；需要「按 SKU 唯一一行」的排行时，请在表外对 `itemUrl` / `itemMngId` 再做透视合并。  

**与 `run_ad_batch.ps1` 的关系**：脚本对 **`rpp-search-item` 只发起单次请求**，区间为解析后的 `start`～`end`。当 `-Range Last30`（或 `Custom`）跨越自然月时，**item 不会自动拆段**；请对上述 item **手工按月补拉并合并**，或改用 **不跨月的区间**（如 `PrevMonth`、当月 `ThisMonth`）做一键批次。同一批次内 **`rpp-search`（按日/按计划）**、**`tda-reports-search-item`**、**券** 等在表内允许更长窗时，仍可按脚本原有单次调用执行。

**合并脚本的触发条件**：① 超出上表窗长；② **`rpp-search-item` 跨自然月**（按月切段 + 本节流程）；③ `cpnadv-performance-retrieve-item` 分页；④ 合规仍失败时再 **7～14 日** 切 `rpp-search` 并合并。

| 脚本 | 作用 |
|------|------|
| `aggregate_ad_exports.py` | 多文件 JSON → 识别类型 → 打印/写出汇总 |
| `merge_rpp_search_json.py` | 按顺序拼接多段 JSON 的 **`data.rppReports`**：适用于 **`rpp-search`**（按日/按计划）与 **`rpp-search-item`**（按商品） |
| `merge_cpnadv_report_json.py` | 拼接 `cpnadv-performance-retrieve-item` 的 `reportDtos` |
| `fetch_rpp_search_slices.ps1` | 按日切片**打印** `rpp-search` 命令（不代执行） |
| `run_ad_batch.ps1` | **一键批次**：按 JST 计算 `Last7` / `Last30` / `ThisMonth` / `PrevMonth`（或 `Custom`），按 **A～G** 字母组合串行 `ziniao rakuten … -o`，默认再跑 `aggregate_ad_exports.py` |

## 批次隔离（避免多批混算）

`-d <目录>` 会读取该目录下**一层**内所有 `*.json`（**不递归子文件夹**）；**排除**文件名以 `_` 开头的文件（如 `_old_rpp.json`）。

| 做法 | 说明 |
|------|------|
| **推荐** | 每批建专用目录：`exports/<店>/batch_<start>_<end>/`，本批全部 `-o` 与 `merge_*` 输出放此目录，再 `aggregate_ad_exports.py -d <该目录> -o <该目录>/summary.json`。 |
| **显式文件** | 不扫目录：`python .../aggregate_ad_exports.py file1.json file2.json -o summary.json`（仅处理列出的文件）。 |
| **归档** | 旧批整夹移走，或将旧文件改名为 `_…` 前缀，避免误入 `-d exports` 根目录扫描。 |

**反例**：在扁平 `exports/` 多次拉数后执行 `-d exports`，会把**所有历史 JSON** 一起汇总，结论不可用于「单批决策」。

## aggregate_ad_exports.py

**类型识别**（`data.*` 优先于顶层）：

| 类型 | 判定 | 输出要点 |
|------|------|----------|
| rpp_item | `rppReports` 行含 `itemUrl` | SKU 花费 Top、720H `gms/spend` 头尾部、合计 |
| rpp_daily | `rppReports` 含 `effectDate`、无计划字段 | 区间合计、高花费日 |
| rpp_campaign | 含 `campaignName` 或 `rppCampaignId` | 按计划聚合花费/点击/720H |
| tda_item | `tdaReports` | 按计划汇总花费与 `vtCvAmount` |
| cpnadv_shop | 顶层 `reportDtos`、无 `itemMngId` | `adFee` / `useCount` 等加总 |
| cpnadv_item | `reportDtos` 含 `itemMngId` | 按 SKU 合并券费、720H gms/cv、Top |
| cpa_billing | `data.billingReports` | `advertisingFees`、`sales` 合计 |

`-d`：仅该目录**非递归**；跳过 `_*.json`（见上节 **批次隔离**）。

**衍生比**：RPP `type720H.gms ÷ adSalesBeforeDiscount` → `ratio720`；cpnadv 按商品 `gmsShopXDevice720h ÷ adFee`；CPA `sales ÷ advertisingFees`。

```powershell
$batch = "exports/myshop/batch_2026-03-11_2026-04-09"
python .cursor/skills/rakuten-ad-reports/scripts/aggregate_ad_exports.py -d $batch -o "$batch/summary.json"

python .cursor/skills/rakuten-ad-reports/scripts/aggregate_ad_exports.py "$batch/rpp_daily.json" "$batch/rpp_item_merged.json" "$batch/tda_item.json" -o "$batch/summary.json"
```

## merge_rpp_search_json.py

按**文件顺序**拼接 `data.rppReports`。下游 **`aggregate_ad_exports.py`** 根据首行字段识别 **按日**、**按计划** 或 **按商品**（含 `itemUrl` 即为 `rpp_item`），无需更换合并命令。

**`rpp-search-item` 跨月示例**（先按月各落一盘，再合并为一文件供汇总）：

```powershell
$batch = "exports/myshop/batch_2026-03-12_2026-04-09"
python .cursor/skills/rakuten-ad-reports/scripts/merge_rpp_search_json.py `
  -o "$batch/rpp_item_merged.json" `
  "$batch/_rpp_item_202603.json" `
  "$batch/_rpp_item_202604.json"
```

单一路径、多段 `rpp-search`（按日/按计划）切片时用法相同，仅输入文件不同。

## merge_cpnadv_report_json.py

按页 `-o` 后按顺序拼接 `reportDtos`。

```powershell
python .cursor/skills/rakuten-ad-reports/scripts/merge_cpnadv_report_json.py -o exports/cpnadv_all.json exports/p0.json exports/p1.json
```

## run_ad_batch.ps1

在**已登录 RMS** 的 shell 中执行；`-SkipCpnadv` 可跳过券拉取。**D（Expert）/ H / I / J** 仍须按 `SKILL.md` 手工或补参（脚本内会 `Write-Warning` 提示）。

**`Last30` / `Custom` 跨自然月**：`rpp-search-item` 见上文 **「跨自然月：标准流程」**；本脚本**不会**自动拆分 item，跨月时请补拉分段并 `merge_rpp_search_json.py` 后再汇总。

```powershell
# 近 7 日 + A+C 组合（与技能菜单 A、C 对齐）
.\.cursor\skills\rakuten-ad-reports\scripts\run_ad_batch.ps1 -Range Last7 -Pack AC

# 本月（JST）+ 指定店铺子目录
.\.cursor\skills\rakuten-ad-reports\scripts\run_ad_batch.ps1 -Range ThisMonth -Pack A -SiteSlug myshop

# 仅打印命令
.\.cursor\skills\rakuten-ad-reports\scripts\run_ad_batch.ps1 -Range Last30 -Pack B -DryRun
```

## fetch_rpp_search_slices.ps1

仅输出可粘贴的 `ziniao` 行；须已满足上表 **3 个月 / end 非当日**；`selection_type=2` 仍异常时缩短 `ChunkDays` 或核对 RPP 标签页。

```powershell
.\.cursor\skills\rakuten-ad-reports\scripts\fetch_rpp_search_slices.ps1 -StartDate 2026-03-11 -EndDate 2026-04-09 -SelectionType 2 -ChunkDays 7
```

## 运行环境

本地读写、无网络；Python 标准库；`fetch_rpp_search_slices.ps1` 需 PowerShell 5.1+。

## 脚本与汇总约定（与 SKILL 一致）

- **汇总**：店侧/批次汇总 **必须** 使用 `scripts/aggregate_ad_exports.py`；**按批次目录或显式文件列表**调用，勿对扁平 `exports/` 一刀切 `-d` 混入历史。勿在业务目录写一次性汇总脚本。  
- **合并**：接口超窗、`rpp-search-item` **跨自然月**、或券分页需要时，用 `merge_rpp_search_json.py` / `merge_cpnadv_report_json.py`，产出放入**同一批次目录**后再汇总；item 跨月合并后注意 **`_` 前缀**或显式文件列表，避免分段与合并件重复计入。  
- **路径**：工作区根下脚本路径：`.cursor/skills/rakuten-ad-reports/scripts/aggregate_ad_exports.py`（以本仓库为准）。
