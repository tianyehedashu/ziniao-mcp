"""Configuration management commands: init / show / set / path / env."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

import typer

from ..help_epilog import GROUP_CLI_EPILOG

app = typer.Typer(no_args_is_help=True, epilog=GROUP_CLI_EPILOG)

_STATE_DIR = Path.home() / ".ziniao"
_GLOBAL_CONFIG = _STATE_DIR / "config.yaml"
_GLOBAL_DOTENV = _STATE_DIR / ".env"


def _detect_chrome_path() -> str:
    """Best-effort Chrome executable detection (registry > common paths > PATH)."""
    if os.name == "nt":
        try:
            import winreg  # pylint: disable=import-outside-toplevel
            for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                for sub in (
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
                    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
                ):
                    try:
                        with winreg.OpenKey(root, sub) as key:
                            val, _ = winreg.QueryValueEx(key, "")
                            if val and os.path.isfile(val):
                                return str(val)
                    except OSError:
                        continue
        except Exception:
            pass
        for p in (
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        ):
            if os.path.isfile(p):
                return p
    else:
        import shutil  # pylint: disable=import-outside-toplevel
        for name in ("google-chrome", "google-chrome-stable", "chromium-browser", "chromium"):
            found = shutil.which(name)
            if found:
                return found
        mac_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if os.path.isfile(mac_path):
            return mac_path
    return ""


def _read_global_config() -> dict:
    """Read ~/.ziniao/config.yaml if it exists."""
    if not _GLOBAL_CONFIG.is_file():
        return {}
    try:
        import yaml  # pylint: disable=import-outside-toplevel
        with open(_GLOBAL_CONFIG, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _write_global_config(data: dict) -> None:
    """Write dict to ~/.ziniao/config.yaml."""
    import yaml  # pylint: disable=import-outside-toplevel
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(_GLOBAL_CONFIG, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _prompt(msg: str, default: str = "") -> str:
    """Interactive input with default."""
    suffix = f" [{default}]" if default else ""
    try:
        val = input(f"{msg}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt) as exc:
        raise typer.Exit(130) from exc
    return val if val else default


def _confirm(msg: str, default: bool = False) -> bool:
    hint = "Y/n" if default else "y/N"
    try:
        val = input(f"{msg} ({hint}): ").strip().lower()
    except (EOFError, KeyboardInterrupt) as exc:
        raise typer.Exit(130) from exc
    if not val:
        return default
    return val in ("y", "yes")


# ---------------------------------------------------------------------------
# ziniao config init
# ---------------------------------------------------------------------------

@app.command("init")
def init(
    force: bool = typer.Option(False, "--force", help="Overwrite existing config."),
) -> None:
    """Interactive setup wizard — generates ~/.ziniao/config.yaml and .env."""
    if _GLOBAL_CONFIG.exists() and not force:
        typer.echo(f"Config already exists: {_GLOBAL_CONFIG}")
        if not _confirm("Overwrite?"):
            raise typer.Exit(0)

    typer.echo("\n=== Ziniao CLI Configuration Wizard ===\n")

    # --- Chrome ---
    typer.echo("[Chrome]")
    detected = _detect_chrome_path()
    if detected:
        typer.echo(f"  Auto-detected Chrome: {detected}")
    chrome_path = _prompt("  Chrome executable path (empty=auto-detect)", detected)
    chrome_user_data = _prompt(
        "  User data directory for state reuse (empty=default ~/.ziniao/chrome-profile)", ""
    )
    chrome_cdp_port = _prompt("  Default CDP port (0=auto)", "0")

    # --- Ziniao ---
    use_ziniao = _confirm("\nConfigure Ziniao client?", default=False)
    ziniao_cfg: dict = {}
    if use_ziniao:
        typer.echo("\n[Ziniao]")
        company = _prompt("  Company name")
        username = _prompt("  Username")
        password = _prompt("  Password")
        client_path = _prompt("  Client path (e.g. D:\\ziniao\\ziniao.exe)")
        version = _prompt("  Version", "v6")
        socket_port = _prompt("  Socket port (empty=auto-detect)", "")
        ziniao_cfg = {
            "browser": {"version": version, "client_path": client_path},
            "user_info": {"company": company, "username": username, "password": password},
        }
        if socket_port:
            ziniao_cfg["browser"]["socket_port"] = int(socket_port)

    # --- Build config ---
    config: dict = {}
    if ziniao_cfg:
        config["ziniao"] = ziniao_cfg

    chrome_section: dict = {}
    if chrome_path:
        chrome_section["executable_path"] = chrome_path
    if chrome_user_data:
        chrome_section["user_data_dir"] = chrome_user_data
    try:
        port_int = int(chrome_cdp_port)
    except (ValueError, TypeError):
        port_int = 0
    if port_int:
        chrome_section["default_cdp_port"] = port_int
    chrome_section["headless"] = False
    config["chrome"] = chrome_section

    _write_global_config(config)
    typer.echo(f"\nConfig written to {_GLOBAL_CONFIG}")

    # --- Generate .env ---
    env_lines = ["# Generated by ziniao config init"]
    if chrome_path:
        env_lines.append(f'CHROME_PATH={chrome_path}')
    if chrome_user_data:
        env_lines.append(f'CHROME_USER_DATA={chrome_user_data}')
    if port_int:
        env_lines.append(f'CHROME_CDP_PORT={port_int}')
    if use_ziniao and ziniao_cfg:
        ui = ziniao_cfg.get("user_info", {})
        br = ziniao_cfg.get("browser", {})
        if ui.get("company"):
            env_lines.append(f'ZINIAO_COMPANY={ui["company"]}')
        if ui.get("username"):
            env_lines.append(f'ZINIAO_USERNAME={ui["username"]}')
        if ui.get("password"):
            env_lines.append(f'ZINIAO_PASSWORD={ui["password"]}')
        if br.get("client_path"):
            env_lines.append(f'ZINIAO_CLIENT_PATH={br["client_path"]}')
        if br.get("version"):
            env_lines.append(f'ZINIAO_VERSION={br["version"]}')

    _GLOBAL_DOTENV.write_text("\n".join(env_lines) + "\n", encoding="utf-8")
    typer.echo(f".env written to {_GLOBAL_DOTENV}")
    typer.echo("\nDone! Run `ziniao config show` to verify.")


# ---------------------------------------------------------------------------
# ziniao config show
# ---------------------------------------------------------------------------

@app.command("show")
def show() -> None:
    """Display the current effective configuration and its sources."""
    from ...dotenv_loader import load_dotenv  # pylint: disable=import-outside-toplevel
    load_dotenv()

    global_cfg = _read_global_config()
    chrome_yaml = global_cfg.get("chrome", {})
    ziniao_yaml = global_cfg.get("ziniao", {})

    project_cfg: dict = {}
    for p in (Path("config/config.yaml"),):
        if p.is_file():
            try:
                import yaml  # pylint: disable=import-outside-toplevel
                with open(p, "r", encoding="utf-8") as f:
                    project_cfg = yaml.safe_load(f) or {}
            except Exception:
                pass
            break

    has_rich = False
    try:
        import importlib.util  # pylint: disable=import-outside-toplevel
        has_rich = importlib.util.find_spec("rich") is not None
    except Exception:  # pylint: disable=broad-except
        pass
    if has_rich:
        _show_rich(global_cfg, project_cfg, chrome_yaml, ziniao_yaml)
    else:
        _show_plain(global_cfg, project_cfg, chrome_yaml, ziniao_yaml)


def _source_of(key: str, env_var: str, chrome_yaml: dict, ziniao_yaml: dict, global_cfg: dict, project_cfg: dict) -> tuple[str, str]:
    """Return (value, source_label) for a config key."""
    env_val = os.environ.get(env_var, "")
    if env_val:
        return env_val, "env"

    proj_chrome = project_cfg.get("chrome", {})
    proj_ziniao = project_cfg.get("ziniao", {})
    sections = {"chrome": proj_chrome, "ziniao_browser": proj_ziniao.get("browser", {}), "ziniao_user": proj_ziniao.get("user_info", {})}
    for sect_name, sect in sections.items():
        if key in sect and sect[key]:
            return str(sect[key]), f"project yaml ({sect_name})"

    sections_global = {"chrome": chrome_yaml, "ziniao_browser": ziniao_yaml.get("browser", {}), "ziniao_user": ziniao_yaml.get("user_info", {})}
    for sect_name, sect in sections_global.items():
        if key in sect and sect[key]:
            return str(sect[key]), f"~/.ziniao/config.yaml ({sect_name})"

    return "", "default"


def _show_rich(global_cfg: dict, project_cfg: dict, chrome_yaml: dict, ziniao_yaml: dict) -> None:
    from rich.console import Console  # pylint: disable=import-outside-toplevel
    from rich.table import Table  # pylint: disable=import-outside-toplevel

    console = Console()

    console.print("\n[bold]Config files[/bold]")
    console.print(f"  Global : {_GLOBAL_CONFIG} {'[green](exists)' if _GLOBAL_CONFIG.is_file() else '[dim](not found)'}")
    console.print(f"  .env   : {_GLOBAL_DOTENV} {'[green](exists)' if _GLOBAL_DOTENV.is_file() else '[dim](not found)'}")
    proj_path = Path("config/config.yaml")
    console.print(f"  Project: {proj_path.resolve()} {'[green](exists)' if proj_path.is_file() else '[dim](not found)'}")

    table = Table(title="\nEffective Configuration", show_lines=True)
    table.add_column("Key", style="cyan")
    table.add_column("Value")
    table.add_column("Source", style="dim")

    entries = [
        ("chrome.executable_path", "CHROME_PATH"),
        ("chrome.user_data_dir", "CHROME_USER_DATA"),
        ("chrome.default_cdp_port", "CHROME_CDP_PORT"),
    ]
    for display_key, env_var in entries:
        yaml_key = display_key.rsplit(".", maxsplit=1)[-1]
        val, src = _source_of(yaml_key, env_var, chrome_yaml, ziniao_yaml, global_cfg, project_cfg)
        table.add_row(display_key, val or "[dim]-", src)

    ziniao_entries = [
        ("ziniao.company", "ZINIAO_COMPANY", "company"),
        ("ziniao.username", "ZINIAO_USERNAME", "username"),
        ("ziniao.client_path", "ZINIAO_CLIENT_PATH", "client_path"),
        ("ziniao.version", "ZINIAO_VERSION", "version"),
    ]
    for display_key, env_var, yaml_key in ziniao_entries:
        val, src = _source_of(yaml_key, env_var, chrome_yaml, ziniao_yaml, global_cfg, project_cfg)
        table.add_row(display_key, val or "[dim]-", src)

    console.print(table)
    console.print("\n[dim]Priority: env var > project config/config.yaml > ~/.ziniao/.env > ~/.ziniao/config.yaml[/dim]\n")


def _show_plain(global_cfg: dict, project_cfg: dict, chrome_yaml: dict, ziniao_yaml: dict) -> None:
    typer.echo("\nConfig files:")
    typer.echo(f"  Global : {_GLOBAL_CONFIG} {'(exists)' if _GLOBAL_CONFIG.is_file() else '(not found)'}")
    typer.echo(f"  .env   : {_GLOBAL_DOTENV} {'(exists)' if _GLOBAL_DOTENV.is_file() else '(not found)'}")
    typer.echo(f"  Project: config/config.yaml {'(exists)' if Path('config/config.yaml').is_file() else '(not found)'}")

    typer.echo("\nEffective Configuration:")
    entries = [
        ("chrome.executable_path", "CHROME_PATH"),
        ("chrome.user_data_dir", "CHROME_USER_DATA"),
        ("chrome.default_cdp_port", "CHROME_CDP_PORT"),
        ("ziniao.company", "ZINIAO_COMPANY"),
        ("ziniao.username", "ZINIAO_USERNAME"),
        ("ziniao.client_path", "ZINIAO_CLIENT_PATH"),
        ("ziniao.version", "ZINIAO_VERSION"),
    ]
    for display_key, env_var in entries:
        yaml_key = display_key.rsplit(".", maxsplit=1)[-1]
        val, src = _source_of(yaml_key, env_var, chrome_yaml, ziniao_yaml, global_cfg, project_cfg)
        typer.echo(f"  {display_key}: {val or '-'} ({src})")

    typer.echo("\nPriority: env var > project config/config.yaml > ~/.ziniao/.env > ~/.ziniao/config.yaml\n")


# ---------------------------------------------------------------------------
# ziniao config set
# ---------------------------------------------------------------------------

@app.command("set")
def set_value(
    key: str = typer.Argument(
        ...,
        help="Dotted config key, e.g. chrome.executable_path or cookie_vault.restore.navigate_settle_sec.",
    ),
    value: str = typer.Argument(..., help="Value to set."),
) -> None:
    """Set a configuration value in ~/.ziniao/config.yaml."""
    config = _read_global_config()
    parts = key.split(".")
    if len(parts) == 1:
        config[parts[0]] = value
    elif len(parts) == 2:
        section, field = parts
        if section == "ziniao":
            _set_ziniao_key(config, field, value)
        else:
            config.setdefault(section, {})[field] = _coerce(value)
    else:
        target = config
        for part in parts[:-1]:
            next_target = target.setdefault(part, {})
            if not isinstance(next_target, dict):
                typer.echo(f"Error: '{part}' is not a config section in '{key}'.", err=True)
                raise typer.Exit(1)
            target = next_target
        target[parts[-1]] = _coerce(value)

    _write_global_config(config)
    typer.echo(f"Set {key} = {value} in {_GLOBAL_CONFIG}")


def _coerce(value: str):
    """Coerce string to bool/int/float if applicable."""
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def _set_ziniao_key(config: dict, field: str, value: str) -> None:
    """Set a ziniao.* key, routing to the correct subsection."""
    zn = config.setdefault("ziniao", {})
    user_fields = {"company", "username", "password"}
    browser_fields = {"version", "client_path", "socket_port"}
    if field in user_fields:
        zn.setdefault("user_info", {})[field] = value
    elif field in browser_fields:
        zn.setdefault("browser", {})[field] = _coerce(value)
    else:
        zn[field] = _coerce(value)


# ---------------------------------------------------------------------------
# ziniao config path
# ---------------------------------------------------------------------------

@app.command("path")
def path_cmd() -> None:
    """Show configuration file paths."""
    typer.echo(f"Global config : {_GLOBAL_CONFIG}")
    typer.echo(f"Global .env   : {_GLOBAL_DOTENV}")
    typer.echo(f"State dir     : {_STATE_DIR}")
    proj = Path("config/config.yaml")
    if proj.is_file():
        typer.echo(f"Project config: {proj.resolve()}")


# ---------------------------------------------------------------------------
# ziniao config env
# ---------------------------------------------------------------------------

@app.command("env")
def env_cmd(
    shell: Optional[str] = typer.Option(
        None, "--shell",
        help="Output format: powershell, bash, json, or mcp. Auto-detected if omitted.",
    ),
) -> None:
    """Output environment variable export statements from current config."""
    from ...dotenv_loader import load_dotenv  # pylint: disable=import-outside-toplevel
    load_dotenv()

    config = _read_global_config()
    chrome = config.get("chrome", {})
    ziniao = config.get("ziniao", {})

    env_map: dict[str, str] = {}
    if chrome.get("executable_path"):
        env_map["CHROME_PATH"] = chrome["executable_path"]
    if chrome.get("user_data_dir"):
        env_map["CHROME_USER_DATA"] = chrome["user_data_dir"]
    if chrome.get("default_cdp_port"):
        env_map["CHROME_CDP_PORT"] = str(chrome["default_cdp_port"])
    ui = ziniao.get("user_info", {})
    br = ziniao.get("browser", {})
    if ui.get("company"):
        env_map["ZINIAO_COMPANY"] = ui["company"]
    if ui.get("username"):
        env_map["ZINIAO_USERNAME"] = ui["username"]
    if ui.get("password"):
        env_map["ZINIAO_PASSWORD"] = ui["password"]
    if br.get("client_path"):
        env_map["ZINIAO_CLIENT_PATH"] = br["client_path"]
    if br.get("version"):
        env_map["ZINIAO_VERSION"] = br["version"]

    if not env_map:
        typer.echo("No configuration found. Run `ziniao config init` first.")
        raise typer.Exit(1)

    fmt = shell or _detect_shell()
    if fmt == "json":
        typer.echo(json.dumps(env_map, ensure_ascii=False, indent=2))
    elif fmt == "mcp":
        typer.echo('"env": ' + json.dumps(env_map, ensure_ascii=False, indent=2))
    elif fmt == "powershell":
        for k, v in env_map.items():
            typer.echo(f'$env:{k} = "{v}"')
    else:
        for k, v in env_map.items():
            typer.echo(f'export {k}="{v}"')


def _detect_shell() -> str:
    if sys.platform == "win32":
        return "powershell"
    return "bash"
