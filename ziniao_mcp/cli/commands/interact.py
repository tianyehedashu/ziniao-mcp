"""Page interaction commands."""

from __future__ import annotations

import json
from typing import List, Optional

import typer

from .. import get_json_mode, run_command
from ..output import print_result

app = typer.Typer(no_args_is_help=True)


@app.command()
def click(selector: str = typer.Argument(..., help="CSS selector to click.")) -> None:
    """Click an element."""
    result = run_command("click", {"selector": selector})
    print_result(result, json_mode=get_json_mode())


@app.command()
def fill(
    selector: str = typer.Argument("", help="Input CSS selector."),
    value: str = typer.Argument("", help="Value to fill."),
    fields_json: Optional[str] = typer.Option(None, "--fields-json", help="JSON array of {selector, value} pairs."),
) -> None:
    """Fill input fields."""
    result = run_command("fill", {"selector": selector, "value": value, "fields_json": fields_json or ""})
    print_result(result, json_mode=get_json_mode())


@app.command("type")
def type_text(
    text: str = typer.Argument(..., help="Text to type character by character."),
    selector: Optional[str] = typer.Option(None, "--selector", "-s", help="Target element selector."),
) -> None:
    """Type text character by character."""
    result = run_command("type_text", {"text": text, "selector": selector or ""})
    print_result(result, json_mode=get_json_mode())


@app.command()
def press(key: str = typer.Argument(..., help="Key name (e.g. Enter, Tab, Control+a).")) -> None:
    """Press a keyboard key."""
    result = run_command("press_key", {"key": key})
    print_result(result, json_mode=get_json_mode())


@app.command()
def hover(selector: str = typer.Argument(..., help="CSS selector to hover.")) -> None:
    """Hover over an element."""
    result = run_command("hover", {"selector": selector})
    print_result(result, json_mode=get_json_mode())


@app.command()
def drag(
    source: str = typer.Argument(..., help="Source element CSS selector."),
    target: str = typer.Argument(..., help="Target element CSS selector."),
) -> None:
    """Drag from source to target element."""
    result = run_command("drag", {"source_selector": source, "target_selector": target})
    print_result(result, json_mode=get_json_mode())


@app.command()
def upload(
    selector: str = typer.Argument(..., help="File input CSS selector."),
    files: List[str] = typer.Argument(..., help="File paths to upload."),
) -> None:
    """Upload files to a file input."""
    result = run_command("upload", {"selector": selector, "file_paths": files})
    print_result(result, json_mode=get_json_mode())


@app.command()
def dialog(
    action: str = typer.Argument("accept", help="Dialog action: accept or dismiss."),
    text: Optional[str] = typer.Option(None, "--text", help="Prompt text for prompt dialogs."),
) -> None:
    """Set dialog handling mode."""
    result = run_command("handle_dialog", {"action": action, "text": text or ""})
    print_result(result, json_mode=get_json_mode())


@app.command()
def dblclick(selector: str = typer.Argument(..., help="CSS selector to double-click.")) -> None:
    """Double-click an element."""
    result = run_command("dblclick", {"selector": selector})
    print_result(result, json_mode=get_json_mode())


@app.command()
def focus(selector: str = typer.Argument(..., help="CSS selector to focus.")) -> None:
    """Focus an element."""
    result = run_command("focus", {"selector": selector})
    print_result(result, json_mode=get_json_mode())


@app.command("select")
def select_option(
    selector: str = typer.Argument(..., help="CSS selector for <select> element."),
    value: str = typer.Argument(..., help="Option value to select."),
) -> None:
    """Select an option from a dropdown."""
    result = run_command("select_option", {"selector": selector, "value": value})
    print_result(result, json_mode=get_json_mode())


@app.command("check")
def check(selector: str = typer.Argument(..., help="CSS selector for checkbox/radio.")) -> None:
    """Check a checkbox or radio button."""
    result = run_command("check", {"selector": selector})
    print_result(result, json_mode=get_json_mode())


@app.command("uncheck")
def uncheck(selector: str = typer.Argument(..., help="CSS selector for checkbox.")) -> None:
    """Uncheck a checkbox."""
    result = run_command("uncheck", {"selector": selector})
    print_result(result, json_mode=get_json_mode())


@app.command("keydown")
def keydown(key: str = typer.Argument(..., help="Key name to press down (e.g. Shift, Control).")) -> None:
    """Press a key down without releasing."""
    result = run_command("keydown", {"key": key})
    print_result(result, json_mode=get_json_mode())


@app.command("keyup")
def keyup(key: str = typer.Argument(..., help="Key name to release.")) -> None:
    """Release a held key."""
    result = run_command("keyup", {"key": key})
    print_result(result, json_mode=get_json_mode())


def register_top_level(parent: typer.Typer) -> None:
    @parent.command("click")
    def _click(selector: str = typer.Argument(...)) -> None:
        """Click an element."""
        click(selector)

    @parent.command("fill")
    def _fill(selector: str = typer.Argument(""), value: str = typer.Argument("")) -> None:
        """Fill an input."""
        fill(selector, value)

    @parent.command("type")
    def _type(text: str = typer.Argument(...), selector: Optional[str] = typer.Option(None, "-s")) -> None:
        """Type text."""
        type_text(text, selector)

    @parent.command("press")
    def _press(key: str = typer.Argument(...)) -> None:
        """Press a key."""
        press(key)

    @parent.command("hover")
    def _hover(selector: str = typer.Argument(...)) -> None:
        """Hover element."""
        hover(selector)

    @parent.command("dblclick")
    def _dblclick(selector: str = typer.Argument(...)) -> None:
        """Double-click element."""
        dblclick(selector)
