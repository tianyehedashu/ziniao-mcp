---

## name: ziniao-cli
description: Browser automation for multi-store sellers and Chrome. Use when the user needs to open stores, navigate pages, fill forms, click buttons, take screenshots, extract data, intercept network requests, call logged-in APIs from the page (site presets / network fetch / page_fetch), manage site presets and repos, install AI agent skills, or automate any browser task. Triggers include "open a store", "open a website", "fill out a form", "click a button", "take a screenshot", "scrape data", "switch session", "multi-store batch", "browser automation", "fetch API with cookies", "site preset", "site repo", "skill install", or any Ziniao/Chrome automation request.
allowed-tools: Bash(ziniao:*)

# Ziniao CLI — Browser Automation from Terminal

Install with `uv tool install ziniao`. Supports Ziniao multi-store sessions and standalone Chrome, with built-in stealth and anti-detection. The daemon starts automatically on first command.

## Quick Setup

**Chrome only (zero config):**

```bash
ziniao launch --url https://example.com
```

**Chrome + state reuse** — wizard or manual:

```bash
ziniao config init              # interactive wizard → ~/.ziniao/config.yaml + .env
# OR:
ziniao config set chrome.user_data_dir "C:\Users\<you>\.ziniao\chrome-profile"
```

**Ziniao + Chrome (full feature):** run `ziniao config init` and answer the Ziniao questions, or copy [assets/config.example.yaml](assets/config.example.yaml) to `~/.ziniao/config.yaml` and fill in values. Put secrets in [assets/env.example](assets/env.example)-style variables.

Config priority: env vars (including `~/.ziniao/.env`) → CLI flags → YAML. Use `ziniao config show` to inspect. See [references/configuration.md](references/configuration.md) for paths and MCP setup.

## Core Workflow

Every automation follows: **Connect → Navigate → Inspect → Interact → Verify**.

Use **CSS selectors** with `click` / `fill` / `wait` (valid for `document.querySelector`). Column `**ref` (`@e0` …)** in `snapshot --interactive` is **only a row label** — **do not** pass `@eN` as a selector.

## Session Targeting Rules for Agents

The daemon has a human-friendly **active session / active tab**, but agents and scripts must treat it as unsafe shared state. For any non-trivial task:

1. Run `ziniao --json session list` and capture the intended `session_id` (or store id).
2. Use one-shot targeting on every command: `ziniao --session <id> ...` or `ziniao --store <store_id> ...`.
3. Use `session switch` only for manual interactive work; do **not** rely on it inside multi-step Agent plans, batch jobs, or parallel tasks.
4. For tab-sensitive work, list/switch tabs immediately before the operation, then verify with `ziniao --session <id> url` or `snapshot`; tab indexes can change after tabs close/open.
5. Before long or parallel workflows, check `ziniao session health`; use `ziniao cluster acquire --session <id> --ttl <sec>` when coordinating multiple agents/jobs.

Safe pattern:

```bash
SID=$(ziniao --json session list | jq -r '.data.sessions[] | select(.name=="Chrome (9222)") | .session_id')
ziniao --session "$SID" navigate "https://example.com"
ziniao --session "$SID" wait "body"
ziniao --session "$SID" snapshot --interactive
```

**Inspect → pick selectors:**

- `**ziniao snapshot --interactive`** — table with a **Selector** column (auto-computed, unique CSS selector like `#id` or `[name="…"]`). Copy the selector directly into `click` / `fill` / `wait`.
- `**ziniao snapshot`** or `**ziniao snapshot --compact**` — full HTML when you need classes/structure or elements the interactive table didn't cover.

```bash
ziniao open-store my-store-001                          # or: ziniao launch --url <url>
ziniao navigate "https://sellercentral.amazon.com/inventory"
ziniao wait ".inventory-table"
ziniao snapshot --interactive                           # Selector column → directly use in click/fill
ziniao click "#edit-btn"
ziniao fill "#price-input" "29.99"
ziniao screenshot after-edit.png
```

## Command Chaining

Commands share a persistent daemon, so chaining with `&&` is safe:

```bash
ziniao navigate "https://example.com" && ziniao wait ".loaded" && ziniao screenshot page.png
ziniao fill "#email" "user@test.com" && ziniao fill "#pass" "secret" && ziniao click "#login"
```

**When to chain:** Use `&&` when you don't need intermediate output. Run separately when you need to parse output first (e.g. `ziniao snapshot` to pick selectors, or `--json` then loop).

## Ziniao Stores vs Chrome


| Backend              | Connect                  | Use case                                                                                   |
| -------------------- | ------------------------ | ------------------------------------------------------------------------------------------ |
| **Ziniao store**     | `ziniao open-store <id>` | Multi-store seller workflows, anti-detection                                               |
| **Chrome (launch)**  | `ziniao launch`          | New Chrome, ziniao owns the process                                                        |
| **Chrome (connect)** | `ziniao connect <port>`  | Chrome already running with `--remote-debugging-port`; `chrome close` detaches ziniao only |


Setting `CHROME_USER_DATA` enables state reuse (cookies, localStorage, extensions persist).

Control is **CDP** on **127.0.0.1** (remote browser → port-forward first). Commands hit the **active session** and **active tab** unless you use one-shot `**--store` / `--session`** (preferred for agents), `**session list|switch**`, or `**tab list|switch -i N**`. For Ziniao shops—even if the window was opened in the desktop app—use `**open-store <id>**`, not `**connect**`. **Stealth** (when enabled): `**launch`** / `**open-store**` patch every open tab’s current document; `**connect**` registers the script on all tabs but only runs the heavy **evaluate** on the **active** tab (others pick it up on next navigation).

## Key Commands

> Full reference: [references/commands.md](references/commands.md)

```bash
# Connect
ziniao store start-client            # Ziniao desktop app (WebDriver HTTP); required for list/open store
ziniao store stop-client             # Quit Ziniao client
ziniao open-store <id>               # Open Ziniao store
ziniao launch [--url u] [--name n]   # Launch Chrome (--headless for headless)
ziniao connect <port>                # Connect to existing Chrome
ziniao session list                  # All sessions (stores + Chrome)
ziniao session switch <id>           # Switch active session
ziniao session health                # CDP liveness for daemon sessions
ziniao cluster status                # Leases + daemon sessions
ziniao cluster acquire --session <id> --ttl 600
ziniao cluster release <lease_id>

# Navigate
ziniao navigate <url>
ziniao back | forward | reload
ziniao tab list | tab new --url <url> | tab switch -i <n>
ziniao wait <selector> [--timeout N]

# Interact
ziniao click <selector>              # Click
ziniao dblclick <selector>           # Double-click
ziniao fill <selector> <value>       # Clear + type
ziniao type <text> [-s <selector>]   # Char-by-char (optional selector)
ziniao press Enter                   # Press key
ziniao hover <selector>
ziniao drag <source> <target>
ziniao act select <selector> <value> # Dropdown
ziniao act check | uncheck <selector>

# Read
ziniao get text|html|value <selector>
ziniao get attr <selector> <attr>
ziniao get count <selector>
ziniao title | url
ziniao is visible|enabled|checked <selector>

# Find (ordinal / semantic)
ziniao find first|last <selector> [action]
ziniao find nth <n> <selector> [action]   # 0-based
ziniao find text "Submit" [action]        # By text content
ziniao find role button [action]          # By ARIA role (--name for accessible name)

# Inspect
ziniao snapshot [--interactive] [--compact] [-s <selector>]
ziniao screenshot [file] [-s <selector>] [--full-page]
ziniao eval "<js>" [--await]              # --await for Promise (fetch, etc.); works in iframe too
ziniao info console | network | errors
ziniao info highlight <selector>

# Cookies, storage, clipboard
ziniao info cookies                       # List
ziniao info cookies set --name k --value v
ziniao info cookies clear
ziniao info storage local get | set -k <key> -v <val>
ziniao info storage session get
ziniao cookie-vault export -o auth.json   # AuthSnapshot: cookies + storage + UA
ziniao cookie-vault import auth.json      # Rejects redacted snapshots; checks origin
ziniao info clipboard read | write --text "hello"

# Scroll
ziniao scroll down|up|left|right [pixels]
ziniao scrollinto <selector>

# Network interception & HAR
ziniao network route "<pattern>" [--abort] [--body ...] [--status N]
ziniao network unroute [pattern]
ziniao network routes
ziniao network list [--filter url] [--clear]
ziniao network har-start
ziniao network har-stop [path]

# Page-context HTTP (inherits tab cookies; optional XSRF from cookie name)
ziniao network fetch [-p preset | -f file | URL] [-X METHOD] [-d body] [-H "K:V"]... [--page N] [--all] [-o file] [--decode-encoding cp932] [--output-encoding utf-8]
ziniao network fetch URL --transport browser_fetch           # default: browser page fetch
ziniao network fetch URL --transport direct --auth-snapshot auth.json
ziniao network fetch URL --transport auto --auth-snapshot auth.json
ziniao network fetch --script '<expr using __BODY__>' -d '{"k":1}'
ziniao network fetch-save [--id N | --filter SUBSTR] -o template.json [--as-preset]

# Site presets (shortcuts: ziniao <site> <action> — templates under ziniao_mcp/sites/ and ~/.ziniao/sites/)
ziniao site list | show <id> [--raw] | enable <id> | disable <id>
ziniao site fork <id> [<new_id>] [--force]        # copy preset to ~/.ziniao/sites/ for editing
# Example: ziniao rakuten rpp-search -V start_date=2026-03-01 -V end_date=2026-03-07 [--page N] [--all] [-o out]
# CSV/binary: ziniao rakuten reviews-csv -o reviews.csv   # preset output_decode_encoding=cp932

# Site & skill management
ziniao site list | show <id> | enable | disable <id> | fork <src> [<dst>]
ziniao site add <git-url> | update [<name>] | remove <name> | repos
ziniao site skills [<name>]
ziniao skill list | install <name> [-a cursor] | remove <name> | installed | update | agents

# Batch, recording, emulation
echo '[{"command":"navigate","args":{"url":"..."}}]' | ziniao batch run [--bail]
ziniao rec start | stop [--name <n>] [--force] | replay <n> [--reuse-tab] [--no-auto-session] | list | view <n> [--metadata-only] [--full] [-o file] | status | delete <n>   # replay: new tab; auto-reconnect from recording if daemon has no session
ziniao emulate --device "iPhone 14"       # Or --width W --height H

# Cleanup
ziniao close-store <id>
ziniao chrome close <id>
ziniao quit                               # Stop daemon
```

## Global Flags

**Placement:** Global flags (`--json`, `--store`, …) apply to the **root** CLI and must appear **before** the subcommand. Wrong: `ziniao list-stores --json` → `No such option: --json`. Right: `ziniao --json list-stores`. You can also set `ZINIAO_JSON=1` to avoid relying on flag order.


| Flag                   | Description                                                       |
| ---------------------- | ----------------------------------------------------------------- |
| `--store <id>`         | Target a Ziniao store (no session switch)                         |
| `--session <id>`       | Target any session (no switch); mutually exclusive with `--store` |
| `--json`               | JSON envelope: `{"success", "data", "error"}`                     |
| `--json-legacy`        | Raw daemon JSON, no envelope; for older scripts                   |
| `--content-boundaries` | Wrap page content with boundary markers (LLM safety)              |
| `--max-output <N>`     | Truncate snapshot/eval output (default 2000 chars; 0 = unlimited) |
| `--timeout <sec>`      | Override timeout (auto: 120s for slow cmds, 60s for others)       |


Env equivalents: `ZINIAO_JSON=1`, `ZINIAO_CONTENT_BOUNDARIES=1`, `ZINIAO_MAX_OUTPUT=N`.

```bash
# Parse JSON results under .data (--json before subcommand)
ACTIVE=$(ziniao --json session list | jq -r '.data.active')
ziniao --json is visible ".next" | jq -e '.data.visible'

# Content boundaries for LLM consumption
ziniao --json --content-boundaries snapshot
```

## Selector Lifecycle

Selectors resolve at execution time. After navigation or DOM changes, **re-snapshot before the next interaction**:

```bash
ziniao click "#submit"                    # May navigate or open modal
ziniao wait ".result"                     # Wait for new content
ziniao snapshot --interactive             # Get fresh selectors
ziniao click ".result a"                  # Now safe to use new selectors
```

For lists, use `ziniao get count` then `ziniao find nth` in a loop — each `find nth` resolves at run time.

## Common Patterns

### Multi-Store Batch

```bash
for store_id in store_001 store_002 store_003; do
    ziniao --store "$store_id" navigate "https://example.com"
    ziniao --store "$store_id" screenshot "${store_id}.png"
done
```

Never use `session switch` inside the loop; it mutates the daemon's global active session and can race with another agent.

### List Iteration

```bash
COUNT=$(ziniao --json get count ".item" | jq '.data.count')
for i in $(seq 0 $((COUNT - 1))); do
    ziniao find nth $i ".item a" click && ziniao back
done
```

### JavaScript Evaluation

Shell quoting can corrupt complex expressions. Keep it simple or use single quotes:

```bash
ziniao eval 'document.title'
ziniao eval 'document.querySelectorAll("img").length'
ziniao eval 'JSON.stringify(Array.from(document.querySelectorAll("tr")).map(r => r.textContent))'
ziniao eval --await 'fetch("/api/me").then(r => r.text())'   # Promise → resolved value
```

## Site Presets — 页面内请求模板

Site presets（站点预设）是在浏览器**活动标签页**内发起 HTTP 请求的声明式 JSON 模板，自动继承页面的 **Cookie / 登录态**，无需额外鉴权。适合已登录后台的 API 数据拉取。

### Transport Selection

- Default: `browser_fetch` — runs inside the targeted tab and reuses browser cookies, storage-derived headers, iframe context, and the browser/Ziniao network environment.
- Optional: `direct_http` (`--transport direct`) — uses an exported AuthSnapshot without opening/using the browser for the request. Only use for low-risk APIs that tolerate Python HTTP replay; it does **not** reuse the browser/Ziniao proxy, TLS fingerprint, or device context.
- Optional: `auto` — probes `direct_http` only for safe methods (`GET` / `HEAD` / `OPTIONS`) and falls back to `browser_fetch`. Non-idempotent methods (`POST`, `PATCH`, etc.) skip direct probing to avoid duplicate side effects.

For direct/auto, first export a snapshot from the correct session and origin:

```bash
ziniao --session "$SID" cookie-vault export -o auth.json --site target-site
ziniao --session "$SID" network fetch "https://api.example.com/me" --transport auto --auth-snapshot auth.json
```

Redacted snapshots are shareable documentation artefacts and are rejected by `import` / `direct_http`. `cookie-vault import` writes storage only when the current tab origin matches the snapshot `page_url` unless `--allow-origin-mismatch` is explicitly passed.

### 三层来源


| 优先级      | 路径                                            | 说明                    |
| -------- | --------------------------------------------- | --------------------- |
| 1 — 用户覆盖 | `~/.ziniao/sites/<site>/<action>.json`        | `site fork` 生成，优先级最高  |
| 2 — 远程仓库 | `~/.ziniao/repos/<repo>/<site>/<action>.json` | `site add` 添加的 Git 仓库 |
| 3 — 内置   | `ziniao_mcp/sites/<site>/<action>.json`       | 随包发布                  |


### 快速使用

```bash
ziniao site list                                       # 列出所有可用预设
ziniao site show rakuten/rpp-search                    # 查看变量、鉴权、用法
ziniao rakuten rpp-search -V start_date=2026-03-01 -V end_date=2026-03-07
ziniao rakuten rpp-search -V start_date=... -V end_date=... --all -o out.json  # 自动翻页
```

### 更新预设与技能（常用）

```bash
ziniao site update                                     # 更新所有仓库预设 + 自动刷新已安装 skill symlink
```

`site update` 是保持预设和技能同步的核心命令：拉取远程仓库最新 JSON 模板，同时自动刷新所有已安装 skill 的 symlink/junction，无需手动 `skill update`。

### 站点管理命令

```bash
ziniao site list                                       # 列出所有预设（含 mode/auth/source 标签）
ziniao site show <site>/<action> [--raw]               # 查看详情 / 原始 JSON
ziniao site enable | disable <site>/<action>           # 启用 / 禁用（禁用后快捷方式不可见，-p 仍可用）
ziniao site fork <src> [<dst>] [--force]               # 复制到 ~/.ziniao/sites/ 供自定义编辑
```

### 站点仓库（Site Repos）

通过 Git 仓库共享和更新站点预设，无需手动复制文件：

```bash
ziniao site add https://github.com/org/ziniao-sites.git [--name <n>] [--branch main]
ziniao site remove <name>                              # 移除仓库
ziniao site repos                                      # 列出已注册仓库
```

### 鉴权类型（auth）


| `auth.type` | 行为                                       | 适用场景                |
| ----------- | ---------------------------------------- | ------------------- |
| `cookie`    | `credentials: 'include'`，仅带 Cookie       | 大多数后台 API           |
| `xsrf`      | Cookie + 从 Cookie 读取 CSRF 令牌注入 Header    | Django / Spring 等框架 |
| `token`     | Bearer / 自定义令牌（从 localStorage / eval 获取） | SPA + JWT           |
| `none`      | 无鉴权                                      | 公开 API              |


### 预设模板关键字段


| 字段                       | 作用                                            |
| ------------------------ | --------------------------------------------- |
| `navigate_url`           | 执行前若不在该页则自动导航                                 |
| `mode`                   | `fetch`（默认）或 `js`（自定义脚本）                      |
| `auth`                   | 鉴权声明（`type` + `hint`）                         |
| `header_inject`          | 声明式 Header 注入规则（cookie / localStorage / eval） |
| `vars`                   | 模板变量定义，CLI 用 `-V name=value` 传入               |
| `pagination`             | 分页配置（`--all` 自动翻页合并）                          |
| `output_decode_encoding` | 默认 `--decode-encoding`（如日文 CSV 用 `cp932`）     |


### 底层命令（调试用）

```bash
ziniao network fetch -p <preset> -V k=v ...            # 指定预设模板
ziniao network fetch -f ./my-request.json              # 指定本地 JSON 文件
ziniao network fetch <url> -X POST -d '{"q":1}'        # 直接请求
ziniao network fetch --script '<expr>' -d '<body>'     # 页面内脚本模式
ziniao network fetch-save --filter "reports" -o tpl.json  # 从抓包生成模板
```

### 响应保存与编码（`-o`）

页面侧用 `**arrayBuffer()` → Base64** 回传 `body_b64`，避免编码损坏。`-o` 默认写入原始字节；加 `--decode-encoding cp932` 可先解码再用 `--output-encoding utf-8` 落盘。预设根字段 `output_decode_encoding` 提供默认值。

## Skills — AI 代理技能

Skills 是 `**SKILL.md`** 文件，为 AI 代理（Cursor / Trae / Claude 等）提供站点操作上下文知识。通过 symlink/junction 安装到代理的全局技能目录。

### 三层来源（`skill list` 显示 `[source]` 标签）


| 优先级      | 路径                                                     | 说明                            |
| -------- | ------------------------------------------------------ | ----------------------------- |
| 1 — 包内置  | `<package_root>/skills/<name>/SKILL.md`                | 随 `uv tool install ziniao` 安装 |
| 2 — 远程仓库 | `~/.ziniao/repos/<repo>/<site>/skills/<name>/SKILL.md` | `site add` 添加                 |
| 3 — 用户覆盖 | `~/.ziniao/skills/<name>/SKILL.md`                     | 手动放置                          |


### 命令

```bash
ziniao skill list                                      # 列出所有可发现的技能（含 [source] 标签）
ziniao skill install <name> [--agent cursor]           # 安装到代理目录（默认 cursor）
ziniao skill remove <name> [--agent trae]              # 移除（仅删 symlink，不影响源文件）
ziniao skill installed [--agent all]                   # 查看已安装
ziniao skill update [--agent all]                      # 刷新已有 + 自动安装新增 + 清理孤儿 symlink
ziniao skill agents                                    # 查看支持的代理及目录
```

支持的代理：`cursor`、`trae`、`claude`、`openclaw`、`copilot`、`windsurf`、`codex`。

### 典型流程

```bash
uv tool install ziniao          # 包含内置 skills
ziniao skill list               # 查看 [builtin] / [repo] / [local]
ziniao skill install ziniao-cli # 安装到代理
ziniao skill update             # 包升级后刷新；自动安装新增、清理孤儿
```

## Install & PATH

```bash
uv tool install ziniao               # install
ziniao update                        # upgrade from PyPI
ziniao update --git                  # upgrade from GitHub main
```

If `ziniao` is not recognized: run `uv tool dir` to find the bin directory, add it to PATH, reopen terminal.

## Troubleshooting


| Problem                                          | Solution                                                                                                                                                                                                  |
| ------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| First time setup                                 | `ziniao config init`                                                                                                                                                                                      |
| Daemon won't start                               | Check `~/.ziniao/daemon.log`                                                                                                                                                                              |
| Connection refused                               | `ziniao quit` then retry                                                                                                                                                                                  |
| `list-stores` / 店铺：WebDriver 端口未开放               | `ziniao store start-client`                                                                                                                                                                               |
| `No such option: --json`                         | Use `ziniao --json <command>` (global flags before subcommand), or `ZINIAO_JSON=1`                                                                                                                        |
| `store start-client` / first command seems stuck | Normal on first run: daemon startup + WebDriver client can take tens of seconds; see `~/.ziniao/daemon.log`                                                                                               |
| Edited `~/.ziniao/.env` but old values persist   | Restart daemon: `ziniao quit` then run any command. Also: variables **already in** `os.environ` (system / user env) are **not** overridden by `.env`; unset them or rename keys. See `ziniao config show` |
| Store not found                                  | `ziniao list-stores` to check IDs                                                                                                                                                                         |
| Timeout                                          | `--timeout 120` or `ziniao wait` before next step                                                                                                                                                         |


## References


| File                                                                         | Content                                                              |
| ---------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| [references/commands.md](references/commands.md)                             | Full command reference with all options                              |
| [references/configuration.md](references/configuration.md)                   | YAML/env paths, precedence, MCP setup                                |
| [references/site-fetch-and-presets.md](references/site-fetch-and-presets.md) | Page-context fetch, site presets, auth/pagination, MCP `page_fetch`  |
| [references/page-fetch-auth.md](references/page-fetch-auth.md)               | Header injection (`header_inject`): usage, implementation, extension |


