# Changelog

本文件记录 ziniao-browser 的版本变更，遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式。

## [0.1.17] - 2026-03-04

### 修复

- **open_store 空白页**：MCP 打开店铺后自动导航到紫鸟返回的 `launcherPage`（店铺平台默认启动页），与客户端手动打开行为一致
- **HTTP 超时**：紫鸟客户端请求超时缩短，避免端口不通或客户端未启动时长时间卡住——`get_browser_list` 15s、`open_store` 60s、`close_store`/`get_exit` 15s/10s、`update_core` 单次轮询 10s

### 变更

- **open_store 返回值**：成功时增加 `launcher_page` 字段（若有）
- **list_stores**：店铺列表为空时提示检查客户端已启动、socket_port 一致、登录信息

## [0.1.16] - 2026-03-04

### 修复

- **反检测与紫鸟/Playwright 兼容**：Playwright 全局变量（`__playwright*`、`__pw_*`）改为仅设为 non-enumerable 隐藏，不再 delete，避免破坏 `page.locator()` 等内部绑定；`navigator.plugins` 覆写改为 `configurable: true`，允许紫鸟配置文件后续注入插件指纹

## [0.1.15] - 2026-03-04

### 新增

- **CDP 反检测**：新增 `ziniao_mcp/stealth` 模块，在打开/连接店铺时自动注入 JS 环境伪装与人类行为模拟，降低被识别为自动化程序的概率
  - JS 环境：覆写 `navigator.webdriver`、补全 `navigator.plugins`/`window.chrome`、清理 Playwright 全局变量、iframe 内 webdriver 修补、权限查询与自动化相关属性
  - 人类行为：随机延迟、贝塞尔曲线鼠标轨迹、逐字输入节奏，可通过 `config.yaml` 的 `ziniao.stealth` 配置开关与参数
  - 紫鸟 `injectJsInfo`：open_store 时向紫鸟客户端传入精简反检测脚本，在 Playwright 连接前即生效
  - 新标签页：`context.on("page")` 确保后续新开页面自动注册监听并继承 init_script

### 变更

- **config.yaml**：新增 `ziniao.stealth` 配置段（enabled、js_patches、human_behavior、delay_range、typing_speed、mouse_movement），示例见 `config/config.yaml.example`

## [0.1.14] - 2026-03-04

### 新增

- **MCP Prompts**：服务器注册 prompt「紫鸟浏览器自动化指引」（ziniao_mcp），客户端可通过 prompts/list 发现并调用，内容简述 list_stores → open_store/connect_store 与常见页面操作

## [0.1.13] - 2026-03-04

### 新增

- **端口自动检测**：新增 `detect_ziniao_port()` 函数，通过扫描运行中的紫鸟/SuperBrowser 进程命令行参数自动发现 HTTP 通信端口，用户无需手动配置 `ZINIAO_SOCKET_PORT`
- **端口冲突自动处理**：`_ensure_client_running()` / `start_client()` 在配置端口无响应时自动检测实际端口并切换，解决紫鸟单实例应用下端口不匹配导致的 3 分钟卡死问题

### 变更

- **端口优先级调整**：显式配置 > 自动检测 > 默认值 16851。`ZINIAO_SOCKET_PORT` 从必填改为可选
- **README / installation.md**：MCP 配置示例去掉 `ZINIAO_SOCKET_PORT`（默认自动检测），环境变量表和故障排查同步更新

## [0.1.12] - 2026-03-04

### 修复

- **端口配置不匹配**：`.mcp.json` 增加 `ZINIAO_SOCKET_PORT` 环境变量透传，Plugin 模式下可正确使用自定义端口（默认 16851，可与客户端实际监听端口一致）
- **heartbeat 超时**：心跳请求超时从 120s 改为 10s，端口不通时快速失败；连接失败时日志提示检查 `ZINIAO_SOCKET_PORT`
- **start_client**：返回信息包含当前端口；启动后仍无法连接时明确提示检查端口配置

### 文档

- **README / installation.md**：MCP 配置示例增加 `ZINIAO_SOCKET_PORT`，环境变量表与故障排查补充端口说明
- **installation.md**：新增「工具调用超时 / Aborted」排查项（端口不匹配、如何确认实际端口）

## [0.1.11] - 2026-03-04

### 文档

- **README**：补充项目 GitHub 地址

## [0.1.10] - 2026-03-04

### 文档

- **README / 安装文档**：补充「查看版本」`uvx ziniao-mcp -V`、刷新与重启说明；前提条件统一为「开启 WebDriver 权限」并保留开通链接

## [0.1.9] - 2026-03-04

### 修复

- **list_stores「未找到程序 ziniao.exe」**：客户端未运行时不再调用 `kill_process`，避免无意义的 taskkill 报错
- **乱码**：`kill_process` 改为 `subprocess.run(..., capture_output=True)`，吞掉 taskkill/killall 的 GBK 输出，避免混入 MCP UTF-8 流
- **未配置客户端路径**：`start_browser` 在路径为空或文件不存在时抛出明确的 `FileNotFoundError`，提示配置 `ZINIAO_CLIENT_PATH` 或 `--client-path`

## [0.1.3] - 2026-03-04

### 修复

- **`--help` 退出报错**：`main()` 启动前先调用 `_resolve_config()` 解析参数，使 `uvx ziniao-mcp --help` 在启动任何 daemon 线程前退出，避免解释器关闭时与 stdin 争用导致 Fatal Python error

### 文档

- **安装文档**：补充 uvx 更新命令（`uvx --refresh ziniao-mcp --help`）、说明勿在终端裸跑 MCP 做测试、故障排查中增加“旧版本缓存”提示

## [0.1.2] - 2026-03-04

### 修复

- **MCP stdout 污染**：将 `ziniao_webdriver/client.py` 中所有 `print()` 改为 `logging`，避免 HTTP 连接失败时异常信息写入 stdout 导致 MCP 客户端 JSON 解析错误（`Unexpected token 'H', "HTTPConnec"...`）
- **日志编码**：`ziniao_mcp/server.py` 中 `logging.basicConfig` 增加 `encoding="utf-8"`，避免中文乱码及 GBK 无法编码字符导致的异常

## [0.2.1] - 2026-03-03

### 新增

- **安装与使用文档**（`docs/installation.md`）：覆盖 Plugin / MCP / PyPI / Claude Desktop 等多种安装方式、配置详解、故障排查
- **打包发布指南**：在 `docs/development.md` 中补充 Cursor Marketplace 和 PyPI 双渠道发布流程、MCP 深度链接生成

### 变更

- **README.md**：精简快速开始部分，指向详细安装文档；新增文档索引表
- **移除常驻 Rules**：删除 `ziniao-workflow.mdc`、`store-safety.mdc`，避免无关对话占用上下文；README、installation、development、CHANGELOG 已同步更新

## [0.2.0] - 2026-03-03

### 新增

- **Cursor Plugin 封装**：项目升级为 Cursor Plugin，提供 MCP 工具之外的 AI 增强能力
  - `.cursor-plugin/plugin.json`：Plugin manifest
  - `.mcp.json`：标准化 MCP Server 配置，Plugin 安装后自动注册
- **Skills（AI 技能指南）**
  - `ziniao-browser`：核心浏览器自动化技能（生命周期、选择器、故障排查）
  - `store-management`：多店铺管理技能（connect vs open、会话恢复、批量操作）
  - `amazon-operations`：亚马逊运营技能（Seller Central 导航、Listing/订单/广告操作流程）
- **Agents（专用角色）**
  - `ziniao-operator`：紫鸟运营专家 Agent，具备跨境电商领域知识和安全操作意识
- **Commands（快捷命令）**
  - `quick-check-stores`：一键检查所有店铺状态
  - `batch-screenshot`：批量截取已打开店铺的当前页面

## [0.1.0] - 2025-06-01

### 新增

- **ziniao_webdriver** 模块：封装紫鸟客户端 HTTP 通信（`ZiniaoClient`）
- **ziniao_mcp** 模块：MCP 服务器，支持 31 个工具
  - 店铺管理（7）：`start_client`、`list_stores`、`list_open_stores`、`open_store`、`connect_store`、`close_store`、`stop_client`
  - 输入自动化（9）：`click`、`fill`、`fill_form`、`type_text`、`press_key`、`hover`、`drag`、`handle_dialog`、`upload_file`
  - 导航（6）：`navigate_page`、`list_pages`、`select_page`、`new_page`、`close_page`、`wait_for`
  - 仿真（2）：`emulate`、`resize_page`
  - 网络（2）：`list_network_requests`、`get_network_request`
  - 调试（5）：`evaluate_script`、`take_screenshot`、`take_snapshot`、`list_console_messages`、`get_console_message`
- 配置优先级：环境变量 > 命令行参数 > config.yaml
- 跨会话状态持久化（`~/.ziniao/sessions.json`），支持 `connect_store` 恢复 CDP 连接
- 跨平台支持：Windows / macOS / Linux
- Cursor MCP 集成配置
