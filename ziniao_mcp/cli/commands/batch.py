"""Batch execution — run multiple commands from stdin JSON."""

from __future__ import annotations

import json
import sys

import typer

from .. import get_json_mode, run_command
from ..help_epilog import GROUP_CLI_EPILOG
from ..output import dumps_cli_json, print_result, set_last_daemon_command

app = typer.Typer(no_args_is_help=True, epilog=GROUP_CLI_EPILOG)


@app.command("run")
def batch_run(
    bail: bool = typer.Option(False, "--bail", help="Stop on first error."),
) -> None:
    """Execute a JSON array of commands from stdin.

    Each element must be: {"command": "<daemon_command>", "args": {...}} — command names match
    dispatch registry (e.g. navigate, snapshot, type_text), not always Typer spellings.

    Stdin must be UTF-8 (e.g. on Windows: Get-Content -Encoding utf8 file.json | ziniao batch run).

    Example: echo '[{"command":"navigate","args":{"url":"https://example.com"}}]' | ziniao batch run
    """
    try:
        raw = sys.stdin.buffer.read().decode("utf-8-sig").strip()
    except (AttributeError, OSError, UnicodeDecodeError):
        if hasattr(sys.stdin, "reconfigure"):
            try:
                sys.stdin.reconfigure(encoding="utf-8")
            except (AttributeError, OSError):
                pass
        raw = sys.stdin.read().strip()
        if raw.startswith("\ufeff"):
            raw = raw[1:]
    if raw.startswith("\ufeff"):
        raw = raw[1:]
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
    executed = 0
    for i, cmd in enumerate(commands):
        if not isinstance(cmd, dict) or "command" not in cmd:
            err = {"error": f"Item {i}: must be an object with 'command' key"}
            results.append(err)
            if bail:
                break
            continue

        executed += 1
        result = run_command(cmd["command"], cmd.get("args", {}))
        results.append(result)

        if bail and "error" in result:
            break

    if get_json_mode():
        set_last_daemon_command("batch_run")
        print(dumps_cli_json({"results": results, "total": len(commands), "executed": executed}))
    else:
        for i, r in enumerate(results):
            typer.echo(f"--- [{i}] ---")
            print_result(r, json_mode=False)


def register_top_level(parent: typer.Typer) -> None:
    pass
