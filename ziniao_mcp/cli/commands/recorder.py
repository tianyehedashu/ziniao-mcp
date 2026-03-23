"""Recorder commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from .. import get_json_mode, run_command
from ..help_epilog import GROUP_CLI_EPILOG
from ..output import print_result

_REC_EPILOG = (
    GROUP_CLI_EPILOG
    + "\n\nRecorder flow: ziniao rec start, perform actions in the browser, then "
    "ziniao rec stop [--name] [--force]. List: ziniao rec list; inspect JSON: "
    "ziniao rec view NAME [--metadata-only] [-o file.json]; replay: "
    "ziniao rec replay NAME or --actions-json '...'. Status: ziniao rec status."
)

app = typer.Typer(
    help=(
        "Record clicks, fills, keys, and navigation in the active tab; stop saves JSON plus a generated script.\n\n"
        "Flow: rec start → interact in the browser → rec stop [--name] [--force]. "
        "Then rec list | rec view NAME | rec replay NAME | rec delete NAME. "
        "rec status shows whether a capture is active."
    ),
    no_args_is_help=True,
    epilog=_REC_EPILOG,
)


@app.command("start")
def start() -> None:
    """Inject recorder into the page and begin capturing actions until `rec stop`."""
    result = run_command("recorder", {"action": "start"})
    print_result(result, json_mode=get_json_mode())


@app.command("stop")
def stop(
    name: Optional[str] = typer.Option(None, "--name", help="Save under this name; omit for auto `rec_YYYYMMDD_HHMMSS`."),
    force: bool = typer.Option(False, "--force", help="Overwrite existing file if --name matches a saved recording."),
) -> None:
    """Stop capture, write recording files, and clear injected recorder state."""
    result = run_command("recorder", {"action": "stop", "name": name or "", "force": force})
    print_result(result, json_mode=get_json_mode())


@app.command("replay")
def replay(
    name: Optional[str] = typer.Argument(
        None,
        help="Saved recording name (output of `ziniao rec list`).",
        show_default=False,
    ),
    actions_json: Optional[str] = typer.Option(
        None,
        "--actions-json",
        help="Inline JSON array of actions; overrides NAME when both given.",
    ),
    speed: float = typer.Option(1.0, "--speed", help="Replay speed multiplier (default 1.0)."),
) -> None:
    """Replay from disk by name, or from `--actions-json`.

    Examples:

        ziniao rec list
        ziniao rec replay my_recording
        ziniao rec replay --actions-json '[{"type":"click","selector":"#btn"}]'
    """
    n = (name or "").strip()
    j = (actions_json or "").strip()
    if not n and not j:
        typer.echo(
            "Error: replay needs a recording name or --actions-json.\n"
            "  ziniao rec list                    # show saved names\n"
            "  ziniao rec replay RECORDING_NAME   # replay a saved file\n"
            "  ziniao rec replay --actions-json '[{...}]'  # replay inline JSON",
            err=True,
        )
        raise typer.Exit(code=2)
    result = run_command("recorder", {
        "action": "replay", "name": n, "actions_json": j, "speed": speed,
    })
    print_result(result, json_mode=get_json_mode())


@app.command("view")
def view_recording(
    name: str = typer.Argument(..., help="Recording name (as shown by `ziniao rec list`)."),
    metadata_only: bool = typer.Option(
        False,
        "--metadata-only",
        help="Omit the actions array (faster; no step payloads).",
    ),
    full: bool = typer.Option(
        False,
        "--full",
        help="Include full actions in the daemon response (human mode still summarizes in the terminal).",
    ),
    out_file: Optional[str] = typer.Option(
        None,
        "--out-file",
        "-o",
        help="Write the on-disk JSON payload (same shape as ~/.ziniao/recordings/NAME.json) to this path.",
    ),
) -> None:
    """Load a saved recording. Fill values may be sensitive; avoid sharing exports.

    Human mode defaults to metadata-only unless --full or -o (full fetch for export).
    JSON mode (--json) returns the full recording unless --metadata-only.
    """
    json_mode = get_json_mode()
    if out_file:
        meta_only = False
    elif json_mode:
        meta_only = metadata_only
    elif metadata_only:
        meta_only = True
    elif full:
        meta_only = False
    else:
        meta_only = True

    result = run_command("recorder", {
        "action": "view",
        "name": name.strip(),
        "metadata_only": meta_only,
    })

    if "error" in result:
        print_result(result, json_mode=json_mode)
        raise typer.Exit(code=1)

    if out_file:
        rec = result.get("recording")
        if not isinstance(rec, dict):
            typer.echo("Error: invalid view response (missing recording).", err=True)
            raise typer.Exit(code=1)
        path = Path(out_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        n_act = len(rec.get("actions") or [])
        typer.echo(f"Wrote recording ({n_act} actions) to {path.resolve()}")
        if not json_mode:
            return
        # JSON mode: still print envelope summary
        brief = {
            "status": "ok",
            "path": result.get("path", ""),
            "written_to": str(path.resolve()),
            "action_count": n_act,
            "message": f"Recording written to {path.resolve()}",
        }
        print_result(brief, json_mode=json_mode)
        return

    print_result(result, json_mode=json_mode)


@app.command("status")
def recording_status() -> None:
    """Show whether the current session is recording and the start URL if known."""
    result = run_command("recorder", {"action": "status"})
    print_result(result, json_mode=get_json_mode())


@app.command("list")
def list_recordings() -> None:
    """List saved recording names (use as `ziniao rec replay NAME`)."""
    result = run_command("recorder", {"action": "list"})
    print_result(result, json_mode=get_json_mode())


@app.command("delete")
def delete(name: str = typer.Argument(..., help="Recording name to remove (same as in `rec list`).")) -> None:
    """Delete a saved recording from disk."""
    result = run_command("recorder", {"action": "delete", "name": name})
    print_result(result, json_mode=get_json_mode())
