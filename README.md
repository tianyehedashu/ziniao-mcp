# ziniao

紫鸟与 Chrome 浏览器 AI 自动化 — 让 AI Agent（Cursor、Claude 等）操控紫鸟店铺与本地 Chrome，统一会话、统一工具。

**GitHub**：[https://github.com/tianyehedashu/ziniao-mcp](https://github.com/tianyehedashu/ziniao-mcp)

## 快速使用

只需两步即可在 Cursor 中使用全部 MCP 工具。紫鸟配置**可选**——不配置紫鸟也能使用全部 Chrome 浏览器功能。

**1. 安装 [uv](https://docs.astral.sh/uv/)**

```bash
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**2. 安装 ziniao**

```bash
uv tool install ziniao
```

若终端无法识别 `ziniao`，请将 `uv tool dir` 输出的目录加入 PATH（见下方「命令行全局使用」）。

**3. 配置 MCP**

打开 `Cursor Settings → MCP → New MCP Server`，根据你的使用场景选择配置：

**仅使用 Chrome 浏览器**（无需紫鸟账号）：

```json
{
  "mcpServers": {
    "ziniao": {
      "command": "ziniao",
      "args": ["serve"]
    }
  }
}
```

配置完成后即可使用 `launch_chrome`、`connect_chrome` 及所有页面操作、录制回放等工具。

**紫鸟店铺 + Chrome 浏览器**（完整功能）：

```json
{
  "mcpServers": {
    "ziniao": {
      "command": "ziniao",
      "args": ["serve"],
      "env": {
        "ZINIAO_COMPANY": "你的企业名",
        "ZINIAO_USERNAME": "你的用户名",
        "ZINIAO_PASSWORD": "你的密码",
        "ZINIAO_CLIENT_PATH": "D:\\soft\\ziniao-v6\\ziniao.exe",
        "ZINIAO_VERSION": "v6"
      }
    }
  }
}
```

| 环境变量 | 说明 |
|----------|------|
| `ZINIAO_COMPANY` | 紫鸟企业名 |
| `ZINIAO_USERNAME` | 登录用户名 |
| `ZINIAO_PASSWORD` | 登录密码 |
| `ZINIAO_CLIENT_PATH` | 紫鸟客户端可执行文件路径 |
| `ZINIAO_SOCKET_PORT` | （可选）与客户端通信的 HTTP 端口。**不配置时自动检测运行中的客户端端口**，检测不到则默认 `16851` |
| `ZINIAO_VERSION` | 客户端版本，默认 `v6` |

配置完成后，在 Cursor 对话框中试试：

```
启动 Chrome 浏览器，打开百度
```

```
列出我所有的紫鸟店铺
```

```
打开第一个亚马逊店铺，截图看看当前页面
```

> **版本**：`ziniao --help`；更新：`uv tool install --upgrade ziniao` 后重启 Cursor MCP。
>
> **紫鸟前提**：使用紫鸟店铺功能需安装 [紫鸟客户端](https://www.ziniao.com/) 并**开启 WebDriver 权限**（[开通说明](https://open.ziniao.com/docSupport?docId=99)）。不使用紫鸟功能时无需安装。
>
> 更多安装方式与故障排查见 [安装与使用](docs/installation.md)。

### 命令行全局使用（ziniao）

若希望在任意目录直接使用 `ziniao` 命令（而不通过 Cursor MCP），推荐用 **uv 工具安装**，一次配置、全局可用：

```bash
# 从 PyPI 安装（推荐）
uv tool install ziniao

# 或从源码安装（克隆后在该目录执行）
uv tool install .
```

安装后会在 uv 工具目录生成 `ziniao` 可执行文件。若终端提示「无法将 ziniao 项识别为…」，请将 uv 工具目录加入 PATH：

- 查看工具目录：`uv tool dir`（Windows 常见为 `%APPDATA%\uv\tools` 或 `%USERPROFILE%\.local\bin`）
- 将该目录加入 [用户环境变量 Path](https://learn.microsoft.com/zh-cn/windows/win32/procthread/environment-variables)  
新开终端后即可直接运行 `ziniao --help`、`ziniao serve` 等。

## 特性

- **紫鸟可选**：不配置紫鸟也能使用全部 Chrome 浏览器功能（启动/连接/页面操作/录制回放），零配置即可上手
- **统一浏览器支持**：紫鸟店铺（多店铺、WebDriver）与本地 Chrome（启动/连接 CDP）同一套 MCP 工具
- **全部 MCP 工具**：店铺管理、Chrome 管理、统一会话、页面导航、输入自动化、录制回放、网络监控、调试截图等
- **4 个 AI 技能（Skills）**：浏览器自动化、店铺管理、亚马逊运营、店铺运营 RPA 脚本生成
- **1 个专用 Agent**：紫鸟运营专家角色，具备跨境电商领域知识
- **2 个快捷命令（Commands）**：一键检查店铺状态、批量截图
- **跨会话状态持久化**：MCP 进程重启后可恢复已打开店铺或 Chrome 的 CDP 连接
- **多会话并行**：同时打开多个紫鸟店铺或 Chrome 实例，按需切换活动会话
- **跨平台**：支持 Windows / macOS / Linux

## 工具列表

### 店铺管理（紫鸟，7 个）

| 工具 | 说明 |
|------|------|
| `start_client` | 启动紫鸟客户端（WebDriver 模式） |
| `list_stores` | 获取所有店铺列表（自动启动客户端） |
| `list_open_stores` | 查询当前已打开的店铺（通过 CDP 端口验证） |
| `open_store` | 打开店铺并建立 CDP 连接 |
| `connect_store` | 连接已运行的店铺（不重启，推荐） |
| `close_store` | 关闭店铺并断开 CDP |
| `stop_client` | 退出紫鸟客户端 |

### Chrome 管理（4 个）

| 工具 | 说明 |
|------|------|
| `launch_chrome` | 启动本地 Chrome 并通过 CDP 连接 |
| `connect_chrome` | 连接已运行的 Chrome（需带 `--remote-debugging-port` 启动） |
| `list_chrome` | 列出当前所有 Chrome 会话 |
| `close_chrome` | 关闭指定 Chrome 会话 |

### 统一会话（1 个）

| 工具 | 说明 |
|------|------|
| `browser_session` | 列出/切换/查看所有浏览器会话（紫鸟 + Chrome） |

### 输入自动化（9 个）

| 工具 | 说明 |
|------|------|
| `click` | 点击元素 |
| `fill` | 清空并填写输入框 |
| `fill_form` | 批量填写表单 |
| `type_text` | 逐字输入文本（模拟真实键盘） |
| `press_key` | 按键（如 Enter、Tab、Ctrl+A） |
| `hover` | 悬停 |
| `drag` | 拖拽元素 |
| `handle_dialog` | 设置弹窗处理策略 |
| `upload_file` | 上传文件 |

### 导航（6 个）

| 工具 | 说明 |
|------|------|
| `navigate_page` | 导航到 URL |
| `list_pages` | 列出所有标签页 |
| `select_page` | 切换标签页 |
| `new_page` | 新建标签页 |
| `close_page` | 关闭标签页 |
| `wait_for` | 等待元素/页面加载 |

### 仿真（2 个）

| 工具 | 说明 |
|------|------|
| `emulate` | 模拟设备（iPhone、iPad、Pixel 等） |
| `resize_page` | 调整视口大小 |

### 网络（2 个）

| 工具 | 说明 |
|------|------|
| `list_network_requests` | 列出捕获的网络请求 |
| `get_network_request` | 获取请求详情（含请求头/响应头） |

### 调试（5 个）

| 工具 | 说明 |
|------|------|
| `evaluate_script` | 执行 JavaScript |
| `take_screenshot` | 截图（支持元素截图和全页截图） |
| `take_snapshot` | 获取页面 HTML 快照 |
| `list_console_messages` | 列出控制台消息 |
| `get_console_message` | 获取消息详情 |

### 录制与回放（1 个）

| 工具 | 说明 |
|------|------|
| `recorder` | 录制浏览器操作（点击/输入/按键/导航），停止后生成 .json + 可独立运行的 .py 脚本；支持回放、列表、删除 |

## RPA 与录制

### RPA 自动化技巧

用 MCP 做店铺或 Chrome 的 RPA 时，建议遵循「探索 → 验证 → 固化」的思路：

- **选择器优先**：`#id` > `[name="x"]` > `[data-testid="x"]` > 有唯一性的 class，避免依赖复杂 DOM 层级。
- **每步验证**：每次 `click` / `fill` / `press_key` 后，用 `wait_for(结果元素)` 或 `take_snapshot()` 确认页面状态，再继续下一步，避免脚本在页面未就绪时操作。
- **异常与弹窗**：操作前可 `handle_dialog(action="accept")` 预设弹窗策略；对懒加载/分页，先滚动或点击下一页再 `wait_for` 新内容。
- **数据与 API**：需要批量取数时，可用 `list_network_requests` / `get_network_request` 抓接口，评估用接口还是页面操作更稳。
- **多店铺一致**：多店铺场景下用 `list_stores`、`connect_store` 切换店铺，在同一流程上验证各站点差异并记录。

配合 **store-rpa-scripting** 技能，可把探索好的步骤整理成文档，再生成不依赖 MCP 的独立 Python 脚本（ziniao_webdriver + nodriver），用于定时任务或本地直接运行。

### 录制与回放

`recorder` 工具提供「录操作 → 停录保存 → 回放或生成脚本」的完整能力，对紫鸟店铺和 Chrome 通用（需先有活动会话）。

| 操作 | 说明 |
|------|------|
| **开始录制** | `recorder(action='start')`：在当前页注入监听，之后在浏览器中的点击、输入、按键、导航都会被记录。**支持跨页**：点击链接导致整页跳转时，会自动在新页重新注入并记录一次 `navigate`。 |
| **停止并保存** | `recorder(action='stop', name='可选名称')`：停止录制，将操作序列保存到 `~/.ziniao/recordings/`，并生成 `.json`（供 MCP 回放）与可独立运行的 `.py` 脚本（基于 nodriver）。 |
| **回放** | `recorder(action='replay', name='录制名称')` 或传入 `actions_json` 直接回放；可用 `speed` 调节回放速度。 |
| **管理** | `recorder(action='list')` 列出已保存录制，`recorder(action='delete', name='...')` 删除指定录制。 |

典型用法：先 `open_store` 或 `launch_chrome` 打开目标页面，再让 Agent 调用 `recorder(action='start')`，你在浏览器里操作一遍，最后 `recorder(action='stop')` 即可得到可复用的脚本与回放数据。

## 典型使用流程

### 基本流程

在 Cursor 中对 Agent 说：

```
打开我的紫鸟店铺列表，打开第一个亚马逊店铺，然后截图看看当前页面
```

Agent 会依次调用：

1. `list_stores` → 获取店铺列表（自动启动客户端）
2. `open_store("xxx")` → 打开店铺并建立 CDP 连接
3. `take_screenshot()` → 截图返回

### 恢复已打开的店铺

```
连接我之前打开的店铺，导航到亚马逊后台
```

Agent 调用：

1. `list_open_stores` → 查看哪些店铺还在运行
2. `connect_store("xxx")` → 恢复 CDP 连接（不重启店铺）
3. `navigate_page("https://sellercentral.amazon.com")` → 导航

### 表单自动化

```
帮我在当前页面填写商品标题和价格
```

Agent 调用：

1. `take_snapshot()` → 获取页面 HTML 分析表单结构
2. `fill_form('[{"selector": "#title", "value": "商品名"}, {"selector": "#price", "value": "99.99"}]')` → 批量填写

## 项目结构

```
ziniao-mcp/
├── .cursor-plugin/
│   └── plugin.json          # Cursor Plugin manifest
├── .mcp.json                # MCP Server 配置（Plugin 自动发现）
├── skills/                  # AI 技能指南
│   ├── ziniao-browser/      # 核心浏览器自动化技能
│   │   └── SKILL.md
│   ├── store-management/    # 多店铺管理技能
│   │   └── SKILL.md
│   ├── amazon-operations/   # 亚马逊运营技能
│   │   └── SKILL.md
│   └── store-rpa-scripting/ # 店铺运营 RPA 脚本生成（探索→确认→生成脚本+过程文档）
│       ├── SKILL.md
│       ├── tools-reference.md
│       ├── doc-template.md
│       └── examples.md
├── agents/                  # 自定义 Agent 角色
│   └── ziniao-operator.md   # 紫鸟运营专家
├── commands/                # 快捷命令
│   ├── quick-check-stores.md
│   └── batch-screenshot.md
├── ziniao_webdriver/        # 紫鸟客户端 HTTP 通信层
│   ├── __init__.py
│   └── client.py            # ZiniaoClient 类
├── ziniao_mcp/              # MCP 服务器
│   ├── __init__.py
│   ├── __main__.py          # python -m ziniao_mcp 入口
│   ├── server.py            # 配置解析 + 工具注册 + 启动
│   ├── session.py           # 会话管理 + CDP 连接 + 状态持久化
│   └── tools/               # MCP 工具集
│       ├── store.py         # 店铺管理 (7)
│       ├── input.py         # 输入自动化 (9)
│       ├── navigation.py    # 导航 (6)
│       ├── emulation.py     # 仿真 (2)
│       ├── network.py       # 网络 (2)
│       └── debug.py         # 调试 (5)
├── config/
│   └── config.yaml          # 默认配置文件
├── docs/                    # 项目文档
│   ├── installation.md      # 安装与使用
│   ├── architecture.md      # 架构设计
│   ├── api-reference.md     # API 参考
│   └── development.md       # 开发指南
├── pyproject.toml
└── README.md
```

## Plugin 组件

### Skills（AI 技能）

| 技能 | 触发场景 |
|------|----------|
| `ziniao-browser` | 浏览器自动化操作、页面交互、截图调试 |
| `store-management` | 多店铺管理、会话恢复、批量操作 |
| `amazon-operations` | 亚马逊 Listing 管理、订单处理、广告分析 |
| `store-rpa-scripting` | RPA 脚本生成：用 MCP 工具探索页面 → 确认步骤 → 生成可独立运行的 Python 脚本（nodriver + ziniao_webdriver）及复现文档 |

### Agents（专用角色）

| Agent | 说明 |
|-------|------|
| `ziniao-operator` | 跨境电商运营专家，具备多平台操作经验和安全意识 |

### Commands（快捷命令）

| 命令 | 说明 |
|------|------|
| `quick-check-stores` | 一键检查所有店铺状态 |
| `batch-screenshot` | 对所有已打开店铺截图 |

## 技术栈

| 组件 | 技术 |
|------|------|
| MCP 协议 | [mcp](https://pypi.org/project/mcp/) (FastMCP) |
| 浏览器自动化 | [nodriver](https://github.com/ultrafunkamsterdam/nodriver) (CDP) |
| 客户端通信 | [requests](https://docs.python-requests.org/) (HTTP) |
| CDP 探测 | [httpx](https://www.python-httpx.org/) (异步) |
| 配置解析 | [PyYAML](https://pyyaml.org/) |
| 包管理 | [uv](https://docs.astral.sh/uv/) + [hatchling](https://hatch.pypa.io/) |

## CDP 调试端口说明

- `open_store` 调用紫鸟的 `startBrowser` API，紫鸟自动为店铺浏览器实例开启 CDP 端口
- MCP 服务器通过 nodriver 的 `Browser.create()` 连接到该端口
- 所有浏览器自动化工具通过此连接操作店铺页面
- 已打开店铺的 CDP 信息持久化在 `~/.ziniao/sessions.json`，支持跨进程恢复

## 文档

| 文档 | 说明 |
|------|------|
| [安装与使用](docs/installation.md) | Plugin / MCP / PyPI 多种安装方式、配置、故障排查 |
| [Windows 下安装 uv](docs/install-uv-windows.md) | 在 Windows 上安装 uv（PowerShell / WinGet / Scoop） |
| [架构设计](docs/architecture.md) | 三层架构、模块职责、数据流 |
| [API 参考](docs/api-reference.md) | 全部 MCP 工具的详细参数和返回值 |
| [开发指南](docs/development.md) | 添加新工具、调试、构建发布、GitHub 自动发布 PyPI |

## 许可证

[MIT](LICENSE)
