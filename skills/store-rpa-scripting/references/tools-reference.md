# ziniao CLI 探索 ↔ 独立脚本对照

**Phase 1** 在终端使用 `ziniao`（子命令速查见本文；完整列表见 `ziniao --help`，或与安装包同仓的 `skills/ziniao-cli/references/commands.md`）。**Phase 3** 将同一语义写成 `ziniao_webdriver` + `nodriver`，进程内直连 CDP，不拉起 CLI。

## Phase 1 常用命令（速查）

### 连接与会话

| CLI | 说明 |
|-----|------|
| `ziniao store start-client` | 以 WebDriver 模式启动紫鸟客户端（HTTP 口） |
| `ziniao store stop-client` | 退出紫鸟客户端 |
| `ziniao list-stores` | 列出紫鸟侧会话 ID（任务需要时） |
| `ziniao open-store <id>` | 打开并接入该会话 |
| `ziniao launch [--url …]` / `ziniao connect <port>` | 非紫鸟或已有 Chrome |
| `ziniao session list` / `session switch <id>` | 多会话 |
| `ziniao --store <id> <子命令>` | 指定会话执行子命令 |
| `ziniao close-store <id>` | 关闭紫鸟会话 |

### 导航与页签

| CLI | 说明 |
|-----|------|
| `ziniao navigate <url>` | 跳转 |
| `ziniao wait <selector> [--timeout N]` | 等待元素 |
| `ziniao back` / `forward` / `reload` | 历史与刷新 |
| `ziniao tab list` / `tab new` / `tab switch` | 标签页 |

### 页面理解

| CLI | 说明 |
|-----|------|
| `ziniao snapshot --interactive` | 表格含 **Selector** 列（勿用 `@eN` 当选择器） |
| `ziniao snapshot` / `snapshot --compact` | 完整或紧凑 HTML |
| `ziniao screenshot [file] [-s <selector>]` | 截图 |
| `ziniao eval '<js>'` | 执行 JS |

### 交互

| CLI | 说明 |
|-----|------|
| `ziniao click <selector>` | 点击 |
| `ziniao fill <selector> <value>` | 清空并输入 |
| `ziniao type <text> [-s <selector>]` | 逐字输入 |
| `ziniao press Enter` | 按键（另有其它 key 子命令见 commands 文档） |
| `ziniao hover` / `dblclick` / `drag` | 见 commands 参考 |
| `ziniao act dialog accept\|dismiss` | 原生 JS 对话框 |
| `ziniao act select` / `check` / `uncheck` | 表单控件 |

### 读取与枚举

| CLI | 说明 |
|-----|------|
| `ziniao get text\|html\|value <selector>` | 读 DOM |
| `ziniao get count <selector>` | 匹配数量 |
| `ziniao find nth <n> <selector> [action]` | 列表第 n 项 |
| `ziniao url` / `ziniao title` | 页面信息 |

### 网络

| CLI | 说明 |
|-----|------|
| `ziniao network list [--filter]` | 已捕获请求 |
| `ziniao network har-start` / `har-stop [path]` | HAR 导出 |

更多选项与全局 flag（`--json`、`--timeout` 等）见 `ziniao --help` 或同仓 `skills/ziniao-cli/references/commands.md`。

## Phase 3：CLI 语义 → Python（nodriver）

### 客户端与 CDP

完整说明见 [lifecycle.md](lifecycle.md)；可运行示例 [../scripts/minimal_store_cdp.py](../scripts/minimal_store_cdp.py)。

| CLI / 概念 | Python（ziniao_webdriver + nodriver） |
|------------|----------------------------------------|
| `store start-client` / 冷启动 | `heartbeat` → 否则 `start_browser()` + `update_core(30)` → 再 `heartbeat` |
| `open-store` 成功 | `client.open_store(id)` → 取 `debuggingPort` |
| 已附着浏览器 | `await nodriver.Browser.create(host="127.0.0.1", port=cdp_port)` |
| 客户端未启动 | 同上，勿省略 `update_core`（与 `ziniao_mcp/session.py` 一致） |

### 页内操作

| CLI | nodriver 思路 |
|-----|----------------|
| `navigate url` | `await tab.get(url)` |
| `wait selector` | `await tab.select(selector, timeout=秒)` |
| `snapshot`（内容） | `await tab.get_content()` 或 evaluate 取结构 |
| `click` | `elem = await tab.select(...); await elem.click()` |
| `fill` | `clear_input` + `send_keys`（与 nodriver API 一致即可） |
| `eval` | `await tab.evaluate(js)` |
| `screenshot` | `cdp.page.capture_screenshot` |
| `tab` 切换 | `browser.tabs` / `bring_to_front` / `get(..., new_tab=True)` |

生成脚本时，保持与 Phase 1 验证过的选择器、等待顺序一致。
