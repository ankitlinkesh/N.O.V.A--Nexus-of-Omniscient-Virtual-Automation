from __future__ import annotations

from typing import Any

from ..tools.registry import ToolRegistry, ToolSpec, register_mcp_tool_specs
from . import client, pins, trust
from .config import McpServerConfig, load_mcp_config, mcp_enabled


def _mcp_call_with_budget(server: McpServerConfig, tool_name: str, kwargs: dict[str, Any]) -> Any:
    """Phase 40c: enforce the per-server call budget before invoking an MCP tool."""
    if trust.budget_exceeded(server.name):
        return {"ok": False, "blocked": True, "error": f"MCP server '{server.name}' exceeded its per-server call budget."}
    trust.record_call(server.name)
    return client.call_tool(server, tool_name, kwargs)


def _schema_or_default(schema: Any) -> dict[str, Any]:
    if isinstance(schema, dict):
        return schema
    return {"type": "object", "properties": {}}


# Tools left out of the last build because their definition changed or looked hostile, for the load report.
LAST_WITHHELD: list[dict[str, str]] = []


def build_mcp_tool_specs(servers: list[McpServerConfig]) -> dict[str, ToolSpec]:
    """Discover tools from each configured MCP server and build gated
    ToolSpecs for them. Every MCP tool is confirm-class: safety_level is
    "sensitive" and requires_confirmation is True, so the tool gate always
    routes it through confirmation and it never auto-executes. One bad
    server's discovery failure does not abort the others.

    Phase 40c: only servers trusted under the MCP trust model are registered —
    an untrusted (unpinned) server's tools are never exposed to the agent."""
    specs: dict[str, ToolSpec] = {}
    LAST_WITHHELD.clear()
    servers = trust.filter_trusted(list(servers))
    for server in servers:
        try:
            discovered = client.discover_tools(server)
        except Exception:  # noqa: BLE001 - a broken server must not break the others
            continue

        for tool in discovered:
            try:
                tool_name = tool["name"]
                full_name = f"mcp.{server.name}.{tool_name}"
                # A server that changes a tool after it was trusted, or ships one whose description reads
                # like instructions, does not get that tool offered (see pins.py).
                status, why = pins.review(server.name, tool)
                if status in {"changed", "quarantined"}:
                    LAST_WITHHELD.append({"tool": full_name, "status": status, "reason": why})
                    continue
                description = tool.get("description") or f"MCP tool {tool_name} from server {server.name}."
                args_schema = _schema_or_default(tool.get("input_schema"))
                spec = ToolSpec(
                    name=full_name,
                    description=description,
                    args_schema=args_schema,
                    safety_level="sensitive",
                    handler=lambda _s=server, _t=tool_name, **kwargs: _mcp_call_with_budget(_s, _t, kwargs),
                    category="mcp",
                    risk="medium",
                    action_type="MCP_TOOL_CALL",
                    risk_categories=("MCP_TOOL_CALL",),
                    requires_confirmation=True,
                )
                specs[full_name] = spec
            except Exception:  # noqa: BLE001 - one malformed tool entry must not break the rest
                continue

    return specs


def load_mcp_tools(registry: ToolRegistry | None = None) -> dict[str, Any]:
    """Entry point for the orchestrator (NOT wired into main.py/startup here):
    discovers and registers MCP tools if, and only if, EVA_MCP_ENABLED is
    truthy and servers are configured. Fully inert otherwise."""
    if not mcp_enabled():
        return {"enabled": False, "loaded": 0}

    servers = load_mcp_config()
    specs = build_mcp_tool_specs(servers)
    register_mcp_tool_specs(specs)
    if registry is not None:
        registry._tools.update(specs)

    return {
        "enabled": True,
        "servers": len(servers),
        "loaded": len(specs),
        "tools": sorted(specs),
        "withheld": list(LAST_WITHHELD),
    }
