"""Recorder commands."""

from __future__ import annotations

from typing import Optional

import typer

from .. import get_json_mode, run_command
from ..output import print_result

app = typer.Typer(no_args_is_help=True)


@app.command("start")
def start() -> None:
    """Start recording browser actions."""
    result = run_command("recorder", {"action": "start"})
    print_result(result, json_mode=get_json_mode())


@app.command("stop")
def stop(name: Optional[str] = typer.Option(None, "--name", help="Recording name.")) -> None:
    """Stop recording and save."""
    result = run_command("recorder", {"action": "stop", "name": name or ""})
    print_result(result, json_mode=get_json_mode())


@app.command("replay")
def replay(
    name: Optional[str] = typer.Argument(None, help="Recording name to replay."),
    actions_json: Optional[str] = typer.Option(None, "--actions-json", help="JSON actions to replay."),
    speed: float = typer.Option(1.0, "--speed", help="Replay speed multiplier."),
) -> None:
    """Replay a saved recording."""
    result = run_command("recorder", {
        "action": "replay", "name": name or "", "actions_json": actions_json or "", "speed": speed,
    })
    print_result(result, json_mode=get_json_mode())


@app.command("list")
def list_recordings() -> None:
    """List all saved recordings."""
    result = run_command("recorder", {"action": "list"})
    print_result(result, json_mode=get_json_mode())


@app.command("delete")
def delete(name: str = typer.Argument(..., help="Recording name to delete.")) -> None:
    """Delete a saved recording."""
    result = run_command("recorder", {"action": "delete", "name": name})
    print_result(result, json_mode=get_json_mode())
