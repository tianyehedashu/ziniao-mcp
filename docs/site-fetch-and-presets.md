# 页面内请求与站点模板（Site presets）

在当前浏览器**活动标签页**的 JavaScript 环境里执行请求，自动带上该页的 **Cookie**；可按模板注入 **XSRF**、**变量**、**分页**。适用于已登录后台的 XHR/API 拉数，而不是无头爬公网。

## 架构

```text
┌─────────────────────────────────────────────────────────────────┐
│ 入口                                                            │
│  CLI: ziniao <site> <action> / network fetch -p / -f / URL      │
│  MCP: page_fetch                                                │
│  fetch-save: 抓包 → JSON 模板                                    │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 归一化：prepare_request()                                        │
│  加载预设/文件 → 渲染 {{vars}} → 合并 CLI 覆盖                     │
│  → plugin.before_fetch() → _normalize_xsrf()                   │
│                                                                 │
│  输出：唯一 spec dict                                             │
│    url, method, body, headers,                                  │
│    xsrf_cookie + xsrf_headers[],                                │
│    navigate_url, mode, pagination …                             │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 执行器：_page_fetch_fetch()                                      │
│  不含业务逻辑；按 spec 生成 JS：                                    │
│    cookie → xsrf_headers[] → h[name] = token                   │
│    fetch(url, {headers, body, credentials:'include'})           │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 浏览器活动标签页                                                  │
│  document.cookie  →  同源 fetch  →  HTTP 响应                    │
└─────────────────────────────────────────────────────────────────┘
```

设计原则：**特例停在归一化层，执行器只按 spec 发请求**。如果某个站点的鉴权逻辑无法用声明字段表达，应使用 `mode: "js"` 或 `SitePlugin.before_fetch`，而不是在执行器里加分支。

## 会话鉴权（auth）

页面内请求复用浏览器的登录态，不做额外登录。`auth.type` 声明服务器**验证身份的方式**：

| `auth.type` | 含义 | 模板字段 |
|-------------|------|---------|
| `cookie` | 只带 Cookie（`credentials: 'include'`） | 无额外字段 |
| `xsrf` | Cookie + 从 Cookie 读反 CSRF 令牌写入请求头 | `xsrf_cookie` + `xsrf_headers` |
| `token` | Bearer / 自定义令牌（通常从页面状态获取） | 一般配合 `mode: "js"` |
| `none` | 无需鉴权 | 无 |

`auth.type` 是**给人和工具看的标签**（`site list` 显示、Agent 决策参考）；实际行为由 `xsrf_cookie` / `xsrf_headers` / `mode` 等字段驱动。

XSRF 策略的字段说明、`fetch-save` 自动识别、扩展方式 → **[page-fetch-xsrf.md](page-fetch-xsrf.md)**。

## 最简用法

先让标签页处在目标站点（或模板里配置了 `navigate_url` 会自动跳转）。

```bash
# 列出内置/用户模板（含鉴权类型、是否支持分页）
ziniao site list

# 查看变量说明与示例
ziniao site show rakuten/rpp-search

# 一行调用
ziniao rakuten rpp-search -V start_date=2026-03-01 -V end_date=2026-03-07

# 分页
ziniao rakuten rpp-search -V start_date=... -V end_date=... --page 2
ziniao rakuten rpp-search -V start_date=... -V end_date=... --all -o out.json

# 禁用/启用模板
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

## JSON 模板字段

| 字段 | 作用 |
|------|------|
| `navigate_url` | 执行前若不在该页则先导航 |
| `mode` | `fetch`（默认）或 `js`（走页面内脚本，配合 `script`） |
| `auth` | `type`: `cookie` / `xsrf` / `token` / `none`；`hint` 给人看的说明 |
| `xsrf_cookie` | Cookie 名；从 `document.cookie` 取令牌 |
| `xsrf_headers` | `string[]`：令牌写入的请求头名；设 `xsrf_cookie` 且不写时默认 `["X-XSRF-TOKEN"]` |
| `vars` | 模板变量定义；正文里用 `{{name}}` |
| `pagination` | `body_field` 或 `offset`：支持 `--all` 自动翻页合并列表 |

## 从内置模板派生（自定义）

```bash
# 将内置模板复制到 ~/.ziniao/sites/ 供编辑（同名覆盖内置）
ziniao site fork rakuten/rpp-search

# 另存为新 ID
ziniao site fork rakuten/rpp-search mysite/rpp-custom
```

编辑后直接用 `-p` 调用——`load_preset` 会优先读用户目录。

也可手动将 `.json` 放到 `~/.ziniao/sites/<站点名>/`，会覆盖同名内置模板。

Python 插件（可选）：`~/.ziniao/sites/<站点>/__init__.py` 或包内 `ziniao_mcp/sites/<站点>/`，继承 `SitePlugin`，实现 `before_fetch` / `after_fetch` / `paginate`（复杂分页）。第三方包可通过 `ziniao.sites` entry point 注册。

## `ziniao eval` 与 Promise

```bash
ziniao eval --await "fetch('/api').then(r => r.text())"
```

`--await` 在主文档与 iframe 上下文中均会传给 CDP。

## MCP

工具 **`page_fetch`**：参数为 URL、method、body、headers（JSON 字符串）、`xsrf_cookie`、`xsrf_headers`（JSON 数组字符串）、`mode`、`script`、`navigate_url`，语义与 daemon 的 `page_fetch` 一致。

## 另见

- **[page-fetch-xsrf.md](page-fetch-xsrf.md)** — XSRF/CSRF 策略：使用、实现与扩展
- 仓库内 Agent 技能：`skills/ziniao-cli/SKILL.md`（速查表）
- 完整命令表：`skills/ziniao-cli/references/commands.md`
