# CLI JSON 输出约定

`ziniao` 在指定 **`--json`** 时输出 **单行或多行 JSON**（默认 `indent=2` 便于阅读），结构与 **agent-browser** CLI 的 `success` / `data` / `error` 信封对齐：

```json
{
  "success": true,
  "data": { ... },
  "error": null
}
```

失败时（daemon 返回体含 `"error"` 键）：

```json
{
  "success": false,
  "data": null,
  "error": "人类可读的错误说明"
}
```

- **`data`**：成功时为 daemon 的完整响应对象（可能含 `ok`、`url`、`sessions`、`html` 等，因命令而异）。
- **`error`**：失败时为字符串；成功时为 `null`。

## `--llm`（信封 + `meta`）

使用 **`--llm`** 时仍输出上述信封，并额外包含顶层 **`meta`**（`data` 内有哪些键、快照语义、批量结果说明等），便于大模型解析。与 **`--json-legacy`** 互斥。详见 [cli-llm.md](cli-llm.md)。

## `--json-legacy`

若脚本仍按 **旧版**「直接解析 daemon 字典」编写（例如 `jq '.sessions'`），请使用 **`--json-legacy`**，输出与原先 **`--json`** 行为一致（无 `success` / `data` / `error` 信封）。**`--json` 与 `--json-legacy` 不能同时使用。**

## 与 `jq` 配合

信封模式下，业务字段在 **`data`** 下，例如：

```bash
ziniao session list --json | jq '.data.sessions'
ziniao get count ".item" --json | jq '.data.count'
ziniao is visible ".btn" --json | jq '.data.visible'
```

## `ziniao batch run --json`

批量命令结束时，stdout 为一层信封，批量元数据在 `data` 内：

```json
{
  "success": true,
  "data": {
    "results": [ { ... }, { ... } ],
    "total": 2,
    "executed": 2
  },
  "error": null
}
```

其中 **`results`** 的每个元素仍是 **daemon 原始字典**（未再套信封）。若需要对每条结果统一解析，可在脚本中对 `results[]` 自行判断 `"error" in item`。

## 写入文件

`ziniao info snapshot -o file.html` 在同时使用 **`--json`** 时，写入文件的 JSON 同样使用上述信封格式。
