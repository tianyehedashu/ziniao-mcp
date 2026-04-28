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


def register_top_level(root: typer.Typer) -> None:
    """Register ``ziniao cookie-vault …`` shortcuts."""
    root.add_typer(app, name="cookie-vault", help="Auth snapshots: export/import cookies + storage.")
