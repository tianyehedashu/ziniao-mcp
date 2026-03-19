"""Core shared logic between MCP tools and CLI dispatch.

Both the MCP server (tools/) and the CLI daemon (cli/dispatch.py) need to
perform the same browser operations.  This module provides shared async
functions that accept a SessionManager (or equivalent) and return plain
dicts, so both layers can reuse the same implementation.
"""
