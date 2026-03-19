---
name: ziniao-cli
description: Command-line interface for automating Ziniao stores and Chrome browsers via CDP. Use when the user needs to manage multi-store sessions, automate page interactions (click, fill, type), take screenshots, record HAR, intercept network requests, or chain browser operations from the terminal. Triggers include "open a store", "switch session", "screenshot", "click a button", "fill a form", "run ziniao commands", "browser automation", "multi-store batch", or any CLI-based Ziniao/Chrome automation task.
allowed-tools: Bash(ziniao:*)
---

# Ziniao CLI — Browser Automation from Terminal

The `ziniao` CLI talks to a background daemon that manages browser sessions (Ziniao stores and Chrome instances) via CDP. Install with `pip install ziniao-mcp`, then use the single `ziniao` command for everything: CLI automation (`ziniao click`, `ziniao fill`, ...) and MCP server (`ziniao serve`). The daemon starts automatically on first CLI command. If your shell reports **"ziniao" is not recognized**, see [Install & PATH](#install--path) below. Ziniao sessions use built-in **stealth and anti-detection** (JS masking + human-like input); Chrome sessions use the same stack when launched via `ziniao launch`.

## Core Workflow

Every browser automation follows this pattern:

1. **Connect**: `ziniao open-store <id>` (Ziniao) or `ziniao launch` (Chrome)
2. **Navigate**: `ziniao navigate <url>`
3. **Inspect**: `ziniao snapshot` (page HTML) or `ziniao snapshot --interactive` (interactive elements only)
4. **Interact**: `ziniao click`, `ziniao fill`, `ziniao type` (use CSS selectors or `ziniao find nth` for lists)
5. **Verify**: `ziniao screenshot`, `ziniao get text`, `ziniao is visible`

```bash
ziniao open-store my-store-001
ziniao navigate "https://sellercentral.amazon.com/inventory"
ziniao wait ".inventory-table"
ziniao snapshot --interactive
ziniao click "#edit-btn"
ziniao fill "#price-input" "29.99"
ziniao screenshot after-edit.png
```

## Command Chaining

Commands share a persistent daemon, so chaining with `&&` is safe and avoids repeated daemon wake-up.

```bash
ziniao navigate "https://example.com" && ziniao wait ".loaded" && ziniao screenshot page.png
ziniao fill "#email" "user@test.com" && ziniao fill "#pass" "secret" && ziniao click "#login"
```

**When to chain:** Use `&&` when you don't need to read the output of an intermediate command (e.g. navigate + wait + screenshot). Run commands separately when you need to parse output first (e.g. `ziniao get count ".item" --json` then loop with `ziniao find nth $i ".item" click`).

## Ziniao Stores vs Chrome Sessions

| Backend | How to connect | Typical use |
|--------|----------------|-------------|
| **Ziniao store** | `ziniao open-store <store_id>` | Multi-store seller workflows, anti-detection, existing Ziniao client |
| **Chrome** | `ziniao launch` or `ziniao connect <port>` | Local Chrome, debugging, headless runs |

Use `ziniao session list` to see all sessions (stores + Chrome). Use `--store <id>` or `--session <id>` to target a session without switching the active one.

## Store Login & Multi-Store Workflows

For seller portals (e.g. Seller Central), open the store once and reuse the same session:

```bash
# Single store: login and extract
ziniao open-store us-store-001
ziniao navigate "https://sellercentral.amazon.com/business-reports"
ziniao wait ".report-table"
ziniao eval "JSON.stringify(Array.from(document.querySelectorAll('tr')).map(r => r.textContent))"
```

**Batch multiple stores** without switching the active session:

```bash
for store_id in store_001 store_002 store_003; do
    ziniao --store "$store_id" navigate "https://sellercentral.amazon.com/inventory"
    ziniao --store "$store_id" wait ".inventory-table"
    ziniao --store "$store_id" screenshot "${store_id}-inventory.png"
done
```

**Batch with JSON (e.g. PowerShell):**

```bash
ziniao session list --json | jq -r '.sessions[].session_id' | while read id; do
    ziniao --session "$id" screenshot "${id}-shot.png"
done
```

## Essential Commands

```bash
# Store management
ziniao list-stores                    # List Ziniao stores
ziniao list-stores --opened-only      # Only opened stores
ziniao open-store <id>                # Open store + connect CDP
ziniao close-store <id>               # Close store

# Chrome management
ziniao launch [--name n] [--url u]   # Launch Chrome
ziniao launch --headless             # Headless Chrome
ziniao connect <port> [--name n]      # Connect to running Chrome (CDP port)
ziniao chrome list                   # List Chrome sessions
ziniao chrome close <id>              # Close Chrome session

# Session control
ziniao session list                   # All sessions (stores + Chrome)
ziniao session switch <id>            # Switch active session
ziniao session info <id>              # Session details

# Navigation
ziniao navigate <url>                 # Go to URL
ziniao back                           # Back
ziniao forward                        # Forward
ziniao reload                         # Reload
ziniao tab list                       # List tabs
ziniao tab new --url <url>            # New tab
ziniao tab switch -i 2                # Switch to tab index 2
ziniao wait <selector> [--timeout N]  # Wait for element (ms)

# Page interaction
ziniao click <selector>               # Click
ziniao dblclick <selector>            # Double-click
ziniao fill <selector> <value>        # Fill input (clear then type)
ziniao type <text> [-s <selector>]    # Type char-by-char (optional selector)
ziniao press Enter                    # Press key
ziniao hover <selector>               # Hover
ziniao drag <source> <target>         # Drag and drop
ziniao act focus <selector>           # Focus
ziniao act select <selector> <value>  # Select option
ziniao act check <selector>           # Check checkbox
ziniao act uncheck <selector>         # Uncheck
ziniao act keydown Shift              # Key down
ziniao act keyup Shift                # Key up

# Get element/page info
ziniao get text <selector>            # Text content
ziniao get html <selector>            # innerHTML
ziniao get value <selector>           # Input value
ziniao get attr <selector> <attr>      # Attribute (e.g. href)
ziniao get count <selector>           # Count matches
ziniao title                          # Page title
ziniao url                            # Current URL

# Find (semantic / ordinal)
ziniao find first <selector> [action] # First match + optional action
ziniao find last <selector> [action]  # Last match
ziniao find nth <n> <selector> [action] # Nth match (0-based) + action
ziniao find text "Submit" [action]     # By text content
ziniao find role button [action]      # By ARIA role

# Check state
ziniao is visible <selector>           # Visible?
ziniao is enabled <selector>          # Enabled?
ziniao is checked <selector>         # Checked? (checkbox)

# Scroll
ziniao scroll down [pixels]           # Down (default 300)
ziniao scroll up [pixels]             # Up
ziniao scrollinto <selector>          # Scroll element into view

# Page inspection
ziniao snapshot                       # Full HTML
ziniao snapshot --interactive         # Interactive elements only
ziniao snapshot --compact            # Compact (no scripts/styles)
ziniao snapshot -s "#section"         # Scope to selector
ziniao screenshot [file]              # Screenshot (file optional)
ziniao screenshot shot.png -s "#el"   # Screenshot element
ziniao eval "document.title"         # Run JavaScript
ziniao info console                   # Console messages
ziniao info network                   # Network requests
ziniao info errors                    # JS errors
ziniao info highlight <selector>     # Highlight element

# Network interception & HAR
ziniao network route "<pattern>" [--abort] [--body ...] [--status N]  # Intercept (glob *)
ziniao network unroute [pattern]      # Remove route(s); omit pattern = all
ziniao network routes                 # List active routes
ziniao network list [--filter url] [--clear]  # List/clear captured requests
ziniao network har-start              # Start HAR recording
ziniao network har-stop [path]        # Stop and save HAR (default ~/.ziniao/har/)

# Cookies & storage
ziniao info cookies                   # List cookies
ziniao info cookies set --name k --value v
ziniao info cookies clear
ziniao info storage local get
ziniao info storage local set -k key -v val
ziniao info storage session get
ziniao info clipboard read
ziniao info clipboard write --text "hello"

# Mouse
ziniao mouse move <x> <y>
ziniao mouse down [button]
ziniao mouse up [button]
ziniao mouse wheel <dy> [dx]

# Batch
echo '[{"command":"navigate","args":{"url":"https://example.com"}}]' | ziniao batch run
echo '[...]' | ziniao batch run --bail   # Stop on first error

# Recording
ziniao rec start
ziniao rec stop --name my-flow
ziniao rec replay my-flow
ziniao rec list

# Emulation
ziniao emulate --device "iPhone 14"
ziniao emulate --width 1920 --height 1080

# MCP server
ziniao serve                           # Start MCP server
ziniao serve --config config.yaml     # With config file
ziniao serve --company x --username y  # With credentials

# Lifecycle
ziniao quit                            # Stop daemon + cleanup
```

## JSON Output Mode

Use `--json` for machine-readable output and scripting:

```bash
ziniao session list --json
# {"active":"store_A","sessions":[...],"count":2}

ACTIVE=$(ziniao session list --json | jq -r '.active')
ziniao is visible ".next" --json | jq -e '.visible'
```

## Global Flags

| Flag | Description |
|------|-------------|
| `--store <id>` | Target a Ziniao store (no session switch) |
| `--session <id>` | Target any session — store or Chrome (no switch) |
| `--json` | Output raw JSON |
| `--timeout <sec>` | Command timeout (default 60) |

`--store` and `--session` are mutually exclusive.

## Session Management and Cleanup

Use named sessions to avoid conflicts when running multiple automations:

```bash
ziniao --session store_A screenshot a.png
ziniao --session chrome-9222 eval "document.title"
ziniao session list
```

Always close stores or Chrome when done to free resources:

```bash
ziniao close-store my-store-001
ziniao chrome close <id>
ziniao quit   # Stop daemon (clears stale PID)
```

If the daemon is stuck, `ziniao quit` then retry; check `~/.ziniao/daemon.log` for errors.

## Selector Lifecycle

Selectors are evaluated at command execution time. After navigation or dynamic DOM updates, re-query or re-snapshot:

- After `ziniao click` that navigates or opens a modal, take a new `ziniao snapshot` or `ziniao wait <selector>` before next interaction.
- For lists, use `ziniao get count ".item"` then `ziniao find nth $i ".item" click` in a loop; each `find nth` resolves at run time.

## Timeouts and Slow Pages

Default command timeout is 60 seconds. Override with `--timeout`:

```bash
ziniao wait ".slow-widget" --timeout 120
ziniao navigate "https://slow.example.com" --timeout 90
```

For slow pages, use `ziniao wait <selector>` after navigate so the next command runs only when the element is ready.

## Stealth & Anti-Detection (Ziniao)

When using **Ziniao stores**, the daemon applies:

- **JS environment masking**: `navigator.webdriver`, plugins, and other detection vectors are patched via CDP before page load.
- **Human-like behavior**: click/fill/type/hover use randomized delays and Bezier mouse movement when stealth is enabled.

This applies to all interactions through the CLI (and MCP) for Ziniao-backed sessions. Chrome sessions launched with `ziniao launch` get the same treatment. To rely on it, use Ziniao stores or `ziniao launch` rather than a raw Chrome started outside ziniao.

## Common Patterns

### List Items — Click First N with find nth

```bash
ziniao navigate "https://example.com/products"
ziniao wait ".product-card"
COUNT=$(ziniao get count ".product-card" --json | jq '.count')
for i in $(seq 0 $((COUNT < 10 ? COUNT - 1 : 9))); do
    ziniao find nth $i ".product-card a" click
    ziniao back
done
```

### Pagination Loop

```bash
while true; do
    ziniao snapshot --interactive
    ziniao is visible ".next-page" --json | jq -e '.visible' || break
    ziniao click ".next-page"
    ziniao wait ".loaded"
done
```

### Batch Execution (JSON)

```bash
echo '[
  {"command": "navigate", "args": {"url": "https://example.com"}},
  {"command": "wait", "args": {"selector": ".loaded"}},
  {"command": "get_title", "args": {}},
  {"command": "screenshot", "args": {}}
]' | ziniao batch run --json
```

### Network Mock / HAR

```bash
# Block images
ziniao network route "*.png" --abort
ziniao network route "*ads*" --abort

# Mock API
ziniao network route "*/api/config" --body '{"debug":true}' --content-type application/json

# Record HAR
ziniao network har-start
ziniao navigate "https://example.com"
ziniao click "#submit"
ziniao network har-stop ./session.har
ziniao network har-stop   # or save to default ~/.ziniao/har/
```

### Record and Replay

```bash
ziniao rec start
# ... interact in browser ...
ziniao rec stop --name login-flow
ziniao rec replay login-flow --speed 2.0
ziniao rec list
```

## Install & PATH

```bash
pip install ziniao-mcp
```

If **`ziniao` is not recognized** after install, the Python Scripts directory is not on PATH:

1. **Add Scripts to PATH**: pip prints the directory (e.g. `...\Python313\Scripts`). Add it to your user PATH, then reopen the terminal.
2. **Run via module**: `python -m ziniao_mcp.cli --help`
3. **From source**: in the project repo run `uv run ziniao --help` or `pip install -e .`.

## Troubleshooting

| Problem | Solution |
|--------|----------|
| Daemon won't start | Check `~/.ziniao/daemon.log` |
| Connection refused | `ziniao quit` then retry (clears stale PID) |
| Store not found | `ziniao list-stores` to check IDs |
| CDP connection lost | `ziniao close-store <id>` then `ziniao open-store <id>` |
| Timeout | Use `--timeout 120` or `ziniao wait <selector>` before next step |

## Deep-Dive References

| Reference | When to Use |
|-----------|-------------|
| [references/commands.md](references/commands.md) | Full command reference with all options |
