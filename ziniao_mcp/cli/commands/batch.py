"""Batch execution — run multiple commands from stdin JSON."""

from __future__ import annotations

import json
import sys

import typer

from .. import get_json_mode, run_command
from ..output import print_result

app = typer.Typer(no_args_is_help=True)


@app.command("run")
def batch_run(
    bail: bool = typer.Option(False, "--bail", help="Stop on first error."),
) -> None:
    """Execute a JSON array of commands from stdin.

    Each element should be: {"command": "...", "args": {...}}

    Example: echo '[{"command":"navigate","args":{"url":"https://example.com"}}]' | ziniao batch run
    """
    raw = sys.stdin.read().strip()
    if not raw:
        typer.echo("Error: no input from stdin", err=True)
        raise typer.Exit(1)

    try:
        commands = json.loads(raw)
    except json.JSONDecodeError as e:
        typer.echo(f"Error: invalid JSON — {e}", err=True)
        raise typer.Exit(1)

    if not isinstance(commands, list):
        typer.echo("Error: input must be a JSON array", err=True)
        raise typer.Exit(1)

    results = []
    for i, cmd in enumerate(commands):
        if not isinstance(cmd, dict) or "command" not in cmd:
            err = {"error": f"Item {i}: must be an object with 'command' key"}
            results.append(err)
            if bail:
                break
            continue

        result = run_command(cmd["command"], cmd.get("args", {}))
        results.append(result)

        if bail and "error" in result:
            break

    if get_json_mode():
        print(json.dumps({"results": results, "total": len(commands), "executed": len(results)},
                         ensure_ascii=False, indent=2))
    else:
        for i, r in enumerate(results):
            typer.echo(f"--- [{i}] ---")
            print_result(r, json_mode=False)


def register_top_level(parent: typer.Typer) -> None:
    pass
