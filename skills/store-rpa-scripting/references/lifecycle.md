# 紫鸟：启动客户端 → 打开店铺 → CDP 连接

> **包关系**：PyPI 包名 `ziniao`，wheel 内含 `ziniao_webdriver`（HTTP 客户端）与 `ziniao_mcp`（CLI/MCP）两个 Python 包。完整说明见仓库 `docs/architecture-packages.md`。

与 **本仓库** 实现一致：HTTP 控制面在 `ziniao_webdriver/client.py`，常用生命周期 helper 在 `ziniao_webdriver/lifecycle.py`（`ensure_http_ready`、`open_store_cdp_port`），CLI/MCP 会话层在 `ziniao_mcp/session.py`（`start_client`、`_ensure_client_running`、`open_store`）。

## 概念顺序

1. **紫鸟客户端（WebDriver 模式）**：必须能响应 `http://127.0.0.1:<socket_port>`。仅用桌面图标启动、未开放该 HTTP 口时，自动化无法接入。
2. **打开店铺**：HTTP `action: startBrowser`，成功响应含 **`debuggingPort`**（Chrome CDP）。
3. **连接浏览器**：nodriver `127.0.0.1:debuggingPort` 附着到已启动的店铺浏览器。

## CLI（对应 `ziniao_mcp/cli/commands/store.py`）

| 目的 | 命令 |
|------|------|
| 启动 WebDriver 模式客户端 | `ziniao store start-client` |
| 列店铺 | `ziniao list-stores` |
| 打开店铺并接 CDP（经守护进程） | `ziniao open-store "<店铺ID>"` |
| 关闭客户端 | `ziniao store stop-client` |

守护进程路径：`open-store` → `dispatch.open_store` → `SessionManager.open_store`（先 `_ensure_client_running`，再 `ZiniaoClient.open_store`）。

**非紫鸟**：`ziniao launch` / `ziniao connect <port>`，见 [tools-reference.md](tools-reference.md) 速查。

## 配置要点

- **client_path**：紫鸟可执行文件（`ZINIAO_CLIENT_PATH` 或 `~/.ziniao/config.yaml` 中 `ziniao.client_path`）。
- **socket_port**：与客户端 `--port=` 一致（`ZINIAO_SOCKET_PORT`，常见默认 16851）。异常时可由 `ziniao_webdriver.detect_ziniao_port()` 扫进程命令行（`SessionManager._try_switch_to_detected_port`）。
- **user_info**：`company` / `username` / `password`，与客户端登录一致；`ZiniaoClient._request` 会自动并入请求体。

## 本仓库中的启动逻辑

- **`ZiniaoClient.start_browser`**：`--run_type=web_driver`、`--ipc_type=http`、`--port=<socket_port>` 拉起子进程；子进程环境会去掉 `ELECTRON_RUN_AS_NODE`（避免在 Cursor 等 Electron 宿主内误启动为 Node 模式）。
- **`SessionManager.start_client` / `_ensure_client_running`**：先 `heartbeat`；必要时 `detect_ziniao_port` 纠偏端口；若仅有普通紫鸟进程而无 HTTP，会提示用 `ziniao store start-client` 或手动带上述参数重启；冷启动在 `start_browser` 后调用 **`update_core`** 等待内核就绪（客户端 5.285.7+）。

## 本仓库中的 open_store → CDP

- **`ZiniaoClient.open_store(store_info)`**：纯数字走 `browserId`，否则走 `browserOauth`；HTTP `action: startBrowser`；成功返回 dict，含 **`debuggingPort`** 等。
- **`SessionManager.open_store`**：店铺存在性与过期 IP 校验；若持久化状态中该店 CDP 仍存活则 **`connect_store` 复用**；否则 `open_store`，等待 CDP 就绪后 **`_connect_cdp`**，再建 `StoreSession`；隐身相关 JS 在连接后由 stealth 模块应用。

## 可运行最小脚本（独立 Python）

不经过 CLI 守护进程时，可直接运行本 skill 内脚本（需已安装 `ziniao_webdriver` 与 `nodriver`，通常在本仓库根目录 `uv run python ...`）：

- [../scripts/minimal_store_cdp.py](../scripts/minimal_store_cdp.py)

流程与上节一致：`ensure_http_ready(client)` 封装 `heartbeat` / `start_browser` / `update_core` → `open_store_cdp_port(client, store_id)` 取端口 → `nodriver.Browser.create(host="127.0.0.1", port=cdp_port)`。两个 helper 均从 `ziniao_webdriver` 顶层导入。

## 常见故障

| 现象 | 处理方向 |
|------|----------|
| 连接 127.0.0.1 拒绝 | 客户端未起或端口错；`store start-client` 或核对 `ZINIAO_SOCKET_PORT` |
| 进程在跑但 HTTP 不通 | 非 WebDriver 模式；关闭后用 `start-client` 或手动 `--run_type=web_driver --ipc_type=http --port=...` |
| 无 `debuggingPort` | `open_store` 失败；看客户端与店铺状态 |
| CDP 长时间未就绪 | 防火墙、启动慢；可先手动在紫鸟内打开该店再试 |

## 源码索引（本仓库）

- `ziniao_webdriver/client.py` — `heartbeat`、`start_browser`、`update_core`、`open_store`、`get_browser_list`
- `ziniao_mcp/session.py` — `start_client`、`_ensure_client_running`、`open_store`、`connect_store`
- `ziniao_mcp/cli/commands/store.py` — `start-client`、`open` / 顶层 `open-store`
