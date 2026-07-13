from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from .config import McpServerConfig
from .runner import run_async


@asynccontextmanager
async def _session(server: McpServerConfig) -> AsyncIterator[ClientSession]:
    """Open a per-call MCP session for the given server config. Connects,
    initializes, yields, and tears down on exit -- simple and correct for now
    (no persistent connection pooling)."""
    if server.transport == "stdio":
        params = StdioServerParameters(command=server.command, args=list(server.args), env=server.env or None)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
    elif server.transport == "http":
        async with streamablehttp_client(server.url) as (read, write, _get_session_id):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
    else:
        raise ValueError(f"Unsupported MCP transport: {server.transport}")


async def _discover(server: McpServerConfig) -> list[dict[str, Any]]:
    async with _session(server) as session:
        resp = await session.list_tools()
        return [
            {
                "name": t.name,
                "description": t.description or "",
                "input_schema": (t.inputSchema or {"type": "object", "properties": {}}),
            }
            for t in resp.tools
        ]


def _content_to_text(result: Any) -> str:
    parts: list[str] = []
    content = getattr(result, "content", None) or []
    for item in content:
        text = getattr(item, "text", None)
        if text:
            parts.append(str(text))
    if parts:
        return "\n".join(parts)
    return str(result)


async def _call(server: McpServerConfig, tool_name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    try:
        async with _session(server) as session:
            result = await session.call_tool(tool_name, arguments or {})
            return {"ok": not getattr(result, "isError", False), "content": _content_to_text(result)}
    except Exception as exc:  # noqa: BLE001 - surfaced to caller as a gated tool result
        return {"ok": False, "error": str(exc)}


def discover_tools(server: McpServerConfig) -> list[dict[str, Any]]:
    """Sync wrapper for the registry: list tools exposed by an MCP server."""
    return run_async(_discover(server))


def call_tool(server: McpServerConfig, tool_name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    """Sync wrapper for the registry: invoke a single MCP tool call."""
    try:
        return run_async(_call(server, tool_name, arguments))
    except Exception as exc:  # noqa: BLE001 - never let a transport error escape as a raw exception
        return {"ok": False, "error": str(exc)}
