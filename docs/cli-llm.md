# 面向大模型 / Agent 的 CLI 输入输出约定

本文说明如何让 **ziniao** 的终端输出更容易被大模型稳定解析，并与脚本、Agent 工具链对齐。

## 推荐组合

| 场景 | 建议标志 | 说明 |
|------|-----------|------|
| 结构化 + 自解释（推荐） | **`--llm`** | 等价打开 JSON 模式，并在响应中加入 **`meta`**（字段名列表、快照语义、批量说明等） |
| 仅要信封、不要 meta | **`--json`** | `success` / `data` / `error`，见 [cli-json.md](cli-json.md) |
| 兼容旧脚本 | **`--json-legacy`** | 原始 daemon 字典，无信封、无 meta |
| 人类可读但可粘贴到对话 | **`--plain`** | 关闭 Rich 表格/颜色，stdout 为 **UTF-8 JSON**（成功为 daemon 字典，失败为 `{"success":false,"error":"..."}`） |

`--llm` 与 **`--json-legacy`** 互斥。`--plain` 在已使用 **`--json` / `--llm`** 时不改变格式（仍以 JSON 信封输出）。

## `--llm` 时的 `meta` 字段

在 **`--json` 信封**之上增加顶层 **`meta`**（对象），例如：

```json
{
  "success": true,
  "data": { ... },
  "error": null,
  "meta": {
    "schema_version": 1,
    "role": "ziniao_cli_response",
    "how_to_read": "...",
    "docs": "docs/cli-llm.md",
    "daemon_command": "session_list",
    "data_field_names": ["active", "count", "sessions"]
  }
}
```

常见附加键：

- **`daemon_command`**：本次对应的 daemon 命令名（批量汇总为 **`batch_run`**）。
- **`data_field_names`**：`data` 的键名列表（便于模型在不读全文时建立结构预期）。
- **`snapshot_semantics`**：当命令为 `snapshot` / `snapshot_enhanced` 时说明与 agent-browser 默认快照（无障碍树）的差异。
- **`batch`**：当 `data` 为批量结果汇总时，说明 **`data.results[]`** 为每步原始字典、可能含 **`error`**。

模型解析顺序建议：**先看 `success` → 再读 `error` 或 `data` → 用 `meta` 校正对字段含义的理解**。

## 输入侧（给模型下指令时写清楚）

1. **命令名**：Typer 子命令（如 `nav go`）与 daemon 名（如 `navigate`）可能不同；写 **batch** 或自动化时必须使用 **daemon 名**，见 [cli-agent-browser-parity.md](cli-agent-browser-parity.md) 第 14 节。
2. **批量 stdin**：形状为 `[{"command":"...", "args":{}}]`，**不是** agent-browser 的「数组的数组」；见 [cli-agent-browser-parity.md](cli-agent-browser-parity.md) 第 2 节。
3. **`act type`**：参数顺序为 **`TEXT` 在前**，`--selector` 在后；与 agent-browser `type <selector> <text>` 相反。
4. **全局选项位置**：`--store` / `--session` / `--json` / `--llm` / `--plain` / `--timeout` 写在**子命令组之前**，例如：  
   `ziniao --llm info snapshot`

## 快照与截图

- 默认 **`snapshot`** 返回的 **`data.html`** 是 **HTML 源码**，不是 agent-browser 那种带 `@e1` 的无障碍树；选型器用 **CSS**，或 `snapshot_enhanced --interactive` 等。
- 截图成功时常见 **`data.data`** 为 **`data:image/...;base64,...`**；解码时取逗号后的 base64。

## 与 MCP 的关系

MCP 工具返回的结构由服务器定义，**不一定**与 CLI 的 `success`/`data`/`error` 信封相同。若 Agent 同时用 MCP 和 CLI，请在提示词里区分两条路径。
