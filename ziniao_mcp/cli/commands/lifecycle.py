"""Daemon lifecycle and emulation commands."""

from __future__ import annotations

from typing import Optional

import typer

from .. import get_json_mode, run_command
from ..help_epilog import GROUP_CLI_EPILOG
from ..output import print_result

app = typer.Typer(no_args_is_help=True, epilog=GROUP_CLI_EPILOG)


@app.command("quit")
def quit_cmd() -> None:
    """Shut down the daemon and release all sessions."""
    result = run_command("quit")
    print_result(result, json_mode=get_json_mode())


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
        """Shut down the daemon."""
        quit_cmd()

    @parent.command("emulate")
    def _emulate(
        device: Optional[str] = typer.Option(None, "--device"),
        width: int = typer.Option(0, "--width"),
        height: int = typer.Option(0, "--height"),
    ) -> None:
        """Set viewport or emulate a device."""
        emulate(device, width, height)
