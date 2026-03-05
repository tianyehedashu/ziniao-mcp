# 安装与使用

ziniao-browser 提供 MCP 工具（31 个）和 Cursor Plugin 两种使用形态，按需选择。

## 前提条件

- [紫鸟浏览器客户端](https://www.ziniao.com/)，并**开启 WebDriver 权限**（[开通说明](https://open.ziniao.com/docSupport?docId=99)）
- [Cursor IDE](https://cursor.com/) 或支持 MCP 的其他客户端

### WebDriver 模式说明

紫鸟客户端有两种运行模式：

| 模式 | 启动方式 | HTTP API | 自动化支持 |
|------|----------|----------|------------|
| **普通模式** | 双击桌面图标 | 不可用 | 不支持 |
| **WebDriver 模式** | 带 `--run_type=web_driver` 参数启动 | 可用 | 支持 |

**最佳实践：始终以 WebDriver 模式启动。** WebDriver 模式下的客户端功能与普通模式完全一致，日常操作不受影响，同时支持 MCP 自动化。紫鸟是**单实例应用**，无需也不能同时运行两个实例。

MCP 的 `start_client` 工具会以 WebDriver 模式启动客户端。如果检测到普通模式实例正在运行，会**自动终止并以 WebDriver 模式重启**。

## 安装方式

### 方式一：通过 uvx 安装（推荐，最简单）

无需 Python、无需 git，只需安装 [uv](https://docs.astral.sh/uv/)。所有 Python 依赖（含 Playwright）由 uvx 自动管理。

> 此方式只包含 MCP Server（31 个工具），不含 Rules / Skills / Agents 等插件组件。如需完整 AI 增强体验请用方式二。

**1. 安装 uv**

```bash
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

> Windows 用户也可参考 [Windows 下安装 uv](install-uv-windows.md)。

**2.（可选）安装 Playwright Chromium**

```bash
uvx playwright install chromium
```

> 本 MCP 通过 CDP 连接紫鸟客户端已打开的浏览器，不会自行启动 Chromium，大多数场景可跳过此步。建议首次安装时执行一次以确保兼容性。

**3. 在 MCP 客户端中配置**

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

> **端口说明**：`ZINIAO_SOCKET_PORT` 通常**无需配置**。MCP 启动时会自动检测运行中的紫鸟客户端端口（通过扫描进程命令行参数 `--port=XXXXX`）。如果客户端未运行且未配置端口，默认使用 `16851`。仅在自动检测不准确时才需要手动指定。

各客户端的配置方式：

| 客户端 | 配置方式 |
|--------|----------|
| **Cursor** | `Cursor Settings → MCP → New MCP Server`，粘贴上方 JSON |
| **Claude Desktop** | 编辑 `claude_desktop_config.json`（macOS: `~/Library/Application Support/Claude/`，Windows: `%APPDATA%\Claude\`） |
| **VS Code / Copilot** | MCP 扩展设置，或 `.vscode/mcp.json` |

配置完成后在 Cursor 中运行 `列出我所有的紫鸟店铺` 验证是否正常。

**4. 版本与更新**

- 查看版本：`uvx ziniao-mcp -V`
- 刷新到最新版：`uvx --refresh ziniao-mcp --help`，然后重启 Cursor MCP



### 方式二：作为 Cursor Plugin 安装（完整 AI 增强）

Plugin 模式会同时加载 MCP 工具 + Rules + Skills + Agents + Commands，提供完整 AI 增强体验。需要 git 和 [uv](https://docs.astral.sh/uv/)。

**1. 克隆并安装依赖**

```bash
# 建议克隆到用户级目录，任意项目可复用
# Windows (PowerShell)
git clone https://github.com/tianyehedashu/ziniao-mcp.git $env:USERPROFILE\.cursor\plugins\ziniao-mcp
cd $env:USERPROFILE\.cursor\plugins\ziniao-mcp

# macOS / Linux
# git clone https://github.com/tianyehedashu/ziniao-mcp.git ~/.cursor/plugins/ziniao-mcp
# cd ~/.cursor/plugins/ziniao-mcp

uv sync
uv run playwright install chromium  # 可选，同方式一说明
```

**2. 在 Cursor 中加载插件**

- **用户级（推荐，任意项目可用）**
  在 `Cursor Settings → MCP → New MCP Server` 中添加，`--directory` 指向克隆路径：

  ```json
  {
    "mcpServers": {
      "ziniao": {
        "command": "uv",
        "args": ["run", "--directory", "C:\\Users\\你的用户名\\.cursor\\plugins\\ziniao-mcp", "python", "-m", "ziniao_mcp"],
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

  若还需 Rules / Skills / Agents 在当前工作区生效，可将插件目录以「添加文件夹到工作区」方式加入。

- **项目级**
  在 Cursor 中直接打开插件目录，自动识别 `.cursor-plugin/plugin.json` 并加载全部组件，仅在该工作区内生效。

## 插件组件说明

通过方式二安装后，以下组件会自动加载：

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

### Skills（AI 技能）

| 技能 | 触发场景 | 手动触发 |
|------|----------|----------|
| `ziniao-browser` | 浏览器自动化、页面交互 | `/ziniao-browser` |
| `store-management` | 多店铺管理、会话恢复 | `/store-management` |
| `amazon-operations` | 亚马逊后台操作 | `/amazon-operations` |
| `tiktok-operations` | TikTok Shop 后台操作 | `/tiktok-operations` |

### Agents & Commands

| 类型 | 名称 | 说明 |
|------|------|------|
| Agent | `ziniao-operator` | 紫鸟运营专家，具备跨境电商领域知识 |
| Command | `quick-check-stores` | 一键检查所有店铺状态 |
| Command | `batch-screenshot` | 批量截取已打开店铺的当前页面 |

## 配置

### 配置优先级

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
| HTTP 端口 | `ZINIAO_SOCKET_PORT` | `--socket-port` | `ziniao.browser.socket_port` | 自动检测，检测不到则 `16851` |
| 版本 | `ZINIAO_VERSION` | `--version` | `ziniao.browser.version` | `v6` |

### config.yaml 示例

```yaml
ziniao:
  browser:
    version: v6
    client_path: D:\ziniao\ziniao.exe
    # socket_port: 16851  # 可选，不配置时自动检测
  user_info:
    company: 您的企业名
    username: 您的用户名
    password: 您的密码
```

## 快速上手

安装完成后，在 Cursor 中尝试以下对话：

```
列出我所有的紫鸟店铺
```

```
打开第一个亚马逊店铺，截图看看当前页面
```

```
连接我之前打开的店铺，导航到亚马逊卖家后台
```

```
帮我在当前页面找到商品标题输入框，填写 "新商品名称"
```

## 故障排查

### MCP Server 未启动

Cursor Settings 中 ziniao 服务器显示为离线。

1. 确认 uv 已安装：`uv --version`
2. 手动运行测试：`uvx ziniao-mcp --help`（方式一）或 `uv run ziniao-mcp --help`（方式二）
3. 检查环境变量是否正确配置
4. 方式一用户若怀疑是旧版本缓存导致：执行 `uvx --refresh ziniao-mcp` 拉取最新版后再试

### 工具调用超时 / Aborted

heartbeat 或工具调用一直卡住最终超时。

1. **v0.1.13+ 已支持自动检测端口**：通常无需手动配置 `ZINIAO_SOCKET_PORT`。MCP 会扫描运行中的紫鸟进程命令行自动发现端口
2. 如果自动检测失败，手动确认客户端实际端口：
   - Windows：在 PowerShell 中运行 `Get-Process -Name "ziniao" | ForEach-Object { (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine }` 查找 `--port=XXXXX`
   - macOS/Linux：`ps aux | grep ziniao | grep -- --port`
3. 在 MCP 配置的 `env` 中设置正确的端口：`"ZINIAO_SOCKET_PORT": "实际端口号"`
4. **紫鸟是单实例应用**：如果客户端已在端口 A 运行，配置端口 B 会导致连接失败且无法启动新实例。v0.1.13+ 已自动处理此场景

### 客户端以普通模式运行

报错"紫鸟客户端正在运行，但未启用 WebDriver 模式"。

这表示紫鸟客户端是通过桌面图标等方式以**普通模式**启动的，HTTP API 端口未开放。

**解决方法（任选其一）：**

1. **使用 `start_client` 工具**（推荐）：MCP 会自动终止普通模式进程并以 WebDriver 模式重启
2. **手动操作**：关闭紫鸟客户端，然后在命令行启动：
   ```bash
   # Windows
   "D:\soft\ziniao-v6\ziniao.exe" --run_type=web_driver --ipc_type=http --port=16851
   ```
3. **养成习惯**：日常也以 WebDriver 模式启动客户端，功能完全一致且支持自动化（参见[前提条件 - WebDriver 模式说明](#webdriver-模式说明)）

### 店铺连接失败

`open_store` 或 `connect_store` 返回错误。

1. 确认紫鸟客户端路径正确（`ZINIAO_CLIENT_PATH`）
2. 确认账号信息正确（企业名、用户名、密码）
3. 确认已开通 WebDriver 权限
4. 检查紫鸟客户端是否可以手动启动

### CDP 连接断开

页面操作工具返回连接错误。

1. 使用 `list_open_stores` 查看店铺状态
2. 使用 `connect_store` 尝试恢复连接
3. 持续失败时清理状态文件后重试：
   - Windows: `del %USERPROFILE%\.ziniao\sessions.json`
   - macOS/Linux: `rm ~/.ziniao/sessions.json`

### Rules 或 Skills 未加载

仅使用方式二时相关。确认在 Cursor 中打开的是插件项目根目录或已将插件目录加入工作区，检查 `Cursor Settings → Rules` 中是否显示 ziniao 相关规则。

## 更多文档

- [Windows 下安装 uv](install-uv-windows.md) — PowerShell / WinGet / Scoop 安装 uv
- [架构设计](architecture.md) — 三层架构、模块职责、数据流
- [API 参考](api-reference.md) — 31 个 MCP 工具的详细参数和返回值
- [开发指南](development.md) — 添加新工具、调试、发布
