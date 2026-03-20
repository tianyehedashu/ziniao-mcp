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

## `--content-boundaries`（与 agent-browser 一致）

与 **agent-browser** 的 **`--content-boundaries`** 相同：在 **`--json`** 输出上增加顶层 **`_boundary`**：

```json
{
  "success": true,
  "data": { ... },
  "error": null,
  "_boundary": { "nonce": "...", "origin": "https://..." }
}
```

`origin` 尽量取自 `data.url` / `data.origin`。人类可读模式下，页面类文本会用 `ZINIAO_PAGE_CONTENT` 标记行包裹。环境变量 **`ZINIAO_CONTENT_BOUNDARIES=1`** 等价于该标志。

## `--max-output`

与 agent-browser 的 **`--max-output N`** 思路一致：限制快照 HTML、`eval` 返回字符串等的字符数。环境变量 **`ZINIAO_MAX_OUTPUT`**。

- **未指定**（CLI 与环境均未设置）时，为 **避免终端被巨量 HTML 拖死**，stdout 上仍会对上述字段应用 **默认 2000 字符** 截断（历史行为）。
- **`--max-output 0`** 或 **`ZINIAO_MAX_OUTPUT=0`**：stdout **不**再自动截断。
- **`ziniao info snapshot -o file`**：写入文件的 HTML / JSON **始终完整**，不受默认截断影响（与「落盘要全量」一致）。

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

`ziniao info snapshot -o file.html` 在同时使用 **`--json`** 时，写入文件的 JSON 同样使用上述信封格式（若启用 **`--content-boundaries`**，也会包含 **`_boundary`**）。

面向 Agent / 大模型的用法见 [cli-llm.md](cli-llm.md)（**不**引入非标准的 JSON 扩展字段，与 agent-browser 设计对齐）。
