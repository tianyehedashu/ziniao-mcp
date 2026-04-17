# Changelog

本文件记录本仓库（GitHub：`ziniao-mcp`）的版本变更；**PyPI 分发包名为 `ziniao`**。遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式。

## [Unreleased]

## [0.2.55] - 2026-04-17

### Added

- **站点媒体契约（`media_contract`）声明式扩展机制**：`--save-images` 改为读站点侧声明，主包不再识别任何具体字段名（`encodedImage` / `fifeUrl` / `images[]` 全部移出）。三级扩展路径 —— (a) preset JSON 顶层 `media_contract: [...]` 零代码声明（`items_at` + `fields` 列表规则、`at` + `source` 单字段规则）；(b) 在 `SitePlugin` 子类中 override `media_contract(result, spec)` 跑任意 Python 逻辑；(c) 什么都不做，默认返回 `[]`。dotted path 支持 dict 键和数字列表索引（`data.pages.0.url`、`arr.-1.key`）；`stem_suffix` 支持 `{idx}` / `{field}` 占位符，多字段默认模板为 `-{idx}-{field}`，单字段为 `-{idx}`
- **站点响应契约（`response_contract`）声明式扩展机制**（与 `media_contract` 对称）：把"JSON body 解析 + 把感兴趣字段提升到顶层"的旧样板代码从 Python 迁到 preset JSON。Schema：`{ "parse": "json", "lift": [ { "from": "<dotted>", "to": "<top-key>", "when_eq": { "<path>": <literal> } } ] }`。三级扩展 —— (a) preset JSON 顶层声明；(b) `SitePlugin.after_fetch(response, spec)` override（可先调 `super().after_fetch()` 保留声明式规则）；(c) 不声明不 override 即 no-op。`when_eq` 为字面量等值合取（AND），不支持 DSL / eval；任一规则失败静默跳过，不影响其他规则与整体响应
- **新模块 `ziniao_mcp/sites/save_media.py::compile_media_contract` 与 `ziniao_mcp/sites/response_contract.py::apply_response_contract`**：前者把声明式媒体规则编译为 `apply_media_contract` 可执行的 save item 列表，后者把声明式响应规则应用到 `response` dict；均复用统一的 dotted path walker，非法规则静默跳过，一条坏规则不拖累整批
- **SKILL / 文档同步**：`site-development` SKILL 改写"Media Output"章节（三级扩展路径 + 智能默认 + 冲突校验）并新增"Response Output Contract"章节；Plugin Hooks 表同步更新 `after_fetch` / `media_contract` 行说明；JSON Template Field Reference 补 `media_contract` / `response_contract` 两个字段；Troubleshooting 增补"`--save-images` 无输出" / "`response["parsed"]` 升级后丢失"两条排查项

### Changed

- **`SitePlugin.media_contract` 签名破坏性变更**：从 `(self, result)` 扩展为 `(self, result, spec)`，下游插件同步升级即可。`spec` 参数让 override 能读到 preset 所有字段（而不仅是响应体），便于实现"按 preset 分支生成不同契约"
- **`SitePlugin.after_fetch` 第二参数重命名（破坏性但无行为变化）**：`(self, response, request)` → `(self, response, spec)`。实参一直是完整 rendered preset，旧名 `request` 语义误导；新名与 `media_contract(result, spec)` 对齐。`pagination.run_site_fetch` 里所有 `after_fetch` 调用点统一改为 `(plugin or SitePlugin()).after_fetch(out, spec)`，让声明式 `response_contract` 对无 Python 插件的站点同样生效
- **多字段 `stem_suffix` 冲突保护**：多 `fields` 规则若使用不含 `{field}` 的自定义模板，`compile_media_contract` 抛 `ValueError("…collide…")` 拒绝运行 —— 旧版本会静默覆盖同名文件导致数据丢失
- **`_spec_for_page_fetch` 过滤 CLI-only 字段**：`media_contract` / `response_contract` 声明仅客户端消费，daemon 侧 page_fetch 拿不到也不需要；`_CLI_ONLY_SPEC_KEYS` 过滤集同时覆盖两者，避免 TCP 流量浪费
- **site-hub/google-flow 两份 preset 同步改为 JSON 声明式契约**：`imagen-generate.json` 声明 `encodedImage` + `fifeUrl` 双字段（runImageFx / batchGenerateImages 两条分支都兼容）；`imagen-ref-generate.json` 只声明接口实际返回的 `fifeUrl`（修复旧契约虚假字段）；`GoogleFlowPlugin` 精简为仅保留 `site_id`，媒体契约完全由 JSON 驱动
- **site-hub/rakuten 15 份 JSON-API preset 迁移到声明式 `response_contract`**：`RakutenPlugin.after_fetch` 的"`{status: SUCCESS, data: …}` → `response["parsed"] = data`" Python 逻辑彻底删除；`afl-report-pending` / `cpa-reports-search` / `cpnadv-performance-retrieve[-item]` / `rmail-reports` / `rpp-exp-merchant` / `rpp-exp-report[-item]` / `rpp-search[-item]` / `shared-purchase-detail` / `tda-exp-report[-item]` / `tda-reports-search[-item]` 全部声明同一份 `response_contract`，CSV preset（`reviews-csv` / `datatool-deal-csv`）保持原样不受影响

### Removed

- **`ziniao_mcp/sites/save_media.py::strip_and_save_encoded_images`**：硬编码 Google Flow `images[]` 契约的旧函数，已被通用 `apply_media_contract` 取代
- **`ziniao_mcp/cli/output.py` 中硬编码的 `ziniao google-flow imagen-generate ...` 提示**：与主包"无具体站点字段知识"原则冲突

## [0.2.54] - 2026-04-17

### Added

- **CLI 版本查询**：根命令支持 `ziniao --version` / `ziniao -V`（`is_eager`，不经 daemon）；子命令 `ziniao version` 等价输出

## [0.2.52] - 2026-04-17

### Fixed

- **`ziniao update` 在 Windows 默认路径下未真正执行升级**：原实现中 `_kill_blocking_nt` 仅排除 `os.getpid()`，会把自身父进程（uv trampoline shim `~/.local/bin/ziniao.exe`）一并杀掉；uv 的 Job Object 连带终止 Python 子进程，主进程在打印完 uv 命令行后就异常退出，升级新窗口与 `_windows_spawn_uv_tool_install` 全程未被调用。现在 `_self_protected_pids()` 同时包含当前 PID 与 `os.getppid()`，Windows 默认路径的主进程不再执行 kill，kill 完全交给新控制台的 `.cmd` 执行
- **同名进程（如紫鸟浏览器）误杀风险（两侧对齐）**：Python 侧 `_kill_blocking_*` 按**绝对路径**比对；Windows 异步路径 `.cmd` 里的 PowerShell 段同样改为按**精确路径 + protected PID 白名单**（见 `_build_nt_kill_ps`）。原先 `.cmd` 还在用 `-like '*\\.local\\bin\\ziniao.exe' / '*\\uv\\tools\\ziniao\\*'` 模糊 wildcard，任何带同字面结尾的同名进程（紫鸟浏览器、名字含 `ziniao` 的第三方工具）都会被牵连——现已彻底堵上
- **`--no-kill` 在有 daemon 运行时几乎必败**：旧实现里 `--no-kill` 连"优雅请 daemon `quit`"也一并跳过；而 daemon 持有 `<uv tool dir>/ziniao/**` 下的 `.pyd` / `python.exe` 句柄，uv 安装必然撞 ERROR 32。现在 `--no-kill` 的严格语义是"只跳过**强杀**"，graceful quit 仍会运行；帮助文本同步更新

### Added

- **升级前优雅停 daemon**：`update` 在任何 kill 路径之前先通过 TCP 向 daemon 发送 `{"command":"quit"}`，让 `SessionManager.cleanup()` 正常执行（关 CDP、flush 录制器、释放店铺会话），再由原有 kill 逻辑兜底处理残留；彻底避免 Windows 下 `Stop-Process -Force` 无感强杀 daemon 导致的资源悬挂与在途请求被无声打断问题
- **环境变量 `ZINIAO_UPDATE_QUIT_TIMEOUT`**：覆盖优雅退出轮询上限（默认 15s——活跃店铺多 / 录制器 flush 较慢时 5s 真实不够；负值/0 视作"不等直接进入强杀"）。超时提示文案带出该变量名
- **升级结果在原终端可见**：`.cmd` 升级完成后原子写入 state 文件（`uv_exit_code` / `new_version` / `status`），主进程轮询并在原 PowerShell 打印"升级完成 + 新版本号"或"升级失败 + uv 退出码"，告别"看完两行就结束、没新窗口、不知是否升级"的体验
- **升级后真版本自证**：新窗口内通过 `<uv tool dir>/ziniao/Scripts/python.exe -c "importlib.metadata.version('ziniao')"` 探测实际生效版本，与 state 文件一并回传
- **环境变量 `ZINIAO_UPDATE_NO_WAIT`**：CI 或想保持"立即退出"的场景可跳过主进程轮询
- **测试**：`tests/test_update_cmd.py` 新增"自身/父进程保护"、"同名进程不误杀"、"state 文件与版本探测"、"Windows 默认路径必须 spawn"、"升级前必须先优雅停 daemon 再 kill/uv"、".cmd 里 PS 必须用精确路径 + protected PID 白名单"、"`--no-kill` 仍调用 graceful"、"路径含单引号时 PowerShell 字面量正确转义"等回归用例（共 41 条）

### Changed

- `ziniao update` 成功提示不再建议用户手动执行 `ziniao quit`——旧 daemon 已在升级入口被优雅停止，下次 ziniao 命令会按需自动启动新 daemon
- `--no-kill` 语义从"不动任何 ziniao 进程（含 daemon）"改为"只跳过**强杀**；graceful quit 仍执行"——避免退化成必败路径

## [0.2.51] - 2026-04-17

### Fixed

- **Windows `ziniao store start-client` 静默退出**：`kill_process` 不再使用 `taskkill /im` 误杀 uv CLI 壳；按 `ExecutablePath` 过滤后用 `taskkill /f /t /pid` 精确终止紫鸟客户端
- **`kill_process` 返回值**：Mac/Linux 在 `killall` 未命中时返回 `False` 且不再无意义 `sleep(3)`；与 Windows「至少杀到一个才 True」语义对齐
- **daemon 空闲关机误判**：`_inflight` 与活跃店铺计数参与 idle watchdog；长耗时命令期间刷新 `_last_activity`
- **`handle_client` 空连接**：初始化 `response`、可选写回、调试日志；`writer` 写回/关闭失败可观测

### Added

- **测试**：`tests/test_daemon_idle.py`（idle watchdog 与 `handle_client` 边界）

### Changed

- **README**：围绕 CLI / Site Presets / Skills 重组安装与命令说明

## [0.2.50] - 2026-04-17

### Added

- **站点预设 `mode: ui`**：声明式 UI 流程（`steps[]`）、`action: extract` / `action: fetch`、`output_contract`、`on_error` 失败快照与截图；`flow_run` 慢命令超时
- **`vars` 中 `type: secret`**：keyring / 环境变量 / 交互输入解析；`output_contract` 与 selector 等字段校验防泄密；失败 HTML / `.err.txt` 经 `_mask_secrets` 脱敏
- **`ziniao_mcp.sites.save_media`**：通用 `save_base64_as_file` / `download_url_to_file` / `strip_and_save_encoded_images`；`flow_images` 保留为兼容 shim
- **文档**：`docs/site-ui-flows.md`、`docs/next-app-reverse-engineering.md`；`docs/CLAUDE.md` 索引更新
- **测试**：`test_flow_run`、`test_secret_var`、`test_flow_images`、`test_sites_file_var`；Click 8.3+ 下移除 `CliRunner(mix_stderr=...)`

### Fixed

- **`human_click` / `human_hover` 卡死**：`_move_mouse_humanlike` 不再经 `tab.evaluate` 读写 `window._lastMouseX`；鼠标末位坐标用 `WeakKeyDictionary` 按 Tab 缓存
- **`extract kind=eval` 与 `ziniao eval` 解包**：`_safe_eval_js` 直连 `cdp.runtime.evaluate`，修正 falsy JSON 与 `RemoteObject` 泄漏；错误信息仅用 `text` + `exception.description`，避免 `repr(RemoteObject)`
- **`eval_in_frame`**：新增 `strict=`；`_run_js_in_context` 统一主文档与 iframe 的异常契约；`insert_text` 带 selector 且元素未找到时显式报错
- **`_inline_fetch_step`**：避免 body 双重 JSON 序列化；失败产物文件名毫秒级 + 步骤序号防碰撞
- **`load_preset`**：正确处理 `Path` 型仓库扫描结果

### Changed

- **`site-hub` 子模块**：`v0.2.0` → **`v0.2.1`**（Google Flow 预设、`flow-demo`、`site-development` SKILL 等）
- **Ruff format**：对 `ziniao_mcp/cli/dispatch.py`、`iframe.py`、`stealth/human_behavior.py` 等与本次改动强相关文件统一格式
- **`lifecycle.py`**：移除未使用的 `signal` / `sys` import（Ruff F401）

## [0.2.48] - 2026-04-15

### Fixed

- **`ziniao quit` 自动清理残留进程**：daemon 关闭后自动 kill 所有残留 ziniao.exe 进程，解决升级时文件锁定（os error 32）的问题。即使 daemon 不可达也会执行清理

## [0.2.47] - 2026-04-15

### Added

- **OpenClaw agent 支持**：`ziniao skill install <name> -a openclaw` 安装 skill 到 `~/.openclaw/skills`（OpenClaw 共享 skill 目录）

## [0.2.46] - 2026-04-15

### Changed

- **`ziniao site update` 自动安装新 skill**：更新 repo 后自动将新发现的 skill 通过 junction 链接到所有已配置的 agent 目录，无需手动 `ziniao skill install`
- **`refresh_symlinks` 返回值变更**：从 `int` 改为 `tuple[int, int]`（refreshed, installed），支持 `auto_install` 参数

## [0.2.45] - 2026-04-15

### Fixed

- **`is_junction` AttributeError**：`skill_cmd.py` 中 `Path.is_junction()` 仅在 Python 3.12+ 可用，改为兼容 3.10+ 的检测方式，修复 `ziniao site update` 在旧 Python 上崩溃的问题

## [0.2.44] - 2026-04-15

### Changed

- **移除 `ziniao-mcp` 可执行文件入口**：统一为单一入口 `ziniao`；MCP 服务通过 `ziniao serve` 或 `python -m ziniao_mcp` 启动，架构更清晰，安装更快、进程占用更少
- **`task.ps1 run`**：`ziniao-mcp` → `ziniao serve`
- **文档统一**：README / CLAUDE / docs / scripts 中可执行文件引用全部对齐为 `ziniao` / `ziniao serve` / `python -m ziniao_mcp`

## [0.2.43] - 2026-04-11

### Added

- **仓库文档索引**：根与各包 **`CLAUDE.md`**（`ziniao` / `ziniao_mcp` / `ziniao_webdriver` / `tests` / `scripts` / `docs`）
- **`docs/directory-conventions.md`**：物理目录用途、wheel 边界与 `exports/` 等落盘约定
- **Cursor skills**：`engineering-lint-test`（Ruff/Pylint/uv 约定）、`strict-code-review`（Diff 评审）

### 工程

- **`pyproject.toml` / `.cursor-plugin/plugin.json`**：与 **`v0.2.43`** 对齐

## [0.2.42] - 2026-04-10

### Added

- **Cursor skill `rakuten-ad-reports`**：`references/SCRIPTS.md`；可执行脚本 `run_ad_batch.ps1`、`aggregate_ad_exports.py`、`merge_rpp_search_json.py`、`merge_cpnadv_report_json.py`、`fetch_rpp_search_slices.ps1`
- **Cursor skill `rakuten-reviews`**：`references/SCRIPTS.md`；`analyze_reviews_csv.py`

### Changed

- **`rakuten-ad-reports` / `rakuten-reviews` SKILL**：交付规范、与 SCRIPTS/scripts 的交叉引用及目录结构与广告技能对齐

### 工程

- **`pyproject.toml` / `.cursor-plugin/plugin.json`**：与 **`v0.2.42`** 对齐（补齐此前与变更日志的插件版本差）

## [0.2.39] - 2026-04-11

### Added

- **站点预设 `rakuten/reviews-csv`**：RMS 评论一览 CSV；**`last_days`**（默认 30，日本时间自然日）或 **`start_date` + `end_date`**；预设 **`output_decode_encoding: cp932`**
- **`coerce_page_fetch_eval_result`**（`ziniao_mcp.sites`）：统一 **`page_fetch`** 在 fetch / js 两种模式下对 **`evaluate` 返回值**的解析与 **`body_b64` → `body`** 解码

### Changed

- **`page_fetch`（`mode: js`）**：若页面脚本返回 **`ArrayBuffer` / `Uint8Array`**，在页内编码为 **`body_b64`**，与 fetch 模式一致，**`-o`** 可无损落盘
- **内置站点插件 `get_plugin`**：仅将 **`ModuleNotFoundError`** 视为「无内置包」；存在多个 **`SitePlugin`** 子类时须设置模块级 **`SITE_PLUGIN`**；**`rakuten`** 显式导出 **`SITE_PLUGIN`**
- **文档与技能**：`site-fetch-and-presets`、API 参考、`ziniao-cli` skill、乐天 preset 冒烟表与脚本、**`rakuten-ad-reports`** skill（含评论 CSV）

### Fixed

- **乐天 `reviews-csv`**：显式日期时校验 **`start_date` ≤ `end_date`**

### 工程

- **`pyproject.toml` / `.cursor-plugin/plugin.json` / Git tag**：与 **`v0.2.39`** 对齐

## [0.2.38] - 2026-04-10

### Changed

- **`-o` / `save_response_body`**：无 **`--decode-encoding`** / **`--output-encoding`** 时，若响应体为 **严格 UTF-8** 则默认写入 **UTF-8 文本**（JSON 仍自动 **pretty-print**）；否则写入 **原始字节**（如未声明 charset 的 **CP932** CSV，需 **`--decode-encoding cp932`** 再得 UTF-8 文件）

### Added

- **`--decode-encoding`**（`ziniao network fetch` / `ziniao <site> <action>`）：按指定 codec 解码 **`body_b64`** 后再落盘（与 **`--output-encoding`** 配合；未指定时文件编码默认 **utf-8**）

### 工程

- **`pyproject.toml` / `.cursor-plugin/plugin.json` / Git tag**：与 **`v0.2.38`** 对齐

## [0.2.37] - 2026-04-09

### Fixed

- **`ziniao network fetch` / `ziniao <site> <action>`（`-o`）**：`page_fetch` 不再用浏览器 **`Response.text()`** 作为唯一数据源，改为 **`arrayBuffer()` → Base64** 传回 **`body_b64`**，避免 Shift_JIS / 错误 charset / 二进制体在 JS 侧被替换成 **U+FFFD**（文件中 **`ef bf bd`**）后不可恢复
- **`save_response_body`**：默认按 **原始字节** 落盘（类 curl）；**UTF-8 JSON** 仍自动 **pretty-print**；新增 **`--output-encoding`** 将响应按 **Content-Type charset** 解码后再以指定编码写入文本

### Added

- **`parse_charset` / `decode_body_bytes`**（`ziniao_mcp.sites`）：供 **`body` 字符串** 按响应头 charset 解码，兼容分页与插件
- **测试**：`tests/test_response_encoding.py` 覆盖 charset 解析、多编码解码与 **`-o` 字节级一致性**

### 工程

- **`pyproject.toml` / `.cursor-plugin/plugin.json` / Git tag**：与 **`v0.2.37`** 对齐

## [0.2.36] - 2026-04-02

### Fixed

- **`page_fetch`（fetch / js 模式）**：与 **`ziniao eval`** 一致，在存在 **`iframe_context`** 时在 **子帧 execution context** 内执行脚本；修复顶层 `document` 读不到 **`meta` / storage** 导致 **`header_inject` 失效**（乐天 **`rakuten/cpnadv-performance-retrieve`** 等 401）
- **乐天 `cpnadv-performance-retrieve`**：**`x-csrf-token`** 改为从 **`<meta name="_csrf">`** 读取（与页面 `fetch` 一致；Cookie **`XSRF-TOKEN`** 与 meta 值不一致）；**`displayStatuses`** 与浏览器一致使用 **`%2C`**

### Added

- **`scripts/rakuten_presets_smoke.py`**：乐天 11 条 preset 冒烟；**`--save`** 将 **`ziniao --json --max-output 0`** 完整输出写入 **`out/rakuten-preset-responses/`**
- **文档**：[docs/rakuten-presets-smoke-test.md](docs/rakuten-presets-smoke-test.md)；[site-fetch-and-presets.md](docs/site-fetch-and-presets.md) / [page-fetch-auth.md](docs/page-fetch-auth.md) 补充 **iframe 与 page_fetch** 说明

### 工程

- **`pyproject.toml` / `.cursor-plugin/plugin.json` / Git tag**：与 **`v0.2.36`** 对齐

## [0.2.35] - 2026-04-02

### Changed

- **站点动态分组（`ziniao <site>`）**：**`--help`** 子命令表首段与无参列表共用 **`_preset_listing_suffix`**，`[mode]` / `[auth]` / `(paginated)` / `(vars: …)` 与直接执行 **`ziniao <site>`** 一致

### Added

- **`ziniao <site>`** 与 **`ziniao <site> --help`** 底部增加 **`Example: …`**（选取该站点下首条含必填变量的 preset，用 **`var_defs` 的 example** 拼命令行；分页预设追加 **`--all`**）；Typer 分组 **`epilog`** 与无参尾注同步

### Fixed

- **CLI**：**`site_cmd`** 将 **`_pick_example_line` / `_set_site_callback`** 置于 **`register_site_commands`** 之前，消除 Pylint 对「未定义变量 / 实参过多」的误报

### 工程

- **`pyproject.toml` / `.cursor-plugin/plugin.json` / Git tag**：与 **`v0.2.35`** 对齐

## [0.2.34] - 2026-04-02

### Breaking

- **页面内 fetch · Header 注入**：移除 **`xsrf_cookie`** / **`xsrf_headers`**；统一为声明式 **`header_inject`**（`source`: `cookie` | `localStorage` | `sessionStorage` | `eval`，见文档）
- **`ziniao network fetch`**：**`--xsrf-cookie` / `--xsrf-header`** 改为可重复的 **`--inject`**（紧凑 `source:key=header` 或 JSON 对象）
- **`ziniao network fetch-save`**：输出 **`header_inject`** 替代 `xsrf_*`
- **MCP `page_fetch`**：参数 **`header_inject`**（JSON 数组字符串）替代 `xsrf_cookie` / `xsrf_headers`
- **乐天内置预设**：8 个 `xsrf` 模板已改为 **`header_inject`** 数组

### Added

- **文档**：[docs/page-fetch-auth.md](docs/page-fetch-auth.md)（替代已删除的 `page-fetch-xsrf.md`）

### Fixed

- **测试**：Typer **`CliRunner`** 在 Click 8+ 默认混合 stderr 时访问 **`result.stderr`** 会报错；相关用例改为 **`CliRunner(mix_stderr=False)`**

### 工程

- **`pyproject.toml` / `.cursor-plugin/plugin.json` / Git tag**：与 **`v0.2.34`** 对齐

## [0.2.33] - 2026-04-02

### Added

- **页面内 fetch · XSRF/CSRF**：预设与 CLI 统一使用 **`xsrf_headers`**（字符串数组）；**`_normalize_xsrf`** 在 **`prepare_request`** 与 **`_page_fetch_fetch`** 中归一化；仅 **`xsrf_cookie`** 时默认 **`["X-XSRF-TOKEN"]`**
- **`network fetch`**：可重复 **`--xsrf-header`**，经 **`prepare_request(xsrf_headers=...)`** 覆盖预设
- **`network fetch-save`**：表驱动识别 CSRF 请求头（**`_CSRF_REQUEST_HEADER_NAMES_ORDERED`**），输出 **`xsrf_cookie` + `xsrf_headers`**
- **MCP `page_fetch`**：**`xsrf_headers`** 参数（JSON 数组字符串）
- **乐天**：**`rakuten/cpnadv-performance-retrieve`** 使用 **`x-csrf-token`** 请求头（修复该接口 401）

### Changed

- **移除** 单字段 **`xsrf_header`**（不再后向兼容）
- **`ziniao site list`**：人类输出增加列说明图例；**`site`** 组帮助与 **`ziniao <site>`** 尾注指向 **`site list`**
- **文档**：[docs/site-fetch-and-presets.md](docs/site-fetch-and-presets.md) 增加架构图与 **会话鉴权（`auth.type`）** 说明；新增 [docs/page-fetch-xsrf.md](docs/page-fetch-xsrf.md)；**README**、**api-reference** 索引同步

### 工程

- **`pyproject.toml` / `.cursor-plugin/plugin.json` / Git tag**：与 **`v0.2.33`** 对齐

## [0.2.32] - 2026-04-01

### Changed

- **站点动态分组（`ziniao <site>`）**：无子命令时输出与 **`ziniao site list`** 同款的 **`[mode]` / `[auth]`**、分页与 **`(vars: …)`** 表格（共用 **`_echo_preset_table`**）；**`ziniao <site> --help`** 仍为 Typer 标准帮助

### 工程

- **`pyproject.toml` / `.cursor-plugin/plugin.json` / Git tag**：与 **`v0.2.32`** 对齐

## [0.2.31] - 2026-04-01

### Added

- **`ziniao <site> <action> --help`**：由 preset **`var_defs`** 生成变量说明、必填示例与分页提示；站点子命令组帮助含命令数量与 **`site list` / `site show`** 指引
- **`list_presets()`**：返回体增加 **`var_defs`**（与 JSON **`vars`** 同源），供 CLI / 集成方展示变量元数据

### Changed

- **乐天文档 / preset**：**`ref.md`** 补充 **merchant → `shopUrl` → `x-shop-url` / `-V shop_url=`** 推荐顺序；**`rpp-exp-merchant`** 描述对齐接口与报表头关系

### 工程

- **`pyproject.toml` / `.cursor-plugin/plugin.json` / Git tag**：与 **`v0.2.31`** 对齐

## [0.2.28] - 2026-03-30

### Added

- **`ziniao site fork`** / **`ziniao site copy`**：将当前生效的 preset 写入 **`~/.ziniao/sites/`**（单参默认同名覆盖内置；可选目标 ID、`--force`）；**`fork_preset`** API
- **`ziniao site show --raw`**：打印原始 preset JSON（无 CLI 信封）
- **文档 / 技能**：**[docs/site-fetch-and-presets.md](docs/site-fetch-and-presets.md)** 增加 fork 工作流；**`skills/ziniao-cli/SKILL.md`** 速查更新

### Changed

- **`network fetch` / `ziniao <site> <action>`**：鉴权说明改为灰色 **`ℹ`** 样式；preset **`auth.show_hint`**（默认 `true`）可关闭逐次提示；**`rakuten/rpp-search`** 默认不打印 fetch 前 hint

### Fixed

- **`fork_preset`**：对 **source** preset ID 做与 destination 相同的安全校验，拒绝路径穿越式 ID

### 工程

- **测试**：**`tests/test_sites_fork.py`**
- **`pyproject.toml` / `.cursor-plugin/plugin.json` / Git tag**：与 **`v0.2.28`** 对齐

## [0.2.27] - 2026-03-29

### Added

- **页面内 HTTP**：`ziniao network fetch`（preset / `-f` / URL / `--script` js 模式）、`ziniao network fetch-save`；daemon **`page_fetch`**；MCP 工具 **`page_fetch`**
- **站点模板（site presets）**：`ziniao_mcp/sites/` 与 `~/.ziniao/sites/` 发现 JSON；**`ziniao site list|show|enable|disable`**；顶层 **`ziniao <site> <action>`**（如 **`ziniao rakuten rpp-search`**）；内置 **`rakuten/rpp-search`** 示例
- **模板字段**：**`auth`**（类型 + `hint`）、**`pagination`**（`body_field` / `offset`）支持 **`--page`**、**`--all`** 合并分页；**`run_site_fetch`** / **`prepare_request`** 等共用逻辑
- **`ziniao eval --await`**：等待 Promise；**iframe** 内 **`eval_in_frame(await_promise=...)`** 与主文档行为一致
- **文档**：**[docs/site-fetch-and-presets.md](docs/site-fetch-and-presets.md)**；**`docs/api-reference.md`** 补充 **`page_fetch`**；**README**、**`skills/ziniao-cli`**

### Changed

- **`ziniao update`**：执行前打印当前包版本与升级来源（PyPI / GitHub）；Windows 新控制台升级提示改为 **stdout**
- **网络子命令帮助**：**`network`** 组描述含 fetch

### 工程

- **测试**：**`tests/test_sites_pagination.py`**、**`tests/test_update_cmd.py`**（版本横幅）
- **`pyproject.toml` / `.cursor-plugin/plugin.json` / Git tag**：与 **`v0.2.27`** 对齐

## [0.2.26] - 2026-03-28

### Added

- **CDP 网络**：在 `RequestWillBeSent` / `LoadingFinished` 后拉取 **POST 正文**（`post_data` / `getRequestPostData`）与 **响应正文**（`getResponseBody`），写入 `NetworkRequest`；**`ziniao network list --id`**（`--json`）返回 **`post_data`**、**`response_body`**
- **HAR**：有正文时导出 **`request.postData.text`**、**`response.content.text`**；`Network.enable` 尽量带上 **`max_post_data_size`** 与 **`max_resource_buffer_size`**
- **`network list` 表格**：增加 **Body** 列（`req` / `res` 表示是否已抓到正文）

### Changed

- **紫鸟主文档点击**：`dispatch_click` 对 **nodriver `Element`** 使用 **`DOM click()`**，避免仅协议级鼠标坐标在部分环境下不命中；**`IFrameElement`** 仍用坐标点击
- **`human_click`**：主文档 **`Element`** 在拟人移动后以 **`element.click()`** 完成激活；**`IFrameElement`** 仍以 **`dispatchMouseEvent`** 坐标点击

### 工程

- **`.gitignore`**：忽略 **`out/`**（本地 HAR/抓包易含敏感信息）
- **`pyproject.toml` / `.cursor-plugin/plugin.json` / Git tag**：与 **`v0.2.26`** 对齐

## [0.2.25] - 2026-03-25

### Changed

- **`connect_chrome`**：stealth 在**至少已有一个 tab**（含必要时新建的 `about:blank`）之后再注册 **`addScriptToEvaluateOnNewDocument`**，避免先注入 0 个 tab、后开页导致新页无 OnNewDocument 钩子
- **`connect_chrome`**：对已有 tab 仅注册 OnNewDocument，**不对每个页面**执行大脚本 **`evaluate`**；仅对**当前活跃 tab** 补一次 **`evaluate`**，减轻多标签外部 Chrome 的卡顿
- **`apply_stealth`**：新增参数 **`evaluate_existing_documents`**；新增 **`evaluate_stealth_existing_document(tab)`** 供单页补 evaluate

### Fixed

- **`_finalize_launched_chrome`**：与 **`connect_chrome`** 相同顺序——先保证 tab 存在再 **`_apply_stealth_to_browser`**，避免 launch 时初始无 tab 导致新开页未挂 stealth

### 工程 / 文档

- **`skills/ziniao-cli/SKILL.md`**：补充 CDP / session、**`connect`** 与 **`launch` / `open-store`** 的 stealth 差异说明
- **测试**：`test_stealth`、`test_session`（含 connect 与 stealth 顺序用例）
- **`pyproject.toml` / `.cursor-plugin/plugin.json` / Git tag**：与 **`v0.2.25`** 对齐

## [0.2.24] - 2026-03-25

### Changed

- **`ziniao update`（Windows）**：通过 **`start "Ziniao CLI - upgrade"`** 启动独立控制台，任务栏可识别升级窗口；临时 **`.cmd`** 使用 **`setlocal`/`endlocal`**；路径经 **`list2cmdline`** 拼接，减少空格路径拆参问题
- **`ziniao update --sync`**：当前终端内 **`uv`** 不再捕获输出，便于查看实时进度
- **非交互 / CI**：识别 **`CI`**、**`GITHUB_ACTIONS`**、**`ZINIAO_UPDATE_NO_PAUSE`**，升级脚本末尾跳过 **`pause`**，避免无人值守挂死

### Fixed

- **Windows 默认升级**：父进程提示改为 **stderr** 并 **flush**，减少「命令无输出」的误判

### 工程

- **`.gitignore`**：忽略误生成的 **`%SystemDrive%/`** 目录名
- **`pyproject.toml` / `.cursor-plugin/plugin.json` / Git tag**：与 **`v0.2.24`** 对齐

## [0.2.22] - 2026-03-25

### Added

- **`ziniao update`**：Windows / Unix 下在升级前尝试终止占用 **`uv` 工具目录** 的进程（MCP、daemon、其它 CLI 实例）；**`--no-kill`** 跳过（含 Windows 升级 **`.cmd`** 内 PowerShell 终止步骤）

### Fixed

- **`ziniao update`（Windows）**：仅在 **`taskkill` 成功**（退出码 0）时计入「已终止」列表，避免误报
- **`ziniao update --no-kill`（Windows）**：升级辅助 **`.cmd`** 不再无条件嵌入 PowerShell 杀进程逻辑，与 **`--no-kill`** 语义一致

### 工程

- **`pyproject.toml` / `.cursor-plugin/plugin.json` / Git tag**：与 **`v0.2.22`** 对齐

## [0.2.21] - 2026-03-25

### Fixed

- **`ZiniaoClient.get_browser_list`**：认证失败（如 `-10003`）、无法连接本地客户端或其他非成功响应时抛出 **`RuntimeError`**，不再静默返回空列表，避免 **`ziniao store list`** / MCP **`list_stores`** 误显示空表
- **`get_store_info`**：文档补充 **`RuntimeError`** 说明（委托 **`get_browser_list`**）

### Changed

- **`README.md`**：Chrome / 紫鸟凭据优先 **`ziniao config init`** 与 **`~/.ziniao`**；说明 MCP **`env`** 与终端 CLI daemon 的差异

### 工程

- **`pyproject.toml` / `.cursor-plugin/plugin.json` / Git tag**：与 **`v0.2.21`** 对齐

## [0.2.20] - 2026-03-24

### Changed

- **`SessionManager`**：紫鸟 WebDriver 相关报错文案同时指向命令行 **`ziniao store start-client`**（与 MCP **`start_client`** 对照），避免误用不存在的顶层 **`ziniao start_client`**
- **`skills/ziniao-cli`**：**`store start-client` / `stop-client`** 写入 **SKILL** 与 **`references/commands.md`**；故障排查补充 **`list-stores`** / WebDriver 端口场景

### 工程

- **`pyproject.toml` / `.cursor-plugin/plugin.json` / Git tag**：与 **`v0.2.20`** 对齐

## [0.2.19] - 2026-03-27

### Added

- **录制（`legacy` / `dom2` 注入脚本）**：`scroll`（防抖）、`dblclick`、`hover`（防抖 + 可交互元素过滤）、`upload`（`type=file` 仅记录文件名）、`dialog`（`alert` / `confirm` / `prompt` 包装记录）、`drag`（`sourceSelector` / `targetSelector`）；**`contenteditable`** 合并为 `fill`；键盘：**Space**、**Home/End**、**PageUp/PageDown**、**F1–F12**；**修饰键 + 单字符** 记为 `press_key`
- **`dom2`**：顶层 **`Page.FrameNavigated`** 补录整页 **`navigate`**；**`StoreSession.recording_dom2_frame_handlers`**，`stop` 时摘除监听器（避免录制结束后仍往 buffer 写）
- **回放（`_do_replay`）**：交互前 **`scrollIntoView`**；`scroll` / `dblclick` / `hover` / `drag`；**`JavascriptDialogOpening`** 按录制顺序 **`handle_java_script_dialog`**；**`target_id`** 变化时启发式切换标签
- **代码生成**：**`emit_nodriver`** / **`emit_playwright`** 覆盖上述新动作类型
- **`tools/_keys.py`**：补充 **F1–F12** 虚拟键码
- **文档**：**`docs/recording.md`** 同步能力与回放说明

### Fixed

- **`ir._dedup_dblclick`**：在缺少 **`mono_ts`/有效 `timestamp`/正数 `delay_ms` 链** 时不再误删前置 `click`；有可靠间隔且小于 **500ms** 时才去重
- **拖拽落盘**：不再写入未消费的 **`sourceLocator`/`targetLocator`**；**`_INTERNAL_KEYS`** 剥离历史字段
- **单测**：**`tests/test_recording_package.py`** 覆盖去重与拖拽字段剥离

### Changed

- **`skills/store-rpa-scripting`**：Phase 1 以 **`ziniao` CLI** 为主线；**`examples.md`** 改为占位符模式示例

### 工程

- **`pyproject.toml` / `.cursor-plugin/plugin.json` / Git tag**：与 **`v0.2.19`** 对齐

## [0.2.18] - 2026-03-26

### Fixed

- **CLI `rec start`**：**`--codegen`** 不再覆盖显式的 **`--engine`**（例如 **`--engine legacy --codegen`** 正确使用 legacy）；**`--codegen`** 保留为兼容旧脚本的空操作（默认已是 **`dom2`**）

### 工程

- **`pyproject.toml` / `.cursor-plugin/plugin.json` / Git tag**：与 **`v0.2.18`** 对齐

## [0.2.17] - 2026-03-25

### Added

- **文档**：**`docs/recording.md`** — 录制双引擎、IR、落盘、代码生成与回放实现说明

### Changed

- **`rec start` / `recorder(action=start)`**：`engine` 默认由 **`legacy` 改为 `dom2`**（CDP binding + 缓冲）；需旧行为时使用 **`--engine legacy`** 或 MCP **`engine=legacy`**
- **回放**：单一路径，自动兼容 schema v1/v2（文档与 MCP 说明已同步）
- **本机 Chrome `launch_chrome`**：若 **`user_data_dir`** 下 **`DevToolsActivePort`** 可读且 CDP 可用，**直接连接已有进程**、不重复启动；抽取 **`_finalize_launched_chrome`**；profile 冲突时对端口探测增加短重试；**`_try_connect_existing_chrome`** 支持 **`relaxed_probe`**，优先信任 profile 内端口以降低误连

### 工程

- **`pyproject.toml` / `.cursor-plugin/plugin.json` / Git tag**：与 **`v0.2.17`** 对齐

## [0.2.16] - 2026-03-24

### Added

- **Codegen 级录制（`dom2`）**：`Runtime.addBinding` + daemon 侧 `RecordingBuffer`，`rec start --engine dom2`，`--scope active|all`、`--max-tabs`；轮询为新 Target 补挂桩；`rec status` 展示 `buffered_events` / `attached_targets`
- **`ziniao_mcp/recording/`**：IR（`schema_version`）、`emit_nodriver`、`emit_playwright`、locator 解析与回放归一化；**`parse_emit`** 置于 **`recording/ir.py`**
- **`rec stop --emit nodriver,playwright`**、MCP `emit`；**`--redact-secrets`** / `record_secrets=false` 脱敏 `fill`；可选生成 **`NAME.spec.ts`**
- **CLI 快捷**：**`rec start --codegen`**（等同 `dom2`）；**`rec stop -a` / `--all`**（等同双 emit + 脱敏）
- **单元测试**：`tests/test_recording_package.py`

### Fixed

- **`actions_for_disk`**：先依据 **`mono_ts`** 计算 **`delay_ms`** 再剥离内部字段，dom2 步间延时正确
- **`rec list`**：仅当 **`.py`** 存在时返回 **`py_file`**（与 **`ts_file`** 一致）；磁盘 JSON 不再泄漏 **`target_id` / `frameUrl` / `perfTs`** 等内部字段

### 工程

- **`pyproject.toml` / `.cursor-plugin/plugin.json` / Git tag**：与 **`v0.2.16`** 对齐

## [0.2.15] - 2026-03-23

### Added

- **录制 JSON / 生成脚本**：保存 **`session_id`**、**`backend_type`**、**`store_name`**；**`NAME.py`** 模块 docstring 同步会话说明
- **`rec replay` 自动恢复会话**：daemon 无活跃会话时，按录制元数据（或旧文件 **`cdp_port`** + **`~/.ziniao/sessions.json`**）调用 **`connect_store` / `connect_chrome`**；**`--no-auto-session`** / MCP **`auto_session=false`** 可关闭
- **`ziniao_mcp/recording_context.py`**：`RecordingBrowserContext`、`resolve_recording_browser_context`；**`SessionManager`**：`has_active_session`、`attach_from_recording_context`

### Changed

- **`rec list` / `rec view`**（human）：展示会话相关列与字段

### 工程

- **`pyproject.toml` / `.cursor-plugin/plugin.json` / Git tag**：与 **`v0.2.15`** 对齐

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
- **控制台入口统一为 `ziniao`**：MCP 服务通过 `ziniao serve` 或 `python -m ziniao_mcp` 启动（已移除 `ziniao-mcp` 别名）

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
