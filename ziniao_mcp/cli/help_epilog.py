"""Shared Typer epilog for command groups (nav, act, info, …)."""

from __future__ import annotations

# Shown under `ziniao <group> --help`.
GROUP_CLI_EPILOG = (
    "Parent options (before the group name), same as root CLI: "
    "--store, --session, --json, --json-legacy, --content-boundaries, --max-output, --timeout; "
    "env ZINIAO_JSON / ZINIAO_CONTENT_BOUNDARIES / ZINIAO_MAX_OUTPUT.\n"
    "Example: ziniao --json --content-boundaries info snapshot\n"
    "See: ziniao --help"
)
