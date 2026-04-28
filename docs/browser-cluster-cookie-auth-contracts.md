# 浏览器集群、Cookie 与 page_fetch 契约（实现侧索引）

本文固化当前行为边界，供 `CookieVault` / `ApiTransport` / `BrowserClusterManager` 扩展时对照，避免破坏既有 CLI 与 daemon 契约。

## Cookie 与 Storage（daemon：`cookies` / `storage`）

- 实现：`ziniao_mcp/cli/dispatch.py` 中 `_cookies`、`_storage`。
- **list**：`cdp.network.get_cookies()`，返回值中 `value` **截断至 100 字符**（仅展示，非全量导出）。
- **set**：`cdp.network.set_cookie(name, value, domain=…)`。
- **clear**：`cdp.network.clear_browser_cookies()`（整浏览器级）。
- **storage**：对**当前活动 tab** 执行 `localStorage` / `sessionStorage` 的 get/set/clear；与 `page_fetch` 的 iframe 子帧路径独立。

## page_fetch（浏览器内 fetch）

- 实现：`_page_fetch` → `_page_fetch_fetch` / `_page_fetch_js`。
- **fetch 模式**：`credentials: 'include'`，同源 Cookie 随请求；`header_inject` 在页面内从 `document.cookie` / storage / `eval` 取值写 header；归一化入口 `_normalize_header_inject`（在 `_page_fetch` 首行调用）。
- **iframe**：若 `StoreSession.iframe_context` 非空，经 `eval_in_frame` 执行脚本。
- **传输扩展**：`transport` 可为 `browser_fetch`（默认）、`direct_http`、`auto`；CLI 也接受 `browser` / `direct` alias。`direct_http` / `auto` 需 `auth_snapshot_path` 指向磁盘上的快照 JSON（由 `cookie_vault export` 生成）。**有 iframe_context 时禁止非 browser_fetch**，否则返回明确错误。
- **直连风险**：`direct_http` 不复用紫鸟/Chrome 的网络上下文、代理、TLS 指纹或设备环境；只有确认站点允许本机 HTTP 重放时才应启用。`auto` 只对 `GET` / `HEAD` / `OPTIONS` 做实际 direct probe，非幂等请求直接回退 `browser_fetch`。

## 站点预设与 CLI network fetch

- `prepare_request`（`ziniao_mcp/sites/request.py`）合并 preset/file/CLI；`run_site_fetch`（`pagination.py`）经 `_spec_for_page_fetch` 去掉 `_ziniao_*` 与 `media_contract` / `response_contract`，**保留** `transport`、`auth_snapshot_path`、`auth_strategy`。
- `auth.type` 等仍为文档/分类用途；可执行鉴权以 `header_inject` + 可选 `auth_strategy` 为准。

## 集群与租约（`~/.ziniao/cluster.json`）

- 记录租约元数据与健康探测入口；**不**替代 `SessionManager` 的会话生命周期。
- 首版不强制所有命令携带 `lease_id`（避免破坏现有 CLI）；租约供编排与可观测性，后续可在 dispatch 层加可选校验。
- `acquire` 会清理过期租约、检查 `max_concurrent_browsers`，并拒绝同一 `session_id` 的重复有效租约。
