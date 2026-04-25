# Passive / Input-only Chrome automation

This document describes the **low-attach** path for high-risk sites (e.g. Shopee) versus the default **nodriver + stealth** path.

## Capability modes

| Mode | How | CDP scope |
|------|-----|-----------|
| **passive** | `ziniao chrome launch-passive`, `chrome passive-open`, `chrome passive-target list`, **`ziniao store passive-open`** | DevTools HTTP only to open/list tabs; no ziniao daemon attach (daemon may still proxy the Ziniao client open call), no nodriver, no stealth. |
| **input_only** | `ziniao chrome input click|type|key|scroll` | Short WebSocket per command; **only** `Input.dispatchMouseEvent`, `Input.dispatchKeyEvent`, `Input.insertText`. |
| **automation** | `ziniao chrome connect`, `ziniao store open`, `nav go`, `act click`, … | Full nodriver session via daemon (CDP Runtime attached). |
| **stealth** | Same as automation when stealth/listeners apply | May inject scripts / listeners; **not** recommended for hosts that treat CDP attachment as risk. |

## Recommended flow (high-risk hosts)

### A. Plain Chrome (no Ziniao client)

1. `ziniao chrome launch-passive [--port N] [--url URL]`
2. `ziniao chrome passive-open "https://…" --port N [--save-as mytab]`
3. `ziniao chrome input click --alias mytab --x … --y …`  
   (or `--port N --target <id>` after reading JSON from `passive-open`)

### B. Ziniao multi-store browser

1. `ziniao store passive-open <store_id>` — desktop client launches the store as
   usual, but the daemon stops at `debuggingPort`: **no `_connect_cdp`, no
   stealth JS, no `StoreSession`**. The CLI returns the live `cdp_port`,
   `launcher_page`, and a Shopee-style `policy_hint` when applicable.
2. `ziniao chrome passive-open "https://…" --port <cdp_port> --save-as mytab`
3. `ziniao chrome input click --alias mytab --x … --y …`

Aliases are stored in `~/.ziniao/passive_targets.json` and are **not**
`StoreSession` / `SessionManager` entries. Do **not** mix:

- A Ziniao store opened via `ziniao store passive-open` → continue with `chrome
  passive-open` / `chrome input` only. Calling `ziniao store open` afterwards
  will trigger the regular nodriver attach path against the same browser
  process and re-introduce the risk signals you were avoiding.
- A store opened via `ziniao store open` → use the standard `nav` / `act`
  commands; the passive CLI on the same port still works but offers no
  additional safety once nodriver has already attached.

## Site policy (built-ins + YAML)

**Built-in** defaults live in `ziniao_mcp/site_policy.py:DEFAULT_SITE_POLICIES`
(Shopee TLD family: `shopee.com`, `shopee.tw`, `shopee.sg`, `shopee.com.my`,
`shopee.co.id`, `shopee.com.br`, `shopee.ph`, `shopee.co.th`, `shopee.vn`,
`shopee.mx`, `shopee.cl`, `shopee.co`).

**YAML merge** (same discovery as other ziniao config: project
`config/config.yaml` + `~/.ziniao/config.yaml` fall-through; `--config` is a
single-file source). Top-level key:

```yaml
site_policy:
  policies:
    shopee.com.my:
      policy_hint: "Optional override: short CLI / JSON hint string."
    your.internal.example:
      default_mode: passive
      allow_runtime_attach: false
      allow_stealth: false
      allow_input_only: true
      policy_hint: "Internal stack: passive only."
```

- **Host keys** are registrable hosts (lowercase); subdomains match by suffix
  (e.g. `seller.shopee.tw` → policy for `shopee.tw`).
- **Per-host merge** is shallow: YAML fields override built-ins for the same
  host; omitted fields keep built-in values. New hosts are **added** from YAML
  only.
- **`policy_hint`**: non-empty string replaces the default passive hint for
  that host in CLI JSON. Other `default_mode` values can still set a custom
  `policy_hint`; if unset and `default_mode` is `passive`, the stock English
  hint is used.

`passive-open` / `launch-passive --url` / `store passive-open` (when
`launcher_page` matches) attach `policy_hint` when a policy applies.

Runtime reload: policies are loaded on **first** use per process; edit YAML and
restart the daemon (or start a new CLI process) to pick up changes.

## Limits and risks

- **Input-only** still opens a CDP WebSocket to the page target; some sites may still correlate this with risk signals — validate per site.
- No DOM selectors or `Runtime.evaluate`; coordinates / focus must come from the user, vision, or other tooling.
- Prefer **not** stacking stealth patches on the Shopee-style path; keep stealth for ordinary automation sessions.

## Dependencies

Input-only uses the **`websockets`** package (declared in `pyproject.toml`), not as a transitive-only dependency.
