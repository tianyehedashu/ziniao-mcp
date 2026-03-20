# ziniao CLI 与 agent-browser CLI 全面对照

本文档对 **agent-browser**（Rust CLI，`cli/src/output.rs` 的 `print_help` / `print_command_help`）与 **ziniao**（Typer CLI + daemon，`ziniao_mcp/cli/`）做**全量能力对照**，便于迁移脚本、对齐 Agent 提示词与排障。

> **范围**：对照的是「用户能调用的 CLI 能力」与「后端 daemon 已注册的命令名」（`dispatch.py` 中 `_COMMANDS`）。agent-browser 另有 iOS / Browserbase 等 provider，ziniao 聚焦 **紫鸟店铺 + Chrome（CDP）**。

## 1. 形态差异（先读这段）

| 项目 | agent-browser | ziniao |
|------|---------------|--------|
| 调用方式 | 扁平 `agent-browser <动词> ...`，部分为复合命令（`get text`、`network route`） | **分组** + **顶层快捷**：`ziniao nav go` 与 `ziniao navigate` 等价；完整参数以 `ziniao <group> <cmd> --help` 为准 |
| 会话 | `--session` 隔离浏览器进程（socket） | `--session` / `--store` 指向**已存在的**店铺或 Chrome 会话，**不切换**全局活动会话（仅本次命令） |
| JSON | `{ success, data, error }` | 默认 **`--json`** 已对齐该信封；**`--json-legacy`** 为原始 daemon 字典（见 [cli-json.md](cli-json.md)） |
| 帮助深度 | 根帮助 + **按命令**长帮助（Usage / Options / Examples / 环境变量） | Typer 默认帮助 + 部分命令 docstring 示例；全局选项见根 **`--help` epilog** 与本文档 |
| 批量 | stdin：**JSON 数组的「字符串数组」**，每项是一条 argv | stdin：**JSON 数组的 `{ "command", "args" }`**，与 daemon 命令名一致（见下节） |

## 2. 批量（batch）— 格式完全不同

| | agent-browser | ziniao |
|---|---------------|--------|
| 命令 | `agent-browser batch` | `ziniao batch run` |
| stdin 形状 | `[["open","https://a.com"],["snapshot","-i"]]` | `[{"command":"navigate","args":{"url":"https://a.com"}},{"command":"snapshot","args":{}}]` |
| 与 CLI 映射 | 内层字符串 = 仿 shell 的 token | `command` 必须为 **daemon 名**（如 `type_text` 而非 `type`） |

迁移时**不能**直接复用 agent-browser 的 batch JSON。

## 3. snapshot — 语义不同（对 AI 最关键）

| | agent-browser | ziniao |
|---|---------------|--------|
| 默认输出 | **无障碍树** + `@e1` 类 ref，供模型点名元素 | **HTML** 快照（或 `snapshot_enhanced`：selector / interactive / compact） |
| 选项风格 | `-i` interactive、`-c` compact、`-d` depth、`-s` selector | `--interactive`、`--compact`、`--selector`；无与 `-d` depth **完全等价**的 CLI 选项（若需需看 MCP/实现） |

从 agent-browser 迁到 ziniao 时，**不能把「snapshot = a11y 树」的假设**直接搬过来。

## 4. 导航与页签

| agent-browser | ziniao CLI（典型） | 备注 |
|---------------|-------------------|------|
| `open` / `goto` / `navigate` | `nav go`、`navigate`（顶层） | URL 行为类似 |
| `back` / `forward` / `reload` | `nav back` …、`reload --ignore-cache` | |
| `tab ...` | `nav tab ...` | 子命令均为 `list` / `new` / `switch` / `close` 等，以 `--help` 为准 |
| `frame ...` | `nav frame ...` | |
| `wait <sel\|ms>` | `nav wait`（selector + `--state` + ms） | agent-browser 支持纯毫秒等待；ziniao 以 daemon `wait` 为准 |
| `connect` | `chrome connect` / 顶层 `connect` | |
| `close`（关浏览器） | `chrome close <session_id>`、`quit`（关 daemon） | 语义分层不同 |

## 5. 交互（点击、输入、键盘）

| agent-browser | ziniao | 备注 |
|---------------|--------|------|
| `click` | `act click` / 顶层 `click` | |
| `fill <sel> <text>` | `act fill` | ziniao 另支持 `--fields-json` |
| `type <sel> <text>` | `act type TEXT [--selector SEL]` | **参数顺序相反**：ziniao 先正文再选择器 |
| `press` / `key` | `act press` | |
| `keyboard type` / `keyboard inserttext` | **无对等 CLI** | 需用 `eval` 或 MCP；daemon 无同名子系统 |
| `hover` / `focus` / `check` / `uncheck` / `select` | `act …` | |
| `dblclick` | `act dblclick` | |
| `drag` / `upload` | `act drag` / `act upload` | |
| `download <sel> <path>` | **无** | agent-browser 专用 |
| `dialog`（handle） | `act dialog` | |

## 6. 滚动与鼠标

| agent-browser | ziniao |
|---------------|--------|
| `scroll <dir> [px]` | `scroll up|down|left|right`；顶层 `scroll-up` … |
| `scrollintoview` / `scrollinto` | `scroll into`；顶层 `scrollinto` |
| `mouse move|down|up|wheel` | `mouse move|down|up|wheel` |

## 7. 页面信息、调试、存储

| agent-browser | ziniao | 备注 |
|---------------|--------|------|
| `screenshot` | `info screenshot` / 顶层 | |
| `pdf` | **无** | |
| `eval` | `info eval` / 顶层 | |
| `console` / `errors` | `info console` / `info errors` | |
| `highlight` | `info highlight` | |
| `cookies` / `storage` | `info cookies` / `info storage` | 子参数以 `--help` 为准 |
| `clipboard` | `info clipboard` | |
| `inspect` | **无** | 打开 DevTools |
| `trace` / `profiler` | **无** | |
| `record start|stop`（视频 WebM） | **无**；有 **`rec start|stop|replay`**（录制回放流，语义不同） | |
| `diff snapshot|screenshot|url` | **无** | |

## 8. get / is / find

| agent-browser | ziniao | 备注 |
|---------------|--------|------|
| `get text|html|value|attr|title|url|count` | `get …` / 顶层同名快捷 | |
| `get box|styles|cdp-url` | **无** | |
| `is visible|enabled|checked` | `is visible|enabled|checked` | |
| `find role|text|label|placeholder|alt|title|testid|first|last|nth` | `find first|last|nth|text|role` | ziniao **无** label/placeholder/alt/title/testid 的独立 find 子命令（能力可能在 MCP 层或需 selector） |

`find` 分组**无顶层快捷**（仅 `ziniao find …`）。

## 9. 网络

| agent-browser | ziniao |
|---------------|--------|
| `network route|unroute|requests|har` | `network route|unroute|routes|list|har-start|har-stop` |

命名与子参数不完全一致，迁移前请对 `ziniao network --help` 与各子命令 `--help`。

## 10. 浏览器设置 / 仿真

| agent-browser | ziniao |
|---------------|--------|
| `set viewport|device|geo|offline|headers|credentials|media` | **`sys emulate`**（device / width / height）为主；无完整 `set` 对等 |
| `emulate`（iOS 等） | 见 agent-browser provider；ziniao 不走该路径 |

## 11. 认证、确认、状态持久化（agent-browser 独有）

| agent-browser | ziniao |
|---------------|--------|
| `auth save|login|list|show|delete` | **无** |
| `confirm` / `deny` | **无** |
| `state save|load`（cookies+storage JSON） | **无**；可用 Chrome `user_data_dir`、紫鸟店铺环境代替部分场景 |

## 12. 会话与安装（名称类似、语义不同）

| agent-browser | ziniao |
|---------------|--------|
| `session` / `session list`（本机 socket 会话） | `session list|switch|info`（**Ziniao + Chrome 逻辑会话**） |
| `install` / `upgrade` | **`ziniao update`**（uv 升级 CLI）；浏览器安装不在此 CLI |
| `config`（agent-browser.json） | **`ziniao config`**（`~/.ziniao` YAML/.env） |

## 13. 仅 ziniao 具备（与 agent-browser 无直接对应）

| 能力 | CLI 入口 |
|------|----------|
| 紫鸟店铺 | `store …`、顶层 `list-stores` / `open-store` / `close-store`、`start-client` / `stop-client` |
| 启动/列出/关闭 Chrome 会话 | `chrome launch|connect|list|close`、顶层 `launch` / `connect` |
| MCP Server | `ziniao serve` |
| 配置向导与导出 | `ziniao config init|show|set|path|env` |
| Daemon 生命周期 | `sys quit`、顶层 `quit`；`sys emulate` |

## 14. ziniao daemon 已注册命令一览（batch / MCP 用）

与 `ziniao batch run` 的 `command` 字段一致（节选归类）：

- **店铺**：`list_stores`、`open_store`、`close_store`、`start_client`、`stop_client`
- **Chrome**：`launch_chrome`、`connect_chrome`、`list_chrome`、`close_chrome`
- **会话**：`session_list`、`session_switch`、`session_info`
- **导航**：`navigate`、`tab`、`frame`、`wait`、`back`、`forward`、`reload`
- **交互**：`click`、`fill`、`type_text`、`press_key`、`hover`、`drag`、`upload`、`handle_dialog`、`dblclick`、`focus`、`select_option`、`check`、`uncheck`、`keydown`、`keyup`
- **信息**：`snapshot`、`snapshot_enhanced`、`screenshot`、`eval`、`console`、`network`
- **查询**：`get_text`、`get_html`、`get_value`、`get_attr`、`get_title`、`get_url`、`get_count`
- **查找**：`find_nth`、`find_text`、`find_role`
- **状态**：`is_visible`、`is_enabled`、`is_checked`
- **滚动/鼠标**：`scroll`、`scroll_into`、`mouse_move`、`mouse_down`、`mouse_up`、`mouse_wheel`
- **存储**：`cookies`、`storage`
- **调试**：`errors`、`highlight`
- **剪贴板**：`clipboard`
- **网络**：`network_route`、`network_unroute`、`network_routes`、`har_start`、`har_stop`
- **录制**：`recorder`（由 `rec` CLI 封装参数）
- **仿真**：`emulate`
- **退出**：`quit`（在 `dispatch` 中单独分支处理，**不在** `_COMMANDS` 表里；`ziniao batch run` 仍可传 `"command":"quit"`）

## 15. 维护建议

1. **改 CLI 时**：同步更新 Typer 的 `help=` / docstring、[README CLI 章节](../README.md#cli-命令行工具)、以及本文档中与 agent-browser 的对照行。
2. **面向 AI Agent**：在提示词中明确 **snapshot 格式差异** 与 **batch JSON 差异**，避免混用 agent-browser 文档中的示例。
3. **全局选项在子分组中的可见性**：各命令分组 Typer（`nav`、`act`、`info` 等）共用 `ziniao_mcp/cli/help_epilog.py` 中的 **`GROUP_CLI_EPILOG`**，在 `ziniao GROUP --help` 底部提示 `--store` / `--session` / `--json` 等与对照文档路径（对齐 agent-browser 在子命令帮助里重复 Global Options 的做法）。

4. **若要对齐 agent-browser 单命令长帮助**：可继续为高频命令增加 docstring 示例或独立 Markdown（类似 `print_command_help`）。

---

对照基准：**agent-browser** `cli/src/output.rs` 中 `print_help`（约 2484 行起）与 `print_command_help` 各分支；**ziniao** `ziniao_mcp/cli/__init__.py` 注册的 Typer 应用与各 `commands/*.py`，以及 `ziniao_mcp/cli/dispatch.py` 中 `_COMMANDS`。
