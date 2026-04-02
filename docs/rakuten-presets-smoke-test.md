# 乐天站点预设（`ziniao rakuten`）冒烟说明

本文档列出内置 **11** 条乐天 preset 的**推荐测试命令**，并说明如何判断成败。自动化脚本：[scripts/rakuten_presets_smoke.py](../scripts/rakuten_presets_smoke.py)。

## 前置条件

1. **守护进程与浏览器会话**：`ziniao` 能连上 daemon，且存在**活动会话**（`open_store` 打开紫鸟店铺，或 `launch_chrome` / `connect_chrome` 连接 Chrome）。
2. **当前活动标签页**：尽量打开与 preset **`navigate_url`** 同域的 RMS 页面并已登录（否则易出现 **Failed to fetch** 或 **403**）。具体见 `ziniao site show rakuten/<name>`。
3. **`shop_url`**（RPP-EXP / TDA-EXP）：可先执行 **`ziniao rakuten rpp-exp-merchant`**，从返回 JSON 的 `result.shopUrl` 取值，再传给 `-V shop_url=`。

## 逐条测试命令

下列命令中的日期、店铺 slug 仅为示例，请按实际报表范围与店铺修改。

| # | Preset | 示例命令 |
|---|--------|----------|
| 1 | `rpp-exp-merchant` | `ziniao rakuten rpp-exp-merchant` |
| 2 | `rmail-reports` | `ziniao rakuten rmail-reports` |
| 3 | `afl-report-pending` | `ziniao rakuten afl-report-pending -V date=2026-03` |
| 4 | `cpa-reports-search` | `ziniao rakuten cpa-reports-search -V start_date=2026-03-01 -V end_date=2026-03-07` |
| 5 | `cpnadv-performance-retrieve` | `ziniao rakuten cpnadv-performance-retrieve -V start_date=2026-03-01 -V end_date=2026-03-07` |
| 6 | `datatool-deal-csv` | `ziniao rakuten datatool-deal-csv -V start_date=20260301 -V end_date=20260331 -V period=daily` |
| 7 | `rpp-exp-report` | `ziniao rakuten rpp-exp-report -V start_date=2026-03-01 -V end_date=2026-03-07 -V shop_url=<slug>` |
| 8 | `rpp-search` | `ziniao rakuten rpp-search -V start_date=2026-03-01 -V end_date=2026-03-07` |
| 9 | `shared-purchase-detail` | `ziniao rakuten shared-purchase-detail -V target_month=2026-03` |
| 10 | `tda-exp-report` | `ziniao rakuten tda-exp-report -V start_date=2026-03-01 -V end_date=2026-03-07 -V shop_url=<slug>` |
| 11 | `tda-reports-search` | `ziniao rakuten tda-reports-search -V start_date=2026-03-01 -V end_date=2026-03-07` |

分页 preset（如 `rpp-search`）可追加 `--page N` 或 `--all`（见 `ziniao rakuten rpp-search --help`）。

## 如何解读输出

| 现象 | 含义 |
|------|------|
| `Error: 没有活动的浏览器会话` | 未连接店铺/Chrome，先建立会话。 |
| `OK` + `status: 200` + JSON/HTML `body` | 请求成功；HTML 多为页面壳或列表页，不一定是最终 CSV 文件流。 |
| `TypeError: Failed to fetch` | 当前标签页与 API **不同源**或网络/CORS 问题；先 **`navigate` 到 preset 对应域**再试。 |
| `status: 403` 等 + 日文业务错误 | 服务端拒绝；按提示检查登录态、广告拦截、权限或稍后重试。 |

## 参考实测记录（单次会话，仅供参考）

以下由 `python scripts/rakuten_presets_smoke.py` 在**已连接浏览器、活动标签页在乐天 RMS 域**下跑出的结果（**2026-04-02** 左右一次）；换店铺、日期或当前 URL 后可能变化，**不作契约断言**。

| Preset | HTTP / 现象 | 摘要 |
|--------|-------------|------|
| `rpp-exp-merchant` | **200** | JSON：`shopUrl` 等正常。 |
| `rmail-reports` | **200** | 报表页 **HTML**（非 JSON）。 |
| `afl-report-pending` | 页面异常 | 页面内 **`Failed to fetch`**；需将活动页切到**超级联盟 / 返利 pending** 对应域后再试。 |
| `cpa-reports-search` | **200** | JSON 报表正常。 |
| `cpnadv-performance-retrieve` | **401**（已修） | 原因：① CSRF 须用 **`<meta name="_csrf">`**，与 Cookie `XSRF-TOKEN` 值不一致；② **`page_fetch` 须在 iframe 上下文执行**（与 `eval` 一致）。更新预设 `header_inject` + daemon 内 `_page_fetch_fetch` 后应 **200**；改代码后需**重启 ziniao 守护进程**。 |
| `datatool-deal-csv` | **200** | 多为数据下载壳页 **HTML**（未必是 CSV 文件流）。 |
| `rpp-exp-report` | **200** | RPP-EXP 报表 JSON（`shop_url` 取自 merchant，示例为 `pettena-collections`）。 |
| `rpp-search` | **201** | 乐天侧用 201 表示创建/检索成功时也属正常，以 body 是否含业务数据为准。 |
| `shared-purchase-detail` | **200** | 广告购入明细 JSON 正常。 |
| `tda-exp-report` | **200** | TDA-EXP 报表 JSON 正常。 |
| `tda-reports-search` | **400** | 请求参数或当前页上下文不满足接口要求；对照 `ziniao site show rakuten/tda-reports-search` 检查可选变量与活动页。 |

## 一键冒烟脚本

在项目根目录执行（需已有活动浏览器会话）：

```bash
python scripts/rakuten_presets_smoke.py
```

输出为 **TSV**（`preset` / `outcome` / `detail` / `command`），便于粘贴到表格或 CI 日志。无会话时 `outcome` 多为 `no_session`。

### 按命令保存返回值（便于本地查看）

将每条命令用 **`ziniao --json --max-output 0`** 再跑一遍，写入目录（默认在 **`out/rakuten-preset-responses/`**，该路径已在仓库 **`.gitignore` 的 `out/`** 下，避免误提交 Cookie/业务数据）：

```bash
python scripts/rakuten_presets_smoke.py --save
# 或指定目录：
python scripts/rakuten_presets_smoke.py --save path/to/dir
```

生成文件：

- **`manifest.json`**：每条 preset 对应的完整命令、`exit_code`、与 TSV 同源的 `outcome`/`detail`、保存的文件名。
- **`<preset>.json`**：若 stdout 为合法 JSON，则格式化的 CLI 信封（含 `success` / `data.status` / `data.body` 等）。
- **`<preset>.raw.txt`**：原始捕获的 stdout（与 `.json` 二选一查看即可）。

## 相关文档

- [site-fetch-and-presets.md](site-fetch-and-presets.md)
- `ziniao site list` / `ziniao site show rakuten/<name>`
