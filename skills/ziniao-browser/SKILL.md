---
name: ziniao-browser
description: 通过紫鸟 MCP 工具进行浏览器自动化操作。当需要操控紫鸟店铺浏览器、自动化页面交互、截图调试、执行 JavaScript 或分析网络请求时使用此技能。
---

## 核心概念

**浏览器生命周期**：紫鸟客户端以 WebDriver 模式启动，在本地监听 HTTP 端口（默认 16851）。MCP 服务器通过该端口控制客户端，再通过 Playwright CDP 连接到各店铺浏览器实例。客户端会在首次需要时自动启动。

**店铺会话**：每个打开的店铺对应一个独立的浏览器实例和 CDP 连接。同一时间可以打开多个店铺，但工具操作的是当前"活动店铺"的"活动页面"。

**状态持久化**：已打开店铺的 CDP 信息保存在 `~/.ziniao/sessions.json`。MCP 进程重启后，可通过 `connect_store` 恢复连接而无需重新打开店铺。

## 工作流模式

### 开始操作前

1. 连接：`connect_store` 或 `open_store` 建立店铺连接
2. 等待：`wait_for` 确保页面加载完成
3. 理解：`take_snapshot` 获取页面 HTML 结构
4. 交互：根据 snapshot 中的元素选择器使用 `click`、`fill` 等工具

### 高效数据获取

- 优先用 `take_snapshot` 获取页面结构（文本化、快速、低 token 消耗）
- 仅在需要视觉确认时使用 `take_screenshot`
- 用 `evaluate_script` 提取 snapshot 无法获取的动态数据（如 JavaScript 变量、计算样式）

### 工具选择指南

| 场景 | 推荐工具 | 原因 |
|------|----------|------|
| 分析页面结构 | `take_snapshot` | 文本化 HTML，适合元素定位 |
| 视觉确认 | `take_screenshot` | 看到实际渲染效果 |
| 提取动态数据 | `evaluate_script` | 访问 JS 运行时数据 |
| 填写单个字段 | `fill` | 清空后填入，简单直接 |
| 填写多个字段 | `fill_form` | 批量操作，一次调用完成 |
| 模拟真实输入 | `type_text` | 逐字触发键盘事件 |
| 分析 API 调用 | `list_network_requests` + `get_network_request` | 查看请求详情 |
| 调试页面错误 | `list_console_messages` + `get_console_message` | 查看控制台输出 |

### 并行执行

可以并行发送多个工具调用，但需保持正确的依赖顺序：连接 -> 等待 -> 快照 -> 交互。

## 选择器使用

支持多种选择器语法：

- **CSS 选择器**：`#submit-btn`、`.product-title`、`input[name="price"]`
- **文本选择器**：`text=登录`、`text=Submit`
- **XPath**：`xpath=//button[@type="submit"]`
- **Playwright 选择器**：`role=button[name="Save"]`

优先使用具有唯一性的选择器（ID > 属性 > 文本 > XPath）。

## 故障排查

| 问题 | 排查步骤 |
|------|----------|
| 工具调用失败 | 检查是否已连接店铺（`list_open_stores`） |
| 元素找不到 | 重新 `take_snapshot` 确认元素是否存在，页面可能已变化 |
| 页面未加载 | 使用 `wait_for` 等待，或增加 timeout |
| CDP 连接断开 | 用 `connect_store` 重新连接 |
| 客户端无响应 | 用 `stop_client` 关闭后重新操作（会自动启动） |
