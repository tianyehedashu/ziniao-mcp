# 浏览器操作录制（Recorder）架构说明

本文档描述 **ziniao-mcp** 中「录制 → 落盘 → 代码生成 → 回放」的完整数据流与实现细节，便于维护与二次开发。

---

## 1. 功能概览

| 能力 | 说明 |
|------|------|
| **录制** | 在真实浏览器里捕获点击、输入、下拉、特殊按键、部分导航事件 |
| **持久化** | 写入 `~/.ziniao/recordings/<name>.json`（元数据 + 动作列表） |
| **代码生成** | 可选生成独立 **`*.py`**（nodriver）与 **`*.spec.ts`**（Playwright 风格模板） |
| **回放** | 通过 MCP / CLI 在当前 CDP 会话中按步骤重放（含 stealth 与人类行为模拟） |
| **管理** | `list` / `view` / `delete` / `status` |

**入口**：

- **CLI**：`ziniao rec …` → `ziniao_mcp/cli/commands/recorder.py` → `run_command("recorder", …)` → `ziniao_mcp/cli/dispatch.py` 的 `_recorder`
- **MCP**：`recorder` 工具 → `ziniao_mcp/tools/recorder.py` 的 `register_tools`

两者最终都调用同一套 `_do_start` / `_do_stop` / `_do_replay` 等函数。

---

## 2. 双引擎：`legacy` 与 `dom2`

录制**如何采集事件**由 `engine` 决定（`start` 时指定；**默认 `dom2`**）。`stop` 时的 **`emit`**（生成哪些文件）与 **`record_secrets`**（是否脱敏）与引擎**独立**。

**回放**只有一条实现路径：`_do_replay` 对磁盘/内联动作统一做 **`normalize_action_for_replay`**，兼容 **`schema_version` 1（legacy 录制）与 2（dom2）**，无需再选引擎。

| 维度 | `legacy`（`--engine legacy`） | `dom2`（默认；CLI 亦可写 `--codegen` 显式指定） |
|------|------------------------------|---------------------------------------------|
| **事件存放位置** | 页面内 JS：不可枚举的 `Symbol.for('__ev_d')` 数组 | 守护进程内存：`RecordingBuffer`（环形缓冲） |
| **事件如何到 Python** | `stop` 时对**当前活动标签**执行 `evaluate`，`JSON.stringify` 该数组 | 页面通过 CDP **`Runtime.addBinding`** 暴露的函数，触发 **`BindingCalled`**，异步 handler 写入 buffer |
| **多标签** | 仅对**注入过的那一页**有效；切走再 `stop` 可能读到错页或空数组 | 可对多标签挂桩（见 `scope` / 轮询）；事件带 `target_id`，按 `seq` 排序 |
| **结构化 locator** | 无，仅 `selector` 字符串 | 每条交互可带 `locator` 对象（testid / role / aria 等），便于生成 Playwright API |
| **JSON `schema_version`** | `1` | `2`（常量 `RECORDING_SCHEMA_VERSION`，见 `ziniao_mcp/recording/ir.py`） |
| **主要源码** | `recorder.py` 内 `_RECORDER_JS`、`_setup_navigation_reinjection` | `ziniao_mcp/recording/capture_dom2.py` |

**CLI 快捷**：

- `ziniao rec start` 默认已为 `dom2`；`--codegen` 与默认等价（显式写法）
- `ziniao rec stop -a` / `--all` ⇔ `--emit nodriver,playwright` 且 `--redact-secrets`（与引擎无关）

---

## 3. 模块与文件布局

```
ziniao_mcp/tools/recorder.py      # MCP 注册、legacy JS、_do_*、落盘/列表/删除
ziniao_mcp/cli/commands/recorder.py   # Typer 子命令
ziniao_mcp/cli/dispatch.py        # CLI → _do_start/_do_stop（透传 engine/emit 等）
ziniao_mcp/session.py             # StoreSession 上 recording_* 状态字段
ziniao_mcp/recording/
  __init__.py                     # 包导出
  buffer.py                       # RecordingBuffer
  ir.py                           # schema、delay、脱敏、parse_emit、actions_for_disk
  locator.py                      # build_locator_dict（JS 片段）、CSS 回退、normalize_action_for_replay
  capture_dom2.py                 # dom2：binding、注入、轮询、stop 清理
  emit_nodriver.py                # generate_nodriver_script
  emit_playwright.py              # generate_playwright_typescript
```

**落盘目录**：`Path.home() / ".ziniao" / "recordings"`（代码中 `_RECORDINGS_DIR`）。

---

## 4. 会话状态：`StoreSession` 录制相关字段

定义于 `ziniao_mcp/session.py` 的 `StoreSession`：

| 字段 | 用途 |
|------|------|
| `recording` | 是否处于录制中 |
| `recording_start_url` | `start` 时记录的起始页 URL（用于元数据与生成脚本） |
| `recording_engine` | `"legacy"` \| `"dom2"` |
| `recording_ring_buffer` | dom2：`RecordingBuffer` 实例 |
| `recording_seq` | dom2：单调递增序号，写入每条事件的 `seq` |
| `recording_binding_name` | dom2：当前 CDP binding 名（由 `store_id` 派生） |
| `recording_dom2_handlers` | `(tab, handler)` 列表，用于 stop 时摘除 `BindingCalled` |
| `recording_script_entries` | `(tab, script_id)`，`add_script_to_evaluate_on_new_document` 的 identifier，stop 时移除 |
| `recording_poll_task` | dom2：后台 `asyncio.Task`，轮询新标签并补挂桩 |
| `recording_scope` | dom2：`"active"` \| `"all"` |
| `recording_max_tabs` | dom2：`scope=all` 时最多挂桩标签数；`0` 表示不限制 |
| `recording_monotonic_t0` | dom2：`time.monotonic()` 基准，用于 `mono_ts` |
| `recording_attached_targets` | 已挂桩的 `target_id` 集合 |
| `recording_dropped_events` | 缓冲溢出丢弃计数（在 drain / stop 时汇总） |

`stop` 成功后会把 `recording_engine` 重置为 `"legacy"`（无论刚才是否为 dom2）。

---

## 5. `legacy` 引擎实现细节

### 5.1 注入与反探测

- 脚本 `_RECORDER_JS` 通过 `tab.evaluate(_RECORDER_JS, await_promise=False)` 注入。
- 使用 `Symbol.for('__ev_a')` / `Symbol.for('__ev_d')` 配合 `Object.defineProperty(..., enumerable: false)`，避免 `Object.keys` / `for-in` / `JSON.stringify(window)` 轻易暴露录制状态。

### 5.2 采集与清空

- **采集**：`_COLLECT_JS` → `JSON.stringify(window[Symbol.for('__ev_d')] || [])`
- **清空**：`_CLEAR_JS` 重置 active 标记与数组

### 5.3 顶层导航后重新注入

`_setup_navigation_reinjection` 在录制中的 Tab 上监听 `cdp.page.FrameNavigated`：

- 仅处理**无 `parent_id` 的帧**（主文档导航）。
- `await asyncio.sleep(1)` 后再次 `inject_fn(tab)`，并通过 `_NAV_PUSH_JS` 向缓冲区追加一条 `type: navigate`（带 URL）。

这样 **SPA 内 pushState 不会触发整页重载** 时，仍依赖页内 `popstate` / `hashchange`（见下）补充导航记录。

### 5.4 页内事件类型与规则（与 dom2 语义对齐）

- **click**：捕获阶段监听；`input`/`textarea` 上点击默认忽略（除非 submit/button/reset/checkbox/radio），避免与 fill 重复。
- **change**：checkbox/radio 记为 `click`；`select` 记为 `select`（含 `value`）。
- **input**：500ms debounce；若上一条已是同 `selector` 的 `fill`，则**原地更新** `value` 与 `timestamp`（合并连续输入）。
- **keydown**：仅记录白名单特殊键（Enter、Tab、Escape、方向键等），并带修饰键前缀 `Control+` 等。
- **navigate**：`popstate`、`hashchange` 时写入 `url`。

每条记录带 `timestamp`（`Date.now()`），**无** `mono_ts` / `locator`（schema v1）。

### 5.5 `stop` 路径

1. `ensure_active_regular_tab` 确保有普通网页标签。
2. `collect_fn(tab)` 拉取数组。
3. `clear_fn(tab)` 清空页内状态。

后续与 dom2 共用 `_save_recording`（见第 8 节）。

---

## 6. `dom2` 引擎实现细节（`capture_dom2.py`）

### 6.1 Binding 名称

`make_binding_name(store_id)`：`sha256(store_id)` 取前 12 位十六进制，前缀 `ziniaoRec`，保证可作为合法 JS 绑定标识的一部分。

### 6.2 页内脚本 `_recorder_js_body(binding_name)`

- 使用 `Symbol.for('__zin_rec_v2')` 做**每文档**幂等 guard，避免重复注册监听。
- `post(obj)`：`window[binding_name](JSON.stringify(obj))`，即调用 CDP 注入的 binding，触发 Python 侧 `BindingCalled`。
- **`getSelector`**：与 legacy 类似的 CSS 推导（id → 属性唯一 → class → 最多 5 层路径）。
- **`getLocator`**：嵌入 `build_locator_dict("el")` 生成的 IIFE，得到结构化对象；若无更好策略则 `{ strategy: 'css', value: getSelector(el) }`。
- **fill**：按 `getSelector` 结果作为 key 做 500ms debounce；**不**合并同字段多条记录（与 legacy 不同，每次 debounce 结束新推一条）。
- 其它事件类型与 legacy 类似；`record` 会附加 `timestamp`、`perfTs`、`frameUrl`（后两者在落盘前会被剥离，见 IR）。

### 6.3 Python 侧 `_make_binding_handler`

对匹配的 `BindingCalled`：

1. 解析 JSON payload。
2. 写入 `target_id`（来自当前 Tab）。
3. 写入单调 `seq`，并递增 `store.recording_seq`。
4. `mono_ts = time.monotonic() - recording_monotonic_t0`。
5. `RecordingBuffer.append(payload)`。

用于跨标签、跨时钟漂移的 **`delay_ms`** 计算（优先 `mono_ts`，否则回退 `timestamp`）。

### 6.4 `_attach_dom2_to_tab`

对每个目标 `Tab` 顺序执行：

1. `cdp.runtime.add_binding(name=binding_name)`
2. `tab.add_handler(cdp.runtime.BindingCalled, handler)`，并把 `(tab, handler)` 记入 `recording_dom2_handlers`
3. `cdp.page.add_script_to_evaluate_on_new_document(source=js, run_immediately=True)`，把 `identifier` 记入 `recording_script_entries`

`run_immediately=True` 表示当前文档立即执行一次，且之后**新文档**（含常见 iframe 导航场景）也会自动执行该脚本，从而避免为每一帧手写 `createIsolatedWorld` 的复杂树遍历。

### 6.5 `scope` 与 `max_tabs`

- **`active`**：初始仅对 `store.active_tab_index` 对应标签挂桩；后台轮询中同样只对**当前活动标签**尝试补挂新 `target_id`。
- **`all`**：对 `_filter_tabs` 后的标签列表，最多前 `max_tabs` 个（`max_tabs == 0` 表示不截断）。

轮询间隔约 **1.5s**，内部 `browser.update_targets()` 后再次尝试未出现在 `recording_attached_targets` 中的标签。

### 6.6 `stop_dom2_capture`

1. 取消 `recording_poll_task`。
2. 对每个已注册 handler：从 `tab.handlers[BindingCalled]` 列表中**直接 remove**（规避部分 nodriver 版本 `remove_handler` 行为问题），再 `runtime.remove_binding`。
3. `page.remove_script_to_evaluate_on_new_document` 移除注入脚本。
4. 将 buffer 的 `dropped` 汇总到 `recording_dropped_events`，清空 buffer 与 binding 名、attached 集合。

### 6.7 `stop` 时事件顺序

`_do_stop` 在 dom2 分支：`buf.drain_keep_stats()` 后按 `int(x.get("seq", 0))` **排序**，再交给 `_save_recording`。

---

## 7. 中间表示（IR）与落盘规范化（`ir.py` + `locator.py`）

### 7.1 `schema_version`

- **1**：legacy；动作主要为 `type` + `selector`（+ 可选 `value` / `url` / `key`）。
- **2**：dom2；动作常含 **`locator`**（字典），仍保留 `selector` 供 CSS 回放。

`_schema_version_for_engine`：`dom2` → 2，否则 1。

### 7.2 `compute_delay_ms(actions)`（原地修改）

对 `i > 0`：

- 若当前与上一条都有 **`mono_ts`**：`delay_ms = max(0, (mono_ts[i] - mono_ts[i-1]) * 1000)` 取整。
- 否则：`delay_ms = max(0, timestamp[i] - timestamp[i-1])`。
- `actions[0]["delay_ms"] = 0`。

**必须在剥离 `mono_ts` 之前调用**；`actions_for_disk` 内先 `compute_delay_ms` 再删内部字段。

### 7.3 `actions_for_disk`

1. `compute_delay_ms(actions)`（传入的列表应仍为原始采集列表，含 `mono_ts` 等）。
2. 去掉 `_INTERNAL_KEYS`：`mono_ts`、`perf_ts`、`perfTs`、`seq`、`target_id`、`frameUrl`。
3. `normalize_action_for_replay`：若 `selector` 为空，用 `locator_to_css_selector(locator)` 补全。
4. 若 `record_secrets is False`：对 `type == "fill"` 的 `value` 做 `redact_actions_secrets`（占位符 + `sha256` 前 12 位，便于比对是否同一秘密而不存明文）。

### 7.4 结构化 `locator` 策略（`build_locator_dict` / `locator_to_css_selector`）

| strategy | 含义 | Playwright 生成侧 | CSS 回退 |
|----------|------|-------------------|----------|
| `testid` | `data-testid` | `getByTestId` | `[data-testid="..."]` |
| `attr` | `data-id`/`data-qa` 或 `name` | `page.locator(...)` | `[attr="..."]` |
| `aria` | `aria-label` | `getByLabel` | `[aria-label="..."]` |
| `role` | `role` + 可选名称 | `getByRole` | `[role="..."]` 等组合 |
| `css` | 显式 CSS 字符串 | `page.locator` | 原样 |

**`normalize_action_for_replay`** 供 **nodriver 回放**与 **emit_nodriver** 使用：保证总有可用的 `selector` 字符串。

---

## 8. 落盘与产物（`_save_recording`）

流程：

1. `parse_emit`（MCP/CLI 字符串 → `["nodriver"]` / `["playwright"]` / 两者；非法片段过滤，空则默认 nodriver）。
2. `actions_for_disk(..., record_secrets=...)` → `disk_actions`。
3. 写 **`{name}.json`**：包含 `schema_version`、`recording_engine`、`actions`、`cdp_port`、`session_id`、`backend_type`、`store_name` 等。
4. 若 `nodriver` in emit：写 **`{name}.py`**（`generate_nodriver_script`）。
5. 若 `playwright` in emit：写 **`{name}.spec.ts`**（`generate_playwright_typescript`；模板内含 `connectOverCDP` 注释与 `page` 占位，需用户接好 CDP 会话）。

**列表 `_list_recordings`**：`py_file` / `ts_file` 仅在该文件**真实存在**时返回路径字符串，否则 `""`，避免「只生成了 ts 却给出虚假 py 路径」。

**删除 `_delete_recording`**：尝试删除 `.json`、`.py`、`.spec.ts`。

---

## 9. 代码生成器要点

### 9.1 nodriver（`emit_nodriver.py`）

- 对每条动作先 `normalize_action_for_replay`。
- 使用动作上的 **`delay_ms`**：大于 100ms 且非第一步时插入 `tab.sleep(...)`。
- `fill`：点击聚焦 + 模拟 Ctrl+A / Backspace + 逐字符 `dispatch_key_event('char')`（与历史行为一致）。
- `press_key`：`ziniao_mcp/tools/_keys.parse_key` 映射虚拟键。

### 9.2 Playwright（`emit_playwright.py`）

- 优先用结构化 `locator` 生成 `getByTestId` / `getByRole` / `getByText` / `getByLabel`，否则 `page.locator(selector)`。
- 默认 **不** 内嵌完整 `connectOverCDP` 实现，避免误连端口；由使用者在模板基础上补全。

---

## 10. 回放（`_do_replay`）

1. 动作来源：`actions_json` 优先，否则从磁盘 `name` 读 `meta["actions"]`。
2. **`auto_session`**：若无活跃会话，可用 `recording_context.resolve_recording_browser_context` 根据元数据尝试 `attach_from_recording_context`（紫鸟 / Chrome 等）。
3. 打开标签：`open_replay_tab(start_url)` 或 `reuse_tab` 时用当前活动标签。
4. 逐步：`normalize_action_for_replay` → 按 `delay_ms` 与 `speed` 睡眠 → `find_element` / 人类行为 `human_click` / `human_fill`（Ziniao 或启用 stealth 时）→ `select` 用 `evaluate` 改 `value` 并 `dispatchEvent('change')` → `press_key` CDP → `navigate` `page.navigate`。

失败步骤记日志并尽量继续后续步骤（计数仍递增）。

---

## 11. `RecordingBuffer`（`buffer.py`）

- 默认最大容量 **10000**；满时弹出最旧一条并 `dropped += 1`（保留最新事件）。
- `drain_keep_stats()`：`stop` 时取出全部事件并返回 `(list, dropped)`，重置缓冲区内 `dropped` 计数。

---

## 12. `status` 返回字段（`_do_status`）

| 字段 | 说明 |
|------|------|
| `recording_active` | 是否在录 |
| `recording_start_url` | 起始 URL |
| `engine` | `legacy` / `dom2` |
| `scope` / `max_tabs` | dom2 策略 |
| `buffered_events` | dom2：当前 buffer 长度 |
| `attached_targets` | dom2：已挂桩 target id 列表 |
| `dropped_events` | 最近一次 dom2 停止后汇总的溢出丢弃数（或历史值，视实现读取时机） |

---

## 13. 已知限制与注意点

1. **全页刷新导航**：legacy 依赖 `FrameNavigated` 再注入；dom2 依赖 `add_script_to_evaluate_on_new_document` 对新文档自动执行。极端页面 CSP 或脚本环境可能仍影响注入成功率。
2. **用户手动切标签**：无原生「用户点了浏览器标签栏」的 CDP 事件；dom2 通过**轮询** `active_tab_index` 与 `update_targets` 补挂桩，存在最多约 1.5s 的延迟窗口。
3. **iframe**：依赖 Chrome 对 `add_script_to_evaluate_on_new_document` 在子帧上的行为；未对每一帧单独维护隔离 world 树。
4. **Playwright 产物**：为模板性质，需自行连接 CDP；多标签录制生成的步骤默认仍假设主要操作在同一 `page` 上表达。
5. **安全**：`record_secrets=true`（默认）时密码等会以明文写入 JSON；生产或分享前应用 `-a` 或 `record_secrets=false` 脱敏。

---

## 14. 相关测试

- `tests/test_recording_package.py`：`parse_emit`、`RecordingBuffer`、`compute_delay_ms`、`actions_for_disk`（含 `mono_ts` 与脱敏）、`locator`、`Playwright` 生成冒烟。
- `tests/test_recorder_view.py`：与 `generate_nodriver_script` 等相关的视图/生成行为。

运行示例：

```bash
uv run pytest tests/test_recording_package.py tests/test_recorder_view.py -q
```

---

## 15. 快速对照：常用命令

```bash
# 默认已是 dom2；双产物 + 脱敏
ziniao rec start
ziniao rec stop -a

# 显式写法（与上等价）
ziniao rec start --engine dom2 --scope active --max-tabs 20
ziniao rec stop --emit nodriver,playwright --redact-secrets

# 显式使用老引擎单页缓冲
ziniao rec start --engine legacy
ziniao rec stop

# 录制中查看状态
ziniao rec status
```

MCP 侧参数与 CLI 对齐，见 `docs/api-reference.md` 中 **`recorder`** 工具说明。
