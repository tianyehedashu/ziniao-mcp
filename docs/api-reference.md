# API 参考

本文档列出 ziniao-mcp 提供的全部 31 个 MCP 工具的详细参数和返回值。

---

## 店铺管理

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
