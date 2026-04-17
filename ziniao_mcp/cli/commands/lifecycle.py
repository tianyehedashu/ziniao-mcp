"""Daemon lifecycle and emulation commands."""

from __future__ import annotations

import os
import subprocess
import time
from typing import Optional

import typer

from .. import get_json_mode, run_command
from ..help_epilog import GROUP_CLI_EPILOG
from ..output import print_result

app = typer.Typer(no_args_is_help=True, epilog=GROUP_CLI_EPILOG)


def _kill_stale_ziniao_processes() -> int:
    """Kill all ziniao.exe processes except the current one. Returns count killed."""
    if os.name != "nt":
        return 0
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq ziniao.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return 0
    pids = []
    for line in result.stdout.strip().splitlines():
        parts = line.split(",")
        if len(parts) >= 2 and "ziniao.exe" in parts[0].strip('"').lower():
            try:
                pid = int(parts[1].strip('"'))
                if pid != os.getpid():
                    pids.append(pid)
            except ValueError:
                continue
    killed = 0
    for pid in pids:
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=3)
            killed += 1
        except Exception:
            continue
    return killed


@app.command("quit")
def quit_cmd() -> None:
    """Shut down the daemon and release all sessions."""
    try:
        result = run_command("quit")
        print_result(result, json_mode=get_json_mode())
    except Exception:
        typer.echo("Daemon not reachable, cleaning up stale processes.")
        result = None

    time.sleep(0.5)
    killed = _kill_stale_ziniao_processes()
    if killed:
        typer.echo(f"  Killed {killed} stale ziniao process(es).")


@app.command("emulate")
def emulate(
    device: Optional[str] = typer.Option(None, "--device", help="Device preset name (e.g. 'iPhone 14')."),
    width: int = typer.Option(0, "--width", help="Custom viewport width."),
    height: int = typer.Option(0, "--height", help="Custom viewport height."),
) -> None:
    """Set viewport size or emulate a device."""
    result = run_command("emulate", {"device_name": device or "", "width": width, "height": height})
    print_result(result, json_mode=get_json_mode())


def register_top_level(parent: typer.Typer) -> None:
    @parent.command("quit")
    def _quit() -> None:
        """quit — Stop ziniao daemon (not the same as closing only the browser). Same as ``ziniao sys quit``."""
        quit_cmd()

    @parent.command("emulate")
    def _emulate(
        device: Optional[str] = typer.Option(None, "--device"),
        width: int = typer.Option(0, "--width"),
        height: int = typer.Option(0, "--height"),
    ) -> None:
        """emulate [--device|--width|--height] — Viewport or device emulation. Same as ``ziniao sys emulate``."""
        emulate(device, width, height)
