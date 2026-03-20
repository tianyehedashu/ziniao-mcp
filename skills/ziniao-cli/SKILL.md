---
name: ziniao-cli
description: Browser automation for multi-store sellers and Chrome. Use when the user needs to open stores, navigate pages, fill forms, click buttons, take screenshots, extract data, intercept network requests, or automate any browser task. Triggers include "open a store", "open a website", "fill out a form", "click a button", "take a screenshot", "scrape data", "switch session", "multi-store batch", "browser automation", or any Ziniao/Chrome automation request.
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

Ziniao uses **CSS selectors** (not refs like `@e1`). After `snapshot --interactive`, read the HTML to pick selectors for the next command.

```bash
ziniao open-store my-store-001                          # or: ziniao launch --url <url>
ziniao navigate "https://sellercentral.amazon.com/inventory"
ziniao wait ".inventory-table"
ziniao snapshot --interactive                            # read HTML, pick CSS selectors
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
| **Chrome (connect)** | `ziniao connect <port>` | Existing Chrome, disconnect only on close |

Setting `CHROME_USER_DATA` enables state reuse (cookies, localStorage, extensions persist).

## Key Commands

> Full reference: [references/commands.md](references/commands.md)

```bash
# Connect
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
ziniao eval "<js>"
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

# Batch, recording, emulation
echo '[{"command":"navigate","args":{"url":"..."}}]' | ziniao batch run [--bail]
ziniao rec start | stop --name <n> | replay <n> | list | delete <n>
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
```

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
| Store not found | `ziniao list-stores` to check IDs |
| Timeout | `--timeout 120` or `ziniao wait` before next step |

## References

| File | Content |
|------|---------|
| [references/commands.md](references/commands.md) | Full command reference with all options |
| [references/configuration.md](references/configuration.md) | YAML/env paths, precedence, MCP setup |
