# 安装与使用

ziniao-browser 以 [Cursor Plugin](https://cursor.com/cn/docs/plugins) 形式分发，安装后可在 Cursor IDE、CLI 和 Cloud 中使用。插件包含 MCP 工具、AI 技能指南、操作规则、专用 Agent 和快捷命令。

## 前提条件

- [紫鸟浏览器客户端](https://www.ziniao.com/)，已开通 WebDriver 权限（[如何开通](https://open.ziniao.com/docSupport?docId=99)）
- Python 3.10+
- [uv](https://docs.astral.sh/uv/) 包管理器
- [Cursor IDE](https://cursor.com/) 或支持 MCP 的其他客户端

## 安装方式

### 方式一：作为 Cursor Plugin 安装（推荐）

Plugin 模式会同时加载 MCP 工具 + Rules + Skills + Agents + Commands，提供完整的 AI 增强体验。

**步骤 1：克隆仓库**

```bash
git clone https://github.com/ziniao/ziniao-browser.git
cd ziniao-browser
```

**步骤 2：安装 Python 依赖**

```bash
uv sync
```

**步骤 3：安装 Playwright 浏览器驱动**

```bash
uv run playwright install chromium
```

**步骤 4：在 Cursor 中加载插件**

在 Cursor 中打开克隆下来的项目目录。Cursor 会自动识别 `.cursor-plugin/plugin.json` 并加载所有插件组件。

**步骤 5：配置环境变量**

在 Cursor Settings 中或系统环境变量中设置：

| 环境变量 | 说明 | 示例 |
|----------|------|------|
| `ZINIAO_COMPANY` | 企业名 | `我的公司` |
| `ZINIAO_USERNAME` | 用户名 | `admin` |
| `ZINIAO_PASSWORD` | 密码 | `xxx` |
| `ZINIAO_CLIENT_PATH` | 客户端可执行文件路径 | `D:\ziniao\ziniao.exe` |

**步骤 6：验证安装**

在 Cursor 中检查以下内容：

1. **MCP 工具**：打开 `Cursor Settings → Features → Model Context Protocol`，确认 `ziniao` 服务器已启用
2. **Rules**：打开 `Cursor Settings → Rules`，确认 `ziniao-workflow` 和 `store-safety` 规则已加载
3. **Skills**：在对话中输入 `/ziniao-browser` 可手动触发浏览器自动化技能

### 方式二：仅安装 MCP Server

如果你只需要 MCP 工具而不需要 Rules/Skills 等 AI 增强组件，可以单独配置 MCP Server。

进入 `Cursor Settings → MCP → New MCP Server`，填入以下配置：

```json
{
  "mcpServers": {
    "ziniao": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/ziniao-browser", "ziniao-mcp"],
      "env": {
        "ZINIAO_COMPANY": "我的公司",
        "ZINIAO_USERNAME": "admin",
        "ZINIAO_PASSWORD": "xxx",
        "ZINIAO_CLIENT_PATH": "D:\\ziniao\\ziniao.exe"
      }
    }
  }
}
```

> 将 `/path/to/ziniao-browser` 替换为实际的项目路径。

### 方式三：通过 PyPI 安装

无需克隆仓库，通过 `uvx` 或 `pip` 直接使用 MCP Server。

> **前提条件**：通过 PyPI 安装只包含 MCP Server（31 个工具），不含 Rules / Skills / Agents / Commands 等 Plugin 组件。如需完整 AI 增强体验，请使用方式一。

**前提**：

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)（推荐）或 pip
- Playwright Chromium 驱动

**安装并运行**：

```bash
# 方式 A：uvx 免安装直接运行（推荐）
uvx ziniao-mcp --help

# 方式 B：pip 安装
pip install ziniao-mcp
ziniao-mcp --help
```

> 首次使用需安装 Playwright 浏览器驱动：`playwright install chromium`

**在 MCP 客户端中配置**（Cursor / Claude Desktop / VS Code 等通用）：

```json
{
  "mcpServers": {
    "ziniao": {
      "command": "uvx",
      "args": ["ziniao-mcp"],
      "env": {
        "ZINIAO_COMPANY": "我的公司",
        "ZINIAO_USERNAME": "admin",
        "ZINIAO_PASSWORD": "xxx",
        "ZINIAO_CLIENT_PATH": "D:\\ziniao\\ziniao.exe"
      }
    }
  }
}
```

各客户端的配置文件位置：

| 客户端 | 配置方式 |
|--------|----------|
| **Cursor** | `Cursor Settings → MCP → New MCP Server` |
| **Claude Desktop** | 编辑 `claude_desktop_config.json`（macOS: `~/Library/Application Support/Claude/`，Windows: `%APPDATA%\Claude\`） |
| **VS Code / Copilot** | MCP 扩展设置，或 `.vscode/mcp.json` |
| **其他 MCP 客户端** | 参照各客户端文档，使用上述 JSON 配置 |

## 插件组件说明

安装为 Cursor Plugin 后，以下组件会自动加载：

### MCP 工具（31 个）

提供完整的浏览器自动化能力，详见 [API 参考](api-reference.md)。

| 分类 | 数量 | 说明 |
|------|------|------|
| 店铺管理 | 7 | 启动客户端、列出/打开/关闭/连接店铺 |
| 输入自动化 | 9 | 点击、填写、拖拽、按键、上传文件等 |
| 导航 | 6 | URL 导航、标签页管理、等待加载 |
| 仿真 | 2 | 设备模拟、视口调整 |
| 网络 | 2 | 请求列表、请求详情 |
| 调试 | 5 | JS 执行、截图、HTML 快照、控制台消息 |

### Rules（操作规则）

以 `alwaysApply: true` 模式自动生效，AI Agent 在每次对话中都会遵循这些规则。

| 规则 | 作用 |
|------|------|
| `ziniao-workflow` | 标准操作流程：连接 → 快照 → 操作 → 验证 |
| `store-safety` | 安全约束：操作确认、批量限制、敏感操作授权 |

### Skills（AI 技能）

AI Agent 会根据任务自动选择合适的技能，也可通过 `/skill-name` 手动触发。

| 技能 | 触发场景 | 手动触发 |
|------|----------|----------|
| `ziniao-browser` | 浏览器自动化、页面交互 | `/ziniao-browser` |
| `store-management` | 多店铺管理、会话恢复 | `/store-management` |
| `amazon-operations` | 亚马逊后台操作 | `/amazon-operations` |

### Agents（专用角色）

| Agent | 说明 |
|-------|------|
| `ziniao-operator` | 紫鸟运营专家，具备跨境电商领域知识和安全操作意识 |

### Commands（快捷命令）

| 命令 | 说明 |
|------|------|
| `quick-check-stores` | 一键检查所有店铺状态（客户端、CDP 连通性） |
| `batch-screenshot` | 批量截取已打开店铺的当前页面 |

## 配置

### 配置优先级

支持三种配置方式，优先级从高到低：

```
环境变量 (ZINIAO_*)     ← 最高优先级，推荐用于 MCP 集成
    ↓
命令行参数 (--company)  ← 适合手动运行和调试
    ↓
config.yaml             ← 适合本地开发
```

### 完整配置项

| 配置项 | 环境变量 | 命令行参数 | config.yaml 路径 | 默认值 |
|--------|----------|------------|------------------|--------|
| 企业名 | `ZINIAO_COMPANY` | `--company` | `ziniao.user_info.company` | — |
| 用户名 | `ZINIAO_USERNAME` | `--username` | `ziniao.user_info.username` | — |
| 密码 | `ZINIAO_PASSWORD` | `--password` | `ziniao.user_info.password` | — |
| 客户端路径 | `ZINIAO_CLIENT_PATH` | `--client-path` | `ziniao.browser.client_path` | — |
| HTTP 端口 | `ZINIAO_SOCKET_PORT` | `--socket-port` | `ziniao.browser.socket_port` | `16851` |
| 版本 | `ZINIAO_VERSION` | `--version` | `ziniao.browser.version` | `v6` |

### config.yaml 示例

```yaml
ziniao:
  browser:
    version: v6
    client_path: D:\ziniao\ziniao.exe
    socket_port: 16851
  user_info:
    company: 您的企业名
    username: 您的用户名
    password: 您的密码
```

## 快速上手

安装完成后，在 Cursor 中尝试以下对话：

### 查看店铺列表

```
列出我所有的紫鸟店铺
```

### 打开店铺并截图

```
打开第一个亚马逊店铺，截图看看当前页面
```

### 恢复已打开的店铺

```
连接我之前打开的店铺，导航到亚马逊卖家后台
```

### 表单自动化

```
帮我在当前页面找到商品标题输入框，填写 "新商品名称"
```

### 批量操作

```
检查所有已打开店铺的状态
```

## 故障排查

### MCP Server 未启动

**现象**：Cursor Settings 中 ziniao 服务器显示为离线。

**排查**：

1. 确认 Python 和 uv 已安装：`uv --version`
2. 确认依赖已安装：`uv sync`
3. 确认 Playwright 驱动已安装：`uv run playwright install chromium`
4. 手动启动测试：`uv run ziniao-mcp --help`
5. 检查环境变量是否正确配置

### 店铺连接失败

**现象**：`open_store` 或 `connect_store` 返回错误。

**排查**：

1. 确认紫鸟客户端路径正确（`ZINIAO_CLIENT_PATH`）
2. 确认账号信息正确（企业名、用户名、密码）
3. 确认已开通 WebDriver 权限
4. 检查紫鸟客户端是否可以手动启动

### CDP 连接断开

**现象**：页面操作工具返回连接错误。

**排查**：

1. 使用 `list_open_stores` 查看店铺状态
2. 使用 `connect_store` 尝试恢复连接
3. 如果持续失败，清理状态文件后重试：
   - Windows: `del %USERPROFILE%\.ziniao\sessions.json`
   - macOS/Linux: `rm ~/.ziniao/sessions.json`

### Rules 或 Skills 未加载

**现象**：AI Agent 不遵循操作规范，或技能不可用。

**排查**：

1. 确认在 Cursor 中打开的是插件项目根目录
2. 检查 `Cursor Settings → Rules` 中是否显示 ziniao 相关规则
3. 重启 Cursor 后重试

## 更多文档

- [架构设计](architecture.md) — 三层架构、模块职责、数据流
- [API 参考](api-reference.md) — 31 个 MCP 工具的详细参数和返回值
- [开发指南](development.md) — 添加新工具、调试、发布
