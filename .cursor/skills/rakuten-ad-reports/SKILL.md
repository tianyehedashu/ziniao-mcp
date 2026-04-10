---
name: rakuten-ad-reports
description: 乐天 RMS 广告数据与决策：选项化菜单（复盘、SKU 加减投、RPP 日/计划/商品体检、Expert、CPA、券、DEAL、邮件、购入、联盟、策略清单）。触发词：乐天广告、RPP、TDA、ROAS、优惠券、DEAL、联盟、购入明细、广告复盘。
allowed-tools: Bash(ziniao:*)
---

# 乐天 RMS 广告报表

`ziniao rakuten <子命令>`：在已登录 RMS 的浏览器会话中请求后台接口，拉取 JSON/HTML/CSV。

**Expert（エキスパート）**：乐天广告后台的增强型报表产品线，与标准 RPP/TDA 报表并列；域名与路径里常见 `rppexp`、`tdaexp`，子命令对应 **`rpp-exp-*`**、**`tda-exp-*`**（须传 `shop_url`）。**RPP-EXP** = 检索型广告的 Expert 版，**TDA-EXP** = 展示型广告的 Expert 版。

## 前提

1. 已 `open-store` / `launch` 并登录 RMS。  
2. 活动标签在 `ad.rms.rakuten.co.jp` 等对应域（preset 会 `navigate_url`）。  
3. `ad.*` 多数走 XSRF（Cookie 自动注入）；`auto-rmail` / `datatool` / `afl` 走 Cookie。  
4. **`cpnadv-*`**：前置条件与异常响应判定见下文 **速查表 · 子命令附注** 中 **`cpnadv-performance-retrieve`** 条目。

## 业务能力菜单（默认以选项呈现给用户）

### Agent 输出规范（必遵守）

1. **首次响应**（用户只说「乐天广告 / 拉报表 / 帮我看广告」等模糊需求时）：先给出下方 **A～K 编号菜单**，每项一行：**编号 + 短标题 + 一句业务价值**，末尾写「请回复 **编号**（可多项，如 `A+C`），并说明**统计区间**（起止日期或最近几周/几月）。」  
2. **用户已点选编号**：再追问仅缺信息（主要是**日期区间**、是否要**按商品**、是否要看 **Expert**）；然后执行拉数并给出**业务结论**（预算建议、SKU 清单、风险点），避免堆砌技术细节。  
3. **用户已说清目标**（例如「上周 RPP 按商品复盘」）：可跳过菜单，直接执行并回报结论。

### 可选业务能力一览（对用户展示的选项文案）

| 编号 | 用户看到的名称（示例） | 能完成的具体业务 | 业务价值 |
|------|------------------------|------------------|----------|
| **A** | 周/月广告总复盘包 | 同一区间内**检索广告（RPP）+ 展示广告（TDA）+ 运用型优惠券**拉齐对照 | 看清钱花在哪类渠道、哪块更划算，直接支撑**下周预算表**与开会材料 |
| **B** | 按商品找「加投 / 减投」名单 | RPP、TDA 各自**按 SKU** 的表现排行与尾部拖累 | 把预算集中到**爆款与高 ROAS 品**，砍掉或收缩**长期吃预算不产出**的 SKU |
| **C** | 日 / 计划 / 商品体检（RPP） | **日、计划** 用 **`rpp-search`**（`selection_type` 1/2）；**按商品** 必须用 **`rpp-search-item`**（勿用 `rpp-search` + `selection_type=3` 替代，见附注） | 定位异常波动、计划结构问题与**拖后腿 SKU**；**搜索词/否词**在 RMS 后台处理 |
| **D** | Expert 深度报表（检索/展示） | RPP-EXP、TDA-EXP 店铺级与**按商品**趋势、分页拉全 | 适合**周报/月报**与老板视角：趋势、聚合周期对比，比单日截图更稳 |
| **E** | 成交成本与广告交叉核对 | CPA 报表与广告花费、订单对照 | 避免「点击很多却不赚钱」**误判为投放问题**，实为落地页或类目转化 |
| **F** | 优惠券与广告是否「打架」 | 优惠券整体 + **按商品** 与广告同期对比 | 防止**券把利润吃光**还误以为广告很成功；决定减券、收窄适用 SKU 或调整广告节奏 |
| **G** | DEAL 活动值不值 | DEAL 导出与同期广告数据对照 | 判断**报名 DEAL 是否带来净增量**，避免只为报表好看续报亏损活动 |
| **H** | 邮件（R-Mail）与广告节奏 | R-Mail 报告与广告高峰对照 | **错峰或统一主题**，减少顾客疲劳，分清邮件带来的量与广告带来的量 |
| **I** | 月度广告购入与结构 | 广告购入明细（按月） | **财务对账、费用结构**、大促月与平月对比，支撑现金流与采购节奏 |
| **J** | 联盟待结算跟进 | 联盟 pending | **回款预期、异常单**清理，避免 pending 堆积影响资金计划 |
| **K** | 历史策略解读与行动清单 | 在已有或刚拉取的数据上，按本 Skill「运营策略」节输出 | 把数据落成**可执行三件事**（加预算/减预算/改商品），减少「有数没结论」 |

**组合建议**：日常 **A+B**；大促前后 **C**；汇报 **D**；让利异常 **F**；对账 **I**；联盟 **J**。

### 编号与数据来源对应（Agent 执行用；对用户的回复里不必展开命令）

| 编号 | 主要 `ziniao rakuten` 子命令 |
|------|------------------------------|
| A | `rpp-search-item`、`tda-reports-search-item`、`cpnadv-performance-retrieve`（按需 `…-item` 与分页） |
| B | 同 A，以 item 报表为主 |
| C | **`rpp-search`**（`selection_type`：**1 日 / 2 计划**）+ **`rpp-search-item`**（**按商品**；勿单用 `rpp-search` + `selection_type=3`） |
| D | `rpp-exp-merchant` → `rpp-exp-report` / `rpp-exp-report-item`、`tda-exp-report` / `tda-exp-report-item` |
| E | `cpa-reports-search`，与 A/B 数据对照 |
| F | `cpnadv-performance-retrieve`、`cpnadv-performance-retrieve-item`，与 A/B 同区间 |
| G | `datatool-deal-csv`，与 A/B 同区间对照 |
| H | `rmail-reports`，与按日 `rpp-search` 等对照 |
| I | `shared-purchase-detail` |
| J | `afl-report-pending` |
| K | 不单独对应命令；基于已拉数据 + 下文「基于历史广告数据的运营策略」产出结论 |

### 用户可说的极简话术（仍触发选项）

- 「乐天广告帮我看看」→ Agent 先输出 **A～K 菜单**。  
- 「只要按商品谁该加投」→ 对应 **B**（可再问日期）。  
- 「券和广告一起复盘」→ **A** 或 **F**（Agent 确认是否要商品维度）。

具体拉数用的子命令、参数与运营策略细节见下文 **速查表**（含 **子命令附注**）、**常用命令与附注**、**基于历史广告数据的运营策略**。

## 速查表

通用：`-V key=value`、`-o` 落盘、`--json`。

| # | 子命令 | 说明 |
|---|--------|------|
| 1 | `rpp-search` | 检索型广告（RPP），默认店铺侧汇总；**按日/按计划** 用 `selection_type` 1/2（**按商品见 #1′**） |
| 1′ | `rpp-search-item` | RPP **按商品** 的正式入口；**`--all`**（勿用 `#1` + `selection_type=3` 替代） |
| 2 | `rpp-exp-report` | RPP-EXP 报表；**`shop_url`** |
| 2′ | `rpp-exp-report-item` | RPP-EXP 按商品 |
| 2补 | `rpp-exp-merchant` | 当前店 `shopUrl` 等（**不要** `shop_url`） |
| 3 | `cpa-reports-search` | CPA |
| 4 | `cpnadv-performance-retrieve` | 运用型优惠券 |
| 4′ | `cpnadv-performance-retrieve-item` | 同上按商品；表单；`-V page=` |
| 5 | `tda-reports-search` | 定向展示（TDA） |
| 5′ | `tda-reports-search-item` | TDA 按商品（默认参数对齐后台按商品视图） |
| 6 | `tda-exp-report` | TDA-EXP；**`shop_url`** |
| 6′ | `tda-exp-report-item` | TDA-EXP 按商品 |
| 7 | `rmail-reports` | R-Mail（HTML） |
| 8 | `datatool-deal-csv` | DEAL CSV |
| 9 | `shared-purchase-detail` | 广告购入明细 |
| 10 | `afl-report-pending` | 联盟 pending |

列 **#** 仅内部对照；以 `ziniao site list` / `rakuten --help` 为准。

### 子命令附注（约束、异常处置、示例）

以下与上表 **子命令名** 一一对应；Agent 执行时**优先查阅对应命令本节**，再调用通用日期口径（见 **「广告报表的日期区间」**）。

#### `rpp-search`（表 `#1`）

- **按商品（SKU）维度**：凡需要 **RPP 按商品** 列表、排行、加减投 SKU 等，**一律使用 `rpp-search-item`**（见表 `#1′`）。**不要**仅用 **`rpp-search -V selection_type=3`** 充当按商品主数据源：与请求体中的 **`periodType=2`** 等组合时易与乐天侧约定冲突，接口常返回 **`TODO`**（无效或未支持组合），表现为拉数失败、空表或不可解析占位，**不可靠**。
- **参数**：`selection_type` — **1 按日 / 2 按计划**；`3` 在本文档中**不推荐**用于生产拉数（按商品请用 **`rpp-search-item`**）。另有 `campaign_type`（完整枚举以 `ziniao rakuten rpp-search --help` 为准）。**本 Skill 不约定通过 ziniao 拉取「按关键词」维度的 RPP 报表**；关键词级导出、否词与出价调整在 **RMS 检索广告后台**完成。  
- **`selection_type=2`（按计划）**：返回体常为 **「计划 × 日」多行明细**，汇总时需按 `campaignName`（及业务所需其它键）**二次聚合**，勿将单行误认为单计划全期总计。  
- **按日（`selection_type=1`）**：单次请求跨度过大（实测约 **25～30** 自然日易触发）时，接口可能返回「リクエストは正常に処理できませんでした」类提示。处置：**拆分为 7～14 自然日**子区间分别 `-o` 落盘，离线合并；必要时先用短区间验证会话与 preset。  
- **结束日**：相对 `rpp-search-item` 通常**允许 `end_date` 取 JST 当日**；若与 `rpp-search-item` 等同批次复盘，建议仍统一为 **「至前一自然日」闭区间**，避免口径错位。

近 7 日、**结束日可为本地当日**（生产请按 **JST** 换算；起始日 = 当日 − 6 日）：

```powershell
$end = Get-Date -Format 'yyyy-MM-dd'
$start = (Get-Date).AddDays(-6).ToString('yyyy-MM-dd')
ziniao rakuten rpp-search -V start_date=$start -V end_date=$end --all
```

#### `rpp-search-item`（表 `#1′`）

- **定位**：**RPP 按商品** 的**唯一推荐** ziniao 子命令；与 **`rpp-search` + `selection_type=3`** 不等价，后者易与 **`periodType=2`** 冲突导致乐天返回 **`TODO`**（见 **`rpp-search`** 附注）。
- **`end_date` 禁止取 JST 当日**：否则常见业务错误 JSON：`集計期間の条件を正しく指定してください。`  
- **Agent**：用户表述「截至今日」「包含今天」时，**`end_date` 一律取前一自然日**（`today(JST) − 1`），并在交付说明中**标明统计截止日**（如「数据截至 JST 前一自然日」）。  
- **仍失败时**：在调整 `end_date` 后，可再按 **7～14 自然日**窗口分段拉取并合并。  
- **近三十日（与 item 口径对齐）**：`end_date` = **JST 前一自然日**，`start_date` = 该日向前 **29** 日（闭区间约 30 自然日）。若同区间 **`rpp-search` 按日**仍失败，按 **周或双周**切片多次落盘后合并。

近 7 日、**满足 item 结束日约束**（`end_date` = 本地**昨日**，`start_date` = 本地今日 − 7 日；生产请按 **JST**）：

```powershell
$end = (Get-Date).AddDays(-1).ToString('yyyy-MM-dd')
$start = (Get-Date).AddDays(-7).ToString('yyyy-MM-dd')
ziniao rakuten rpp-search-item -V start_date=$start -V end_date=$end --all
```

#### `cpnadv-performance-retrieve` / `cpnadv-performance-retrieve-item`（表 `#4` / `#4′`）

- **浏览器上下文**：执行前须将活动标签页置于 **運用型クーポン広告**（`/cpnadv/`），并确认页面可正常渲染、无系统错误提示。仅在 RPP 等其它模块标签页调用时，响应体常被重写为 **整页 HTML**（如「システムエラー」「ユーザー情報が正しく取得できない」），**非 JSON**。  
- **成功判定**：落盘内容为 **JSON**（含结构化 `errors` 亦为 JSON）；若以 `<!DOCTYPE html>` 起首，即视为本次拉取失败，应先完成登录与页面导航后重试。  
- **分页**：可使用 `--all` 或 `-V page=`（item 变体同）。

#### `tda-reports-search-item`（表 `#5′`）

- 支持 **`--all`** 合并分页；`start_date` / `end_date` 口径同 **「广告报表的日期区间」**（JST 自然日、`YYYY-MM-DD`）。

#### 通用：极小响应体与 `"errors"`

- 若文件体积极小（约数十～数百字节）且含 `"errors"`：多为会话失效、XSRF、域名或参数不符合 preset。**核对 `ad.rms.rakuten.co.jp` 登录与活动标签**；并对照本条以上各命令附注逐项排查。

### 按商品（`*-item`）一行例

**`rpp-search-item` / `cpnadv-*`** 的结束日与浏览器上下文等约束，以 **上文「子命令附注」对应条目** 为准（勿仅照抄下列日期）。

```powershell
ziniao rakuten rpp-search-item -V start_date=2026-03-01 -V end_date=2026-03-31 --all
ziniao rakuten cpnadv-performance-retrieve-item -V start_date=2026-03-01 -V end_date=2026-03-07 -V page=0
ziniao rakuten tda-reports-search-item -V start_date=2026-03-01 -V end_date=2026-03-07
ziniao rakuten rpp-exp-report-item -V start_date=2026-03-01 -V end_date=2026-03-05 -V shop_url=<slug>
ziniao rakuten tda-exp-report-item -V start_date=2026-03-01 -V end_date=2026-03-05 -V shop_url=<slug>
# 可选 -V search_product_name=
```


## 广告报表的日期区间

**通用口径**（各命令**专项约束**见上文 **速查表 · 子命令附注**）：

- **广告类子命令**（`rpp-search`、`cpnadv-*`、`tda-*`、`*-exp-*` 等）不提供 `last_days`，须由调用方计算 **`start_date` / `end_date`**（`YYYY-MM-DD`）并经 `-V` 传入。  
- 区间一般为 **起止自然日均闭合**；日界以 **RMS / 日本时间（JST）** 为准。运行环境与 JST 不一致时，须在脚本中 **显式换算** 后再传参。

仅 **JST 前一自然日** 单日（常用于监控；**`rpp-search`**）：

```powershell
$d = (Get-Date).AddDays(-1).ToString('yyyy-MM-dd')
ziniao rakuten rpp-search -V start_date=$d -V end_date=$d --all
```

`datatool-deal-csv` 使用 **无横杠** `YYYYMMDD`。若已有 `$start`/`$end`（`yyyy-MM-dd`），可先转换再传参：

```powershell
$dealStart = $start.Replace('-', '')
$dealEnd = $end.Replace('-', '')
ziniao rakuten datatool-deal-csv -V start_date=$dealStart -V end_date=$dealEnd -V period=daily
```

## 常用命令与附注

下列示例中的日期、`shop_url`、店铺标识等 **仅作占位**，执行前须替换为实际值。 **`rpp-search` / `rpp-search-item` / `cpnadv-*` 的专项约束** 见 **速查表 · 子命令附注**。

### `rpp-search`

标准 RPP 汇总与下钻（`selection_type`：**日 / 计划**；**按商品请用 `rpp-search-item`**，勿依赖 `selection_type=3`，见附注）。大跨度 **按日** 请求须分段，见附注。

```powershell
ziniao rakuten rpp-search -V start_date=2026-03-01 -V end_date=2026-03-31 --all
```

### `rpp-search-item`

RPP **按商品**（**正式入口**；勿用 `rpp-search` + `selection_type=3` 替代）；全量分页请使用 `--all`。**`end_date` 不得取 JST 当日**，见附注。

```powershell
ziniao rakuten rpp-search-item -V start_date=2026-03-01 -V end_date=2026-03-31 --all
```

### `rpp-exp-merchant`

获取当前会话店铺的 `shopUrl` 等，供 Expert 报表 **`shop_url`** 传参；输出建议配合 `--json` 解析。

```powershell
ziniao --json rakuten rpp-exp-merchant
```

### `rpp-exp-report` / `rpp-exp-report-item`

RPP Expert（须 **`shop_url`**）；按店或按商品趋势、分页参数见 `ziniao rakuten rpp-exp-report --help`。

```powershell
ziniao rakuten rpp-exp-report -V start_date=2026-03-01 -V end_date=2026-03-31 -V shop_url=<slug>
ziniao rakuten rpp-exp-report-item -V start_date=2026-03-01 -V end_date=2026-03-05 -V shop_url=<slug>
```

### `cpa-reports-search`

CPA 报表；与 RPP/TDA 同区间对照时使用。

```powershell
ziniao rakuten cpa-reports-search -V start_date=2026-03-01 -V end_date=2026-03-31
```

### `cpnadv-performance-retrieve` / `cpnadv-performance-retrieve-item`

运用型优惠券效果；**须先处于 `/cpnadv/` 浏览器上下文**，见附注。分页可用 `--all` 或 `-V page=`。

```powershell
ziniao rakuten cpnadv-performance-retrieve -V start_date=2026-03-01 -V end_date=2026-03-29 -V page=0
ziniao rakuten cpnadv-performance-retrieve-item -V start_date=2026-03-01 -V end_date=2026-03-29 -V page=0
```

### `tda-reports-search` / `tda-reports-search-item`

定向展示（TDA）标准报表；按商品视图支持 `--all`。

```powershell
ziniao rakuten tda-reports-search -V start_date=2026-03-01 -V end_date=2026-03-05
ziniao rakuten tda-reports-search-item -V start_date=2026-03-01 -V end_date=2026-03-05
```

### `tda-exp-report` / `tda-exp-report-item`

TDA Expert（须 **`shop_url`**）。

```powershell
ziniao rakuten tda-exp-report -V start_date=2026-03-01 -V end_date=2026-03-05 -V shop_url=<slug>
ziniao rakuten tda-exp-report-item -V start_date=2026-03-01 -V end_date=2026-03-05 -V shop_url=<slug>
```

### `rmail-reports`

R-Mail 报表页，响应体多为 HTML，建议 `-o` 落盘后再做离线解析。

```powershell
ziniao rakuten rmail-reports
```

### `datatool-deal-csv`

DEAL 导出；日期为 **`YYYYMMDD`**，与广告类 `YYYY-MM-DD` 口径不同。

```powershell
ziniao rakuten datatool-deal-csv -V start_date=20260301 -V end_date=20260331 -V period=daily
```

### `shared-purchase-detail` / `afl-report-pending`

按月维度：`target_month` / `date` 格式 **`YYYY-MM`**。

```powershell
ziniao rakuten shared-purchase-detail -V target_month=2026-03
ziniao rakuten afl-report-pending -V date=2026-03
```

**其余参数**：`rpp-exp-report` / `tda-exp-report` 支持 `page_no`、`page_size`、`aggregation_period`；`*-exp-report-item` 支持 `search_product_name` 等，以 `--help` 为准。

## 典型流程

```powershell
ziniao open-store rakuten-shop-001
ziniao rakuten rpp-search -V start_date=2026-03-01 -V end_date=2026-03-31 --all -o rpp.json
ziniao rakuten rpp-search-item -V start_date=2026-03-01 -V end_date=2026-03-31 --all -o rpp_item.json
ziniao --json rakuten rpp-exp-merchant
ziniao rakuten rpp-exp-report -V start_date=2026-03-01 -V end_date=2026-03-05 -V shop_url=<slug>
ziniao rakuten rpp-exp-report-item -V start_date=2026-03-01 -V end_date=2026-03-05 -V shop_url=<slug>
```

## 基于历史广告数据的运营策略

以下与上文 **同一套 ziniao 拉数能力** 衔接：先把**同一店铺、同一日期区间**的多份报表落盘，再在表外做透视与决策。具体字段名以各接口返回 JSON 为准；策略是**框架**，需结合品类、客单、库存与乐天活动规则裁剪。

**推荐最小分析包（每周或每月固定跑一遍）**：`rpp-search-item` + `tda-reports-search-item` + `cpnadv-performance-retrieve`（或 item）+ 视需要 `rpp-exp-report` / `tda-exp-report`；大促周加拉 **日粒度** `rpp-search`（`selection_type` 按日）；月末加 `shared-purchase-detail`；用 DEAL 时加 `datatool-deal-csv`。

### 数据与报表分工（拉什么、回答什么问题）

| 目的 | 建议报表 / 子命令 | 典型用途 |
|------|-------------------|----------|
| 搜索意图与计划/商品效率 | **`rpp-search`**（`selection_type`：**日/计划**）+ **`rpp-search-item`**（**按商品**；勿单用 `rpp-search` + `selection_type=3`） | 预算向高转化计划与 SKU 倾斜；长尾词与否词在 RMS 侧维护 |
| Expert 细粒度与多周期趋势 | `rpp-exp-report`、`rpp-exp-report-item`、`tda-exp-report`、`tda-exp-report-item`（`aggregation_period`、`page_no`/`page_size`） | 周报/月报；分页拉全量后算 ROAS、环比 |
| 展示触达与商品侧表现 | `tda-reports-search`、`tda-reports-search-item` | 素材/定向迭代；与 RPP 对照看「搜」与「展」占比 |
| 成交成本结构 | `cpa-reports-search` | 与 RPP/TDA 花费、订单对照，避免单一报表误判 |
| 优惠券叠加 | `cpnadv-performance-retrieve`、`cpnadv-performance-retrieve-item` | 与广告同区间对比：是否券抢归因、毛利是否合算 |
| DEAL 活动 | `datatool-deal-csv` | DEAL 期间拉齐 `YYYYMMDD` 区间，和广告报表对照看增量与费比 |
| 月度广告侧购入结构 | `shared-purchase-detail`（`target_month`） | 财务/对账口径；与大促月对比 |
| 联盟结算 | `afl-report-pending` | pending 清理、异常跟踪 |
| 邮件触达 | `rmail-reports` | 与广告排期协同或错峰，避免同一人群过度轰炸 |

`rpp-exp-merchant` 用于确认 **`shop_url`**，保证 Expert 与店铺上下文一致。

**按子命令再细一层（落地时怎么用）**

- **`rpp-search`**：先看店铺或计划侧汇总，再以 `selection_type` 在 **日 / 计划** 间下钻。**日粒度**适用于大促、改价、改标题后的短周期波动；**计划粒度**用于预算集中度与计划结构。**按商品** 请用 **`rpp-search-item`**，勿用 `selection_type=3`（易与 **`periodType=2`** 冲突，乐天返回 **`TODO`**）。**关键词级**分析、否词与出价细则在 **RMS 检索广告后台**完成，本 Skill 不通过 ziniao 约定该维度拉数。  
- **`rpp-search-item`**：以 SKU 为单位的「花费—销售额—订单」效率表，适合做 **ABC 分层**（见下）与备货联动；务必 `--all` 拉全以免截断长尾。  
- **`*-exp-report*`**：标准报表不够用时，用 Expert 做 **分页全量**（`page_no`/`page_size`）与 **聚合周期**（`aggregation_period`）趋势；按商品的 `search_product_name` 适合盯爆款或问题款。  
- **`tda-reports-search` / `tda-reports-search-item`**：重点看展示类渠道的 **CTR、CPC、转化效率** 与 RPP 的差异；商品维度用于判断「适合展示引流的 SKU」与「只适合搜索的 SKU」。  
- **`cpa-reports-search`**：当 RPP/TDA 显示「点击多、订单少」时，用 CPA 视角核对是否 **落地页或类目** 导致转化断层。  
- **`cpnadv-performance-retrieve(-item)`**：按商品看 **券带来的流量/成交** 是否侵蚀广告效率；item 版配合 `-V page=` 翻页拉全。  
- **`datatool-deal-csv`**：DEAL 报名前后各拉一段 **对称区间**（如前后各 14 天），与广告报表同区间对比，避免把自然大促增量误归为 DEAL。  
- **`shared-purchase-detail`**：按月对齐 **财务复盘**；与广告 JSON 中的花费字段对照，检查是否有异常月份需人工核对账单。  
- **`afl-report-pending`**：列出待结算联盟单；与店铺运营活动对照，识别异常高峰或规则变更影响。  
- **`rmail-reports`**：保存 HTML 后关注发送窗口与活动重叠度；与 `rpp-search` 按日对照，判断邮件是否挤压或放大广告高峰。

### 分析前提（避免误判）

1. **区间对齐**：广告类统一 `YYYY-MM-DD`；DEAL 用无横杠日期；购入/联盟用月维度。对比 RPP、TDA、优惠券时**起止日期必须一致**。  
2. **时区与日界**：乐天报表日界多为 **日本时间自然日**；若在海外办公，生成 `start_date`/`end_date` 时避免用本地自然日硬套。  
3. **样本量**：过短区间（例如单日）易受大促、库存、异常点击干扰；常规调参至少 **7 天滑动**或完整自然周；**大促单独切片**（节前 3～7 天、节中、节后 3～7 天）再与「平销周」对比。  
4. **归因边界**：报表反映的是**广告体系内指标**，不是店铺整体 GMV；与自然流量、SEO、店外引流叠加时要留解释空间。  
5. **延迟与修订**：成交类指标常有 **回写延迟**；大促后复盘宜在结束后 **再等 2～3 个自然日**拉数，减少订单回补造成的假象。  
6. **同比/环比**：同比看节气与大促（楽天セール等），环比看上周调参是否生效；**不要**拿大促周与平销周直接比 ROAS 绝对值。  
7. **成本与毛利**：ROAS/CPA 优秀但若叠加高额优惠券或低毛利 SKU，仍需用内部毛利表二次过滤。  
8. **异常值**：单日花费或点击暴增时，先排除 **误操作预算、爬虫/异常流量、追踪故障**，再改策略。

### 指标阅读（通用）

在落盘 JSON 中优先构造（或脚本聚合）这些衍生量（分母为 0 时跳过）：

- **CTR** = 点击 / 展示；**CPC** = 花费 / 点击；**CPM** = 花费 / 展示 × 1000（衡量展示类「买量贵贱」）。  
- **CVR（点击→订单）** = 订单数 / 点击（字段名以实际 JSON 为准），区分「流量质量差」与「落地页/商详差」。  
- **ROAS** = 广告归因销售额 / 广告花费（或店铺内统一口径的「成效金额/成本」）。  
- **单订单广告成本** = 花费 / 订单数；与 `cpa-reports-search` 交叉验证。  
- **件单价 / 客单价** = 销售额 / 订单数，用于识别「低价引流款」是否拉低利润。  
- **渠道份额**：同一 SKU 在 **RPP vs TDA** 上的花费占比、销售额占比，用于决定渠道组合，而非只看单一 ROAS。

**分层与排序（可操作）**

- **ABC（帕累托）**：按销售额或毛利贡献排序 SKU，通常 **少数 A 类占大头**；预算优先保障 A 类库存与曝光，B 类测试放量，C 类长尾限制出价或合并计划。  
- **四象限（示例轴）**：横轴花费、纵轴 ROAS（或销售额）：高花费高 ROAS → 加码但盯库存；高花费低 ROAS → 先诊断再减投；低花费高 ROAS → 放量试探天花板；低花费低 ROAS → 观察或淘汰。  
- **最小数据门槛**：再小的计划/词也要满足「足够点击或足够花费」再判死刑；可自定店内规则：**至少 N 次点击或 M 日元花费** 仍无转化再否词/暂停。

按 **SKU / 计划 / 词 / 创意** 聚合后再排序，比只看店铺汇总更能指导调价与下架。

### 常见症状 → 数据下钻 → 运营动作（诊断清单）

| 现象 | 优先拉取的数 | 可能原因与动作方向 |
|------|----------------|-------------------|
| 花费暴涨、订单不涨 | 日粒度 `rpp-search`，并下钻至 **计划**；**商品** 侧用 `rpp-search-item`；对照 `tda-reports-search`；词面问题结合 **RMS 关键词报表** | 误提预算、匹配过宽、竞品抬价；否词/收窄匹配/限计划预算 |
| 展示骤降、花费萎缩 | 同上 + 核对商品 **下架/缺货/违规**；结合店内**评价与客诉**是否异常 | 恢复库存与链接；修正主图/标题违规；必要时重建计划 |
| CTR 高、CVR 低 | `rpp-search-item` + 店内价/配送 + **商详与评价反馈** | 价不配、图骗点击、配送 SLA 差；优化主图与价梯、缩短发货 |
| CTR 低、展示正常 | **`rpp-search-item`**（商品）与 **`rpp-search`**（计划）；`tda` 换素材；搜索侧配合 **RMS 词报表** | 意图不匹配或素材疲劳；换主图、改卖点、分计划测词 |
| RPP ROAS 好、TDA ROAS 差 | 两渠道按 SKU 拆开 | 展示只保爆款或拉新；其余 SKU 减展示加搜索 |
| 券很猛、广告 ROAS 也「好看」 | `cpnadv-performance-retrieve(-item)` 同区间 + 内部毛利 | 券侵蚀利润；减券或缩 SKU 范围，而非加广告 |
| 大促后 ROAS 断崖 | 节后 **延迟数日**再拉；`rpp-search` 按日 | 延迟归因未回写；或需求透支；调整后续两周预算曲线 |

### 策略矩阵（可组合使用）

**预算与渠道结构**

- 对比 **RPP vs TDA** 同区间 ROAS 与增量：若 TDA ROAS 长期低于阈值且拉新目标已满足，收缩展示预算转投检索或保留给爆款。  
- **RPP-EXP / TDA-EXP** 用 `aggregation_period` 看趋势，避免被单日噪声带偏；月报建议固定周期（如自然月）以便同比。  
- 大促前 **适度预留**预算，大促中用日维度监控；大促后一周做「余波」复盘，避免立刻按峰值定常态预算。  
- **增量测试**：给「待验证渠道或 SKU」设 **独立小预算帽**，用 1～2 周数据决定是否并入主预算池。

**商品与生命周期**

- `rpp-search-item`、`tda-reports-search-item`、`*-exp-report-item` 识别 **头部 SKU**：加预算、加库存、争取更好坑位与素材。  
- 中长期低转化、高花费：**减投、改落地页、或清仓**；避免与优惠券叠成负毛利。  
- 新品：**小预算多计划 A/B**，区间足够长再决定去留；可用 `search_product_name` 聚焦单 SKU 观察。  
- **季节性**：历史按月归档 JSON，做「去年同月」对照，提前 2～4 周调整备货与预售广告。  
- **清仓/停产**：逐步降出价并缩小词面，避免突然停投导致库存积压；同步看 `cpa-reports-search` 与**商详评价、客诉反馈**。

**检索型（RPP）**

- 用 `selection_type` 在 **日 / 计划** 间切换审视波动与结构；**按商品** 用 **`rpp-search-item`**（勿用 `selection_type=3`）；**否词、拓词、词级出价** 在 **RMS 后台**执行与导出。  
- 持续高 CTR 低转化：检查价格、**商详评价**、配送、优惠券是否竞争力不足。  
- **词策略**：品牌词保量保位；品类词设 CPC 上限；泛词单独计划 + 严格否词；定期导出词表做 **词根聚类** 比逐条扫更高效。  
- **计划结构**：避免同一 SKU 多计划互相竞价；合并低效计划，减少学习期碎片化。

**展示型（TDA）**

- 对比不同素材/版位（以后台实际维度为准）的 CTR 与 ROAS；低效素材轮换或下线。  
- 与 RPP 重复触达过高时，考虑频次与人群排除（在 RMS 内操作，非本 skill 命令）。  
- **创意迭代**：一次只改一个变量（主图/文案/落地 SKU），区间对齐前后两周做对照。

**优惠券与广告协同**

- `cpnadv-performance-retrieve(-item)` 与 RPP/TDA **同区间**：若券后 ROAS 虚高、全店毛利差，应降低券力度或收窄券适用 SKU，而非盲目加广告费。  
- 防止「券引来的单」在报表上与广告重复理解：以内部归因规则为准，广告侧只作趋势参考。  
- **节奏**：大促前避免「券+广告」双峰值叠在 **无备货 SKU** 上；大促中用 item 报表看券是否过度集中在少数 SKU。

**DEAL 与邮件**

- `datatool-deal-csv` 覆盖期间单独存档；与广告花费、销售额对比判断 DEAL 是否值得续报。  
- `rmail-reports` 与广告高峰错开或统一主题，减少用户疲劳。  
- **对照**：邮件爆发日与纯广告日分开记录，避免把邮件带来的成交误读为广告 ROAS。

**财务与联盟**

- `shared-purchase-detail` 做 **月度**广告购入与结构复盘；与会计口径对齐。  
- `afl-report-pending` 定期清理，避免 pending 膨胀影响现金流预测。  
- **台账建议**：日期区间、店铺、拉数时间、`ziniao`/preset 版本、原始文件名、是否大促；便于半年后审计与排障。

### 节奏建议（运营日历）

| 频率 | 动作 |
|------|------|
| 每日 | 监控花费突增/暴降、0 展示计划；抽查头部 SKU 是否断货或差评激增；大促日改 **日粒度** 报表 |
| 每周 | 固定区间拉 `rpp-search-item`、`tda-reports-search-item`、必要时 Expert；输出「加减预算清单」「否词/暂停清单」「待测 SKU 清单」 |
| 每月 | `shared-purchase-detail`、联盟 pending、DEAL 月报（若用 DEAL）；定下月渠道预算比例与重点 SKU；做同比/环比一页纸结论 |
| 大促前后 | 单独文件夹存档；节后 **延迟数日**再拉终版 JSON；复盘记录规则变更、库存、竞品动作 |

### 可复现的数据习惯（配合 CLI）

- 目录建议：`exports/<店铺>/<YYYY-MM>/`，文件名 **`报表类型_起止日期.json`**（例如 `rpp_item_20260301_20260331.json`），便于脚本 join。  
- **同一批次**决策使用同一 `start_date`/`end_date` 拉齐 RPP、TDA、优惠券，避免「用两周 RPP 对比一周优惠券」。  
- 需要全量时：`rpp-search` / `rpp-search-item` 用 `--all`；其余按 `page` / `page_no` 分页直至无数据。  
- **元数据**：每次拉数记录命令行（或 shell history）、`ziniao` 版本、是否大促；大文件可选 md5，避免覆盖后扯不清。  
- 大文件用 `jq`、Python pandas 等在仓库外部分析即可；本 skill 不绑定特定 BI 工具。  
- **周报应答三问**：① 本周 ROAS 相对上周，变化主要来自哪些 SKU？② RPP/TDA 花费结构是否更健康？③ 下周唯一要动的 **三件事** 是什么？

## 管理

`ziniao site list` · `site show rakuten/<名>` · `site fork` · `site disable`

## 注意

- **PowerShell**：示例中多条命令请**逐行执行**，或同一行用 **分号 `;`** 串联；**不要**使用 **`&&`**（Windows PowerShell 5.1 不支持；PowerShell 7+ 支持 `&&`，为兼容 5.1 文档统一用分号或换行）。  
- **`shop_url`**：店铺 slug（如 `pettena-collections`）→ 头 `x-shop-url`；不明则先 `rpp-exp-merchant` 读 `result.shopUrl`。  
- **日期口径**：DEAL 使用 `YYYYMMDD`；广告购入、联盟等按月使用 `YYYY-MM`；其余多为 `YYYY-MM-DD`。**`rpp-search-item` 的 `end_date` 等专项规则** 见 **速查表 · 子命令附注 · `rpp-search-item`**。  
- **`--all`**：适用子命令见 **速查表 · 子命令附注**（`rpp-search`、`rpp-search-item`、`tda-reports-search-item`、`cpnadv-performance-retrieve` 等）；其余以 `page` / `page_no` 翻页为准。
