"""Browser cluster: lease bookkeeping and combined status."""

from __future__ import annotations

import typer

from .. import get_json_mode, run_command
from ..help_epilog import GROUP_CLI_EPILOG
from ..output import print_result

app = typer.Typer(no_args_is_help=True, epilog=GROUP_CLI_EPILOG)


@app.command("status")
def cluster_status() -> None:
    """Show cluster.json leases and daemon sessions."""
    result = run_command("cluster", {"action": "status"})
    print_result(result, json_mode=get_json_mode())


@app.command("acquire")
def cluster_acquire(
    session_id: str = typer.Option(
        "",
        "--session",
        "-s",
        help="Session id (default: current active session).",
    ),
    ttl_sec: float = typer.Option(600.0, "--ttl", help="Lease TTL in seconds."),
    owner: str = typer.Option("", "--owner", help="Optional owner label."),
    label: str = typer.Option("", "--label", help="Optional task label."),
) -> None:
    """Acquire a lease row for a session (persisted under ~/.ziniao/cluster.json)."""
    result = run_command(
        "cluster",
        {
            "action": "acquire",
            "session_id": session_id,
            "ttl_sec": ttl_sec,
            "owner": owner,
            "label": label,
        },
    )
    print_result(result, json_mode=get_json_mode())


@app.command("release")
def cluster_release(
    lease_id: str = typer.Argument(..., help="Lease id returned by cluster acquire."),
) -> None:
    """Release a lease by id."""
    result = run_command("cluster", {"action": "release", "lease_id": lease_id})
    print_result(result, json_mode=get_json_mode())


def register_top_level(root: typer.Typer) -> None:
    root.add_typer(app, name="cluster", help="Cluster leases and status (~/.ziniao/cluster.json).")
