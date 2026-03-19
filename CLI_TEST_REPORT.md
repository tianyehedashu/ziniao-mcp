# ziniao CLI 全命令测试报告

测试环境：Chrome 会话已存在（chrome-50450），页面为 Google 搜索 / example.com。  
测试时间：一次完整遍历。

---

## 通过（OK）

| 命令 | 说明 |
|------|------|
| `ziniao --help` | 主帮助正常 |
| `ziniao --json session list` | 返回 JSON 会话列表 |
| `ziniao title` / `ziniao --json title` | 获取页面标题 |
| `ziniao url` / `ziniao --json url` | 获取当前 URL |
| `ziniao tab list` | 标签页列表（含 URL、title、active） |
| `ziniao chrome list` | Chrome 会话列表表格 |
| `ziniao launch --url <url>` | 启动 Chrome 并打开 URL（已修复 OptionInfo 序列化） |
| `ziniao navigate <url>` | 导航到 URL，返回页面 title |
| `ziniao wait "selector"` | 等待元素（已修复 OptionInfo） |
| `ziniao reload` | 刷新页面 |
| `ziniao click "textarea[name=q]"` | 点击元素 |
| `ziniao press Escape` | 按键 |
| `ziniao hover "selector"` | 悬停（对隐藏元素会报错，符合预期） |
| `ziniao --json eval "1+1"` | 执行 JS，返回 `{"ok":true,"result":2}` |
| `ziniao scroll down` | 页面向下滚动 |
| `ziniao --json network list` | 网络请求列表（含 id/method/url/status/resource_type） |
| `ziniao --json network list --id 230` | 按 request_id 取详情（含 request/response headers） |
| `ziniao --json network list --id 99999` | 不存在的 ID 返回 JSON `{"error":"Request ID not found: 99999"}` |
| `ziniao network routes` | 拦截路由列表 |
| `ziniao network har-start` | 开始 HAR 录制 |
| `ziniao network har-stop` | 停止并保存 HAR 文件 |
| `ziniao network route "*.example.com*" --abort` | 添加拦截路由 |
| `ziniao network unroute "*.example.com*"` | 移除拦截路由 |
| `ziniao emulate --width 800 --height 600` | 设置视口 |
| `ziniao emulate --help` | 设备/视口选项正常 |
| `ziniao find text "Google Search"` | 按文本查找并点击，返回 clicked |
| `ziniao get url` / `ziniao get title` | 获取 URL/标题 |
| `ziniao is visible "textarea[name=q]"` | 检查元素可见性 |
| `ziniao rec list` | 录制列表（JSON） |
| `ziniao tab new --url https://example.com` | 新建标签页 |
| `ziniao scrollinto "h1"` | 滚动到元素 |
| `ziniao serve --help` | MCP 服务帮助 |
| `ziniao type -s "h1" "abc"` | 在 selector 元素上输入文本 |
| `ziniao mouse move 100 100` | 鼠标移动 |
| `ziniao nav go https://example.com` | 导航（nav 组下为 go） |
| `ziniao dblclick "h1"` | 双击元素 |

---

## 失败 / 需注意

| 命令 | 现象 | 说明 |
|------|------|------|
| `ziniao back` | `'tuple' object has no attribute 'current_index'` | 服务端历史栈处理 bug，需在 daemon 侧修复（本仓库无 daemon 源码） |
| `ziniao forward` | 同上 | 同上 |
| `ziniao click/fill/hover "input[name=q]"` | `could not find position for ... type="hidden"` | 匹配到隐藏 input，应改用 `textarea[name=q]` 等可见元素 |
| `ziniao snapshot`（含大量 HTML） | `UnicodeEncodeError: 'gbk' codec can't encode character ...` | 已支持 `--out-file`/`-o` 写入 UTF-8 文件；入口已设 Windows UTF-8 |
| `ziniao --json snapshot` | 同上（JSON 打印到 stdout 时仍经控制台编码） | 使用 `ziniao snapshot -o out.html` 或 `--out-file` 写入文件 |
| `ziniao title`（部分页面） | 返回 `RemoteObject(type_='string', ...)` 未解析 | CLI 已做防御：若为 dict 则取 `value` 显示 |
| `ziniao list-stores` | 需紫鸟配置（ZINIAO_COMPANY 等） | 未配置时提示使用 Chrome 功能，符合预期 |
| `ziniao batch run` | ~~`invalid JSON`（从管道/文件读取）~~ | 已修复：stdin 按 utf-8-sig 解码并去除 BOM；PowerShell 管道可用 |
| `ziniao tab new https://example.com` | ~~`Got unexpected extra argument`~~ | 已修复：支持 positional URL，`tab new <url>` 与 `tab new --url <url>` 均可 |
| `ziniao nav navigate <url>` | ~~`No such command 'navigate'`~~ | 已修复：已增加 `nav navigate` 别名 |
| `ziniao info url` | ~~`No such command 'url'`~~ | 已修复：已增加 `info url` 命令 |
| `ziniao screenshot <path>` | 超时（30s） | 可能因页面或路径导致未在时限内返回，需单独验证 |

---

## 命令组与顶层对应关系

- **导航**：顶层 `navigate`、`wait`、`back`、`forward`、`reload`、`tab`；组 `nav` 下为 `go`、`navigate`、`tab`、`wait`、`back`、`forward`、`reload`。
- **信息**：顶层 `title`、`url`、`snapshot`、`screenshot`、`eval`；组 `info` 下为 `snapshot`、`screenshot`、`eval`、`url`、`console`、`network` 等。
- **网络**：顶层无单条命令，组 `network` 下为 `list`、`routes`、`route`、`unroute`、`har-start`、`har-stop`。
- **店铺**：顶层 `list-stores`、`open-store`、`close-store`；组 `store` 下为 `list`、`open`、`close`、`start-client`、`stop-client`。

---

## 已修复（本次测试前/中）

1. **OptionInfo 序列化**：`launch`、`wait` 等传参时 Typer Option 对象被送入 daemon 导致 `Object of type OptionInfo is not JSON serializable`。已在 `connection.py` 中对 `args` 做 `_json_safe()`，并在 `chrome.py` 的 `launch` 中对参数做类型收缩。
2. **network 错误格式**：`request_id` 不存在时由返回纯字符串改为返回 JSON `{"error": "Request ID not found: ..."}`。

---

## 后续建议

- **仍需修复（仅 daemon 侧）**：**back / forward** — 需在含 daemon 的仓库中修复历史栈结构（避免 `tuple` 无 `current_index`），本仓库无 daemon 源码。
- **本轮已在 CLI 侧完成**：title 防御性解析、snapshot 的 `--out-file`/`-o`、batch run 的 utf-8-sig/BOM 处理及文档说明，均已在上面“失败/需注意”表中标为已修复。
