"""Cookie vault: export/import auth snapshots (cookies + storage + UA)."""

from __future__ import annotations

from pathlib import Path

import typer

from .. import get_json_mode, run_command
from ..help_epilog import GROUP_CLI_EPILOG
from ..output import print_result

app = typer.Typer(no_args_is_help=True, epilog=GROUP_CLI_EPILOG)


@app.command("export")
def vault_export(
    output: Path = typer.Option(
        ...,
        "--output",
        "-o",
        help="Write auth snapshot JSON (cookies, localStorage, sessionStorage, UA).",
    ),
    redact: bool = typer.Option(
        False,
        "--redact",
        help="Mask cookie/storage values for sharing (not reversible).",
    ),
    site: str = typer.Option("", "--site", help="Optional site label stored in snapshot."),
    profile_id: str = typer.Option("", "--profile-id", help="Override profile_id (default: active session id)."),
    risk_level: str = typer.Option("unknown", "--risk-level", help="Risk hint stored in snapshot."),
) -> None:
    """Export an auth snapshot from the active browser session."""
    result = run_command(
        "cookie_vault",
        {
            "action": "export",
            "path": str(output.expanduser()),
            "redact": redact,
            "site": site,
            "profile_id": profile_id,
            "risk_level": risk_level,
        },
    )
    print_result(result, json_mode=get_json_mode())


@app.command("import")
def vault_import(
    snapshot: Path = typer.Argument(..., help="Auth snapshot JSON from cookie-vault export."),
    clear_cookies: bool = typer.Option(
        False,
        "--clear-cookies",
        help="Clear browser cookies before applying snapshot (destructive).",
    ),
    allow_origin_mismatch: bool = typer.Option(
        False,
        "--allow-origin-mismatch",
        help="Write storage even if the active tab origin differs from snapshot page_url.",
    ),
) -> None:
    """Import cookies + storage from a snapshot into the active session."""
    result = run_command(
        "cookie_vault",
        {
            "action": "import",
            "path": str(snapshot.expanduser()),
            "clear_cookies": clear_cookies,
            "allow_origin_mismatch": allow_origin_mismatch,
        },
    )
    print_result(result, json_mode=get_json_mode())


@app.command("restore")
def vault_restore(
    snapshot: Path = typer.Argument(..., help="Auth snapshot JSON from cookie-vault export."),
    url: str = typer.Option(
        "",
        "--url",
        help="Navigate here before import (default: snapshot page_url if set).",
    ),
    no_reload: bool = typer.Option(
        False,
        "--no-reload",
        help="Skip reload after importing cookies and storage.",
    ),
    verify_selector: str = typer.Option(
        "",
        "--verify-selector",
        help="CSS selector that must appear after restore (optional).",
    ),
    verify_timeout: float = typer.Option(
        15.0,
        "--verify-timeout",
        help="Seconds to wait for --verify-selector.",
    ),
    clear_cookies: bool = typer.Option(
        False,
        "--clear-cookies",
        help="Clear browser cookies before applying snapshot (destructive).",
    ),
    allow_origin_mismatch: bool = typer.Option(
        False,
        "--allow-origin-mismatch",
        help="Allow storage write when active tab origin differs from snapshot page_url.",
    ),
    navigate_settle: float | None = typer.Option(
        None,
        "--navigate-settle",
        help="Override configured seconds to wait after navigate before importing snapshot (>=0).",
        hidden=True,
    ),
    reload_settle: float | None = typer.Option(
        None,
        "--reload-settle",
        help="Override configured seconds to wait after reload before verify (>=0).",
        hidden=True,
    ),
) -> None:
    """Navigate (optional), import snapshot, reload, and optionally verify login UI."""
    result = run_command(
        "cookie_vault",
        {
            "action": "restore",
            "path": str(snapshot.expanduser()),
            "navigate_url": url,
            "reload": not no_reload,
            "verify_selector": verify_selector,
            "verify_timeout_sec": verify_timeout,
            "clear_cookies": clear_cookies,
            "allow_origin_mismatch": allow_origin_mismatch,
            "navigate_settle_sec": navigate_settle,
            "reload_settle_sec": reload_settle,
        },
    )
    print_result(result, json_mode=get_json_mode())


@app.command("probe-api")
def vault_probe_api(
    snapshot: Path = typer.Argument(..., help="Auth snapshot JSON."),
    url: str = typer.Argument(..., help="API URL to request with snapshot (GET/HEAD/OPTIONS only)."),
    method: str = typer.Option("GET", "--method", help="HTTP method (GET, HEAD, or OPTIONS)."),
) -> None:
    """Probe whether an API is usable via direct_http with this snapshot (safe methods only)."""
    result = run_command(
        "cookie_vault",
        {
            "action": "probe_api",
            "path": str(snapshot.expanduser()),
            "url": url,
            "method": method,
        },
    )
    print_result(result, json_mode=get_json_mode())


def register_top_level(root: typer.Typer) -> None:
    """Register ``ziniao cookie-vault …`` shortcuts."""
    root.add_typer(
        app,
        name="cookie-vault",
        help="Auth snapshots: export/import/restore cookies + storage; probe-api for direct_http.",
    )
