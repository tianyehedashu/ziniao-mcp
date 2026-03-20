"""Shared Typer epilogs so subcommand groups surface parent/global flags like agent-browser."""

from __future__ import annotations

# Shown under `ziniao <group> --help` (nav, act, info, …).
GROUP_CLI_EPILOG = (
    "Parent options (before the group name), same as root CLI: "
    "--store, --session, --json, --json-legacy, --llm, --plain, --timeout. "
    "Example: ziniao --llm nav go https://example.com\n"
    "Full root help: ziniao --help\n"
    "vs agent-browser CLI: docs/cli-agent-browser-parity.md\n"
    "JSON: docs/cli-json.md | LLM-oriented I/O: docs/cli-llm.md"
)
