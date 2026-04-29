---
name: rpa-flows
description: 设计、编写、运行和调试 ziniao 统一声明式 Flow（推荐 `kind: rpa_flow`）。用户提到 RPA flow、ziniao flow、声明式流程、控制流、重试、断点恢复、录制转草稿、flow validate/run/diagnose/step 时使用。
compatibility: 需要本机已安装 ziniao CLI；浏览器动作需要已打开 Chrome 或紫鸟店铺会话，纯数据 flow 可无浏览器运行。
allowed-tools: Bash(ziniao:*)
---

# Ziniao 统一 Flow

Ziniao 只维护一套浏览器 Flow 模型：`click` / `fill` / `extract` / `fetch` / `snapshot` 等 UI steps 统一由 `ziniao_mcp.flows.runner.run_flow` 执行。`kind: rpa_flow` 是新流程的推荐写法；旧 `mode: ui` 站点预设继续兼容，但不要再把新能力扩成第二套。

本 skill 用于把浏览器操作固化为统一 Flow JSON，并通过 `ziniao flow` 校验、运行、诊断和恢复。它适合交付给用户或 Agent 重复运行；如果目标是长期脱离 daemon 的定时脚本，再转 `store-rpa-scripting` 生成独立 Python。

## 何时使用

- 用户要“做一个 RPA 流程”“把这些点击/填表步骤固化”“用 JSON 描述浏览器自动化”。
- 需要 `if` / `for_each` / `while` / `for_range` / `retry` / `call_flow` / `call_preset`。
- 需要读取或写入 JSON/CSV/text，或调用外部 HTTP/MCP。
- 需要失败工件、`state.json`/`report.json`、断点、恢复、单步重跑。
- 录制后需要把操作转为 `.rpa-flow.draft.json` 并补变量、断言、输出。

## 默认工作流

1. **探索页面**：打开店铺或 Chrome，用 `snapshot --interactive` 找稳定 CSS selector；不要把 `@e0` 这类 ref 当 selector。
2. **写 flow**：新流程创建 `kind: rpa_flow` / `schema_version: rpa/1` JSON，步骤必须有稳定 `id`。
3. **离线检查**：先 `ziniao flow validate x.json`，再 `ziniao flow dry-run x.json --plan`。
4. **执行**：`ziniao flow run x.json --var k=v`，需要文件变量时用 `--vars-from data.json|data.yaml|data.csv`。
5. **诊断**：失败后取返回的 `run_id`，运行 `ziniao flow diagnose <run_id> --emit nodriver`。
6. **恢复/单步**：用 `--replay <run_id> --resume-from step_id` 或 `ziniao flow step x.json step_id --state <run_id>`。

## 最小模板

```json
{
  "kind": "rpa_flow",
  "schema_version": "rpa/1",
  "name": "demo",
  "navigate_url": "https://example.com",
  "vars": {
    "keyword": {"type": "str", "default": "demo"}
  },
  "steps": [
    {"id": "wait_body", "action": "wait", "selector": "body", "state": "visible", "timeout": 10},
    {"id": "set_keyword", "action": "set_var", "name": "q", "value": "{{vars.keyword}}"},
    {"id": "log_keyword", "action": "log", "message": "keyword={{vars.q}}"}
  ],
  "output_contract": {}
}
```

运行：

```bash
ziniao flow validate ./demo.rpa-flow.json
ziniao flow dry-run ./demo.rpa-flow.json --plan
ziniao flow run ./demo.rpa-flow.json --var keyword=test
```

## 可用步骤

- UI 叶子：统一 Flow 浏览器动作，如 `wait`、`click`、`fill`、`extract`、`fetch`、`snapshot`；旧 `mode: ui` 也复用这些动作。
- 控制流：`if`、`for_each`、`while`、`for_range`、`retry`、`break`、`continue`、`return`、`fail`。
- 数据与工具：`sleep`、`set_var`、`log`、`assert`、`code`、`read_csv`、`write_csv`、`read_json`、`write_json`、`read_text`、`write_text`。
- 复用：`call_preset` 调站点 preset；`call_flow` 调另一个 rpa_flow 文件。
- 外部调用：`external_call` 支持 `kind: http` 和 `kind: mcp`，按 policy 限制执行。

## 表达式规则

- 普通步骤字段插值使用 `{{vars.name}}`、`{{steps.step_id.value}}`，花括号内不要加空格。
- `when`、`over` 等控制流字段走 Jinja，可写 `{{ vars.flag }}`，但表达式应保持轻量。
- 对列表循环优先把数组放到 `vars` 或前序 `read_json`/`read_csv` 的结果里，再用 `for_each.over` 引用。

## 安全策略

默认 policy 来自 `~/.ziniao/policy.yaml`，也可临时指定：

```bash
ziniao flow run ./x.json --policy ./policy.yaml
```

要点：

- HTTP 外呼默认拦截私网、loopback、link-local、保留地址和 DNS 解析到私网的域名。
- `--allow-private-network` 只放开私网检查，不绕过 `url_allowlist`。
- MCP 外呼默认关闭；需要 `external_call.mcp.enabled: true` 和 `tool_allowlist`。
- 本地文件 IO 默认只允许当前工作目录、`~/.ziniao` 和系统临时目录；跨目录写入需显式 policy。
- `code` step 是受限 Python，有运行时间和输出大小限制；不要把不可信脚本放进去。

## 调试命令

```bash
ziniao flow run ./x.json --break-at step_id
ziniao flow run ./x.json --replay <run_id> --resume-from step_id --strict
ziniao flow run ./x.json --replay <run_id> --resume-from step_id --auto-resync
ziniao flow step ./x.json step_id --state <run_id>
ziniao flow diagnose <run_id> --emit nodriver
```

State handling:

- `state.json` is produced automatically under `~/.ziniao/runs/<run_id>/` after each successful leaf step; `--break-at` writes it before the paused step.
- Independent steps can run without `--state`: literal `sleep`/`wait`/`click`/`log`, or `vars.*` values supplied by defaults/CLI.
- Steps that reference `steps.*` or `extracted.*` need prior context. `flow step` auto-detects `{{steps...}}`, `{{extracted...}}`, and `{{vars...}}`; if required context is missing it fails early with the missing paths.
- Use explicit `inputs` only for dependencies that cannot be inferred from templates.

`~/.ziniao/runs/<run_id>/` 下会有：

- `state.json`：当前上下文、会话信息、等待锚点、脱敏变量。
- `report.json`：成功/失败、`failures`、`diagnostics`、耗时字段。
- 失败截图、HTML、err 文本：受 `on_error` 控制。
- `repro.py`：`diagnose --emit nodriver` 生成的 best-effort 复现脚本。

## 录制转草稿

```bash
ziniao rec start
# 在浏览器中操作
ziniao rec stop --name my-flow --emit nodriver,preset
```

会生成 `~/.ziniao/recordings/my-flow.rpa-flow.draft.json`。草稿只能作为骨架，交付前必须补：

- `vars`：把账号、关键词、日期、文件路径等改成变量。
- `assert` / `wait`：补业务成功条件。
- `retry` / 分支：补慢加载、空结果、错误提示。
- `output_contract`：声明最终给用户/脚本的输出。
- `policy`：外部 HTTP/MCP/文件 IO/code 的安全边界。

## 交付检查

- 每个关键步骤有稳定 `id`，便于 `--break-at` / `--resume-from` / `flow step`。
- selector 来自实测 `snapshot --interactive` 或 `get count`，没有使用 `@eN`。
- 先跑过 `flow validate` 和 `flow dry-run --plan`。
- 失败路径有 `on_error` 和可读 `message`。
- 外部调用和文件 IO 已按最小权限配置 policy。
- 示例运行命令写清楚变量来源、输出位置、恢复方式。

## 参考

- 仓库文档：`docs/rpa-flows.md`
- 示例：`examples/rpa/*.rpa-flow.json`
- 需要脱离 daemon 的长期脚本：使用 `store-rpa-scripting`

