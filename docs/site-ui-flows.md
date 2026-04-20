# Declarative UI Flows (`mode: ui` presets)

> 把浏览器 UI 操作（登录 / 表单填写 / UI 导出 / DOM 抓取 / UI→API 混合）封装成与 API preset 同形的动作，交给 `ziniao <site> <action>` 统一调用。

## 1. 何时使用

| 场景 | 推荐 |
|------|------|
| 有稳定公开 API | `mode: fetch` / `mode: js` — UI 更脆弱、更慢、更吵 |
| 登录 / 2FA / 跳转中段 | ✅ `mode: ui`（再用 `action: fetch` 续上 API 调用） |
| UI-only 导出（无 API，仅前端按钮触发下载） | ✅ `mode: ui` + `extract` + `fetch` 落盘 |
| 批量表单录入 | ✅ `mode: ui`（Phase 2 再加 `for_each`） |
| DOM 抓取 | ✅ `mode: ui` + `action: extract` |
| 高并发批量调用 | ❌ 走 `mode: fetch`，UI 调度成本太高 |

## 2. 与 `mode: fetch / js` 的关系

- **命名空间统一**：`site-hub/<site>/<action>.json`，调用方看到的都是 `ziniao <site> <action>`，只差 `mode` 字段。
- **纯加法**：`mode: ui` 不动 `fetch / js / plugin` 任何现有路径；`_register_action` 按 `mode` 分派，UI 走 `flow_run` 命令，其它不变。
- **变量渲染共用**：`render_vars` 对 `steps[]` 一视同仁，同样支持 `{{var}}` 占位与 `type: int/float/bool/file/file_list/secret`。

## 3. Preset Schema（MVP）

```jsonc
{
  "name": "Example · UI Export",
  "mode": "ui",
  "navigate_url": "https://site.com/dashboard",   // 可选：执行前导航
  "force_navigate": false,                         // 可选：强制重新跳转（见 3.0）
  "vars": {
    "start_date": { "type": "str",    "required": true },
    "password":   { "type": "secret", "source": "keyring:myapp:admin", "required": true }
  },
  "steps": [
    { "id": "user",    "action": "fill",        "selector": "#u",            "value": "alice" },
    { "id": "pw",      "action": "fill",        "selector": "#pw",           "value": "{{password}}" },
    { "id": "submit",  "action": "click",       "selector": "button[type=submit]" },
    { "id": "wait_dl", "action": "wait",        "selector": "a.download",    "timeout": 30 },
    { "id": "grab",    "action": "extract",     "as": "download_url",
      "selector": "a.download", "kind": "attribute", "attr": "href" },
    { "id": "dl",      "action": "fetch",       "method": "GET",
      "url": "{{extracted.download_url}}",      "save_body_to": "exports/report.csv" }
  ],
  "output_contract": {
    "download_url": "$.extracted.download_url",
    "file":         "$.steps.dl.saved_path"
  },
  "on_error": { "screenshot": true, "snapshot": true }
}
```

### 3.0 Preset 顶层字段

| 字段 | 说明 |
|------|------|
| `mode` | 必填；固定为 `"ui"` |
| `name` / `description` | 展示用；`ziniao <site> <action> --help` 会读 |
| `navigate_url` | 可选；执行 steps 前的目标 URL |
| `force_navigate` | 可选 bool，默认 `false`。默认行为：只有当前 URL 的去 query/fragment 前缀**不等于** `navigate_url` 的同源段时才跳转（避免 SPA 同页无意义 reload）。传 `true` 会强制重新 `Page.navigate`，用于必须重置 JS 上下文的场景 |
| `vars` | 变量声明（`str` / `int` / `float` / `bool` / `file` / `file_list` / `secret`） |
| `steps` | 必填；见 3.1 / 3.2 |
| `output_contract` | 可选；见 3.4 |
| `on_error` | 可选；见 3.5 |

### 3.1 Step 通用字段

| 字段 | 说明 |
|------|------|
| `id` | 可选；用于后续 step 通过 `{{steps.<id>.value}}` 引用。建议每步都写 |
| `action` | 必填；见下方白名单 |
| `continue_on_error` | `true` 时失败不终止流程，只记录到 `failures[]` |

### 3.2 Action 白名单

| action | 说明 | 关键字段 |
|--------|------|----------|
| `navigate` | 导航到 URL | `url` |
| `wait` | 等待元素出现/消失 | `selector`, `state` (visible/hidden/attached), `timeout` (秒) |
| `click` | 点击 | `selector` |
| `fill` | 填充 input/textarea | `selector`, `value` |
| `type_text` | 模拟按键输入 | `selector`, `text` |
| `insert_text` | CDP `Input.insertText`（Slate/ProseMirror 富文本编辑器） | `selector`, `text` |
| `press_key` | 按单键（如 `Enter`/`Tab`） | `key` |
| `hover` | 悬停 | `selector` |
| `dblclick` | 双击 | `selector` |
| `upload` | 上传文件到 `<input type=file>` | `selector`, `file_paths` 或 `file_path` |
| `upload-hijack` | SPA 隐藏 input 上传：在触发元素点击前预置 `createElement('input')` hook 接管 `DOM.setFileInputFiles` | `file_paths` 或 `file_path`, `trigger`（点击目标 selector）, `wait_ms?`（默认 30000） |
| `upload-react` | React/SPA 友好上传：CDP `Page.setInterceptFileChooserDialog` + 点击触发器 + `DOM.setFileInputFiles` | `file_paths` 或 `file_path`, `trigger`（点击目标 selector） |
| `clear-overlay` | 主动关闭/移除页面遮罩、弹窗、cookie 条、强制登录 modal 等，释放后续点击目标。`click` / `upload-hijack` 已在内部自动先跑一次本 action | （无） |
| `inject-file` | 读取本地文本文件写入浏览器 `window[var]`，供后续 `eval` step 消费大型 HTML/JSON | `path`（本地文件路径）, `var?`（默认 `__injected_file`） |
| `inject-vars` | 把 `flow_vars`（即 preset `vars`）重新注入到 `window.__flow_vars`。用于 SPA 导航后 JS 上下文重置的场景（如抖音上传后裁剪页）。大值（≥50KB）会单独注入以避免 CDP eval 长度上限。`_flow_run` 启动时已自动跑一次 | （无） |
| `screenshot` | 截图（手动存档；失败自动也会截） | `selector?`, `full_page?` |
| `snapshot` | DOM HTML 快照 | （无） |
| `eval` | 运行自定义 JS（返回值存入 `step.value`） | `script`, `await_promise?` |
| `extract` | 抽取 DOM 数据到 `extracted[<as>]` | `as`, `kind`, `selector` |
| `fetch` | inline HTTP（混合 UI→API） | `url`, `method`, `body`, `headers`, `save_body_to?` |

### 3.3 变量占位

- **Flow 输入变量**：`{{var_name}}` 由 `render_vars` 在流启动前替换。
- **Step 间引用**：`{{steps.<id>.value}}` / `{{steps.<id>.saved_path}}` / `{{extracted.<as>}}` 在每步执行前再渲染。
- **完整替换 vs 插值**：`"{{steps.x.value}}"` 整值匹配时会保留原类型（数字、列表），否则按字符串拼接。

### 3.4 `output_contract`

声明用户可见的最终形状。仅支持 `$.a.b.c` 点路径：

```jsonc
{ "download_url": "$.extracted.download_url", "file": "$.steps.dl.saved_path" }
```

结果会写到 `result.output[<key>]`，`result.steps / result.extracted` 仍完整保留以便 agent 追溯。

### 3.5 `on_error`

```jsonc
{ "screenshot": true, "snapshot": true }
```

失败时自动写 `exports/flow-errors/<yyyymmdd-hhmmss>-<step_id>.{png,html,err.txt}`，并把路径写进 `failures[i].screenshot_path / snapshot_path` 供 agent 自愈。

## 4. `action: extract` 详解

| kind | 说明 | 关键字段 |
|------|------|----------|
| `text` | `el.innerText`（默认） | `selector` |
| `html` | `el.outerHTML` | `selector` |
| `attribute` | `el.getAttribute(attr)` | `selector`, `attr` |
| `querySelectorAll` | 批量：返回每个元素的 `innerText`/指定 sub_attr | `selector`, `sub_attr?` |
| `table` | 返回二维 `string[][]`（rows × cells） | `selector`（指向 `<table>`） |
| `eval` | 自定义 JS 返回值 | `script`, `await_promise?` |

## 5. `action: fetch` 详解

- 复用底层 `page_fetch` fetch 模式（在浏览器上下文执行，自动携带 cookies）。
- 支持 `header_inject`（cookie/localStorage/sessionStorage/eval → header）。
- `save_body_to` 落盘二进制友好（`body_b64` 优先写为字节，否则 UTF-8 文本）。

## 6. `type: secret` 变量

三种来源（precedence 从高到低）：

1. `source: keyring:<service>:<key>` — 需要 `pip install keyring`；CLI 传入值被**忽略**（防止历史泄漏）。
2. `source: env:<VAR>` — 从环境变量读。
3. 无 `source` 时 `-V key=value` 传值；终端交互时自动 `getpass` 提示。

**全链脱敏**：resolved 值进入 `spec._ziniao_secret_values`；`_flow_run` 在失败 artefact / 日志打印前用 `***` 全部替换。

**schema 校验**：`secret` 变量的占位只允许出现在 `fill.value / type_text.text / insert_text.text / fetch.headers / fetch.body / fill.fields_json` 里；放在 URL / selector / log 字段会被 `_validate_ui_preset` 拒绝。

## 7. 调用

```bash
# 基本
ziniao <site> <action> -V start_date=2026-01-01

# 显式更长超时（UI 流通常需要；daemon 内部 auto 120s，CLI 默认 60s）
ziniao --timeout 300 <site> <action> -V start_date=2026-01-01

# JSON 模式（agent / 脚本使用）
ziniao --json <site> <action> -V ...
```

**注意**：`--all` / `--page` 对 `mode: ui` 无效；若传入会被 CLI 拒绝（见 `site_cmd.py`）。

## 8. 结果契约

```jsonc
{
  "ok": true,
  "steps": {
    "go":   { "ok": true, "clicked": "button#export" },
    "grab": { "ok": true, "value": "https://dl...", "kind": "attribute" },
    "dl":   { "ok": true, "status": 200, "saved_path": "…/report.csv" }
  },
  "extracted": { "download_url": "https://dl..." },
  "failures": [],
  "output":   { "download_url": "https://dl...", "file": "…/report.csv" }
}
```

失败时：

```jsonc
{
  "ok": false,
  "steps": { "a": {...}, "b": { "error": "..." , "screenshot_path": "..." } },
  "extracted": {},
  "failures": [
    { "step_id": "b", "action": "click", "error": "Element not found: #x",
      "screenshot_path": "exports/flow-errors/20260101-...png",
      "snapshot_path":   "exports/flow-errors/20260101-...html" }
  ]
}
```

## 9. 风险与边界

| 风险 | 缓解 |
|------|------|
| 凭据泄漏 | `type: secret` 全链脱敏 + `_validate_ui_preset` 禁止 secret 出现在非受信字段 |
| 选择器失效 | 失败自动 `screenshot + snapshot` 写 `exports/flow-errors/`，喂给 agent 自愈 |
| UI 反风控 | 所有 step 原语（`click`/`fill`/`type_text`/`hover`/`insert_text`/`press_key`/`dblclick`）在 `stealth_config.human_behavior` 启用时统一走贝塞尔鼠标轨迹 + 随机延迟；`insert_text` 分块发送（Slate/ProseMirror 兼容），`press_key` 在 `rawKeyDown` 与 `keyUp` 之间加入 ~60ms 抖动；文档明确"有 API 就用 API" |
| 失败快照泄密 | `exports/flow-errors/*.html` 与 `.err.txt` 在写盘前经 `_mask_secrets` 处理，已解析的 `type: secret` 值不会通过 DOM / 错误信息落盘（PNG 像素层面无法脱敏，敏感页可在 `on_error` 中关 `screenshot`） |
| 与录制系统重叠 | 录制 = 草稿生成器（Phase 2 `rec stop --emit preset`）；preset = 手写可 diff 契约 |
| schema 漂移 | `UI_ACTION_WHITELIST` 受控；未来破坏性变更走 `schema_version: "ui/2"` |

## 10. 相关代码位置

- 运行器：[ziniao_mcp/cli/dispatch.py](../ziniao_mcp/cli/dispatch.py) `_flow_run / _extract_step / _inline_fetch_step`
- schema 校验 + 变量：[ziniao_mcp/sites/__init__.py](../ziniao_mcp/sites/__init__.py) `_validate_ui_preset / _resolve_secret / render_vars`
- CLI 分派：[ziniao_mcp/cli/commands/site_cmd.py](../ziniao_mcp/cli/commands/site_cmd.py) `_register_action`
- 测试：[tests/test_flow_run.py](../tests/test_flow_run.py) / [tests/test_secret_var.py](../tests/test_secret_var.py)
- 示例 preset：[site-hub/flow-demo/](../site-hub/flow-demo/)

## 11. 分阶段路线

### Phase 1（当前）· MVP 已达成

- [x] `_flow_run` 按序执行 + step 间引用
- [x] `action: extract`（text/html/attribute/querySelectorAll/table/eval）
- [x] 内联 `action: fetch` + `save_body_to`
- [x] `type: secret`（keyring/env/interactive）+ 全链脱敏
- [x] `_validate_ui_preset` 白名单 + secret 防护
- [x] CLI `mode: ui` 分派
- [x] 失败自动截图/快照
- [x] 文档 + 示范 preset

### Phase 2 · Hybrid 完善 + 录制桥接

- [ ] `action: for_each` 批量录入
- [ ] `rec stop --emit preset` 把录制 IR 导出为 `steps[]` 草稿
- [ ] `steps_ref: "~/.ziniao/recordings/<name>.json"` 直挂录制
- [ ] `session_artifacts.save_cookies` 让后续 inline fetch 自动消费 UI 登录态

### Phase 3 · 加固

- [ ] 结构化 locator：`testid / role+name / aria`（复用 `recording/locator.py`）
- [ ] `--dry-run` 打印渲染后 steps（secret 打码）不实际执行
- [ ] `on_error.fallback_selector` 备选选择器
- [ ] `flow_run` 直接作为 MCP tool 暴露给 agent
