---
name: ziniao-cli
description: Browser automation for multi-store sellers and Chrome. Use when the user needs to open stores, navigate pages, fill forms, click buttons, take screenshots, extract data, intercept network requests, call logged-in APIs from the page (site presets / network fetch / page_fetch), or automate any browser task. Triggers include "open a store", "open a website", "fill out a form", "click a button", "take a screenshot", "scrape data", "switch session", "multi-store batch", "browser automation", "fetch API with cookies", "site preset", or any Ziniao/Chrome automation request.
allowed-tools: Bash(ziniao:*)
---

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

Use **CSS selectors** with `click` / `fill` / `wait` (valid for `document.querySelector`). Column **`ref` (`@e0` …)** in `snapshot --interactive` is **only a row label** — **do not** pass `@eN` as a selector.

**Inspect → pick selectors:**

- **`ziniao snapshot --interactive`** — table with a **Selector** column (auto-computed, unique CSS selector like `#id` or `[name="…"]`). Copy the selector directly into `click` / `fill` / `wait`.
- **`ziniao snapshot`** or **`ziniao snapshot --compact`** — full HTML when you need classes/structure or elements the interactive table didn't cover.

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

| Backend | Connect | Use case |
|---------|---------|----------|
| **Ziniao store** | `ziniao open-store <id>` | Multi-store seller workflows, anti-detection |
| **Chrome (launch)** | `ziniao launch` | New Chrome, ziniao owns the process |
| **Chrome (connect)** | `ziniao connect <port>` | Chrome already running with `--remote-debugging-port`; `chrome close` detaches ziniao only |

Setting `CHROME_USER_DATA` enables state reuse (cookies, localStorage, extensions persist).

Control is **CDP** on **127.0.0.1** (remote browser → port-forward first). Commands hit the **active session** and **active tab** unless you use **`session list|switch`**, **`tab list|switch -i N`**, or one-shot **`--store` / `--session`**. For Ziniao shops—even if the window was opened in the desktop app—use **`open-store <id>`**, not **`connect`**. **Stealth** (when enabled): **`launch`** / **`open-store`** patch every open tab’s current document; **`connect`** registers the script on all tabs but only runs the heavy **evaluate** on the **active** tab (others pick it up on next navigation).

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
ziniao network fetch --script '<expr using __BODY__>' -d '{"k":1}'
ziniao network fetch-save [--id N | --filter SUBSTR] -o template.json [--as-preset]

# Site presets (shortcuts: ziniao <site> <action> — templates under ziniao_mcp/sites/ and ~/.ziniao/sites/)
ziniao site list | show <id> [--raw] | enable <id> | disable <id>
ziniao site fork <id> [<new_id>] [--force]        # copy preset to ~/.ziniao/sites/ for editing
# Example: ziniao rakuten rpp-search -V start_date=2026-03-01 -V end_date=2026-03-07 [--page N] [--all] [-o out]
# CSV/binary: ziniao rakuten reviews-csv -o reviews.csv   # preset output_decode_encoding=cp932

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

| Flag | Description |
|------|-------------|
| `--store <id>` | Target a Ziniao store (no session switch) |
| `--session <id>` | Target any session (no switch); mutually exclusive with `--store` |
| `--json` | JSON envelope: `{"success", "data", "error"}` |
| `--json-legacy` | Raw daemon JSON, no envelope; for older scripts |
| `--content-boundaries` | Wrap page content with boundary markers (LLM safety) |
| `--max-output <N>` | Truncate snapshot/eval output (default 2000 chars; 0 = unlimited) |
| `--timeout <sec>` | Override timeout (auto: 120s for slow cmds, 60s for others) |

Env equivalents: `ZINIAO_JSON=1`, `ZINIAO_CONTENT_BOUNDARIES=1`, `ZINIAO_MAX_OUTPUT=N`.

```bash
# Parse JSON results under .data
ACTIVE=$(ziniao session list --json | jq -r '.data.active')
ziniao is visible ".next" --json | jq -e '.data.visible'

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

### List Iteration

```bash
COUNT=$(ziniao get count ".item" --json | jq '.data.count')
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

### Logged-in API from the page (site presets)

Use when the site expects **session cookies** (and sometimes **XSRF**). Prefer **`ziniao <site> <action>`** over `network fetch -p` for brevity. Templates may declare **`auth`** / **`pagination`** for hints and **`--all`**. With **`-o`**, responses use **`body_b64`** end-to-end; use **`--decode-encoding`** / preset **`output_decode_encoding`** for Shift_JIS/CP932 CSV. See **[../../docs/site-fetch-and-presets.md](../../docs/site-fetch-and-presets.md)**.

## Install & PATH

```bash
uv tool install ziniao               # install
ziniao update                        # upgrade from PyPI
ziniao update --git                  # upgrade from GitHub main
```

If `ziniao` is not recognized: run `uv tool dir` to find the bin directory, add it to PATH, reopen terminal.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| First time setup | `ziniao config init` |
| Daemon won't start | Check `~/.ziniao/daemon.log` |
| Connection refused | `ziniao quit` then retry |
| `list-stores` / 店铺：WebDriver 端口未开放 | `ziniao store start-client` |
| Store not found | `ziniao list-stores` to check IDs |
| Timeout | `--timeout 120` or `ziniao wait` before next step |

## References

| File | Content |
|------|---------|
| [references/commands.md](references/commands.md) | Full command reference with all options |
| [references/configuration.md](references/configuration.md) | YAML/env paths, precedence, MCP setup |
| [../../docs/site-fetch-and-presets.md](../../docs/site-fetch-and-presets.md) | Page-context fetch, site presets, auth/pagination, MCP `page_fetch` |
