"""Get information commands — retrieve element text, attributes, page info."""

from __future__ import annotations

import typer

from .. import get_json_mode, run_command
from ..output import print_result

app = typer.Typer(no_args_is_help=True)


@app.command("text")
def get_text(selector: str = typer.Argument(..., help="CSS selector.")) -> None:
    """Get the text content of an element."""
    result = run_command("get_text", {"selector": selector})
    print_result(result, json_mode=get_json_mode())


@app.command("html")
def get_html(selector: str = typer.Argument(..., help="CSS selector.")) -> None:
    """Get the innerHTML of an element."""
    result = run_command("get_html", {"selector": selector})
    print_result(result, json_mode=get_json_mode())


@app.command("value")
def get_value(selector: str = typer.Argument(..., help="CSS selector for input element.")) -> None:
    """Get the value of an input element."""
    result = run_command("get_value", {"selector": selector})
    print_result(result, json_mode=get_json_mode())


@app.command("attr")
def get_attr(
    selector: str = typer.Argument(..., help="CSS selector."),
    attribute: str = typer.Argument(..., help="Attribute name."),
) -> None:
    """Get an attribute value of an element."""
    result = run_command("get_attr", {"selector": selector, "attribute": attribute})
    print_result(result, json_mode=get_json_mode())


@app.command("title")
def get_title() -> None:
    """Get the current page title."""
    result = run_command("get_title", {})
    print_result(result, json_mode=get_json_mode())


@app.command("url")
def get_url() -> None:
    """Get the current page URL."""
    result = run_command("get_url", {})
    print_result(result, json_mode=get_json_mode())


@app.command("count")
def get_count(selector: str = typer.Argument(..., help="CSS selector.")) -> None:
    """Count matching elements."""
    result = run_command("get_count", {"selector": selector})
    print_result(result, json_mode=get_json_mode())


def register_top_level(parent: typer.Typer) -> None:
    @parent.command("title")
    def _title() -> None:
        """Get page title."""
        get_title()

    @parent.command("url")
    def _url() -> None:
        """Get page URL."""
        get_url()
