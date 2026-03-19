"""Session management commands."""

from __future__ import annotations

import typer

from .. import get_json_mode, run_command
from ..output import print_result

app = typer.Typer(no_args_is_help=True)


@app.command("list")
def session_list() -> None:
    """List all active sessions (Ziniao + Chrome)."""
    result = run_command("session_list")
    print_result(result, json_mode=get_json_mode())


@app.command("switch")
def session_switch(
    session_id: str = typer.Argument(..., help="Session ID to switch to."),
) -> None:
    """Switch the active session."""
    result = run_command("session_switch", {"session_id": session_id})
    print_result(result, json_mode=get_json_mode())


@app.command("info")
def session_info(
    session_id: str = typer.Argument(..., help="Session ID to inspect."),
) -> None:
    """Get detailed info about a session."""
    result = run_command("session_info", {"session_id": session_id})
    print_result(result, json_mode=get_json_mode())
