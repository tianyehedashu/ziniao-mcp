"""Scroll commands — page scroll and scroll-into-view."""

from __future__ import annotations

from typing import Optional

import typer

from .. import get_json_mode, run_command
from ..output import print_result

app = typer.Typer(no_args_is_help=True)


@app.command("up")
def scroll_up(
    pixels: int = typer.Argument(300, help="Pixels to scroll."),
    selector: Optional[str] = typer.Option(None, "--selector", "-s", help="Scroll inside this element."),
) -> None:
    """Scroll up."""
    result = run_command("scroll", {"direction": "up", "pixels": pixels, "selector": selector or ""})
    print_result(result, json_mode=get_json_mode())


@app.command("down")
def scroll_down(
    pixels: int = typer.Argument(300, help="Pixels to scroll."),
    selector: Optional[str] = typer.Option(None, "--selector", "-s", help="Scroll inside this element."),
) -> None:
    """Scroll down."""
    result = run_command("scroll", {"direction": "down", "pixels": pixels, "selector": selector or ""})
    print_result(result, json_mode=get_json_mode())


@app.command("left")
def scroll_left(
    pixels: int = typer.Argument(300, help="Pixels to scroll."),
    selector: Optional[str] = typer.Option(None, "--selector", "-s", help="Scroll inside this element."),
) -> None:
    """Scroll left."""
    result = run_command("scroll", {"direction": "left", "pixels": pixels, "selector": selector or ""})
    print_result(result, json_mode=get_json_mode())


@app.command("right")
def scroll_right(
    pixels: int = typer.Argument(300, help="Pixels to scroll."),
    selector: Optional[str] = typer.Option(None, "--selector", "-s", help="Scroll inside this element."),
) -> None:
    """Scroll right."""
    result = run_command("scroll", {"direction": "right", "pixels": pixels, "selector": selector or ""})
    print_result(result, json_mode=get_json_mode())


@app.command("into")
def scroll_into(selector: str = typer.Argument(..., help="CSS selector of the target element.")) -> None:
    """Scroll an element into view."""
    result = run_command("scroll_into", {"selector": selector})
    print_result(result, json_mode=get_json_mode())


def register_top_level(parent: typer.Typer) -> None:
    @parent.command("scrollinto")
    def _scrollinto(selector: str = typer.Argument(...)) -> None:
        """Scroll element into view."""
        scroll_into(selector)
