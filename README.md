# ziniao

紫鸟与 Chrome 浏览器 AI 自动化 — 让 AI Agent（Cursor、Claude 等）和终端用户共用同一套 CLI 操控紫鸟店铺与本地 Chrome。

- **GitHub**：[tianyehedashu/ziniao-mcp](https://github.com/tianyehedashu/ziniao-mcp)
- **PyPI**：[`ziniao`](https://pypi.org/project/ziniao/) — 控制台命令 `ziniao`；可选 MCP 服务通过 `ziniao serve` 启动

## 一等公民

本项目围绕三个一等公民构建，按优先级使用即可：

1. **CLI（`ziniao …`）** — 完整的浏览器自动化命令行，人和 Agent 共享同一入口；首条命令自动拉起后台 daemon，多会话复用。
2. **Site Presets（`ziniao site …`）** — JSON 模板 + 浏览器登录态，免 API Key 直接调用站点接口（Rakuten 广告、评论、Amazon 后台等），支持分页、CSRF、Python 插件。
3. **Skills（`ziniao skill …`）** — 把 `ziniao-cli` 等业务技能一键安装到 Cursor / Claude Code / Trae / OpenClaw 等 Agent 的全局目录。

> MCP 工具集是**可选的备选路径**，仅在 Agent 无终端权限或你明确需要 MCP 协议时使用，能力覆盖小于 CLI，详见文末「MCP 服务器（可选）」。

## 安装

```bash
# 1) 安装 uv（推荐：已有 Python 时用 pipx/pip，免过 PowerShell / curl|sh 执行策略）
pipx install uv                                # 推荐
python -m pip install --user uv               # 没有 pipx 时
# 备选（官方 standalone 安装器，升级走 uv self update）
#   Windows:      powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
#   macOS/Linux:  curl -LsSf https://astral.sh/uv/install.sh | sh

# 2) 安装 ziniao CLI
uv tool install ziniao

# 3) 必装两件套：ziniao-cli（Agent 调 CLI） + site-development（新站点适配）
#    默认装到 Cursor，`-a claude` / `-a all` 可指定 Agent
ziniao skill install ziniao-cli
ziniao skill install site-development
# 可选：业务 skills，用到哪个装哪个
ziniao skill install rakuten-ads              # Rakuten 广告报表
ziniao skill install store-rpa-scripting      # RPA 脚本固化
# 更多：ziniao skill list
```

> **为什么 `ziniao-cli` 和 `site-development` 是必装**：前者让 Agent 知道如何正确调 `ziniao` 全部命令与 JSON 输出约定；后者是站点扩展的"入场券"——用户要你加一个新站点适配时，Agent 会按它的 6 步工作流（逆向 → 选 Tier → 写 preset → 可选 plugin → CLI 测试 → 提交 site-hub）来工作，避免瞎写。

若终端识别不到 `ziniao`，把 `uv tool dir` 输出的目录加入 PATH；升级用 `ziniao update`（Windows 默认新窗口延迟执行以避开 `ziniao.exe` 自占用，脚本/CI 用 `--sync`）。

> **uv 升级**：脚本/WinGet/Scoop 安装的 uv 用 `uv self update`；**pipx / pip 安装的 uv 不支持 `uv self update`**，请改用 `pipx upgrade uv` 或 `pip install -U uv`。

**紫鸟店铺**（可选）：安装 [紫鸟客户端](https://www.ziniao.com/) 并开启 WebDriver 权限，再执行 `ziniao config init` 写入账号信息。仅用 Chrome 时无需任何紫鸟配置。

## 三行上手

```bash
ziniao launch --url https://example.com        # 启动 Chrome
ziniao snapshot --interactive                  # 查看可交互元素（自动给出 CSS selector）
ziniao click "#submit" && ziniao screenshot after.png
```

## 配置

纯 Chrome 场景零配置即可跑。需要 profile 复用、紫鸟账号或 CDP 端口控制时，`ziniao config init` 写入 `~/.ziniao/.env` / `config.yaml`（CLI 与 MCP 共用）。

```bash
ziniao config init [--force]                  # 交互向导 → ~/.ziniao/config.yaml + .env
ziniao config show                            # 查看生效配置及来源
ziniao config set chrome.user_data_dir "C:\Users\me\.ziniao\chrome-profile"
ziniao config env --shell powershell|bash|json|mcp
ziniao config path
```

**生效优先级**：环境变量 > CLI 参数 > `~/.ziniao/.env` > 项目 `config/config.yaml` > `~/.ziniao/config.yaml`。

**Chrome 环境变量**（纯 Chrome 场景可全部省略）：

| 环境变量 | 说明 |
|---------|------|
| `CHROME_PATH` | Chrome 可执行文件路径；不设置时自动检测（注册表 > 常见路径 > PATH） |
| `CHROME_USER_DATA` | Chrome 用户数据目录（profile），用于复用登录态 / Cookie / 扩展；默认 `~/.ziniao/chrome-profile` |
| `CHROME_CDP_PORT` | Chrome CDP 调试端口；不设置时自动分配 |

**紫鸟环境变量**（使用紫鸟店铺功能时必需，仅用 Chrome 可全部省略）：

| 环境变量 | 必填 | 说明 |
|---------|------|------|
| `ZINIAO_COMPANY` | ✅ | 紫鸟企业名 |
| `ZINIAO_USERNAME` | ✅ | 紫鸟登录用户名 |
| `ZINIAO_PASSWORD` | ✅ | 紫鸟登录密码 |
| `ZINIAO_CLIENT_PATH` | ✅ | 紫鸟客户端可执行文件路径 |
| `ZINIAO_SOCKET_PORT` | — | 与客户端通信的 HTTP 端口；不设置时自动检测运行中的客户端端口，检测不到则默认 `16851` |
| `ZINIAO_VERSION` | — | 客户端版本，默认 `v6` |

> 使用紫鸟需先安装 [紫鸟客户端](https://www.ziniao.com/) 并开启 WebDriver 权限（[开通说明](https://open.ziniao.com/docSupport?docId=99)）。

## CLI

### 全局选项

```bash
ziniao [全局选项] <命令> [参数]
```

| 选项 | 说明 |
|------|------|
| `--store <id>` / `--session <id>` | 指定目标店铺 / 会话（互斥） |
| `--json` | 机器可读信封 `{success, data, error}`（与 agent-browser 一致） |
| `--json-legacy` | daemon 原始 JSON（无信封），与 `--json` 互斥 |
| `--content-boundaries` | JSON 加 `_boundary`；stdout 加边界行（`ZINIAO_CONTENT_BOUNDARIES=1`） |
| `--max-output <N>` | 限制快照 / `eval` 在 **stdout** 的字符数；默认 2000，`0` 不截断；`-o` 写文件始终全量 |
| `--timeout <秒>` | `0` 自动（navigate/click/snapshot 等 120s，其余 60s） |

环境变量 `ZINIAO_JSON=1` 等价 `--json`，`NO_COLOR` 关闭着色。详见 [docs/cli-json.md](docs/cli-json.md)、[docs/cli-llm.md](docs/cli-llm.md)。

### 站点预设 `site`（一等公民）

**JSON 模板 + 浏览器登录态**，免 API Key 直接调站点接口。一个预设就是一个 JSON 文件，声明 URL / 方法 / 变量 / 鉴权 / 分页 / 输出约定，执行时复用当前浏览器 Cookie、`localStorage`、CSRF token。预设支持三种模式，覆盖从纯接口到纯 UI 的所有场景：

| 模式 | 适用 | 说明 |
|------|------|------|
| `mode: fetch` | 登录态 API | 通过浏览器 `fetch` 发请求，声明式 header 注入（cookie / storage / eval），支持 offset / cursor 分页 |
| `mode: js` | 特殊场景 | 在页面里执行自定义 JS 胶水（如 GCS 签名 URL 下载、富文本交互） |
| `mode: ui` | 非 API / 混合 | 声明式 UI 步骤（点击、填表、`type: secret` 安全输入、DOM `extract`、内联 `fetch`），带 bezier 轨迹反风控、失败快照自动脱敏 |

```bash
ziniao site list                        # 列出所有预设
ziniao site show rakuten/rpp-search     # 查看预设详情
ziniao site repos                       # 已注册仓库
ziniao site update                      # 拉取仓库最新预设（含 skills）
ziniao site skills                      # 列出仓库内 AI skills
```

运行预设（顶层快捷自动生成为 `ziniao <site> <action>`）：

```bash
ziniao rakuten rpp-search -V start_date=2026-03-01 -V end_date=2026-03-07
ziniao rakuten reviews-csv -o reviews.csv
ziniao network fetch -p rakuten/rpp-search -V start_date=2026-03-01 --all -o out.json
```

#### site-hub — 业务预设 + 业务 skills 仓库

[`site-hub`](https://github.com/tianyehedashu/site-hub) 是与主仓库解耦的**业务预设仓库**，通过 `ziniao site update` 按需拉取，避免主仓库膨胀：

- **按站点组织**：`site-hub/<site>/<action>.json`（如 `rakuten/rpp-search.json`、`google-flow/imagen-generate.json`），附配套 `README.md`、`plugin.py`、Flow demos。
- **随预设发布 AI skills**：`site-hub/skills/<skill>/SKILL.md` 与预设版本强绑定，`ziniao skill install <name>` 一键装到 Agent；站点作者想让 Agent 怎么用自己的站点，就写一份 skill 进去。
- **独立版本与 Tag**：子仓库自己管版本，主 CLI 向后兼容即可升级预设。

#### 开发新站点 → 用 `site-development` 技能

想给新站点（如自家 ERP、Shopee、Lazada）加预设，用 [`site-development`](https://github.com/tianyehedashu/site-hub/tree/main/skills/site-development) 技能，让 Agent 帮你按 6 步工作流产出代码：

```bash
ziniao skill install site-development           # 装到 Cursor / Claude Code
# 在 Agent 里说："帮我给 xxx.com 的订单导出接口加一个预设"
```

技能里沉淀了：三层认证（cookie / `header_inject` / 插件）选择决策树、`mode` 选型、分页约定、错误处理、反风控注意事项、落盘复用 `ziniao_mcp.sites.save_media`、Next.js API 逆向方法（`docs/next-app-reverse-engineering.md`）等。

架构与鉴权细节见 [docs/site-fetch-and-presets.md](docs/site-fetch-and-presets.md)、[docs/page-fetch-auth.md](docs/page-fetch-auth.md)、[docs/site-ui-flows.md](docs/site-ui-flows.md)。

### Agent Skill 管理 `skill`（一等公民）

```bash
ziniao skill agents                        # 支持的 agent（cursor / trae / claude / openclaw …）
ziniao skill list                          # 可安装的 skills
ziniao skill install ziniao-cli            # 默认 Cursor
ziniao skill install rakuten-ads -a all    # 全部 agent
ziniao skill update                        # 刷新已安装的 symlink
ziniao skill remove rakuten-ads -a all
ziniao skill installed                     # 已安装
```

> **刷新策略**：`ziniao site update` 拉取 `site-hub` 全量文件（含根目录 `skills/` 与各站点 `<site>/skills/`）并**自动** `refresh_symlinks`，Agent 目录无需再手动刷。`ziniao update`（升级 CLI 自身）只替换 built-in skills 的文件内容，**不**自动建立新增 skill 的 symlink——若升级后想让新内置 skill 出现在 Agent 里，再跑一次 `ziniao skill update`。

**内置与业务 skills**（⭐ 强烈建议装；按需装其余）：

| 技能 | 用途 |
|------|------|
| **`ziniao-cli`** ⭐ | Agent 直接调 `ziniao` 命令完成浏览器自动化、站点预设、skill 管理 |
| **`site-development`** ⭐ | 新站点适配器开发（6 步工作流、3 层认证、`mode: fetch/js/ui` 选型） |
| `store-rpa-scripting` | 探索 → 固化为独立 Python 脚本（nodriver + ziniao_webdriver） |
| `store-management` / `amazon-operations` | 多店管理 / 亚马逊后台 |
| `rakuten-ads` / `rakuten-reviews` | Rakuten 广告报表 / 评论 CSV |

### Chrome / 店铺 / 会话

```bash
ziniao launch [--url <url>] [--name <名]  # chrome launch，外部未被占用时自动启动进程
ziniao connect <cdp_port>                 # chrome connect，连接外部 Chrome
ziniao chrome list / close <sid>
ziniao list-stores / open-store <id> / close-store <id>
ziniao store start-client / stop-client
ziniao session list / switch <sid> / info <sid>
```

`launch` 由 ziniao 启动的 Chrome 在 `close` 时会被终止；`connect` 连接的外部 Chrome 仅断开 CDP。若 `launch` 发现 profile 已被占用会自动降级为 connect。

### 导航与页面交互

```bash
ziniao navigate <url> / back / forward / reload [--ignore-cache]
ziniao tab list / new [url] / switch --index <i> / close
ziniao nav frame list
ziniao wait <selector>

ziniao click / dblclick / hover <selector>
ziniao fill <selector> <value>
ziniao type <text> [-s <selector>]
ziniao press <key>                        # Enter / Tab / Ctrl+a
ziniao act drag <src> <dst>
ziniao act upload <selector> <file...>
ziniao upload-hijack <file...> [--trigger SEL]  # SPA 隐藏 input 上传
ziniao act focus / select / check / uncheck / dialog / keydown / keyup
```

### 页面信息 / 取值 / 查找 / 状态 / 滚动 / 鼠标

```bash
ziniao snapshot [-o file.html] [--interactive|--compact]
ziniao screenshot [file.png]
ziniao eval <js>                          # --await 等待 Promise
ziniao url / title
ziniao info console [--level error] / network / errors / highlight / cookies / storage / clipboard

ziniao get text / html / value / attr / count <selector> [<attr>]
ziniao find text <文本> [--action click] / role <角色> [--name <名称>] / first / last / nth
ziniao is visible / enabled / checked <selector>
ziniao scroll down / up / left / right [--pixels N]
ziniao scroll into <selector>
ziniao mouse move <x> <y> / down / up [--button left|right] / wheel --delta-y <n>
```

### 网络、录制、批量、系统、升级

```bash
ziniao network list [--filter <pattern>|--id <id>]
ziniao network route <pattern> --abort / unroute / routes
ziniao network har-start / har-stop [<file>]

ziniao rec start [--engine legacy|dom2] [--scope active|all] [--max-tabs N]
ziniao rec stop [--name <名>] [--emit nodriver,playwright] [--redact-secrets]
ziniao rec replay <名> [--speed 1.0] / list / delete <名> / status

echo '[{"command":"navigate","args":{"url":"https://example.com"}}]' | ziniao batch run

ziniao quit / emulate --device "iPhone 15" / emulate --width 800 --height 600
ziniao update [--git] [--sync] [--dry-run]
```

`rec` 默认 `dom2` 引擎（CDP `Runtime.addBinding` 缓冲到 daemon，跨标签不丢），`--engine legacy` 走页内 Symbol 缓冲。

## RPA 与录制

遵循「探索 → 验证 → 固化」：`snapshot --interactive` 选择器 → `click` / `fill` → `wait_for` 或 `snapshot` 验证 → 把步骤交给 `store-rpa-scripting` 技能，生成不依赖 daemon 的独立 Python 脚本（`ziniao_webdriver` + `nodriver`）。

录制：`ziniao rec start` → 在浏览器里操作 → `ziniao rec stop --name my-flow` 产出 `.json`（回放）+ `.py`（独立脚本），`ziniao rec replay my-flow` 复现。

## 常用示例

```bash
ziniao launch --url https://www.baidu.com
ziniao navigate https://example.com && ziniao wait ".loaded" && ziniao screenshot page.png
ziniao fill "#email" "u@test.com" && ziniao fill "#pass" "secret" && ziniao click "#login"

# 页面内登录态接口（架构见 docs/site-fetch-and-presets.md）
ziniao rakuten rpp-search -V start_date=2026-03-01 -V end_date=2026-03-07
ziniao rakuten reviews-csv -o reviews.csv

# JSON 输出
ziniao --json session list
ziniao --json --content-boundaries --max-output 8000 info snapshot
```

所有命令支持 `--help`，如 `ziniao chrome launch --help`。

## MCP 服务器（可选）

仅在 Agent 不方便走终端命令、或你明确需要 MCP 协议时使用；功能是 CLI 的子集。

**Cursor 配置**（`Cursor Settings → MCP → New MCP Server`）：

```json
{
  "mcpServers": {
    "ziniao": { "command": "ziniao", "args": ["serve"] }
  }
}
```

账号与 Chrome 路径写入 `~/.ziniao/.env` / `config.yaml` 即可与 MCP 共用；仅在 IDE 内覆盖时再在 `mcp.json` 增 `env`（可用 `ziniao config env --shell mcp` 导出）。

> MCP 进程里已有的环境变量不会被 `.env` 覆盖；终端的 `ziniao` 走独立 daemon，不读 `mcp.json`。

**MCP 工具集速览**（完整参数见 [docs/api-reference.md](docs/api-reference.md)）：

| 分组 | 工具 |
|------|------|
| 店铺 | `start_client` / `stop_client` / `list_stores` / `list_open_stores` / `open_store` / `connect_store` / `close_store` |
| Chrome / 会话 | `launch_chrome` / `connect_chrome` / `list_chrome` / `close_chrome` / `browser_session` |
| 导航 | `navigate_page` / `list_pages` / `select_page` / `new_page` / `close_page` / `wait_for` |
| 输入 | `click` / `fill` / `fill_form` / `type_text` / `press_key` / `hover` / `drag` / `handle_dialog` / `upload_file` / `upload_hijack` |
| 调试 | `evaluate_script` / `take_screenshot` / `take_snapshot` / `list_console_messages` / `get_console_message` |
| 网络 / 仿真 / 录制 | `list_network_requests` / `get_network_request` / `emulate` / `resize_page` / `recorder` |

## 文档

| 文档 | 说明 |
|------|------|
| [installation.md](docs/installation.md) | 多种安装方式、配置、故障排查 |
| [install-uv-windows.md](docs/install-uv-windows.md) | Windows 下安装 uv |
| [architecture.md](docs/architecture.md) | 三层架构、模块职责、数据流 |
| [api-reference.md](docs/api-reference.md) | 全部 MCP 工具参数与返回值 |
| [development.md](docs/development.md) | 添加新工具、构建、发布 |
| [cli-json.md](docs/cli-json.md) / [cli-llm.md](docs/cli-llm.md) | `--json` 信封、与 agent-browser 对齐 |
| [cli-agent-browser-parity.md](docs/cli-agent-browser-parity.md) | 全量命令与参数对照 |
| [site-fetch-and-presets.md](docs/site-fetch-and-presets.md) | 站点模板架构、`auth.type`、分页、`page_fetch` |
| [page-fetch-auth.md](docs/page-fetch-auth.md) | 声明式 header 注入（cookie/localStorage/eval） |
| [site-ui-flows.md](docs/site-ui-flows.md) | Declarative UI Flows (`mode: ui`)、反风控、`type: secret` |

## 上游与许可证

主仓库：[github.com/tianyehedashu/ziniao-mcp](https://github.com/tianyehedashu/ziniao-mcp)。以 submodule 嵌入时请在上游提 PR，再更新父仓库指针。

许可证以根目录 [LICENSE](LICENSE) 为准（MIT）。调试时注意 `~/.ziniao/mcp_debug.log` 在 DEBUG 级别可能含 URL 等敏感信息。
