"""Store management commands."""

from __future__ import annotations

from typing import Optional

import typer

from .. import get_json_mode, run_command
from ..help_epilog import GROUP_CLI_EPILOG
from ..output import print_result

app = typer.Typer(no_args_is_help=True, epilog=GROUP_CLI_EPILOG)


@app.command("list")
def list_stores(
    opened_only: bool = typer.Option(False, "--opened-only", help="Only show currently opened stores."),
) -> None:
    """List Ziniao stores."""
    result = run_command("list_stores", {"opened_only": opened_only})
    print_result(result, json_mode=get_json_mode())


@app.command("open")
def open_store(store_id: str = typer.Argument(..., help="Store ID to open.")) -> None:
    """Open a Ziniao store and connect via CDP."""
    result = run_command("open_store", {"store_id": store_id})
    print_result(result, json_mode=get_json_mode())


@app.command("close")
def close_store(store_id: str = typer.Argument(..., help="Store ID to close.")) -> None:
    """Close a Ziniao store."""
    result = run_command("close_store", {"store_id": store_id})
    print_result(result, json_mode=get_json_mode())


@app.command("start-client")
def start_client() -> None:
    """Start the Ziniao client process."""
    result = run_command("start_client")
    print_result(result, json_mode=get_json_mode())


@app.command("stop-client")
def stop_client() -> None:
    """Stop the Ziniao client process."""
    result = run_command("stop_client")
    print_result(result, json_mode=get_json_mode())


def register_top_level(parent: typer.Typer) -> None:
    """Register top-level shortcuts on the parent app."""

    @parent.command("list-stores")
    def _list_stores(
        opened_only: bool = typer.Option(False, "--opened-only", help="Only show currently opened stores."),
    ) -> None:
        """List Ziniao stores."""
        list_stores(opened_only)

    @parent.command("open-store")
    def _open_store(store_id: str = typer.Argument(..., help="Store ID.")) -> None:
        """Open a Ziniao store."""
        open_store(store_id)

    @parent.command("close-store")
    def _close_store(store_id: str = typer.Argument(..., help="Store ID.")) -> None:
        """Close a Ziniao store."""
        close_store(store_id)
