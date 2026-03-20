# ziniao

紫鸟与 Chrome 浏览器 AI 自动化 — 让 AI Agent（Cursor、Claude 等）操控紫鸟店铺与本地 Chrome，统一会话、统一工具。

**GitHub**：[https://github.com/tianyehedashu/ziniao-mcp](https://github.com/tianyehedashu/ziniao-mcp)

**PyPI 包名**：[`ziniao`](https://pypi.org/project/ziniao/)（与仓库名 `ziniao-mcp` 不同；控制台命令为 `ziniao`，另提供 `ziniao-mcp` 作为 `python -m ziniao_mcp` 的兼容入口）。

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

如需指定 Chrome 路径或复用浏览器状态（登录态、Cookie 等），可添加环境变量：

```json
{
  "mcpServers": {
    "ziniao": {
      "command": "ziniao",
      "args": ["serve"],
      "env": {
        "CHROME_PATH": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        "CHROME_USER_DATA": "E:/my-project/.chrome-profile"
      }
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

**Chrome 环境变量**（可选，紫鸟配置和 Chrome 配置可同时使用）：

| 环境变量 | 说明 |
|----------|------|
| `CHROME_PATH` | Chrome 可执行文件路径。不设置时自动检测（注册表 > 常见路径 > PATH） |
| `CHROME_USER_DATA` | Chrome 用户数据目录（profile）。设置后可复用登录态、Cookie、扩展等状态。不设置时使用 `~/.ziniao/chrome-profile` |
| `CHROME_CDP_PORT` | （可选）Chrome CDP 调试端口，不设置时自动分配 |

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

> **版本**：`ziniao --help`。升级 CLI：优先 `ziniao update`（从 PyPI 升级；**Windows** 下默认会**新开控制台、延迟约 2 秒后执行 uv**，并让当前进程立即退出，从而避免 **`ziniao.exe` 自占用**导致的错误 32；需要在本终端同步执行并得到退出码时用 `ziniao update --sync`）。若要从 **GitHub `main`** 安装，使用 `ziniao update --git`。升级后请 **`ziniao quit`** 并新开终端，使用 MCP 时**重启 Cursor MCP**。若仍有**其它进程**占用 `ziniao.exe`（多开终端、Cursor MCP 等），请先关闭后再试；失败时 `ziniao update` 会打印可复制的 `uv` 命令。
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

已安装后升级（需本机 PATH 中有 `uv`）：

```bash
ziniao update              # PyPI 最新版（Windows 默认新窗口延迟安装并退出本进程）
ziniao update --sync       # 在当前进程同步执行 uv（脚本/CI；Win 上可能遇 exe 占用）
ziniao update --git        # GitHub 仓库 main 最新提交
ziniao update --dry-run    # 仅打印将执行的 uv 命令（可在另一终端手动执行）
```

安装后会在 uv 工具目录生成 `ziniao` 可执行文件。若终端提示「无法将 ziniao 项识别为…」，请将 uv 工具目录加入 PATH：

- 查看工具目录：`uv tool dir`（Windows 常见为 `%APPDATA%\uv\tools` 或 `%USERPROFILE%\.local\bin`）
- 将该目录加入 [用户环境变量 Path](https://learn.microsoft.com/zh-cn/windows/win32/procthread/environment-variables)  
新开终端后即可直接运行 `ziniao --help`、`ziniao serve` 等。

### 快速配置（ziniao config）

安装后可通过交互式向导一键生成全局配置，CLI 和 MCP Server 共享：

```bash
ziniao config init          # 交互式向导 → 生成 ~/.ziniao/config.yaml 和 .env
ziniao config show          # 查看当前生效配置及来源
ziniao config set chrome.executable_path "C:\Program Files\Google\Chrome\Application\chrome.exe"
ziniao config env --shell mcp   # 输出可粘贴到 mcp.json 的 env 配置
```

向导会自动检测 Chrome 路径，询问是否配置紫鸟，然后生成两个文件：

- `~/.ziniao/config.yaml` — 全局配置（CLI daemon + MCP Server 自动读取）
- `~/.ziniao/.env` — 环境变量版本（自动加载，也可复制到 MCP json `env` 中）

**配置优先级**：环境变量 > CLI 参数 > `~/.ziniao/.env` > 项目 `config/config.yaml` > `~/.ziniao/config.yaml`

**仅用 Chrome（零配置）**：不需要任何配置，直接 `ziniao launch` 即可。Chrome 路径自动检测。

**Chrome + 状态复用**：设置 `user_data_dir` 即可跨次启动复用登录态、Cookie、扩展：

```bash
ziniao config set chrome.user_data_dir "C:\Users\你的用户名\.ziniao\chrome-profile"
```

**紫鸟 + Chrome 全功能**：`ziniao config init` 向导中选择配置紫鸟即可。

## CLI 命令行工具

除了 MCP 工具（给 AI Agent 用），ziniao 还提供完整的命令行界面，可在终端直接操控浏览器。首次执行任意命令时会自动启动后台 daemon。

### 全局选项

```bash
ziniao [全局选项] <命令> [参数]
```

| 选项 | 说明 |
|------|------|
| `--store <id>` | 指定目标紫鸟店铺（不切换活动会话）；与 `--session` 互斥 |
| `--session <id>` | 指定目标会话（店铺或 Chrome）；与 `--store` 互斥 |
| `--json` | 机器可读 JSON，固定信封 `{"success": bool, "data": object\|null, "error": string\|null}`（与 agent-browser CLI 一致）；成功时 `data` 为 daemon 返回体 |
| `--json-legacy` | 输出 daemon 原始 JSON 对象（无信封）；与 `--json` / `--llm` 互斥；适用于依赖旧输出的脚本 |
| `--llm` | 等价启用 JSON 信封，并附加 **`meta`**（字段名列表、快照/批量说明等），便于大模型与 Agent 解析 |
| `--plain` | 关闭 Rich：stdout 为 UTF-8 JSON（成功为 daemon 字典，失败为 `success`+`error`）；与 `--json`/`--llm` 同时使用时仍以信封 JSON 为准 |
| `--timeout <秒>` | 命令超时；`0` 表示自动（navigate/click/snapshot/screenshot 等慢命令 120s，其余 60s） |
| `--help` | 查看帮助；根命令底部会列出上述全局选项摘要 |

详见 [docs/cli-json.md](docs/cli-json.md)、[docs/cli-llm.md](docs/cli-llm.md)。

### 命令概览

#### 店铺管理 `store`

```bash
ziniao store list [--opened-only]        # 列出店铺
ziniao store open <store_id>             # 打开店铺
ziniao store close <store_id>            # 关闭店铺
ziniao store start-client                # 启动紫鸟客户端
ziniao store stop-client                 # 停止紫鸟客户端
```

> 顶层快捷：`ziniao list-stores`、`ziniao open-store <id>`、`ziniao close-store <id>`

#### Chrome 管理 `chrome`

```bash
ziniao chrome launch [--url <url>] [--name <名称>]    # 启动 Chrome
ziniao chrome connect <cdp_port> [--name <名称>]      # 连接已有 Chrome
ziniao chrome list                                     # 列出 Chrome 会话
ziniao chrome close <session_id>                       # 关闭 Chrome 会话
```

> 顶层快捷：`ziniao launch`、`ziniao connect <port>`

**launch vs connect**：`launch` 由 ziniao 启动 Chrome 进程，`close` 时会终止该进程；`connect` 连接外部已有 Chrome，`close` 时仅断开 CDP 连接，不杀进程。若 `launch` 检测到 profile 已被占用（如 Chrome 已在运行），会自动降级为 connect 模式。

Chrome 路径和 profile 目录通过环境变量 `CHROME_PATH` / `CHROME_USER_DATA` 配置（见上方环境变量表），设置 `CHROME_USER_DATA` 可跨次启动复用登录态和 Cookie。

#### 会话管理 `session`

```bash
ziniao session list                      # 列出所有会话（紫鸟 + Chrome）
ziniao session switch <session_id>       # 切换活动会话
ziniao session info <session_id>         # 查看会话详情
```

#### 导航 `nav`

```bash
ziniao nav go <url>                      # 导航到 URL
ziniao nav tab list                      # 标签页列表
ziniao nav tab new [url]                 # 新建标签页
ziniao nav tab switch --index <i>        # 切换标签页
ziniao nav tab close                     # 关闭当前标签页
ziniao nav frame list                    # iframe 列表
ziniao nav wait <selector>               # 等待元素
ziniao nav back                          # 后退
ziniao nav forward                       # 前进
ziniao nav reload [--ignore-cache]       # 刷新
```

> 顶层快捷：`ziniao navigate <url>`、`ziniao tab`、`ziniao wait`、`ziniao back`、`ziniao forward`、`ziniao reload`

#### 页面交互 `act`

```bash
ziniao act click <selector>              # 点击
ziniao act fill <selector> <value>       # 填写输入框
ziniao act type <text> [-s <selector>]   # 逐字输入
ziniao act press <key>                   # 按键（Enter, Tab, Ctrl+a 等）
ziniao act hover <selector>              # 悬停
ziniao act dblclick <selector>           # 双击
ziniao act drag <source> <target>        # 拖拽
ziniao act upload <selector> <file...>   # 上传文件
ziniao act dialog [accept|dismiss]       # 弹窗处理
ziniao act focus <selector>              # 聚焦
ziniao act select <selector> <value>     # 下拉选择
ziniao act check <selector>              # 勾选
ziniao act uncheck <selector>            # 取消勾选
ziniao act keydown <key>                 # 按下键
ziniao act keyup <key>                   # 释放键
```

> 顶层快捷：`ziniao click`、`ziniao fill`、`ziniao type`、`ziniao press`、`ziniao hover`、`ziniao dblclick`

#### 页面信息 `info`

```bash
ziniao info snapshot [-o file.html]      # HTML 快照
ziniao info screenshot [file.png]        # 截图
ziniao info eval <js_expression>         # 执行 JavaScript
ziniao info url                          # 当前 URL
ziniao info console [--level error]      # 控制台消息
ziniao info network [--id <id>]          # 网络请求
ziniao info errors                       # 页面错误
ziniao info highlight <selector>         # 高亮元素
ziniao info cookies [--action list|set|clear]   # Cookie 管理
ziniao info storage [--type local|session]      # Storage 管理
ziniao info clipboard [--action read|write]     # 剪贴板
```

> 顶层快捷：`ziniao snapshot`、`ziniao screenshot`、`ziniao eval`、`ziniao url`

#### 获取元素信息 `get`

```bash
ziniao get text <selector>               # 元素文本
ziniao get html <selector>               # 元素 HTML
ziniao get value <selector>              # 输入框值
ziniao get attr <selector> <attribute>   # 元素属性
ziniao get title                         # 页面标题
ziniao get url                           # 页面 URL
ziniao get count <selector>              # 匹配元素数量
```

> 顶层快捷：`ziniao title`、`ziniao url`（即 `get title` / `get url`）

#### 查找元素 `find`

```bash
ziniao find text <文本> [--action click]       # 按文本查找
ziniao find role <角色> [--name <名称>]        # 按 ARIA 角色查找
ziniao find first <selector>                   # 第一个匹配元素
ziniao find last <selector>                    # 最后一个匹配元素
ziniao find nth <selector> --index <n>         # 第 N 个匹配元素
```

#### 状态检查 `is`

```bash
ziniao is visible <selector>             # 是否可见
ziniao is enabled <selector>             # 是否可用
ziniao is checked <selector>             # 是否选中
```

#### 滚动 `scroll`

```bash
ziniao scroll down [--pixels 300]        # 向下滚动
ziniao scroll up [--pixels 300]          # 向上滚动
ziniao scroll left / right               # 左右滚动
ziniao scroll into <selector>            # 滚动到元素
```

> 顶层快捷：`ziniao scrollinto <selector>`

#### 鼠标 `mouse`

```bash
ziniao mouse move <x> <y>               # 移动到坐标
ziniao mouse down [--button left|right]  # 按下
ziniao mouse up [--button left|right]    # 释放
ziniao mouse wheel --delta-y <n>         # 滚轮
```

#### 网络拦截 `network`

```bash
ziniao network list [--filter <pattern>] # 请求列表
ziniao network list --id <request_id>    # 请求详情
ziniao network route <pattern> --abort   # 拦截请求
ziniao network unroute [<pattern>]       # 移除拦截
ziniao network routes                    # 查看拦截规则
ziniao network har-start                 # 开始 HAR 录制
ziniao network har-stop [<file>]         # 停止并保存 HAR
```

#### 录制回放 `rec`

```bash
ziniao rec start                         # 开始录制
ziniao rec stop [--name <名称>]          # 停止并保存
ziniao rec replay <名称> [--speed 1.0]   # 回放
ziniao rec list                          # 列出录制
ziniao rec delete <名称>                 # 删除录制
```

#### 批量执行 `batch`

```bash
echo '[{"command":"navigate","args":{"url":"https://example.com"}}]' | ziniao batch run
```

从 stdin 读取 JSON 命令数组，依次执行。配合 `--bail` 可在首个错误时停止。

#### 系统 `sys`

```bash
ziniao sys quit                          # 关闭 daemon
ziniao sys emulate --device "iPhone 15"  # 设备模拟
ziniao sys emulate --width 800 --height 600   # 自定义视口
```

> 顶层快捷：`ziniao quit`、`ziniao emulate`

#### 配置管理 `config`

```bash
ziniao config init [--force]             # 交互式向导 → 生成 ~/.ziniao/config.yaml
ziniao config show                       # 显示当前生效配置及来源
ziniao config set <key> <value>          # 修改配置（dotted key: chrome.path）
ziniao config path                       # 显示配置文件路径
ziniao config env [--shell powershell|bash|json|mcp]  # 输出环境变量导出语句
```

#### 升级 `update`

```bash
ziniao update [--git] [--sync] [--dry-run]  # 用 uv 升级 CLI（Windows 默认新窗口避免 exe 自占用）
```

#### MCP 服务 `serve`

```bash
ziniao serve [--config config.yaml]      # 启动 MCP Server
```

### 常用示例

```bash
# 启动 Chrome 并打开百度
ziniao launch --url https://www.baidu.com

# 连接已有 Chrome（需以 --remote-debugging-port 启动）
ziniao connect 9222

# 查看当前所有会话
ziniao session list

# 导航、交互、获取信息
ziniao navigate https://example.com
ziniao click "button.submit"
ziniao fill "input[name=search]" "关键词"
ziniao press Enter
ziniao title
ziniao --json url

# 截图与快照
ziniao screenshot page.png
ziniao snapshot -o page.html

# 执行 JavaScript
ziniao eval "document.title"
ziniao --json eval "document.querySelectorAll('a').length"

# 网络监控
ziniao --json network list --limit 10
ziniao network route "*.ads.*" --abort

# 录制操作
ziniao rec start
# ...在浏览器中操作...
ziniao rec stop --name my-flow
ziniao rec replay my-flow

# JSON 输出（信封: success / data / error；业务字段在 .data，jq 示例：.data.title）
ziniao --json session list
ziniao --json get title
# 旧脚本需扁平 daemon JSON 时用：ziniao --json-legacy session list
```

> **提示**：所有命令均支持 `--help` 查看详细参数，如 `ziniao chrome launch --help`。

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
├── ziniao_mcp/              # MCP 服务器 + CLI
│   ├── __init__.py
│   ├── __main__.py          # python -m ziniao_mcp 入口
│   ├── server.py            # 配置解析 + 工具注册 + 启动
│   ├── session.py           # 会话管理 + CDP 连接 + 状态持久化
│   ├── cli/                 # CLI 命令行工具（90 个子命令）
│   │   ├── __init__.py      # Typer 主入口 + 全局选项
│   │   ├── connection.py    # daemon 连接层
│   │   ├── dispatch.py      # 命令分发（daemon 侧）
│   │   └── commands/        # 16 个命令组
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
| CLI 框架 | [typer](https://typer.tiangolo.com/) + [rich](https://rich.readthedocs.io/) |
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
| [CLI JSON 输出](docs/cli-json.md) | `--json` / `--json-legacy` 与 `jq` 字段路径 |
| [CLI 与 LLM](docs/cli-llm.md) | `--llm` / `--plain`、输入约定、快照语义 |
| [与 agent-browser CLI 对照](docs/cli-agent-browser-parity.md) | 全量命令、参数语义、batch/snapshot 差异与 daemon 命令表 |

## 上游与贡献

本仓库主托管于 [github.com/tianyehedashu/ziniao-mcp](https://github.com/tianyehedashu/ziniao-mcp)。若以 submodule 或 vendor 方式嵌入其他项目，建议在 **上游仓库** 提交 PR，再于父仓库更新 submodule 指针（`git submodule update --remote third_party/ziniao-mcp` 等），以便 PyPI 包 `ziniao` 与文档单一来源。

## 许可证

以仓库根目录 [LICENSE](LICENSE) 为准（当前为 **MIT**）。`pyproject.toml` 中的 `license` 字段与之一致，便于 PyPI 元数据展示。

调试时请注意：`~/.ziniao/mcp_debug.log` 在 DEBUG 级别下可能包含 URL 等敏感信息，勿随意分享。
