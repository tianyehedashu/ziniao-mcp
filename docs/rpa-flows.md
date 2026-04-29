# 统一 Flow（`kind: rpa_flow`）

紫鸟的浏览器自动化只保留一套声明式 Flow 能力：同一组 UI steps（`click` / `fill` / `extract` / `fetch` / `snapshot` …）由 `ziniao_mcp.flows.runner.run_flow` 统一执行。`kind: rpa_flow` 是推荐的新文档形态，补齐控制流、重试、文件 IO、HTTP/MCP 外呼、`code`、运行工件与恢复调试；历史 `mode: ui` 站点预设继续兼容，但不再作为第二套模型扩展。

简单说：**以后新增浏览器流程优先写 `kind: rpa_flow`；已有 `mode: ui` 能跑，但它只是兼容入口。**

## 适用场景

- **优先用统一 Flow（`kind: rpa_flow`）**：页面操作步骤明确、需要 `if` / `for_each` / `retry` / 文件 IO / 失败工件 / 可恢复调试，并希望流程以 JSON 交付给用户或 Agent 重跑。
- **优先用 Site Preset**：目标主要是已登录页面内 API 抓取，`mode: fetch` / `mode: js` 足够表达。
- **优先用独立 Python 脚本**：需要脱离 ziniao daemon 定时运行、复杂业务封装、长期批处理或部署到非交互环境。探索阶段仍建议先用 `ziniao flow` / CLI 验证。

## 快速开始

- **校验（仅文档 / schema）**  
`ziniao flow validate ./my-flow.json`
- **Dry-run**  
  - 静态：`ziniao flow dry-run ./my-flow.json` 或 `ziniao flow dry-run ./my-flow.json --static`  
  - 计划说明（外部调用 / code 预览 / 变量脱敏）：`ziniao flow dry-run ./my-flow.json --plan`
- **执行（经 daemon，`flow_run`）**  
`ziniao flow run ./my-flow.json --var start_date=2025-01-01`  
合并 stdin 变量（JSON 对象，与 `--var` 可混用，stdin 键优先）：`Get-Content vars.json | ziniao flow run ./x.json --vars-stdin`  
文件变量：`--vars-from data.json|data.yaml|data.csv`（CSV 会作为 `rows` 注入，可重复）。  
可选：`--run-dir` 指定工件目录；`--policy` 指定临时 policy；`--allow-private-network` / `--allow-mcp` 是单次运行覆盖。`flow run` 会设置 `_ziniao_flow_base_dir` 为 flow 文件所在目录，`**call_flow` 的相对 `path` 相对该目录解析**。
- **运行产物**  
默认写入 `~/.ziniao/runs/<run_id>/`：`state.json`、`report.json`；`report` 与成功回包含 `**started_at` / `ended_at` / `duration_ms`（UTC）**。失败时在同目录落截图 / HTML / err（若 `on_error` 未关闭）。

最小流程：

```json
{
  "kind": "rpa_flow",
  "schema_version": "rpa/1",
  "name": "demo-login",
  "navigate_url": "https://example.com/login",
  "vars": {
    "username": {"type": "str", "default": "demo"}
  },
  "steps": [
    {"id": "fill_user", "action": "fill", "selector": "#username", "value": "{{vars.username}}"},
    {"id": "submit", "action": "click", "selector": "button[type=submit]"},
    {"id": "extract_title", "action": "extract", "as": "title", "selector": "title", "kind": "text"}
  ],
  "output_contract": {"title": "$.extracted.title"}
}
```

推荐工作流：

1. 用 `ziniao launch` / `open-store` 打开目标页面。
2. 用 `snapshot --interactive` 选稳定 CSS selector。
3. 写 `kind: rpa_flow` JSON，并先跑 `ziniao flow dry-run x.json --plan`。
4. 执行 `ziniao flow run x.json --var k=v`。
5. 失败时用 `ziniao flow diagnose <run_id> --emit nodriver`，必要时 `--replay <run_id> --resume-from step_id`。

## 给 Agent / Cursor 用户

安装内置 skill 后，用户可以直接让 Agent 设计或维护统一 Flow：

```bash
ziniao skill install rpa-flows
ziniao skill install ziniao-cli
```

常见提法：

- “把这个登录后导出报表的流程写成 `kind: rpa_flow`。”
- “基于这个录制草稿补变量、断言和输出契约。”
- “运行 `ziniao flow diagnose <run_id>` 看为什么失败，并从失败步骤恢复。”
- “把这个 flow 拆成父流程 + `call_flow` 子流程。”

Agent 默认应先用 `flow validate` / `dry-run --plan` 检查，再执行真实 `flow run`；涉及外部 HTTP/MCP、文件写入、`code` step 时必须说明 policy 边界。

## 文档模型


| 字段                | 说明                                                              |
| ----------------- | --------------------------------------------------------------- |
| `kind`            | 新流程使用 `rpa_flow`（`schema_version: rpa/1`）；旧 `mode: ui` 仅作为兼容入口。 |
| `schema_version`  | 当前仅 `rpa/1`。                                                    |
| `vars`            | 与站点预设相同风格的变量定义（可选）；`prepare_request` 负责合并与 secret。              |
| `steps`           | 步骤数组：UI 叶子 + 控制流 + RPA 叶子（见下）。                                  |
| `navigate_url`    | 可选，流程开始时导航。                                                     |
| `output_contract` | 与 UI 预设相同，`$.extracted.`* / `$.steps.`* 点路径。                    |
| `on_error`        | 与现有 flow 一致（截图 / snapshot）。                                     |


## 占位符与表达式

- **步骤字段插值**（`click.selector`、`fill.value` 等与站点预设一致）：使用 `{{vars.key}}`、`{{steps.id.value}}` 等形式时，**双花括号内不要加空格**（实现为单行正则）；否则占位符不会被替换。
- `**when` / `over` 等控制流字符串**：由 Jinja 渲染，可使用带空格的写法，例如 `{{ vars.flag }}`；单次求值有 **~100ms** 超时，防死循环。

## 控制流（P0）

- `if`：`when`（Jinja 表达式字符串）、`then` / `else` 子步骤列表。  
- `for_each`：`over`、`as`、`do`，支持 `max_iterations`、`continue_on_error`。  
- `while`：`when`、`do`、`max_iterations`（超出抛错）。  
- `for_range`：`from`、`to`、`as`、`do`；可选 `inclusive_to`、`max_span`。  
- `retry`：`do`、`max_attempts`、`delay_ms`、`backoff`（`none` / `exponential`）。  
- `break` / `continue`：仅在最内层 `for_each` / `while` / `for_range` 中合法。  
- `return` / `fail`：提前结束或主动失败。  
- `call_preset`：调用站点 `preset`，`with` 显式传参；栈深默认 ≤4；子运行失败会合并 `failures`。
- `call_flow`：执行另一 **rpa_flow** JSON 文件（`path` 或 `file`），`with` 传子 flow 的变量；相对路径相对**父 flow 文件所在目录**（由 `ziniao flow run` 或父 `call_flow` 注入的 base 目录）解析；栈深与 `call_preset` 共用上限。

## 数据 IO 与外部调用

- `read_json` / `write_json` / `read_text` / `write_text`：本地路径受 `~/.ziniao/policy.yaml` 中 `file_write_outside_workspace` 约束；未显式允许时仅允许 **当前工作目录、`~/.ziniao`、系统临时目录** 下的路径。
- `external_call` + `kind: http`：默认禁止私网 / loopback / link-local / 保留地址，且 DNS 解析到私网也会被拦截。`--allow-private-network` 或 policy 中 `allow_private_network: true` 只放开私网检查，**不会绕过 `url_allowlist*`*。
- `external_call` + `kind: mcp`：需 `external_call.mcp.enabled: true` 且 `tool_allowlist` 含 `server:tool` 或 `server:*` 等；**实现方式二选一**：`http_bridge_url` / 环境变量 `ZINIAO_MCP_HTTP_BRIDGE` 指向可接收 `{server, tool, arguments}` 的 HTTP 服务，或在 `external_call.mcp.servers` 下配置 stdio 子进程（`command` + `args`），再发 JSON-RPC 调工具。

示例 `~/.ziniao/policy.yaml`：

```yaml
external_call:
  http:
    enabled: true
    allow_private_network: false
    url_allowlist:
      - "https://api.example.com/*"
  mcp:
    enabled: false
    tool_allowlist: []
code_step:
  enabled: true
  language_allowlist: ["python"]
  max_runtime_seconds: 5
  max_output_kb: 64
file_write_outside_workspace:
  enabled: false
```

## 叶级重试

- 任意**叶步**可设 `retry: { "max_attempts", "delay_ms", "backoff": "none"|"exponential" }`（与块级 `action: retry` 不同），在**同一步**上重试 UI / RPA 叶动作。
- 块级 `action: retry` 与叶级 `retry` 都支持 `on: ["selector_missing", ...]`，设置后仅匹配 diagnostics category 时重试。

## 调试与隔离运行

- `ziniao flow run x.json --break-at step_id`：运行到指定 step 前暂停，写出 `state.json`，回包含 `paused`。
- `ziniao flow run x.json --resume-from step_id --replay <run_id>`：读取旧 `state.json` 并跳过目标 step 之前的步骤；支持进入嵌套控制流步骤。`--auto-resync` 可在 URL 不一致时自动导航，`--strict` 则直接失败。
- `ziniao flow run x.json --on-fail=pdb|repl|none`：daemon 模式不会阻塞 stdin；失败时把 debug mode 写入 diagnostics，供 Agent/IDE 后续接管。
- `ziniao flow step x.json step_id`：单步运行指定 step；如果该 step 不引用前序 `steps.*` / `extracted.*`，可以不传 state。
- `ziniao flow step x.json step_id --state <run_id>`：用旧 state 的 ctx 单步隔离运行指定 step；CLI 会自动从 `{{steps...}}` / `{{extracted...}}` / `{{vars...}}` 推断依赖并提前报缺失项，也可继续用显式 `inputs` 声明必须存在的上下文。
- `ziniao flow diagnose <run_id> --emit nodriver`：生成 `~/.ziniao/runs/<run_id>/repro.py`，包含 state/report 快照，作为 IDE 复现脚本入口。

`state.json` 的来源：

- 正常 `flow run` 每完成一个叶子步骤都会更新 `~/.ziniao/runs/<run_id>/state.json`。
- `--break-at step_id` 会在目标步骤执行前写出 state，适合调试“下一步”。
- 失败时 `report.json` 记录 failures/diagnostics；`state.json` 保留最近一次成功步骤后的上下文。

哪些步骤可以不依赖 state：

- 纯字面量步骤：如 `sleep`、固定 selector 的 `click` / `wait`、固定内容 `log`。
- 只使用 flow 变量且变量有默认值或由运行参数提供的步骤：如 `value: "{{vars.username}}"`。
- 会依赖 state 的步骤：引用 `{{steps.some_id...}}`、`{{extracted.name}}`，或显式写了 `inputs` 的步骤。

## RPA 叶子

- `sleep`、`set_var`、`log`、`assert`  
- `code`：受限 Python（见 `~/.ziniao/policy.yaml` 中 `code_step`）  
- `external_call`（`http` / `mcp`）：见上节  
- `read_csv` / `write_csv` / `read_json` / `write_json` / `read_text` / `write_text`

## 录制 → 草稿

```bash
ziniao rec stop --emit nodriver,preset --name mylogin
```

会在 `~/.ziniao/recordings/` 写出 `mylogin.rpa-flow.draft.json`（`meta.draft: true`），需人工补变量、断言与 `output_contract` 后再当生产流程使用。

录制草稿适合做第一版骨架，不应直接当生产流程：录制只能看到操作事实，看不到业务断言、循环边界、错误分支和输出契约。

## 与 `dispatch._flow_run` 的关系

守护进程命令仍为 `flow_run`；`ziniao_mcp.cli.dispatch._flow_run` **仅委托** `ziniao_mcp.flows.runner.run_flow`，以保持单一路径与行为一致。

## 相关代码

- `ziniao_mcp/flows/schema.py` — 白名单与递归校验  
- `ziniao_mcp/flows/runner.py` — 执行、`dry_run_static` / `dry_run_plan`  
- `ziniao_mcp/flows/policy.py` — 策略合并与 URL / MCP / 本地路径规则  
- `ziniao_mcp/flows/mcp_invoke.py` — `external_call` MCP 调用（HTTP 桥或 stdio）  
- `ziniao_mcp/recording/emit_preset.py` — 录制 IR → 草稿 JSON

