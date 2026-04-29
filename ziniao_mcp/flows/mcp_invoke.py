"""Invoke MCP tools for ``external_call`` with ``kind: mcp`` (stdio server or HTTP bridge)."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import timedelta
from typing import Any

import httpx

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, get_default_environment, stdio_client


async def invoke_mcp_tool(
    *,
    policy: dict[str, Any],
    server: str,
    tool: str,
    arguments: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    """Call an MCP tool via configured HTTP bridge or stdio server."""
    mcp_cfg = (policy.get("external_call") or {}).get("mcp") or {}
    bridge = (mcp_cfg.get("http_bridge_url") or os.environ.get("ZINIAO_MCP_HTTP_BRIDGE") or "").strip()
    if bridge:
        payload = {"server": server, "tool": tool, "arguments": arguments}
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(bridge, json=payload)
        try:
            body: Any = resp.json()
        except json.JSONDecodeError:
            body = {"text": resp.text[:8192]}
        return {"ok": resp.status_code < 400, "status": resp.status_code, "result": body}

    servers = mcp_cfg.get("servers") or {}
    spec = servers.get(server)
    if not isinstance(spec, dict):
        return {
            "error": (
                "external_call mcp: configure policy external_call.mcp.servers["
                f"{server!r}] with {{command, args}} or set http_bridge_url / "
                "ZINIAO_MCP_HTTP_BRIDGE."
            ),
        }

    command = spec.get("command")
    args = list(spec.get("args") or [])
    env = spec.get("env")
    cwd = spec.get("cwd")
    if not command:
        return {"error": "mcp server config missing 'command'."}

    merged_env = {**get_default_environment(), **env} if isinstance(env, dict) else None
    params = StdioServerParameters(
        command=str(command),
        args=[str(a) for a in args],
        env=merged_env,
        cwd=str(cwd) if cwd else None,
    )

    async def _call_stdio() -> Any:
        async with stdio_client(params) as streams:
            read, write = streams
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=timeout)
                return await session.call_tool(
                    name=tool,
                    arguments=arguments or {},
                    read_timeout_seconds=timedelta(seconds=timeout),
                )

    try:
        result = await asyncio.wait_for(_call_stdio(), timeout=timeout + 1)
    except asyncio.TimeoutError:
        return {"error": f"external_call mcp timed out after {timeout}s."}
    text_parts: list[str] = []
    if result.content:
        for block in result.content:
            if getattr(block, "text", None):
                text_parts.append(str(block.text))
    merged = "\n".join(text_parts) if text_parts else ""
    try:
        parsed = json.loads(merged) if merged.strip().startswith("{") else merged
    except json.JSONDecodeError:
        parsed = merged
    is_err = bool(getattr(result, "isError", False))
    return {"ok": not is_err, "value": parsed, "is_error": is_err}
