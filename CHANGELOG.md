# Changelog

本文件记录 ziniao-browser 的版本变更，遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式。

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
