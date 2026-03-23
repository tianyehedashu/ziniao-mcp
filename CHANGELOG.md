# Changelog

本文件记录本仓库（GitHub：`ziniao-mcp`）的版本变更；**PyPI 分发包名为 `ziniao`**。遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式。

## [Unreleased]

## [0.2.14] - 2026-03-23

### Changed

- **`ziniao rec replay`** / MCP **`recorder(action='replay')`**：默认在**新标签页**回放（优先录制里的 **`start_url`**，否则 **`about:blank`**）；**`--reuse-tab`** / **`reuse_tab=true`** 仍在当前活动标签上回放
- **`rec start` / `rec stop`**：若无可用普通网页标签，自动新开一页再注入/采集，避免「没有打开的页面」
- **录制生成的 `NAME.py`**：改为 **`await browser.get(start_url 或 about:blank, new_tab=True)`** 再重放，不再使用 **`browser.tabs[0]`**

### 工程

- **`pyproject.toml` / `.cursor-plugin/plugin.json` / Git tag**：与 **`v0.2.14`** 对齐

## [0.2.13] - 2026-03-23

### Added

- **Recorder CLI**: `ziniao rec view NAME` to inspect saved recordings (`--metadata-only`, `--full`, `-o` writes the same JSON as on disk); `ziniao rec status` for active capture state
- **Recorder MCP**: `recorder(action='view'|'status')`; `view` accepts `metadata_only`; `stop` accepts `force` to overwrite an existing file
- **CLI output**: human mode uses Rich tables/summaries for `rec list`, `rec view`, and `rec status` instead of dumping large raw JSON

### Changed

- **`rec stop --name`**: if `~/.ziniao/recordings/<name>.json` already exists, fail unless **`--force`** or MCP `force=true` (auto timestamp filenames unchanged)
- **MCP prompts**: recorder guide and related strings in English; group epilog uses `See: ziniao --help` (avoids awkward line wraps)

### 工程

- **`pyproject.toml` / `.cursor-plugin/plugin.json` / Git tag**：与 **`v0.2.13`** 对齐

## [0.2.12] - 2026-03-23

### 变更

- **CLI 根级 `--help` epilog**：去掉与 **agent-browser** 对照及 **docs/** 引用；保留全局选项顺序、扁平/分组命令说明、环境变量与 **NO_COLOR**；段落分行便于 Rich 阅读
- **`ziniao <group> --help`**：`GROUP_CLI_EPILOG` 去掉文档链接与 agent-browser 表述
- **`--json`**：`help` 仅描述 ziniao 信封字段；顶层 **`type`** 说明去掉外部 CLI 对比

### 工程

- **`pyproject.toml` / `.cursor-plugin/plugin.json` / Git 标签**：与 **`v0.2.12`** 对齐

## [0.2.11] - 2026-03-23

### 变更

- **CLI 根级 `--help`**：全局选项（`--store` / `--session` / `--json` / `--json-legacy` / `--content-boundaries` / `--max-output` / `--timeout`）的 **Typer `help=`** 与 **epilog** 补充 **E.g.** 示例及用法顺序说明；**`--install-completion` / `--show-completion`** 写入 epilog
- **`--content-boundaries`**：文案与实现对齐——人类 stdout 为 **`ZINIAO_PAGE_CONTENT`** 边界行，带 **`--json`** 时另有顶层 **`_boundary`**

### 工程

- **`pyproject.toml` / `.cursor-plugin/plugin.json` / Git 标签**：与 **`v0.2.11`** 对齐

## [0.2.10] - 2026-03-23

### 修复

- **`ziniao rec start`**：将 `_setup_navigation_reinjection` 提升为 `recorder` 模块顶层导出，修复 CLI 侧 `ImportError`；`dispatch` 中导航后重注入由占位改为实际调用，与 MCP 录制行为一致

### 工程

- **`pyproject.toml` / `.cursor-plugin/plugin.json` / Git 标签**：与 **`v0.2.10`** 对齐

## [0.2.9] - 2026-03-23

### 变更

- **CLI `--help`**：根级 epilog 增加 **Quick reference** 与 **agent-browser 差异** 摘要（指向 `docs/cli-agent-browser-parity.md`）；顶层快捷命令与各分组 `Typer` 的 `help=` 改为「用法形态 + Same as …」英文说明
- **`ziniao update`**：`--git` / `--dry-run` / `--sync` 与命令说明改为英文
- **去重**：移除 `info.register_top_level` 中重复的顶层 `url`（保留 `get` 注册；`ziniao info url` 不变）

### 工程

- **`pyproject.toml` / `.cursor-plugin/plugin.json` / Git 标签**：与 **`v0.2.9`** 对齐

## [0.2.8] - 2026-03-20

### 新增

- **`snapshot --interactive`**：每条交互元素自动计算 **`selector`** 字段（`#id` → `[name=…]` → `[aria-label=…]`，浏览器内验证唯一性）；终端表格显示 **Selector** 列，模型可直接用于 `click` / `fill`
- **截断提示优化**：纯 HTML 快照被截断时追加 `snapshot --interactive` 建议，引导模型获取结构化选择器

### 文档

- **`skills/ziniao-cli/SKILL.md`**：纠正「交互快照后从 HTML 选选择器」的表述；说明 `ref` 与 CSS 选择器的关系及与完整快照的配合

### 工程

- **`pyproject.toml` / `.cursor-plugin/plugin.json` / Git 标签**：与 **`v0.2.8`** 对齐

## [0.2.7] - 2026-03-20

### 文档

- **`skills/ziniao-cli/SKILL.md`**：精简并重排 Agent Skill（核心工作流、命令速查、全局选项与实现一致）；frontmatter 聚焦能力描述；移除对仓库外文档的依赖

### 工程

- **`pyproject.toml` / `.cursor-plugin/plugin.json` / Git 标签**：与 **`v0.2.7`** 对齐

## [0.2.6] - 2026-03-21

### 新增

- **`--content-boundaries`**、**`--max-output`**：与 **agent-browser** CLI 同名的全局选项；JSON 可选顶层 **`_boundary`**；长文本按字符截断。环境变量 **`ZINIAO_JSON`**、**`ZINIAO_CONTENT_BOUNDARIES`**、**`ZINIAO_MAX_OUTPUT`**（对标 `AGENT_BROWSER_*`）。终端着色遵循 **`NO_COLOR`**
- **`ziniao_mcp/cli/help_epilog.py`**：各命令分组 `Typer` 共用 `GROUP_CLI_EPILOG`，`ziniao <group> --help` 底部提示父级全局选项与对照文档（对齐 agent-browser 在子命令帮助中重复 Global Options 的体验）
- **`--json-legacy`**：输出无信封的 daemon JSON，与变更前的 `--json` 行为兼容
- **`docs/cli-json.md`**：`--json` 信封与 `jq` 示例说明
- **`docs/cli-llm.md`**：面向 Agent 的约定（对齐 agent-browser，**不**使用自创 JSON `meta` 字段）
- **`docs/cli-agent-browser-parity.md`**：与 agent-browser CLI 的全量能力对照（含 daemon `_COMMANDS` 列表）

### 变更

- **`--json`**：默认输出 `{"success","data","error"}` 信封（与 agent-browser CLI 对齐）；顶层快捷命令与 `nav` / `act` / `info` / `get` / `scroll` / `chrome` 子命令参数对齐（如 `wait` 的 `state`、`screenshot` 的 `--full-page`、`launch` 的 `--executable-path` 等）
- **移除** 实验性 **`--llm`**（顶层 `meta`）与 **`--plain`**，避免与 agent-browser 设计分叉；请改用 **`--json`** + **`--content-boundaries`** + **`--max-output`**
- **stdout 截断**：未指定 **`--max-output` / `ZINIAO_MAX_OUTPUT`** 时，快照 HTML 与 `eval` 字符串在终端 / JSON stdout 上恢复 **默认 2000 字符** 上限；**`--max-output 0`** 关闭；**`info snapshot -o`** 写入文件仍为完整 HTML / JSON

### 工程

- **`pyproject.toml` / Git 标签**：包版本与 **`v0.2.6`** 标签对齐

## [0.2.5] - 2026-03-20

### 变更

- **`ziniao update`（Windows）**：默认改为「临时 .cmd + 新控制台 + 延迟 2s + 当前进程立即退出」，避免 **`ziniao.exe` 自占用**导致 `uv` 复制失败（错误 32）；`--sync` 恢复在当前进程内同步执行（便于脚本/CI）

## [0.2.4] - 2026-03-20

### 新增

- **`ziniao update`**：通过本机 `uv tool install` 自升级 CLI（`--git` 从 GitHub `main`，`--dry-run` 仅打印命令）
- **控制台别名 `ziniao-mcp`**：与 `python -m ziniao_mcp` 等价，便于兼容旧文档与 MCP 配置

### 修复

- **`launch_chrome` 路径优先级**：未显式传入可执行路径时，先读 `CHROME_PATH` / `CHROME_EXECUTABLE_PATH`，再读配置文件，与文档一致

### 文档与工程

- 统一 PyPI 安装说明为包名 **`ziniao`**（`uvx ziniao serve`、`pip install ziniao`）；`Makefile` 的 `run` 改为 `uv run ziniao serve`
- **`.gitignore`**：忽略本地 `.chrome-test-profile/`
- **CI**：新增 `.github/workflows/ci.yml`（`pytest`，不含集成测试）
- **`pyproject.toml` 许可证元数据**：与仓库 `LICENSE`（MIT）对齐

## [0.2.3] - 2026-03-19

### 修复

- **Unix daemon 启动**：非 Windows 下启动 daemon 时补充 `stdin=subprocess.DEVNULL`，与 Windows 一致，避免继承父进程 stdin 导致终端断开后 daemon 异常

## [0.1.31] - 2026-03-19

### 修复

- **back / forward 崩溃**：CDP `getNavigationHistory` 返回 tuple 时报 `'tuple' object has no attribute 'current_index'`。新增 `_parse_navigation_history` 与 `_entry_id` 兼容 dict/tuple/object 三种返回格式

### 文档

- **README 新增 CLI 命令行工具章节**：完整列出 16 个命令组（store / chrome / session / nav / act / info / get / find / is / scroll / mouse / network / rec / batch / sys / serve）共 90 个子命令的用法、参数和常用示例
- **docs/installation.md** 补充 CLI 快速示例，引导用户从终端直接操控浏览器
- **CLI_TEST_REPORT.md** 更新全量 --help 测试结果（90 通过、0 失败），back/forward 标记为已修复

## [0.1.30] - 2026-03-18

### 修复

- **connect_chrome 空标签页**：仅在成功创建新标签页后清空目标 URL，避免异常时仍尝试导航导致逻辑错误

## [0.1.26] - 2026-03-12

### 新增

- **CDP 连接等待**：`open_store` 前轮询 CDP 端口最多 30 秒（`_wait_cdp_ready`），再尝试连接，减少“端口未就绪”失败
- **CDP 连接错误文案**：`_format_cdp_connection_error` 统一输出检查清单（先手动打开店铺、开启远程调试、防火墙），并对 WinError 1225 / ConnectionRefused 给出“端口未监听”提示
- **tabs 为空时**：`open_store` 连接成功后若无普通网页标签，自动尝试 `about:blank` 新建标签；返回中 `tabs: 0` 时附带 `hint` 引导使用 `tab new` 或先在紫鸟内打开页面

### 变更

- MCP `instructions` 与紫鸟 prompt 补充 CDP 连不上时的排查步骤
- `open_store` 工具 docstring 增加 Prerequisites（手动打开店铺、开启 CDP、防火墙）
- 测试中 `detect_ziniao_port` 的 patch 路径改为 `ziniao_webdriver.detect_ziniao_port`；新增 `_format_cdp_connection_error`、`_wait_cdp_ready` 单测

## [0.1.25] - 2026-03-12

### 变更

- **MCP 工具描述与返回文案英文化**：所有工具（store/chrome/session/input/navigation/emulation/network/debug/recorder）的 docstring、Args、返回消息与错误文案统一为英文，风格参照 chrome-devtools-mcp（短句、祈使/陈述、参数说明简洁）
- 服务器 `instructions`、argparse 描述、prompt 的 title/description 改为英文
- 录制生成脚本内的注释与 `--help` 文案改为英文

## [0.1.24] - 2026-03-11

### 新增

- **紫鸟配置可选**：不配置紫鸟环境变量也能正常启动 MCP Server，使用全部 Chrome 浏览器功能（launch_chrome、connect_chrome、页面操作、录制回放等）
- 未配置紫鸟时调用店铺工具（list_stores、open_store 等）会返回友好提示而非超时报错

### 变更

- `SessionManager` 的 `client` 参数改为 Optional，紫鸟相关方法在无 client 时抛出明确错误信息
- `create_server()` 仅在检测到紫鸟配置时才创建 `ZiniaoClient` 和检测端口，避免无紫鸟环境下的不必要开销
- 环境变量空字符串不再被视为有效配置值

### 文档

- README 快速使用新增「仅使用 Chrome 浏览器」零配置示例
- 特性列表新增「紫鸟可选」说明

## [0.1.23] - 2026-03-11

### 新增

- **Prompt「录制与回放」**：`ziniao_recorder` 指引 AI 使用 recorder 的 start/stop/replay/list/delete，含跨页录制说明

## [0.1.22] - 2026-03-11

### 新增

- **Chrome 浏览器支持**：`launch_chrome`、`connect_chrome`、`list_chrome`、`close_chrome`，与紫鸟店铺共用同一套 MCP 工具
- **统一会话管理**：`browser_session` 列出/切换/查看所有浏览器会话（紫鸟 + Chrome）
- **录制与代码生成**：`recorder` 工具支持 start/stop/replay/list/delete，生成基于 nodriver 的独立 Python 脚本
- 配置项 `chrome`（executable_path、default_cdp_port、user_data_dir、headless），支持环境变量覆盖

### 变更

- 项目描述与文档统一为「紫鸟与 Chrome 浏览器」双后端
- `stop_client` 仅关闭紫鸟店铺会话并清理对应状态，Chrome 会话不受影响
- 状态持久化区分 `backend_type`（ziniao/chrome），支持跨进程恢复两类会话
- Prompt「ziniao MCP 使用指引」补充 Chrome、会话管理、录制说明

### 文档

- README、api-reference、architecture、installation 同步更新工具列表与架构说明
- config.yaml.example 增加 chrome 配置示例

## [0.1.20] - 2026-03-10

### 文档

- **stealth.md**：反检测模块说明与配置参考

### 测试

- 新增 `tests/test_stealth.py`，覆盖 stealth 相关行为

## [0.1.18] - 2026-03-05

### 修复

- **start_client 无法启动 HTTP 服务**：从子进程环境中移除 `ELECTRON_RUN_AS_NODE`。Cursor/VS Code 宿主会设置该变量，导致 ziniao.exe 以 Node.js 模式运行而非 Electron GUI 模式，端口无法监听；`start_browser()` 现传入清理后的 `env` 再启动客户端。

## [0.1.17] - 2026-03-04

### 修复

- **open_store 空白页**：MCP 打开店铺后自动导航到紫鸟返回的 `launcherPage`（店铺平台默认启动页），与客户端手动打开行为一致
- **HTTP 超时**：紫鸟客户端请求超时缩短，避免端口不通或客户端未启动时长时间卡住——`get_browser_list` 15s、`open_store` 60s、`close_store`/`get_exit` 15s/10s、`update_core` 单次轮询 10s
- **客户端启动卡死**：`_ensure_client_running()` 和 `start_client()` 均添加 `asyncio.wait_for` 超时保护（35 秒 / 45 秒），`update_core` 重试次数从 90 降至 15，避免 MCP 调用无限阻塞导致 Cursor 报 Aborted
- **普通模式检测**：新增 `is_process_running()` 方法，检测紫鸟进程是否存在（无论模式）；当客户端以普通模式（非 WebDriver）运行时，立即返回清晰错误信息而非等待超时
- **子进程 stdio 泄漏**：`start_browser()` 的 `subprocess.Popen` 改为显式重定向 `stdin/stdout/stderr` 到 `DEVNULL`，防止子进程继承 MCP 通信管道导致服务器崩溃
- **工具层异常处理**：`list_stores` 和 `start_client` 工具添加 `try/except RuntimeError`，捕获错误返回结构化 JSON 而非崩溃 MCP 服务器

### 变更

- **open_store 返回值**：成功时增加 `launcher_page` 字段（若有）
- **list_stores**：店铺列表为空时提示检查客户端已启动、socket_port 一致、登录信息
- **start_client**：检测到普通模式实例时自动终止并以 WebDriver 模式重启，描述中说明此行为

### 文档

- **installation.md**：新增「WebDriver 模式说明」章节（模式对比、最佳实践）和「客户端以普通模式运行」故障排查

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
