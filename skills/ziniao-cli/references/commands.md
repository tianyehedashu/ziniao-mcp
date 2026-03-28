# Ziniao CLI — Command Reference

Full command reference. For workflow and patterns see [SKILL.md](../SKILL.md).

## Store & Chrome

| Command | Description |
|---------|-------------|
| `ziniao list-stores` | List Ziniao stores |
| `ziniao list-stores --opened-only` | Only opened stores |
| `ziniao open-store <id>` | Open store and connect CDP |
| `ziniao close-store <id>` | Close store |
| `ziniao store start-client` | Start Ziniao client (WebDriver / HTTP) |
| `ziniao store stop-client` | Stop Ziniao client |
| `ziniao launch [--name n] [--url u]` | Launch Chrome |
| `ziniao launch --headless` | Launch headless Chrome |
| `ziniao connect <port> [--name n]` | Connect to Chrome by CDP port |
| `ziniao chrome list` | List Chrome sessions |
| `ziniao chrome close <id>` | Close Chrome session |

## Session

| Command | Description |
|---------|-------------|
| `ziniao session list` | List all sessions (stores + Chrome) |
| `ziniao session switch <id>` | Switch active session |
| `ziniao session info <id>` | Session details |

## Navigation

| Command | Description |
|---------|-------------|
| `ziniao navigate <url>` | Go to URL |
| `ziniao back` | Back |
| `ziniao forward` | Forward |
| `ziniao reload` | Reload |
| `ziniao tab list` | List tabs |
| `ziniao tab new --url <url>` | New tab |
| `ziniao tab switch -i <index>` | Switch tab by index |
| `ziniao wait <selector> [--timeout N]` | Wait for element (timeout ms) |

## Interaction

| Command | Description |
|---------|-------------|
| `ziniao click <selector>` | Click |
| `ziniao dblclick <selector>` | Double-click |
| `ziniao fill <selector> <value>` | Fill input |
| `ziniao type <text> [-s <selector>]` | Type text (optional selector) |
| `ziniao press <key>` | Press key |
| `ziniao hover <selector>` | Hover |
| `ziniao drag <source> <target>` | Drag and drop |
| `ziniao act focus <selector>` | Focus |
| `ziniao act select <selector> <value>` | Select option |
| `ziniao act check <selector>` | Check checkbox |
| `ziniao act uncheck <selector>` | Uncheck |
| `ziniao act keydown <key>` | Key down |
| `ziniao act keyup <key>` | Key up |

## Get & Find

| Command | Description |
|---------|-------------|
| `ziniao get text <selector>` | Element text |
| `ziniao get html <selector>` | innerHTML |
| `ziniao get value <selector>` | Input value |
| `ziniao get attr <selector> <attr>` | Attribute value |
| `ziniao get count <selector>` | Count matches |
| `ziniao title` | Page title |
| `ziniao url` | Current URL |
| `ziniao find first <selector> [action]` | First match + action |
| `ziniao find last <selector> [action]` | Last match + action |
| `ziniao find nth <n> <selector> [action]` | Nth match (0-based) + action |
| `ziniao find text "<text>" [action]` | By text + action |
| `ziniao find role <role> [action]` | By ARIA role + action |

## Check & Scroll

| Command | Description |
|---------|-------------|
| `ziniao is visible <selector>` | Visible? |
| `ziniao is enabled <selector>` | Enabled? |
| `ziniao is checked <selector>` | Checked? |
| `ziniao scroll down [pixels]` | Scroll down (default 300) |
| `ziniao scroll up [pixels]` | Scroll up |
| `ziniao scrollinto <selector>` | Scroll into view |

## Inspect & Capture

| Command | Description |
|---------|-------------|
| `ziniao snapshot` | Full HTML |
| `ziniao snapshot --interactive` | Interactive elements only |
| `ziniao snapshot --compact` | Compact output |
| `ziniao snapshot -s <selector>` | Scope to selector |
| `ziniao screenshot [file]` | Screenshot |
| `ziniao screenshot <file> -s <selector>` | Screenshot element |
| `ziniao eval "<js>" [--await]` | Run JavaScript; `--await` waits for Promise (main doc + iframe) |
| `ziniao info console` | Console messages |
| `ziniao info network` | Network requests |
| `ziniao info errors` | JS errors |
| `ziniao info highlight <selector>` | Highlight element |

## Network

| Command | Description |
|---------|-------------|
| `ziniao network route "<pattern>" [--abort] [--body ...] [--status N]` | Add route (glob `*`) |
| `ziniao network unroute [pattern]` | Remove route(s); omit = all |
| `ziniao network routes` | List routes |
| `ziniao network list [--filter url] [--clear]` | List/clear requests |
| `ziniao network har-start` | Start HAR recording |
| `ziniao network har-stop [path]` | Stop and save HAR |
| `ziniao network fetch [URL] [-p preset] [-f file] [--script …] [-X METHOD] [-d JSON] [-H "K:V"]… [--var K=V]… [--page N] [--all] [-o file]` | HTTP in **page context** (cookies; optional `xsrf_cookie` in JSON) |
| `ziniao network fetch-save [--id N \| --filter SUBSTR] -o file [--full-headers] [--as-preset]` | Build JSON template from captured request |

## Site presets

JSON templates under `ziniao_mcp/sites/` and `~/.ziniao/sites/<site>/`. Shortcuts: **`ziniao <site> <action>`** (same options as fetch for vars/page/all/output).

| Command | Description |
|---------|-------------|
| `ziniao site list` | List presets (`auth`, `paginated` flags in table) |
| `ziniao site show <site/action-id>` | Variables, auth hint, pagination, usage |
| `ziniao site enable <id>` / `disable <id>` | Toggle shortcut registration (`~/.ziniao/sites.json`) |

## Cookies, Storage, Clipboard, Mouse

| Command | Description |
|---------|-------------|
| `ziniao info cookies` | List cookies |
| `ziniao info cookies set --name k --value v` | Set cookie |
| `ziniao info cookies clear` | Clear cookies |
| `ziniao info storage local get` | localStorage |
| `ziniao info storage local set -k key -v val` | Set localStorage |
| `ziniao info storage session get` | sessionStorage |
| `ziniao info clipboard read` | Read clipboard |
| `ziniao info clipboard write --text "..."` | Write clipboard |
| `ziniao mouse move <x> <y>` | Move mouse |
| `ziniao mouse down [button]` | Mouse down |
| `ziniao mouse up [button]` | Mouse up |
| `ziniao mouse wheel <dy> [dx]` | Wheel |

## Batch, Recording, Emulation, Lifecycle

| Command | Description |
|---------|-------------|
| `echo '[{"command":...,"args":...}]' \| ziniao batch run` | Run batch JSON |
| `ziniao batch run --bail` | Stop on first error |
| `ziniao rec start [--engine dom2\|legacy] …` (default **dom2**) | Start recording |
| `ziniao rec stop [--name <name>] [--emit nodriver,playwright] [--redact-secrets]` | Stop and save |
| `ziniao rec status` | Show engine, scope, buffer size while recording |
| `ziniao rec replay <name>` | Replay |
| `ziniao rec list` | List recordings |
| `ziniao emulate --device "iPhone 14"` | Device emulation |
| `ziniao emulate --width W --height H` | Viewport |
| `ziniao serve [--config ...] [--company ...] [--username ...]` | Start MCP server |
| `ziniao quit` | Stop daemon |

More detail: [docs/site-fetch-and-presets.md](../../docs/site-fetch-and-presets.md) (page-context fetch, `auth` / `pagination` in JSON, MCP `page_fetch`).

## Global flags

- `--store <id>` — Target store without switching
- `--session <id>` — Target session (store or Chrome) without switching
- `--json` — JSON output
- `--timeout <sec>` — Command timeout (default 60)
