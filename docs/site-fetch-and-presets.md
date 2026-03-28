# 页面内请求与站点模板（Site presets）

在当前浏览器**活动标签页**的 JavaScript 环境里执行请求，自动带上该页的 **Cookie**；可按模板注入 **XSRF**、**变量**、**分页**。适用于已登录后台的 XHR/API 拉数，而不是无头爬公网。

## 最简用法（推荐）

先让标签页处在目标站点（或模板里配置了 `navigate_url` 会自动跳转）。

```bash
# 列出内置/用户模板（含鉴权类型、是否支持分页）
ziniao site list

# 查看变量说明与示例
ziniao site show rakuten/rpp-search

# 一行调用（等价于以前的 network fetch -p …）
ziniao rakuten rpp-search -V start_date=2026-03-01 -V end_date=2026-03-07

# 指定页 / 拉全部分页并合并（模板内需配置 pagination）
ziniao rakuten rpp-search -V start_date=... -V end_date=... --page 2
ziniao rakuten rpp-search -V start_date=... -V end_date=... --all -o out.json

# 禁用/启用某个模板（禁用后不再注册顶层 ziniao <site> <action>，仍可用 -f JSON）
ziniao site disable rakuten/rpp-search
ziniao site enable rakuten/rpp-search
```

## 底层命令（调试用）

```bash
ziniao network fetch -p rakuten/rpp-search -V start_date=... -V end_date=... [--page N] [--all] [-o file]
ziniao network fetch -f ./my-request.json
ziniao network fetch https://api.example.com/x -X POST -d '{"q":1}'
ziniao network fetch --script 'axios.post("/api", __BODY__).then(r=>r.data)' -d '{"q":1}'
ziniao network fetch-save --filter "reports/search" -o tpl.json
```

`fetch-save`：从已捕获请求生成 JSON 模板（可先 `ziniao network list` 看 id）。

## JSON 模板要点

| 字段 | 作用 |
|------|------|
| `navigate_url` | 执行前若不在该页则先导航 |
| `mode` | `fetch`（默认）或 `js`（走页面内脚本，配合 `script`） |
| `xsrf_cookie` | Cookie 名，用于自动填 `X-XSRF-TOKEN` |
| `vars` | 模板变量定义；正文里用 `{{name}}` |
| `auth` | `type`: `cookie` / `xsrf` / `token` / `none`；`hint` 给人看的说明 |
| `pagination` | `body_field` 或 `offset`：支持 `--all` 自动翻页合并列表 |

用户自定义：将 `.json` 放到 `~/.ziniao/sites/<站点名>/`，会覆盖同名内置模板。

Python 插件（可选）：`~/.ziniao/sites/<站点>/__init__.py` 或包内 `ziniao_mcp/sites/<站点>/`，继承 `SitePlugin`，实现 `before_fetch` / `after_fetch` / `paginate`（复杂分页）。第三方包可通过 `ziniao.sites` entry point 注册。

## `ziniao eval` 与 Promise

异步表达式需等待结果时：

```bash
ziniao eval --await "fetch('/api').then(r => r.text())"
```

`--await` 在**主文档与 iframe 上下文**中均会传给 CDP（行为一致）。

## MCP

工具 **`page_fetch`**：参数为 URL、method、body、headers（JSON 字符串）、`xsrf_cookie`、`mode`、`script`、`navigate_url`，语义与 daemon 的 `page_fetch` 一致。

## 另见

- 仓库内 Agent 技能：`skills/ziniao-cli/SKILL.md`（速查表）
- 完整命令表：`skills/ziniao-cli/references/commands.md`
