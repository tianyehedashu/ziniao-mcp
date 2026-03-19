"""State check commands — is visible/enabled/checked."""

from __future__ import annotations

import typer

from .. import get_json_mode, run_command
from ..output import print_result

app = typer.Typer(no_args_is_help=True)


@app.command("visible")
def is_visible(selector: str = typer.Argument(..., help="CSS selector.")) -> None:
    """Check if an element is visible."""
    result = run_command("is_visible", {"selector": selector})
    print_result(result, json_mode=get_json_mode())


@app.command("enabled")
def is_enabled(selector: str = typer.Argument(..., help="CSS selector.")) -> None:
    """Check if an element is enabled (not disabled)."""
    result = run_command("is_enabled", {"selector": selector})
    print_result(result, json_mode=get_json_mode())


@app.command("checked")
def is_checked(selector: str = typer.Argument(..., help="CSS selector.")) -> None:
    """Check if a checkbox/radio is checked."""
    result = run_command("is_checked", {"selector": selector})
    print_result(result, json_mode=get_json_mode())


def register_top_level(parent: typer.Typer) -> None:
    pass
