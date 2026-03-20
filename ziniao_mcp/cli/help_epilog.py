"""Shared Typer epilogs so subcommand groups surface parent/global flags like agent-browser."""

from __future__ import annotations

# Shown under `ziniao <group> --help` (nav, act, info, …).
GROUP_CLI_EPILOG = (
    "Parent options (before the group name), same as root CLI: "
    "--store, --session, --json, --json-legacy, --content-boundaries, --max-output, --timeout; "
    "env ZINIAO_JSON / ZINIAO_CONTENT_BOUNDARIES / ZINIAO_MAX_OUTPUT (agent-browser-style).\n"
    "Example: ziniao --json --content-boundaries info snapshot\n"
    "Full root help: ziniao --help\n"
    "Parity: docs/cli-agent-browser-parity.md | JSON: docs/cli-json.md | Agents: docs/cli-llm.md"
)
