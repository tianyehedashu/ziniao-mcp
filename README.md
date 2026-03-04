# ziniao-browser

紫鸟浏览器 AI 自动化工具集 — 让 AI Agent（Cursor、Claude 等）直接操控紫鸟店铺。

参考 [chrome-devtools-mcp](https://github.com/ChromeDevTools/chrome-devtools-mcp) 设计，基于 [紫鸟 WebDriver API](https://open.ziniao.com/docSupport?docId=98) 和 Playwright CDP 实现。以 Cursor Plugin 形式提供 MCP 工具、AI 技能指南、操作规范和快捷命令。

## 特性

- **31 个 MCP 工具**：覆盖店铺管理、页面导航、输入自动化、网络监控、调试截图等场景
- **3 个 AI 技能（Skills）**：浏览器自动化、店铺管理、亚马逊运营的领域知识指南
- **1 个专用 Agent**：紫鸟运营专家角色，具备跨境电商领域知识
- **2 个快捷命令（Commands）**：一键检查店铺状态、批量截图
- **跨会话状态持久化**：MCP 进程重启后可自动恢复已打开店铺的 CDP 连接
- **多店铺并行**：同时打开多个店铺，按需切换活动会话
- **跨平台**：支持 Windows / macOS / Linux

## 前提

- 开通紫鸟账号 WebDriver 权限：[如何开通](https://open.ziniao.com/docSupport?docId=99)
- Python 3.10+
- [uv](https://docs.astral.sh/uv/) 包管理器

## 快速开始

```bash
git clone https://github.com/tianyehedashu/ziniao-mcp.git
cd ziniao-mcp
uv sync
uv run playwright install chromium
```

在 Cursor 中打开项目目录，插件自动加载。配置环境变量后即可使用：

| 环境变量 | 说明 |
|----------|------|
| `ZINIAO_COMPANY` | 企业名 |
| `ZINIAO_USERNAME` | 用户名 |
| `ZINIAO_PASSWORD` | 密码 |
| `ZINIAO_CLIENT_PATH` | 客户端路径（如 `D:\ziniao\ziniao.exe`） |

> 完整安装说明（Plugin / MCP / PyPI / Claude Desktop 等多种方式）请参见 [安装与使用文档](docs/installation.md)。

### 开发任务脚本

项目根目录提供统一入口，方便执行常用命令：

| 方式 | 用法示例 |
|------|----------|
| **Makefile**（需安装 make） | `make install` / `make run` / `make test` / `make upgrade` |
| **PowerShell**（Windows） | `.\task.ps1 install` / `.\task.ps1 run` / `.\task.ps1 test` / `.\task.ps1 upgrade` |

`make help` 或 `.\task.ps1 help` 可查看全部任务；集成测试需先配置 `.env`，对应任务为 `make test-integration` / `.\task.ps1 test-integration`。

## 工具列表

### 店铺管理（7 个）

| 工具 | 说明 |
|------|------|
| `start_client` | 启动紫鸟客户端（WebDriver 模式） |
| `list_stores` | 获取所有店铺列表（自动启动客户端） |
| `list_open_stores` | 查询当前已打开的店铺（通过 CDP 端口验证） |
| `open_store` | 打开店铺并建立 CDP 连接 |
| `connect_store` | 连接已运行的店铺（不重启，推荐） |
| `close_store` | 关闭店铺并断开 CDP |
| `stop_client` | 退出紫鸟客户端 |

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
│   └── amazon-operations/   # 亚马逊运营技能
│       └── SKILL.md
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
| 浏览器自动化 | [Playwright](https://playwright.dev/python/) (CDP) |
| 客户端通信 | [requests](https://docs.python-requests.org/) (HTTP) |
| CDP 探测 | [httpx](https://www.python-httpx.org/) (异步) |
| 配置解析 | [PyYAML](https://pyyaml.org/) |
| 包管理 | [uv](https://docs.astral.sh/uv/) + [hatchling](https://hatch.pypa.io/) |

## CDP 调试端口说明

- `open_store` 调用紫鸟的 `startBrowser` API，紫鸟自动为店铺浏览器实例开启 CDP 端口
- MCP 服务器通过 Playwright 的 `connect_over_cdp()` 连接到该端口
- 所有浏览器自动化工具通过此连接操作店铺页面
- 已打开店铺的 CDP 信息持久化在 `~/.ziniao/sessions.json`，支持跨进程恢复

## 文档

| 文档 | 说明 |
|------|------|
| [安装与使用](docs/installation.md) | Plugin / MCP / PyPI 多种安装方式、配置、故障排查 |
| [Windows 下安装 uv](docs/install-uv-windows.md) | 在 Windows 上安装 uv（PowerShell / WinGet / Scoop） |
| [架构设计](docs/architecture.md) | 三层架构、模块职责、数据流 |
| [API 参考](docs/api-reference.md) | 31 个 MCP 工具的详细参数和返回值 |
| [开发指南](docs/development.md) | 添加新工具、调试、构建发布、GitHub 自动发布 PyPI |

## 许可证

[MIT](LICENSE)
