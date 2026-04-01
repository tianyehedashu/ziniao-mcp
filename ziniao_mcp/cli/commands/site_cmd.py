"""Site plugin management and dynamic site shortcut commands.

``ziniao site list / show / enable / disable`` for management.
``ziniao <site> <action>`` shortcuts registered dynamically at CLI init.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

import typer

from .. import get_json_mode, run_command
from ..output import print_result

app = typer.Typer(no_args_is_help=True, help="Site plugins: list, show, enable, disable.")

_STATE_FILE = Path.home() / ".ziniao" / "sites.json"


# ---------------------------------------------------------------------------
# Persistent enable/disable state
# ---------------------------------------------------------------------------

def _load_state() -> dict:
    if _STATE_FILE.is_file():
        try:
            return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_state(state: dict) -> None:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def is_preset_enabled(preset_id: str) -> bool:
    state = _load_state()
    disabled = state.get("disabled", [])
    return preset_id not in disabled


# ---------------------------------------------------------------------------
# site list
# ---------------------------------------------------------------------------

@app.command("list")
def site_list() -> None:
    """List all available site presets and their status.

    Examples:
        ziniao site list
        ziniao --json site list
    """
    from ...sites import list_presets  # pylint: disable=import-outside-toplevel

    presets = list_presets()
    state = _load_state()
    disabled = set(state.get("disabled", []))

    if get_json_mode():
        for p in presets:
            p["enabled"] = p["id"] not in disabled
        print_result({"presets": presets, "count": len(presets)}, json_mode=True)
        return

    if not presets:
        typer.echo("No site presets found.")
        return

    max_id = max(len(p["id"]) for p in presets)
    for p in presets:
        status = "  " if p["id"] not in disabled else "x "
        mode_tag = f"[{p['mode']}]"
        auth_tag = f"[{p.get('auth', 'cookie')}]"
        pag_note = " (paginated)" if p.get("paginated") else ""
        vars_str = ", ".join(p.get("vars", [])) if p.get("vars") else ""
        line = f"  {status}{p['id']:<{max_id}}  {mode_tag:<8} {auth_tag:<8}{pag_note}  {p.get('description', '')}"
        if vars_str:
            line += f"  (vars: {vars_str})"
        typer.echo(line)
    typer.echo(f"\n  Total: {len(presets)}  (x = disabled)")


# ---------------------------------------------------------------------------
# site show
# ---------------------------------------------------------------------------

@app.command("show")
def site_show(
    preset_id: str = typer.Argument(..., help="Preset ID (e.g. rakuten/rpp-search)."),
    raw: bool = typer.Option(False, "--raw", help="Print the raw preset JSON template."),
) -> None:
    """Show preset details, variables, and usage example.

    Example: ziniao site show rakuten/rpp-search
             ziniao site show rakuten/rpp-search --raw
    """
    from ...sites import load_preset  # pylint: disable=import-outside-toplevel

    try:
        data = load_preset(preset_id)
    except FileNotFoundError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    if raw:
        typer.echo(json.dumps(data, ensure_ascii=False, indent=2))
        return

    if get_json_mode():
        data["enabled"] = is_preset_enabled(preset_id)
        print_result(data, json_mode=True)
        return

    enabled = is_preset_enabled(preset_id)
    site_name = preset_id.split("/")[0]
    action_name = preset_id.split("/", 1)[1] if "/" in preset_id else preset_id

    typer.echo(f"  {data.get('name', preset_id)}  {'(enabled)' if enabled else '(DISABLED)'}")
    typer.echo(f"  {data.get('description', '')}")
    typer.echo(f"  Mode: {data.get('mode', 'fetch')}")
    auth = data.get("auth") or {}
    if auth:
        hint = f" ({auth['hint']})" if auth.get("hint") else ""
        typer.echo(f"  Auth: {auth.get('type', 'cookie')}{hint}")
    pag = data.get("pagination") or {}
    ptype = pag.get("type", "none")
    if ptype not in ("", "none", None):
        extra = ", ".join(
            f"{k}={pag[k]}"
            for k in ("page_field", "total_field", "offset_field", "limit_field", "merge_items_field")
            if pag.get(k)
        )
        typer.echo(f"  Pagination: {ptype}" + (f" ({extra})" if extra else ""))
    if data.get("navigate_url"):
        typer.echo(f"  Page: {data['navigate_url']}")

    var_defs = data.get("vars") or {}
    if var_defs:
        typer.echo("\n  Variables:")
        for vname, vdef in var_defs.items():
            req = " *" if vdef.get("required") else ""
            default = f" [={vdef['default']}]" if "default" in vdef else ""
            example = f"  e.g. {vdef['example']}" if "example" in vdef else ""
            typer.echo(f"    {vname}{req}{default}  {vdef.get('description', '')}{example}")

    var_args = " ".join(
        f"-V {k}={v.get('example', '...')}" for k, v in var_defs.items() if v.get("required")
    )
    page_hint = " [--page N] [--all]" if ptype not in ("", "none", None) else ""
    typer.echo(f"\n  Usage: ziniao {site_name} {action_name} {var_args}{page_hint}")


# ---------------------------------------------------------------------------
# site fork / copy — copy a preset to the user directory for editing
# ---------------------------------------------------------------------------

def _site_fork(
    src: str = typer.Argument(..., help="Source preset ID (e.g. rakuten/rpp-search)."),
    dst: Optional[str] = typer.Argument(None, help="Target preset ID (defaults to same as source)."),
    force: bool = typer.Option(False, "--force", help="Overwrite if the target file already exists."),
) -> None:
    """Copy a preset to ~/.ziniao/sites/ for editing.

    Examples:
        ziniao site fork rakuten/rpp-search
        ziniao site fork rakuten/rpp-search mysite/rpp-custom --force
    """
    from ...sites import fork_preset  # pylint: disable=import-outside-toplevel

    try:
        path = fork_preset(src, dst, force=force)
    except (FileNotFoundError, ValueError, FileExistsError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    target_id = dst or src
    typer.echo(f"  Saved: {path}")
    typer.echo(f"  Edit the file, then run: ziniao network fetch -p {target_id} ...")


app.command("fork")(_site_fork)
app.command("copy", hidden=True)(_site_fork)


# ---------------------------------------------------------------------------
# site enable / disable
# ---------------------------------------------------------------------------

@app.command("enable")
def site_enable(
    preset_id: str = typer.Argument(..., help="Preset ID to enable (e.g. rakuten/rpp-search)."),
) -> None:
    """Enable a site preset."""
    state = _load_state()
    disabled = state.get("disabled", [])
    if preset_id in disabled:
        disabled.remove(preset_id)
        state["disabled"] = disabled
        _save_state(state)
        typer.echo(f"Enabled: {preset_id}")
    else:
        typer.echo(f"Already enabled: {preset_id}")


@app.command("disable")
def site_disable(
    preset_id: str = typer.Argument(..., help="Preset ID to disable (e.g. rakuten/rpp-search)."),
) -> None:
    """Disable a site preset (hidden from shortcuts, still usable via --file)."""
    state = _load_state()
    disabled = state.get("disabled", [])
    if preset_id not in disabled:
        disabled.append(preset_id)
        state["disabled"] = disabled
        _save_state(state)
        typer.echo(f"Disabled: {preset_id}")
    else:
        typer.echo(f"Already disabled: {preset_id}")


# ---------------------------------------------------------------------------
# Dynamic site shortcut registration: ziniao <site> <action>
# ---------------------------------------------------------------------------

def register_site_commands(root_app: typer.Typer) -> None:
    """Scan all enabled presets and register ``ziniao <site> <action>`` shortcuts."""
    from ...sites import list_presets  # pylint: disable=import-outside-toplevel

    presets = list_presets()
    state = _load_state()
    disabled = set(state.get("disabled", []))

    site_groups: dict[str, typer.Typer] = {}
    site_counts: dict[str, int] = {}

    for p in presets:
        if p["id"] in disabled:
            continue
        parts = p["id"].split("/", 1)
        if len(parts) != 2:
            continue
        site_name, action_name = parts

        if site_name not in site_groups:
            site_groups[site_name] = typer.Typer(no_args_is_help=True)
            site_counts[site_name] = 0
            root_app.add_typer(site_groups[site_name], name=site_name, hidden=False)

        site_counts[site_name] += 1
        _register_action(site_groups[site_name], p["id"], site_name, action_name, p)

    for site_name, grp in site_groups.items():
        n = site_counts[site_name]
        grp.info.help = (
            f"{site_name} site presets ({n} commands).\n\n"
            f"Run 'ziniao site list' for tags & variables overview,\n"
            f"or  'ziniao site show {site_name}/<action>' for full details."
        )


def _build_command_help(meta: dict, site_name: str, action_name: str) -> str:
    """Build an informative help string for ``ziniao <site> <action> --help``."""
    parts: list[str] = []

    desc = meta.get("description", "")
    if desc:
        parts.append(desc)

    tags = [f"Mode: {meta.get('mode', 'fetch')}", f"Auth: {meta.get('auth', 'cookie')}"]
    if meta.get("paginated"):
        tags.append("Paginated")
    parts.append(" · ".join(tags))

    var_defs: dict = meta.get("var_defs") or {}
    if var_defs:
        var_lines: list[str] = []
        for vname, vdef in var_defs.items():
            req = " *" if vdef.get("required") else ""
            default = f" (={vdef['default']})" if "default" in vdef else ""
            vdesc = vdef.get("description", "")
            example = f"  e.g. {vdef['example']}" if vdef.get("example") else ""
            var_lines.append(f"  {vname}{req}{default}  {vdesc}{example}")
        parts.append("Vars (-V key=value):\n" + "\n".join(var_lines))

    required_vars = {k: v for k, v in var_defs.items() if v.get("required")}
    var_args = " ".join(f"-V {k}={v.get('example', '...')}" for k, v in required_vars.items())
    pag_hint = " --all" if meta.get("paginated") else ""
    if var_args or pag_hint:
        parts.append(f"Example: ziniao {site_name} {action_name} {var_args}{pag_hint}")
    parts.append(f"Full info: ziniao site show {site_name}/{action_name}")

    return "\n\n".join(parts)


def _register_action(
    site_app: typer.Typer,
    preset_id: str,
    site_name: str,
    action_name: str,
    meta: dict,
) -> None:
    """Register a single ``ziniao <site> <action>`` command."""

    help_text = _build_command_help(meta, site_name, action_name)

    @site_app.command(action_name, help=help_text)
    def _action(
        var: Optional[List[str]] = typer.Option(None, "--var", "-V", help="Variable key=value (repeatable)."),
        page: Optional[int] = typer.Option(None, "--page", help="Override page number (paginated presets)."),
        fetch_all: bool = typer.Option(False, "--all", help="Fetch and merge all pages (needs pagination in template)."),
        output: Optional[str] = typer.Option(None, "--output", "-o", help="Save response body to file."),
    ) -> None:
        from ...sites import (  # pylint: disable=import-outside-toplevel
            prepare_request,
            run_site_fetch,
            save_response_body,
        )

        if fetch_all and page is not None:
            typer.echo("Error: use either --page or --all, not both.", err=True)
            raise typer.Exit(1)

        parsed_vars = _parse_var_list(var)
        if page is not None:
            parsed_vars["page"] = str(page)

        try:
            spec, plugin = prepare_request(preset=preset_id, var_values=parsed_vars)
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc

        if not get_json_mode():
            auth = spec.get("auth") or {}
            if auth.get("show_hint", True) and auth.get("hint"):
                typer.echo(typer.style(f"  ℹ {auth['hint']}", dim=True))

        def _fetch_sync(s: dict) -> dict:
            return run_command("page_fetch", s)

        result = run_site_fetch(spec, plugin, _fetch_sync, fetch_all=fetch_all)

        if output and result.get("body"):
            typer.echo(save_response_body(result["body"], output))
            return

        print_result(result, json_mode=get_json_mode())


def _parse_var_list(var: Optional[List[str]]) -> dict[str, str]:
    """Parse ``["k=v", ...]`` into ``{k: v}``."""
    result: dict[str, str] = {}
    for v in (var or []):
        if "=" in v:
            k, val = v.split("=", 1)
            result[k.strip()] = val.strip()
    return result
