# 浏览器集群、Cookie 与 page_fetch 契约（实现侧索引）

本文固化当前行为边界，供 `CookieVault` / `ApiTransport` / `BrowserClusterManager` 扩展时对照，避免破坏既有 CLI 与 daemon 契约。

## Cookie 与 Storage（daemon：`cookies` / `storage`）

- 实现：`ziniao_mcp/cli/dispatch.py` 中 `_cookies`、`_storage`。
- **list**：`cdp.network.get_cookies()`，返回值中 `value` **截断至 100 字符**（仅展示，非全量导出）。
- **set**：`cdp.network.set_cookie(name, value, domain=…)`。
- **clear**：`cdp.network.clear_browser_cookies()`（整浏览器级）。
- **storage**：对**当前活动 tab** 执行 `localStorage` / `sessionStorage` 的 get/set/clear；与 `page_fetch` 的 iframe 子帧路径独立。

## CookieVault（CLI：`ziniao cookie-vault`）

实现：`ziniao_mcp/cli/dispatch.py` 中 `_cookie_vault`；快照逻辑：`ziniao_mcp/cookie_vault.py`；导入/恢复编排：`ziniao_mcp/core/auth_restore.py`；导出时读 Cookie（绕过 nodriver schema drift）：`ziniao_mcp/core/cdp_raw.py`。

| 子命令 | 作用 | 契约要点 |
|--------|------|----------|
| `export` | 从当前活动 tab 导出 AuthSnapshot JSON | 含 `cookies`、`local_storage`、`session_storage`、`user_agent`、`page_url`；`cookie_source` 为 `raw_cdp_network`；`--redact` 生成不可执行快照 |
| `import` | 将快照写入当前会话（cookie + storage） | 默认要求当前 tab 的 origin 与快照 `page_url` 同源；`--allow-origin-mismatch` 显式放宽；成功返回 `imported_cookies`、`imported_local_storage_keys`、`imported_session_storage_keys`、`current_origin`、`snapshot_origin` |
| `restore` | 可选 `--url` 导航 → 导入 → 默认 reload → 可选 `--verify-selector`；导航/刷新后的 settle 等待默认走配置 | 返回 `ok`、`restored`、`verified`、`verification`、`imported_*`；验证失败时 `restored=true`、`verified=false`；`--no-reload` 跳过刷新。若 CDP `navigate` / `reload` 抛错，返回 `phase` 为 `navigate` 或 `reload` 的结构化错误（`restored` 在 reload 失败但导入已成功时为 `true`） |
| `probe-api` | 仅用 **GET / HEAD / OPTIONS** 对给定 URL 发 `direct_http_fetch` 并判断是否「看起来像成功」 | 顶层 `ok: true` 表示 **probe 子命令本身执行成功**（快照可执行、已发起探测）。`probe_invocation_ok` 与顶层 `ok` 同义；`probe_http_ok` 为内层 `direct_http_fetch` 的传输是否成功（`probe.ok`）；`direct_http_usable` 为启发式「响应是否像可用 API」（HTTP 成功且非登录页 HTML 等）。`probe` 为完整 direct 结果；`warnings` 含 `network_context_warning`；**不**替代正式业务写操作 |

**同源**：`cookie_vault.origin_of_url()` 与 `import` / `restore` 的 origin 检查一致。

**风险**：仅用于**已授权**会话迁移；不得用于窃取或未授权复用他人 Cookie。

**Restore settle 配置**：默认值为 `navigate_settle_sec=2.0`、`reload_settle_sec=1.0`，可在 `config/config.yaml` 或 `~/.ziniao/config.yaml` 中配置：

```yaml
cookie_vault:
  restore:
    navigate_settle_sec: 2.0
    reload_settle_sec: 1.0
```

也可用 `ziniao config set cookie_vault.restore.navigate_settle_sec 2.0` 写入全局配置。CLI 仍保留隐藏覆盖参数用于临时排障，但不作为常用命令面。

### `dispatch.py` 维护边界（CookieVault 与 RPA）

- **`_cookie_vault`**：Cookie / AuthSnapshot 相关变更应主要落在此分支及 `cookie_vault.py`、`auth_restore.py`、`api_transport.py`。
- **`_flow_run` / `_capture_failure_artifacts`**：与 **`ziniao_mcp/flows/runner.py`** 的 RPA flow 共用；修改其签名、落盘目录或语义时需同步回归 flow 测试，**不要**与仅 CookieVault 的改动混为同一主题 PR（除非有明确的联合需求）。

## page_fetch（浏览器内 fetch）

- 实现：`_page_fetch` → `_page_fetch_fetch` / `_page_fetch_js`。
- **fetch 模式**：`credentials: 'include'`，同源 Cookie 随请求；`header_inject` 在页面内从 `document.cookie` / storage / `eval` 取值写 header；归一化入口 `_normalize_header_inject`（在 `_page_fetch` 首行调用）。
- **iframe**：若 `StoreSession.iframe_context` 非空，经 `eval_in_frame` 执行脚本。
- **传输扩展**：`transport` 可为 `browser_fetch`（默认）、`direct_http`、`auto`；CLI 也接受 `browser` / `direct` alias。`direct_http` / `auto` 需 `auth_snapshot_path` 指向磁盘上的快照 JSON（由 `cookie_vault export` 生成）。**有 iframe_context 时禁止非 browser_fetch**，否则返回明确错误。
- **直连风险**：`direct_http` 不复用紫鸟/Chrome 的网络上下文、代理、TLS 指纹或设备环境；只有确认站点允许本机 HTTP 重放时才应启用。`auto` 只对 `GET` / `HEAD` / `OPTIONS` 做实际 direct probe，非幂等请求直接回退 `browser_fetch`。
- **direct_http 响应元数据**（`ziniao_mcp/api_transport.py`）：成功路径与 **`ensure_executable_snapshot` 失败**（如 redacted 快照）等错误路径均会附带 `auth_snapshot_used`、`browser_context_reused`（恒为 `false`）、`snapshot_site`、`snapshot_profile_id`（来自快照字段，可空）；并保留 `network_context_warning`（若有）。
- **header_inject**：`direct_http` 下仅 `cookie` / `localStorage` / `sessionStorage` 生效；`eval` 仅在 `browser_fetch` 页面内生效。

## 站点预设与 CLI network fetch

- `prepare_request`（`ziniao_mcp/sites/request.py`）合并 preset/file/CLI；`run_site_fetch`（`pagination.py`）经 `_spec_for_page_fetch` 去掉 `_ziniao_*` 与 `media_contract` / `response_contract`，**保留** `transport`、`auth_snapshot_path`、`auth_strategy`。
- `auth.type` 等仍为文档/分类用途；可执行鉴权以 `header_inject` + 可选 `auth_strategy` 为准。

## 集群与租约（`~/.ziniao/cluster.json`）

- 记录租约元数据与健康探测入口；**不**替代 `SessionManager` 的会话生命周期。
- 首版不强制所有命令携带 `lease_id`（避免破坏现有 CLI）；租约供编排与可观测性，后续可在 dispatch 层加可选校验。
- `acquire` 会清理过期租约、检查 `max_concurrent_browsers`，并拒绝同一 `session_id` 的重复有效租约。
