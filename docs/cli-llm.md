# 大模型 / Agent 如何消费 ziniao CLI 输出（与 agent-browser 对齐）

不要依赖 **非标准** 的 CLI 扩展字段；业界常见做法是 **固定 JSON 信封 + 可选内容边界 + 截断 + 环境变量**，与 [agent-browser](https://github.com/vercel/agent-browser) CLI 一致。

## 1. 机器可读：只用 `--json`

与 agent-browser 的 **`--json`** 相同，顶层为：

```json
{"success": true, "data": { ... }, "error": null}
```

失败时 `data` 为 `null`，`error` 为字符串。业务字段永远在 **`data`** 里（与 `jq '.data.*'` 一致）。

脚本或 Agent 应 **默认使用 `--json`**，而不是解析 Rich 表格。

## 2. 内容与指令混淆： `--content-boundaries`

与 agent-browser 的 **`--content-boundaries`** 同思路：

- **JSON**：在顶层增加 **`_boundary`: `{"nonce","origin"}`**（与 agent-browser 在 JSON 中附加边界元数据一致）。
- **人类可读**：对快照 HTML、`eval` 长字符串等，在 stdout 用 **`--- ZINIAO_PAGE_CONTENT ... ---`** / **`END_...`** 包裹（命名与 agent-browser 的 `AGENT_BROWSER_PAGE_CONTENT` 并列，避免与页面正文混淆）。

`nonce` 使用加密安全随机数，降低不可信页面伪造边界行的风险（与 agent-browser 设计动机一致）。

## 3. 过长输出：`--max-output N`

与 agent-browser 的 **`--max-output`** 思路一致：限制 **字符数**，并在截断处附加说明行。**未设置**时 stdout 仍对快照 HTML、`eval` 字符串使用 **默认 2000 字符**（终端安全）。**`0` / `ZINIAO_MAX_OUTPUT=0`** 表示 stdout 不截断。**`-o` 写文件**始终全量。

## 4. 环境变量（对标 `AGENT_BROWSER_*`）

| ziniao | 含义 | agent-browser 对照 |
|--------|------|---------------------|
| `ZINIAO_JSON=1` | 等价开启 JSON 信封 | `AGENT_BROWSER_JSON` |
| `ZINIAO_CONTENT_BOUNDARIES=1` | 等价 `--content-boundaries` | `AGENT_BROWSER_CONTENT_BOUNDARIES` |
| `ZINIAO_MAX_OUTPUT` | 正整数，等价 `--max-output` | `AGENT_BROWSER_MAX_OUTPUT` |

CLI 显式传入的标志优先于环境变量中的布尔/数值合并逻辑见实现（与常见 CLI 一致）。

## 5. 终端颜色：`NO_COLOR`

与 agent-browser 仓库 **AGENTS.md** 一致：遵循 [no-color.org](https://no-color.org/)，**`NO_COLOR`** 下 Rich 等库应关闭着色（由依赖库处理）。

## 6. 语义差异（文档约定，非 CLI 魔法字段）

- **快照**：ziniao 默认 **`data.html`** 为 HTML；agent-browser 默认快照为 **无障碍树 + @ref**。迁移 Agent 提示词时必须在文档层说清，**不要**在 JSON 里塞自定义 `meta` 对象替代文档。
- **batch**：stdin 格式与 agent-browser **不同**，见 [cli-agent-browser-parity.md](cli-agent-browser-parity.md)。

## 7. 推荐 Agent 提示词片段

```text
调用 ziniao 时使用：ziniao --json [--content-boundaries] [--max-output 8000] <子命令>...
解析：先读 success，再读 data 或 error。若启用 content-boundaries，先读 _boundary 再解析 data。
快照字段为 HTML 时使用 CSS 选择器，不要假设存在 @e1 式 ref。
```
