---
name: rakuten-ad-reports
description: 乐天 RMS 广告数据拉取。覆盖 RPP / RPP-EXP（含 merchant 取 shopUrl）/ CPA / 运用型优惠券 / TDA / TDA-EXP / R-Mail / DEAL CSV / 广告购入明细 / 联盟 pending 共 10 个报表接口 + RPP-EXP merchant；另有 **`reviews-csv`**（评论一览 CSV，非广告）。使用 ziniao CLI site preset 在已登录的浏览器会话内调用后台 API。当用户提到乐天广告、Rakuten 报表、RPP、TDA、CPA、DEAL CSV、联盟、R-Mail、广告购入明细、乐天数据导出、**RMS 评论 CSV** 时触发。
allowed-tools: Bash(ziniao:*)
---

# 乐天 RMS 广告报表拉取

通过 `ziniao rakuten <action>` 子命令，在已登录 RMS 的浏览器会话中直接调用后台 API，拉取各类广告报表数据。

## 前提

1. 浏览器已通过 `ziniao open-store <id>` 或 `ziniao launch` 打开并**登录 RMS**。
2. 活跃标签页处于对应子域（`ad.rms.rakuten.co.jp` 等）。preset 会自动 `navigate_url` 跳转到正确页面。
3. `ad.rms.rakuten.co.jp` 系接口使用 XSRF 鉴权（自动从 Cookie 注入）；`auto-rmail` / `datatool` / `afl` 子域使用 Cookie 鉴权。

## 命令速查

所有命令通用选项：`-V key=value`（设置变量，可重复）、`-o file.json`（保存响应）、`--json`（JSON 输出）。

| PRD | 子命令 | 中文名称 |
|-----|--------|----------|
| 1 | `rpp-search` | 检索型广告（搜索广告） |
| 2 | `rpp-exp-report` | RPP 专家版报表 |
| 2 补 | `rpp-exp-merchant` | RPP-EXP 当前店铺信息（`shopUrl` 等） |
| 3 | `cpa-reports-search` | CPA 广告（按转化付费） |
| 4 | `cpnadv-performance-retrieve` | 运用型优惠券效果报表 |
| 5 | `tda-reports-search` | 定向展示广告（TDA） |
| 6 | `tda-exp-report` | TDA 专家版报表 |
| 7 | `rmail-reports` | 邮件营销（R-Mail / 邮件杂志） |
| 8 | `datatool-deal-csv` | DEAL 活动 CSV 下载 |
| 9 | `shared-purchase-detail` | 广告购入历史明细 |
| 10 | `afl-report-pending` | 联盟返利待确认（pending） |

### RMS 评论 CSV（非广告）

```bash
ziniao rakuten reviews-csv -o reviews.csv
# 可选：-V last_days=30（默认，日本时间自然日）或同时 -V start_date= -V end_date= 覆盖
```

预设 **`output_decode_encoding: cp932`**；`-o` 落盘为 UTF-8 文本。详见仓库 **`docs/site-fetch-and-presets.md`**。

### PRD 1 — RPP（检索型広告）｜中文：检索型广告（搜索广告）

```bash
ziniao rakuten rpp-search -V start_date=2026-03-01 -V end_date=2026-03-31
# 支持 --all 自动翻页合并 | --page N 指定页
# 可选 vars: selection_type (1=日别/2=campaign/3=商品/4=关键词), campaign_type
```

### PRD 2 — RPP-EXP（RPP エキスパート）｜中文：RPP 专家版报表

```bash
ziniao rakuten rpp-exp-report -V start_date=2026-03-01 -V end_date=2026-03-31 -V shop_url=your-shop-slug
# 可选 vars: page_no, page_size(默认30), aggregation_period(默认3=自定义)
```

### PRD 2 补 — RPP-EXP merchant｜当前店铺信息（取 `shop_url`）

与页面首屏一致：`GET https://ad.rms.rakuten.co.jp/rppexp/api/core/merchant`（XSRF + Cookie），**不需要** `-V shop_url`。

```bash
ziniao --json rakuten rpp-exp-merchant
# 或保存: ziniao rakuten rpp-exp-merchant -o merchant.json
```

成功响应（`body` 内 JSON）典型结构：

- `code`: `RPPEXP-CORE-API-S000`
- `message`: `Success`
- `result`:
  - `merchantName`：店铺名
  - `shopId`：店铺数字 ID
  - **`shopUrl`**：店铺 slug（填入 `rpp-exp-report` / `tda-exp-report` 的 `-V shop_url=`）
  - `customerId`、`inactiveTime`、`shopStatus`、`rsFlag`

### PRD 3 — CPA｜中文：CPA 广告（按转化付费）

```bash
ziniao rakuten cpa-reports-search -V start_date=2026-03-01 -V end_date=2026-03-31
# 可选 vars: page(默认1), period_type(默认2=自定义)
```

### PRD 4 — 运用型优惠券（運用型クーポン）｜中文：运用型优惠券效果报表

```bash
ziniao rakuten cpnadv-performance-retrieve -V start_date=2026-03-01 -V end_date=2026-03-29
# 可选 vars: page(默认0，0始まり)
# body 为 application/x-www-form-urlencoded
```

### PRD 5 — TDA（ターゲティングディスプレイ広告）｜中文：定向展示广告

```bash
ziniao rakuten tda-reports-search -V start_date=2026-03-01 -V end_date=2026-03-05
# 可选 vars: page, campaign_type, selection_type, period_type(默认3)
```

### PRD 6 — TDA-EXP（TDA エキスパート）｜中文：TDA 专家版报表

```bash
ziniao rakuten tda-exp-report -V start_date=2026-03-01 -V end_date=2026-03-05 -V shop_url=your-shop-slug
# 可选 vars: page_no, page_size(默认30), aggregation_period(默认3)
```

### PRD 7 — R-Mail（メルマガ）｜中文：邮件营销 / 邮件杂志

```bash
ziniao rakuten rmail-reports
# 无 vars；返回 HTML 报表页面
# auth: cookie（需先登录 auto-rmail.rms.rakuten.co.jp）
```

### PRD 8 — DEAL CSV｜中文：DEAL 活动 CSV 数据

```bash
ziniao rakuten datatool-deal-csv -V start_date=20260301 -V end_date=20260331
# 日期格式 YYYYMMDD（无横杠）
# 可选 vars: period(daily/weekly/monthly，默认daily)
# auth: cookie（需先登录 datatool.rms.rakuten.co.jp）
```

### PRD 9 — 广告购入明细（広告購入履歴明細）｜中文：广告购入历史明细

```bash
ziniao rakuten shared-purchase-detail -V target_month=2026-03
# target_month 格式 YYYY-MM
# 可选 vars: period(默认1), flag_ec/flag_grp/flag_rpp/flag_rpp_exp/flag_cpa/flag_ca/flag_tda/flag_tda_exp/flag_agree_yes/flag_agree_no（均默认 true）
```

### PRD 10 — 联盟 pending（超级联盟）｜中文：联盟返利待确认

```bash
ziniao rakuten afl-report-pending -V date=2026-03
# date 格式 YYYY-MM
# 可选 vars: offset(默认0), limit(默认100), order(asc/desc)
# auth: cookie（需先登录 afl.rms.rakuten.co.jp）
```

## 典型工作流

```bash
# 1. 接入店铺会话
ziniao open-store rakuten-shop-001

# 2. 拉取 RPP 全量日报并保存
ziniao rakuten rpp-search -V start_date=2026-03-01 -V end_date=2026-03-31 --all -o rpp_march.json

# 2b. 先取 RPP-EXP 的 shopUrl 再拉报表（脚本里可 jq 解析 data.body）
ziniao --json rakuten rpp-exp-merchant
ziniao rakuten rpp-exp-report -V start_date=2026-03-01 -V end_date=2026-03-05 -V shop_url=pettena-collections

# 3. 拉取多个报表
ziniao rakuten cpa-reports-search -V start_date=2026-03-01 -V end_date=2026-03-31 -o cpa_march.json
ziniao rakuten tda-reports-search -V start_date=2026-03-01 -V end_date=2026-03-31 -o tda_march.json

# 4. 多店铺批量
for store in shop-001 shop-002 shop-003; do
    ziniao --store "$store" rakuten rpp-search -V start_date=2026-03-01 -V end_date=2026-03-31 --all -o "rpp_${store}.json"
done
```

## 管理与自定义

```bash
ziniao site list                              # 查看所有 preset（含 rakuten/*）
ziniao site show rakuten/rpp-search           # 查看详情、变量、用法示例
ziniao site fork rakuten/rpp-search           # 复制到 ~/.ziniao/sites/ 进行自定义编辑
ziniao site disable rakuten/rmail-reports     # 禁用不需要的 preset
```

## 注意事项

- `shop_url` 参数（PRD 2、6）对应乐天店铺 URL slug（如 `pettena-collections`），会注入 `x-shop-url` header。不确定 slug 时先用 **`ziniao rakuten rpp-exp-merchant`**（或 `--json`）从 `result.shopUrl` 读取。
- PRD 4 的 body 是 URL 编码字符串（非 JSON），preset 已处理好格式。
- 日期格式因接口而异：PRD 8 使用 `YYYYMMDD`，PRD 9/10 使用 `YYYY-MM`，其余使用 `YYYY-MM-DD`。
- `--all` 仅 PRD 1（rpp-search）支持自动翻页；其他接口通过 `-V page=N` 手动翻页。
