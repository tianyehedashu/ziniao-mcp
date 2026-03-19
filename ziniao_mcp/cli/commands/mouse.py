"""Mouse control commands — move, down, up, wheel."""

from __future__ import annotations

from typing import Optional

import typer

from .. import get_json_mode, run_command
from ..output import print_result

app = typer.Typer(no_args_is_help=True)


@app.command("move")
def mouse_move(
    x: float = typer.Argument(..., help="X coordinate."),
    y: float = typer.Argument(..., help="Y coordinate."),
) -> None:
    """Move the mouse to coordinates."""
    result = run_command("mouse_move", {"x": x, "y": y})
    print_result(result, json_mode=get_json_mode())


@app.command("down")
def mouse_down(
    button: str = typer.Argument("left", help="Mouse button: left, right, middle."),
) -> None:
    """Press a mouse button down."""
    result = run_command("mouse_down", {"button": button})
    print_result(result, json_mode=get_json_mode())


@app.command("up")
def mouse_up(
    button: str = typer.Argument("left", help="Mouse button: left, right, middle."),
) -> None:
    """Release a mouse button."""
    result = run_command("mouse_up", {"button": button})
    print_result(result, json_mode=get_json_mode())


@app.command("wheel")
def mouse_wheel(
    delta_y: float = typer.Argument(..., help="Vertical scroll amount."),
    delta_x: float = typer.Argument(0, help="Horizontal scroll amount."),
) -> None:
    """Scroll the mouse wheel."""
    result = run_command("mouse_wheel", {"delta_x": delta_x, "delta_y": delta_y})
    print_result(result, json_mode=get_json_mode())


def register_top_level(parent: typer.Typer) -> None:
    pass
