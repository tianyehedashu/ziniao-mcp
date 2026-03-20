"""Find/nth semantic element location — first/last/nth/text/role + subaction."""

from __future__ import annotations

from typing import Optional

import typer

from .. import get_json_mode, run_command
from ..help_epilog import GROUP_CLI_EPILOG
from ..output import print_result

app = typer.Typer(no_args_is_help=True, epilog=GROUP_CLI_EPILOG)


@app.command("first")
def find_first(
    selector: str = typer.Argument(..., help="CSS selector."),
    action: str = typer.Argument("click", help="Sub-action: click, text, html, value."),
) -> None:
    """Act on the first matching element."""
    result = run_command("find_nth", {"selector": selector, "index": 0, "action": action})
    print_result(result, json_mode=get_json_mode())


@app.command("last")
def find_last(
    selector: str = typer.Argument(..., help="CSS selector."),
    action: str = typer.Argument("click", help="Sub-action: click, text, html, value."),
) -> None:
    """Act on the last matching element."""
    result = run_command("find_nth", {"selector": selector, "index": -1, "action": action})
    print_result(result, json_mode=get_json_mode())


@app.command("nth")
def find_nth(
    index: int = typer.Argument(..., help="0-based index of the element."),
    selector: str = typer.Argument(..., help="CSS selector."),
    action: str = typer.Argument("click", help="Sub-action: click, text, html, value."),
) -> None:
    """Act on the nth matching element."""
    result = run_command("find_nth", {"selector": selector, "index": index, "action": action})
    print_result(result, json_mode=get_json_mode())


@app.command("text")
def find_text(
    text: str = typer.Argument(..., help="Text content to search for."),
    action: str = typer.Argument("click", help="Sub-action: click, text, html, value."),
    tag: Optional[str] = typer.Option(None, "--tag", help="Limit to specific tag name."),
) -> None:
    """Find an element by its text content and act on it."""
    result = run_command("find_text", {"text": text, "action": action, "tag": tag or ""})
    print_result(result, json_mode=get_json_mode())


@app.command("role")
def find_role(
    role: str = typer.Argument(..., help="ARIA role (e.g. button, link, textbox)."),
    action: str = typer.Argument("click", help="Sub-action: click, text, html, value."),
    name: Optional[str] = typer.Option(None, "--name", help="Accessible name filter."),
) -> None:
    """Find an element by ARIA role and act on it."""
    result = run_command("find_role", {"role": role, "action": action, "name": name or ""})
    print_result(result, json_mode=get_json_mode())


def register_top_level(parent: typer.Typer) -> None:
    pass
