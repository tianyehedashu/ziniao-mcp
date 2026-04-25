[根 CLAUDE](../CLAUDE.md) » **ziniao_mcp**

## 职责

**CLI**（`ziniao` 命令）、**MCP 服务**（`ziniao serve` / `python -m ziniao_mcp`）、**后台 daemon**、**会话与工具编排**：连接紫鸟店铺或独立 Chrome，经 `nodriver` 执行页面自动化；站点预设、网络拦截、`page_fetch`、录制 IR 与多目标 emit 等。

## 入口

| 入口 | 说明 |
|------|------|
| `cli/__init__.py` | Typer `app`，`main` 注册子命令；全局 flag（JSON、timeout、session/store） |
| `cli/__main__.py` / `__main__.py` | `python -m ziniao_mcp` |
| `server.py` | FastMCP 构建、配置解析、工具注册、日志到 `~/.ziniao/` 状态目录 |
| `cli/daemon.py` | 常驻进程：收 CLI JSON 请求并 `dispatch` |
| `cli/dispatch.py` | 命令名 → `SessionManager` / tools 的分发中枢（大文件） |
| `session.py` | `SessionManager`：多店会话、打开流程、与 `ZiniaoClient` / CDP 协作；`open_store_passive` 走紫鸟客户端打开但**不** attach、不 stealth、不入 `_stores` |

## 包根模块（与 `cli/` 平级）

| 模块 | 说明 |
|------|------|
| `chrome_passive.py` | 无 nodriver 启动 Chrome、DevTools HTTP 开 tab、`passive_targets.json` 别名、`/json/list` 解析 ws URL |
| `chrome_input.py` | 仅 `Input.*` 的 raw WebSocket CDP 短连接客户端（依赖 `websockets`） |
| `site_policy.py` | 强风控站点策略：内置表 + 可选 YAML ``site_policy.policies`` 合并；`policy_hint` 可 YAML 覆盖 |
| `config_yaml.py` | 共享 YAML 加载与 project↔global 合并；供 `server` 与 `site_policy` 复用 |

## 子目录速查

| 目录 | 说明 |
|------|------|
| `cli/commands/` | 按功能分组的 Typer 命令（`navigate`、`store`、`chrome`、`session`、`network`…） |
| `tools/` | MCP/内部可调用的工具实现（chrome、store、network、input、recorder…） |
| `core/` | 与页面相关的底层能力（find、scroll、check、get_info、network 辅助等） |
| `sites/` | 站点预设、分页、`page_fetch` 结果规整（含 `rakuten/`） |
| `stealth/` | `apply_stealth()` 等于在 `open_store` 后经 CDP 注入；JS 规范在 `ziniao_webdriver/js_patches.py` |
| `recording/` | 录制缓冲、定位器、DOM 捕获、向 nodriver / Playwright 等 emit |
| `recording_context.py` | 录制会话上下文 |

## 依赖

- **内部**：强依赖 `ziniao_webdriver`。
- **外部**：`mcp`、`nodriver`、`typer`、`rich`、`httpx`、`PyYAML`、`websockets`（input-only CDP）等（见根 `pyproject.toml`）。

## 配置与状态

- `dotenv_loader.py`：与 README 一致的加载顺序。
- `session` 使用 `_STATE_DIR` 等路径（参见 `server.py` 调试日志位置）。

## 测试

- CLI / JSON 信封 / 站点 / 录制 / stealth 等：`tests/test_cli_*.py`、`tests/test_session.py`、`tests/test_sites_*.py`、`tests/test_recording_*.py`、`tests/test_stealth.py`；端到端风格见 `tests/integration_test.py`。

## 深挖建议

- 新增或修改 **CLI 命令**：从 `cli/commands/__init__.py` 注册链路与 `dispatch.py` 中的 `_COMMANDS` 映射同时排查。
- **站点业务**：优先读 `sites/_base.py` 再下钻具体平台子包。
