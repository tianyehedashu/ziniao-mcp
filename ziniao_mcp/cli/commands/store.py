"""Store management commands."""

from __future__ import annotations


import typer

from ...site_policy import policy_hint_for_url
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


@app.command("passive-open")
def passive_open_store(
    store_id: str = typer.Argument(..., help="Store ID to open in passive mode."),
) -> None:
    """Open a Ziniao store **without** attaching nodriver/stealth.

    The desktop client still launches the browser and reports a ``cdp_port``,
    but the daemon stops there: no CDP Runtime attach, no JS injection, no
    ``StoreSession`` registered. Continue the workflow with
    ``ziniao chrome passive-open --port <cdp_port>`` (or ``--save-as`` for
    a reusable alias) and ``ziniao chrome input ...`` for raw ``Input.*``
    events. Recommended for Shopee-class anti-bot sites.
    """
    result = run_command("open_store_passive", {"store_id": store_id})
    if isinstance(result, dict) and result.get("ok"):
        # Hint primarily off launcher_page (the URL Ziniao opens by default).
        url_for_hint = result.get("launcher_page") or ""
        hint = policy_hint_for_url(url_for_hint) if url_for_hint else None
        if hint:
            result["policy_hint"] = hint
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
        """list-stores [--opened-only] — List Ziniao stores. Same as ``ziniao store list``."""
        list_stores(opened_only)

    @parent.command("open-store")
    def _open_store(store_id: str = typer.Argument(..., help="Store ID.")) -> None:
        """open-store <id> — Open store and connect CDP. Same as ``ziniao store open``."""
        open_store(store_id)

    @parent.command("passive-open-store")
    def _passive_open_store(store_id: str = typer.Argument(..., help="Store ID.")) -> None:
        """passive-open-store <id> — Open store without CDP attach. Same as ``ziniao store passive-open``."""
        passive_open_store(store_id)

    @parent.command("close-store")
    def _close_store(store_id: str = typer.Argument(..., help="Store ID.")) -> None:
        """close-store <id> — Close store. Same as ``ziniao store close``."""
        close_store(store_id)
