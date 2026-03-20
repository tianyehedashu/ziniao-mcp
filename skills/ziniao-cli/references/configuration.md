# Configuration reference

Use this when you need file paths, precedence, MCP setup, or stealth keys beyond the quick snippets in `SKILL.md`.

## Where config lives

| Location | Scope |
|----------|--------|
| `~/.ziniao/config.yaml` | Global YAML |
| `config/config.yaml` (project root, cwd) | Repo-local YAML |
| `~/.ziniao/.env` | Loaded into the process environment (via `load_dotenv`) |

### Daemon, `ziniao serve`, and MCP (`_resolve_config`)

Used when the background daemon or MCP server starts. `load_dotenv()` runs first (so `.env` behaves like env vars).

1. **YAML file** — first existing path wins, in order: `./config/config.yaml` → `<package>/config/config.yaml` → `~/.ziniao/config.yaml`.
2. **Per-field merge** for Ziniao login / Chrome: **environment variable** → **`serve` CLI arguments** → **value from that YAML file**.

`stealth` comes from `ziniao.stealth` in the same YAML only (no separate env override in server code).

### `ziniao config show` (diagnostics)

The table printed by `ziniao config show` uses: **env** (including variables injected from `~/.ziniao/.env`) → **project `config/config.yaml`** → **`~/.ziniao/config.yaml`**. Use it to inspect paths and credentials sources; if something looks wrong, compare with the YAML file the daemon actually picked (first match in the list above).

Run `ziniao config show` after `cd` to the project you care about.

## Templates

From the skill root:

- [`../assets/config.example.yaml`](../assets/config.example.yaml) — full YAML (Ziniao + Chrome + `stealth` under `ziniao`).
- [`../assets/env.example`](../assets/env.example) — variable names for `.env` or MCP.

## MCP (Cursor / other clients)

1. Prefer `ziniao config init` then `ziniao config env --shell mcp` and paste the printed `env` block into your MCP server config.
2. Or set the same keys manually (see `env.example`): `ZINIAO_*`, `CHROME_*`.

After changing MCP env, restart the MCP server / Cursor MCP.

## YAML structure (Ziniao)

- `ziniao.browser`: `version` (`v5` | `v6`), `client_path`, `socket_port`
- `ziniao.user_info`: `company`, `username`, `password`
- `ziniao.stealth`: `enabled`, `js_patches`, `human_behavior`, `delay_range`, `typing_speed`, `mouse_movement`

Chrome-only workflows can omit or leave `ziniao` credentials empty.

## Security

- Do not commit `config.yaml` or `.env` with real passwords; add them to `.gitignore` if you keep secrets in-repo paths.
- Rotate credentials if they were ever committed or shared.

## Commands

| Command | Purpose |
|---------|---------|
| `ziniao config init` | Wizard → `~/.ziniao/config.yaml` + `.env` |
| `ziniao config set <dotted.key> <value>` | Update global config |
| `ziniao config path` | Show which files are used |
| `ziniao config env --shell mcp` | Export env block for MCP JSON |
