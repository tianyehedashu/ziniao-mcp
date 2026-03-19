# ziniao CLI 全命令测试报告

**最近测试**：2026-03-19，紫鸟 v6 店铺（速卖通）+ daemon 重启后验证 back/forward 修复。  
**历史测试**：Chrome 会话（chrome-50450），页面为 Google 搜索 / example.com。

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
| ~~`ziniao back` / `ziniao forward`~~ | ~~`'tuple' object has no attribute 'current_index'`~~ | **已修复**：`dispatch.py` 中兼容 CDP 返回 dict/tuple/object，统一解析为 `(entries, current_index)` |
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
3. **back / forward**：CDP `getNavigationHistory` 可能返回 tuple/dict，已在 `dispatch.py` 中增加 `_parse_navigation_history` 与 `_entry_id`，兼容多种返回格式。

---

## 紫鸟 v6 实际连接测试（2026-03-19）

配置参考 `mcp.json`：`ZINIAO_COMPANY=三方平台大卖`，`ZINIAO_SOCKET_PORT=16852`，`ZINIAO_VERSION=v6`。  
测试前重启 daemon（`ziniao quit` + 再次执行命令自动启动），确保加载最新代码。

| 命令 | 结果 | 说明 |
|------|------|------|
| `ziniao --help` | OK | 主帮助正常显示全部命令和组 |
| `ziniao --json session list` | OK | 空会话列表 |
| `ziniao --json store start-client` | OK | 紫鸟客户端已在运行 (端口 16852) |
| `ziniao --json list-stores` | OK | 返回全部店铺列表 |
| `ziniao --json list-stores --opened-only` | OK | 空列表 |
| `ziniao --json store open <id>` | OK | 打开速卖通店铺，cdp_port: 21167 |
| `ziniao --json session list` | OK | 显示已打开的紫鸟店铺会话 |
| `ziniao --json title` | OK | "Seller Platform" |
| `ziniao --json url` | OK | 返回正确 URL |
| `ziniao tab list` | OK | Rich 表格显示标签列表 |
| `ziniao navigate https://example.com` | OK | |
| `ziniao --json eval "document.title"` | OK | "Example Domain" |
| `ziniao --json get title` | OK | |
| `ziniao --json get url` | OK | |
| `ziniao --json get text "h1"` | OK | "Example Domain" |
| `ziniao --json get html "h1"` | OK | |
| `ziniao --json get count "p"` | OK | 2 |
| `ziniao --json is visible "h1"` | OK | true |
| `ziniao --json click "h1"` | OK | 耗时 ~21s（紫鸟反检测延迟） |
| `ziniao --json hover "a"` | OK | |
| `ziniao --json dblclick "h1"` | OK | 耗时 ~6s |
| `ziniao --json press Escape` | OK | |
| `ziniao --json reload` | OK | |
| `ziniao --json tab new --url https://example.com` | OK | |
| `ziniao --json back` | **OK** | **修复已验证** — 之前报 tuple 无 current_index |
| `ziniao --json forward` | **OK** | **修复已验证** |
| `ziniao --json scroll down` | OK | |
| `ziniao --json scrollinto "a"` | OK | |
| `ziniao --json mouse move 100 100` | OK | |
| `ziniao --json find text "More information..."` | OK | 找到并点击 |
| `ziniao --json wait "h1"` | OK | |
| `ziniao type -s "h1" "test"` | OK | 耗时 ~44s（拟人输入） |
| `ziniao snapshot -o file.html` | OK | 写入 UTF-8 文件 |
| `ziniao screenshot file.png` | OK | 保存 13011 字节 |
| `ziniao --json emulate --width 800 --height 600` | OK | |
| `ziniao --json network list --limit 5` | OK | 返回请求列表 |
| `ziniao --json network routes` | OK | |
| `ziniao --json rec list` | OK | 显示已有录制 |
| `ziniao --json store close <id>` | OK | |
| `ziniao chrome list` | OK | |

> **back / forward 修复已通过真实紫鸟 v6 环境验证。** 全部 39 项命令测试通过。

---

## 后续建议

- **本轮已完成**：title 防御性解析、snapshot 的 `--out-file`/`-o`、batch run 的 utf-8-sig/BOM 处理、back/forward 历史栈解析，均已修复并通过紫鸟 v6 验证。
- **紫鸟浏览器注意**：访问被安全插件拦截的 URL（如 google.com）会导致标签页关闭；click / type 等操作因紫鸟反检测延迟耗时较长（20-40 秒），使用 `--timeout 120` 可避免超时。

## 全量 --help 测试结果

- 通过: 90
- 失败: 0

### 通过列表
| 命令 |
|------|
| `主帮助` |
| `serve --help` |
| `store list --help` |
| `store open --help` |
| `store close --help` |
| `store start-client --help` |
| `store stop-client --help` |
| `chrome list --help` |
| `chrome launch --help` |
| `chrome connect --help` |
| `chrome close --help` |
| `session list --help` |
| `session switch --help` |
| `session info --help` |
| `nav go --help` |
| `nav navigate --help` |
| `nav tab --help` |
| `nav frame --help` |
| `nav wait --help` |
| `nav back --help` |
| `nav forward --help` |
| `nav reload --help` |
| `act click --help` |
| `act fill --help` |
| `act type --help` |
| `act press --help` |
| `act hover --help` |
| `act dblclick --help` |
| `info snapshot --help` |
| `info screenshot --help` |
| `info eval --help` |
| `info console --help` |
| `info network --help` |
| `info errors --help` |
| `info highlight --help` |
| `info cookies --help` |
| `info storage --help` |
| `info url --help` |
| `info clipboard --help` |
| `rec start --help` |
| `rec stop --help` |
| `rec replay --help` |
| `rec list --help` |
| `rec delete --help` |
| `sys quit --help` |
| `sys emulate --help` |
| `get text --help` |
| `get html --help` |
| `get value --help` |
| `get attr --help` |
| `get title --help` |
| `get url --help` |
| `get count --help` |
| `find first --help` |
| `find last --help` |
| `find nth --help` |
| `find text --help` |
| `find role --help` |
| `is visible --help` |
| `is enabled --help` |
| `is checked --help` |
| `scroll up --help` |
| `scroll down --help` |
| `scroll left --help` |
| `scroll right --help` |
| `scroll into --help` |
| `batch run --help` |
| `mouse move --help` |
| `mouse down --help` |
| `mouse up --help` |
| `mouse wheel --help` |
| `network route --help` |
| `network unroute --help` |
| `network routes --help` |
| `network list --help` |
| `network har-start --help` |
| `network har-stop --help` |
| `list-stores --help` |
| `chrome launch --help (top-level)` |
| `navigate --help` |
| `tab --help` |
| `wait --help` |
| `back --help` |
| `forward --help` |
| `reload --help` |
| `click --help` |
| `eval --help` |
| `title --help` |
| `url --help` |
| `scrollinto --help` |

### 失败列表
| 命令 | 退出码 | 说明 |
|------|--------|------|
