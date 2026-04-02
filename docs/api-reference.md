# API 参考

本文档列出 ziniao-mcp 提供的全部 MCP 工具（紫鸟店铺 + Chrome 浏览器）的详细参数和返回值。

---

## 店铺管理（紫鸟）

### `start_client`

启动紫鸟客户端进程（WebDriver 模式）。如果客户端已在运行则跳过。

**参数**：无

**返回**：`string` — 启动状态消息

---

### `list_stores`

获取当前账号下的所有店铺列表。如果客户端未运行会自动启动。

**参数**：无

**返回**：`string` — JSON 数组，每个元素包含：

| 字段 | 类型 | 说明 |
|------|------|------|
| `browserId` | `string` | 店铺数字 ID |
| `browserOauth` | `string` | 店铺 OAuth 标识 |
| `browserName` | `string` | 店铺名称 |
| `siteId` | `string` | 站点 ID |
| `siteName` | `string` | 站点名称（如 Amazon US） |
| `is_open` | `boolean` | 该店铺是否正在运行 |

---

### `list_open_stores`

查询当前已打开（正在运行）的店铺列表。通过 CDP 端口连通性验证确认店铺是否真正在运行，自动清理已失效的记录。

**参数**：无

**返回**：`string` — JSON 对象：

```json
{
  "stores": [
    { "store_id": "xxx", "store_name": "我的店铺", "cdp_port": 9222 }
  ],
  "count": 1
}
```

---

### `open_store`

打开紫鸟店铺并建立 CDP 浏览器连接。成功后该店铺成为当前活动店铺。

> 对已打开的店铺调用此工具会导致重启。如需连接已运行的店铺，请使用 `connect_store`。

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `store_id` | `string` | 是 | 店铺标识（`browserId` 或 `browserOauth`，从 `list_stores` 获取） |

**返回**：`string` — JSON 对象：

```json
{
  "status": "success",
  "store_id": "xxx",
  "store_name": "我的店铺",
  "cdp_port": 9222,
  "tabs": 1
}
```

---

### `connect_store`

连接一个已经在运行的紫鸟店铺（不会重启）。优先从状态文件恢复 CDP 连接；如果店铺未运行则自动 fallback 到 `open_store`。

**推荐在不确定店铺是否已打开时使用此工具。**

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `store_id` | `string` | 是 | 店铺标识 |

**返回**：`string` — JSON 对象（同 `open_store`，`status` 为 `"connected"`，`pages` 替换为 `tabs`）

---

### `close_store`

关闭紫鸟店铺并断开 CDP 连接。

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `store_id` | `string` | 是 | 店铺标识 |

**返回**：`string` — JSON 对象：

```json
{
  "status": "closed",
  "store_id": "xxx",
  "remaining_stores": ["yyy"]
}
```

---

### `stop_client`

退出紫鸟客户端。会先关闭所有已打开的店铺。

**参数**：无

**返回**：`string` — 退出状态消息

---

## 输入自动化

> 以下工具均操作当前活动店铺的活动页面。使用前需先通过 `open_store` 或 `connect_store` 打开店铺。

### `click`

点击页面元素。

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `selector` | `string` | 是 | CSS 选择器（如 `#submit-btn`、`.login-button`、`input[type=text]`） |

**返回**：`string` — 操作确认消息

---

### `fill`

清空并填写输入框。

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `selector` | `string` | 是 | 输入框的选择器 |
| `value` | `string` | 是 | 要填入的值 |

**返回**：`string` — 操作确认消息

---

### `fill_form`

批量填写表单字段。

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `fields_json` | `string` | 是 | JSON 格式的字段列表 |

`fields_json` 格式：

```json
[
  { "selector": "#name", "value": "张三" },
  { "selector": "#email", "value": "a@b.com" }
]
```

**返回**：`string` — 填写数量确认

---

### `type_text`

逐字输入文本（模拟真实键盘打字），适用于需要触发 `input`/`keydown` 等事件的场景。

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `text` | `string` | 是 | 要输入的文本 |
| `selector` | `string` | 否 | 目标元素选择器。为空则在当前焦点元素输入 |

**返回**：`string` — 操作确认消息

---

### `press_key`

按下键盘按键。

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `key` | `string` | 是 | 按键名称 |

常用按键：`Enter`、`Tab`、`Escape`、`Backspace`、`ArrowDown`、`ArrowUp`、`Control+a`、`Control+c`、`Control+v`

**返回**：`string` — 操作确认消息

---

### `hover`

将鼠标悬停在元素上。

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `selector` | `string` | 是 | 目标元素的选择器 |

**返回**：`string` — 操作确认消息

---

### `drag`

将元素拖拽到另一个元素上。

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `source_selector` | `string` | 是 | 源元素选择器 |
| `target_selector` | `string` | 是 | 目标元素选择器 |

**返回**：`string` — 操作确认消息

---

### `handle_dialog`

设置浏览器弹窗（alert/confirm/prompt）的处理策略。设置后，后续弹窗将自动按此策略处理。

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `action` | `string` | 否 | `"accept"` 确认 或 `"dismiss"` 取消（默认 `"accept"`） |
| `text` | `string` | 否 | prompt 弹窗的输入文本 |

**返回**：`string` — 策略设置确认

---

### `upload_file`

上传文件到文件输入框。

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `selector` | `string` | 是 | 文件输入框的选择器（`<input type="file">`） |
| `file_paths_json` | `string` | 是 | JSON 格式的文件路径列表 |

`file_paths_json` 格式：

```json
["C:/images/photo.jpg", "C:/images/logo.png"]
```

**返回**：`string` — 上传数量确认

---

## 导航

### `navigate_page`

导航到指定 URL。

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `url` | `string` | 是 | 目标 URL |

**返回**：`string` — JSON 对象：

```json
{
  "url": "https://www.amazon.com/",
  "title": "Amazon.com",
  "status": "ok"
}
```

---

### `list_pages`

列出当前店铺浏览器的所有标签页。

**参数**：无

**返回**：`string` — JSON 数组：

```json
[
  { "index": 0, "url": "https://...", "title": "...", "is_active": true },
  { "index": 1, "url": "about:blank", "title": "", "is_active": false }
]
```

---

### `select_page`

切换到指定标签页。

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `page_index` | `int` | 是 | 标签页索引（从 0 开始，通过 `list_pages` 查看） |

**返回**：`string` — JSON 对象（index、url、title）

---

### `new_page`

新建标签页。

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `url` | `string` | 否 | 新标签页要打开的 URL，为空则打开空白页 |

**返回**：`string` — JSON 对象（index、url、total_pages）

---

### `close_page`

关闭标签页。

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `page_index` | `int` | 否 | 要关闭的标签页索引，`-1` 表示关闭当前活动页（默认 `-1`） |

**返回**：`string` — JSON 对象（closed_url、remaining_pages）

---

### `wait_for`

等待条件满足。

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `selector` | `string` | 否 | 等待的元素选择器。为空则等待页面加载完成 |
| `state` | `string` | 否 | 等待状态：`visible`（默认）、`hidden`、`attached`、`detached` |
| `timeout` | `int` | 否 | 超时毫秒数（默认 30000） |

**返回**：`string` — 等待结果消息

---

## 仿真

### `emulate`

模拟指定设备（调整视口大小和 User-Agent）。

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `device_name` | `string` | 是 | 预置设备名 |

常用设备名：`iPhone 14`、`iPhone 14 Pro Max`、`iPhone 15`、`iPad Pro 11`、`Pixel 7`、`Samsung Galaxy S23`、`Desktop 1920x1080`

**返回**：`string` — JSON 对象（device、viewport、user_agent）。如设备名无效，返回可用设备列表。

---

### `resize_page`

调整页面视口大小。

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `width` | `int` | 是 | 视口宽度（像素） |
| `height` | `int` | 是 | 视口高度（像素） |

**返回**：`string` — 调整确认消息

---

## 网络

### `list_network_requests`

列出已捕获的网络请求。从打开店铺或切换页面起自动捕获。

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `url_pattern` | `string` | 否 | URL 子串过滤（如 `"api"` 只显示含 api 的请求） |
| `limit` | `int` | 否 | 返回条数上限（默认 50） |

**返回**：`string` — JSON 数组，每个元素包含 `id`、`method`、`url`（截断至 200 字符）、`status`、`resource_type`

---

### `get_network_request`

获取指定网络请求的详细信息。

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `request_id` | `int` | 是 | 请求 ID（从 `list_network_requests` 获取） |

**返回**：`string` — JSON 对象，包含完整 URL、method、status、status_text、resource_type、request_headers、response_headers

---

### `page_fetch`

在当前**活动标签页**的页面上下文中发起 HTTP 请求（`fetch` 或自定义 `js`），自动携带该页 **Cookie**；可与 CLI `ziniao network fetch` 对照使用。模板变量、分页、会话鉴权等见 [site-fetch-and-presets.md](site-fetch-and-presets.md)；XSRF 策略详情见 [page-fetch-xsrf.md](page-fetch-xsrf.md)。

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `url` | `string` | fetch 模式必填 | 请求 URL |
| `method` | `string` | 否 | 默认 `GET` |
| `body` | `string` | 否 | 请求体（多为 JSON 字符串） |
| `headers` | `string` | 否 | 请求头 JSON 字符串，如 `'{"Accept":"application/json"}'` |
| `xsrf_cookie` | `string` | 否 | Cookie 名称；从 `document.cookie` 取令牌 |
| `xsrf_headers` | `string` | 否 | JSON 数组字符串，如 `'["x-csrf-token"]'`；设 `xsrf_cookie` 且不传时默认 `["X-XSRF-TOKEN"]` |
| `mode` | `string` | 否 | `fetch`（默认）或 `js` |
| `script` | `string` | 否 | `js` 模式下执行的表达式；可使用注入的 `__BODY__` / `__BODY_STR__` |
| `navigate_url` | `string` | 否 | 若当前 URL 不匹配则先导航到此地址 |

**返回**：`string` — JSON，含 `ok`、`status`、`statusText`、`body`（响应正文文本）或 `error`

---

## 调试

### `evaluate_script`

在当前页面执行 JavaScript 代码并返回结果。

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `script` | `string` | 是 | JavaScript 代码 |

示例：`"document.title"`、`"window.location.href"`、`"document.querySelectorAll('a').length"`

**返回**：`string` — JSON 序列化的执行结果

---

### `take_screenshot`

截取页面或指定元素的截图。

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `selector` | `string` | 否 | 元素选择器。为空则截取整个可视区域 |
| `full_page` | `bool` | 否 | 是否截取完整页面（含滚动区域），仅在无 `selector` 时生效（默认 `false`） |

**返回**：`string` — `data:image/png;base64,...` 格式的 base64 编码 PNG 图片

---

### `take_snapshot`

获取当前页面的完整 HTML 快照。

**参数**：无

**返回**：`string` — 完整 HTML 内容

---

### `list_console_messages`

列出页面控制台消息。从打开店铺或切换页面起自动捕获。

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `level` | `string` | 否 | 按级别过滤：`log`、`warning`、`error`、`info`、`debug` |
| `limit` | `int` | 否 | 返回条数上限（默认 50） |

**返回**：`string` — JSON 数组，每个元素包含 `id`、`level`、`text`（截断至 500 字符）

---

### `get_console_message`

获取指定控制台消息的完整内容。

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `message_id` | `int` | 是 | 消息 ID（从 `list_console_messages` 获取） |

**返回**：`string` — JSON 对象，包含 `id`、`level`、`text`（完整内容）、`timestamp`

---

## 录制与代码生成

### `recorder`

浏览器操作录制与代码生成（类 Playwright Codegen）。录制用户在浏览器中的交互操作（点击、输入、按键、导航），停止后生成可独立运行的 Python 脚本（基于 nodriver），也可在 MCP 内回放。支持跨页面导航——页面跳转后自动重新注入录制器。

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `action` | `string` | 否 | 操作类型（默认 `"start"`），见下表 |
| `name` | `string` | 否 | 录制名称（`stop` 时保存用，`replay`/`delete` 时指定目标） |
| `actions_json` | `string` | 否 | 回放时可直接传入 JSON 动作列表（优先级高于 `name`） |
| `speed` | `float` | 否 | 回放速度倍率（默认 `1.0`，`2.0` 表示双倍速） |
| `engine` | `string` | 否 | `start`：`dom2`（`Runtime.addBinding` + 守护进程缓冲，多标签，默认）或 `legacy`（页内 Symbol 缓冲） |
| `scope` | `string` | 否 | `start` 且 `dom2`：`active`（当前活动标签 + 轮询新标签）或 `all`（最多 `max_tabs` 个页面） |
| `max_tabs` | `int` | 否 | `start` 且 `dom2` 且 `scope=all` 时上限；`0` 表示不限制 |
| `emit` | `string` | 否 | `stop`：逗号分隔 `nodriver`、`playwright`（生成 `.py` 与/或 `.spec.ts`），默认 `nodriver` |
| `record_secrets` | `bool` | 否 | `stop`：为 `false` 时对 `fill` 的 `value` 做脱敏后再写入 JSON（默认 `true` 保持明文以兼容旧行为） |
| `metadata_only` | `bool` | 否 | `view`：仅元数据 |
| `force` | `bool` | 否 | `stop`：覆盖同名文件 |
| `reuse_tab` | `bool` | 否 | `replay`：在当前标签回放 |
| `auto_session` | `bool` | 否 | `replay`：无会话时按元数据自动连接 |

**action 取值**：

| action | 说明 |
|--------|------|
| `start` | 开始录制：默认 `dom2`（binding + 缓冲）；`legacy` 时为页内 Symbol 缓冲并绑定主帧导航重注入 |
| `stop` | 停止录制：提取操作序列，生成 Python 脚本并保存到 `~/.ziniao/recordings/` |
| `replay` | 回放录制：通过 `name` 加载已保存的录制，或传入 `actions_json` 直接回放 |
| `list` | 列出所有已保存的录制 |
| `delete` | 删除指定录制 |

#### action = `"start"`

注入 JS 录制器到当前活动页面，开始捕获用户交互。支持录制以下操作类型：

- **click** — 点击元素
- **fill** — 输入框填写（自动去抖合并连续输入）
- **select** — 下拉选择
- **press_key** — 特殊按键（Enter、Tab、Escape 等）
- **navigate** — 页面导航（跨页面自动检测）

**返回**：`string` — JSON 对象：

```json
{
  "status": "recording",
  "message": "录制已开始，请在浏览器中操作。完成后调用 recorder(action='stop') 停止。",
  "start_url": "https://www.amazon.com/"
}
```

#### action = `"stop"`

停止录制，提取操作序列，同时生成：
- `.json` 文件 — 元数据 + 动作序列（含 `schema_version`；`dom2` 含结构化 `locator` 字段）
- `.py` 文件 — 可独立运行的 Python 脚本（基于 nodriver，`emit` 含 `nodriver` 时）
- `.spec.ts` — Playwright 风格模板（`emit` 含 `playwright` 时，需自行接 `connectOverCDP`）

**stealth**：`dom2` 与反检测脚本均通过 `Page.addScriptToEvaluateOnNewDocument` 注入；勿在页面侧依赖可枚举的录制状态。

**返回**：`string` — JSON 对象：

```json
{
  "status": "saved",
  "name": "rec_20260311_143022",
  "action_count": 12,
  "files": {
    "json": "C:/Users/xxx/.ziniao/recordings/rec_20260311_143022.json",
    "py": "C:/Users/xxx/.ziniao/recordings/rec_20260311_143022.py"
  },
  "message": "已录制 12 个操作，Python 脚本已生成: ..."
}
```

生成的 Python 脚本特点：
- 完全独立，只依赖 nodriver
- CDP 端口可通过 `--port` 参数覆盖
- 每步带注释，保留原始操作间隔

#### action = `"replay"`

在 MCP 内回放录制的操作序列。通过 `name` 加载已保存的录制，或通过 `actions_json` 传入动作列表。`speed` 控制回放速度。

**返回**：`string` — JSON 对象：

```json
{
  "status": "done",
  "replayed": 12,
  "total": 12,
  "message": "已回放 12/12 个操作"
}
```

#### action = `"list"`

列出 `~/.ziniao/recordings/` 下所有已保存的录制。

**返回**：`string` — JSON 对象：

```json
{
  "recordings": [
    {
      "name": "rec_20260311_143022",
      "created_at": "2026-03-11T14:30:22",
      "start_url": "https://www.amazon.com/",
      "action_count": 12,
      "py_file": "C:/Users/xxx/.ziniao/recordings/rec_20260311_143022.py"
    }
  ],
  "count": 1
}
```

#### action = `"delete"`

删除指定名称的录制（同时删除 `.json` 和 `.py` 文件）。

**返回**：`string` — JSON 对象：

```json
{
  "status": "deleted",
  "name": "rec_20260311_143022"
}
```

---

## Chrome 浏览器管理

### `launch_chrome`

启动一个新的 Chrome 浏览器实例并通过 CDP 连接。成功后成为当前活动浏览器。

**参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | `string` | `""` | 会话名称（可选，用于标识和后续切换） |
| `url` | `string` | `""` | 启动后打开的 URL |
| `executable_path` | `string` | `""` | Chrome 可执行文件路径（空则自动检测） |
| `cdp_port` | `int` | `0` | CDP 远程调试端口（0 则自动分配） |
| `user_data_dir` | `string` | `""` | 用户数据目录（空则使用 ~/.ziniao/chrome-profile，复用登录与状态） |
| `headless` | `bool` | `false` | 是否以无头模式启动 |

**返回**：`string` — JSON 对象：

```json
{
  "status": "success",
  "session_id": "research",
  "name": "research",
  "cdp_port": 9222,
  "tabs": 1
}
```

---

### `connect_chrome`

连接到一个已运行的 Chrome 浏览器（通过 CDP 端口）。成功后成为当前活动浏览器。

**参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `cdp_port` | `int` | — | Chrome 的 CDP 远程调试端口（必填） |
| `name` | `string` | `""` | 会话名称（可选） |

**返回**：`string` — JSON 对象，格式同 `launch_chrome`

---

### `list_chrome`

列出当前所有 Chrome 浏览器会话。

**参数**：无

**返回**：`string` — JSON 对象：

```json
{
  "sessions": [
    {
      "session_id": "chrome-9222",
      "name": "Chrome (9222)",
      "cdp_port": 9222,
      "tabs": 3,
      "is_active": true
    }
  ],
  "count": 1
}
```

---

### `close_chrome`

关闭指定的 Chrome 浏览器会话。

**参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `session_id` | `string` | 会话标识 |

**返回**：`string` — JSON 对象，包含 `status` 和 `remaining_chrome_sessions`

---

## 统一会话管理

### `browser_session`

管理所有浏览器会话（跨紫鸟店铺和 Chrome 实例）。

**参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `action` | `string` | `"list"` | 操作类型：`list` / `switch` / `info` |
| `session_id` | `string` | `""` | `switch` / `info` 时的目标会话 ID |

#### action = `"list"`

列出所有活跃浏览器会话，标记当前活跃的那个。

**返回**：

```json
{
  "active_session": "store-abc123",
  "sessions": [
    {
      "session_id": "store-abc123",
      "name": "Amazon US 店铺",
      "type": "ziniao",
      "cdp_port": 12345,
      "tabs": 3,
      "is_active": true
    },
    {
      "session_id": "chrome-9222",
      "name": "research",
      "type": "chrome",
      "cdp_port": 9222,
      "tabs": 5,
      "is_active": false
    }
  ],
  "count": 2
}
```

#### action = `"switch"`

切换当前活跃会话。后续所有页面操作（click/fill/navigate 等）将作用于新的活跃会话。

**返回**：

```json
{
  "status": "success",
  "active_session": "chrome-9222",
  "name": "research",
  "type": "chrome",
  "tabs": 5
}
```

#### action = `"info"`

查看指定会话的详细信息。

**返回**：

```json
{
  "session_id": "chrome-9222",
  "name": "research",
  "type": "chrome",
  "cdp_port": 9222,
  "active_tab_index": 0,
  "tabs": [
    {"index": 0, "url": "https://google.com", "title": "Google"},
    {"index": 1, "url": "https://example.com", "title": "Example"}
  ],
  "is_active": true
}
```
