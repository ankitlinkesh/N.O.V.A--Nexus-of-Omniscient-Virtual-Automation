"""First-party domain MCP servers (Phase 160).

``build_server(domain)`` serves a domain's existing native tools over MCP without rewriting them:
it reads each ToolSpec from the registry, advertises the same description and argument schema,
and calls the same handler. What it adds is the gate. A tool the registry treats as gated
(confirm-class or not "safe") is only executed when the call carries an ``_approval`` token that
only NOVA's confirmation flow can mint -- an HMAC over the tool name and its exact arguments,
keyed by a per-process secret handed to the server at spawn. A client that connects to the
server directly, or a model that invents the argument, gets ``needs_confirmation`` back and
nothing runs. ``confirmed`` is never accepted from a caller; it is set here only after the
token verifies.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
from dataclasses import asdict
from typing import Any

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from .domains import DOMAIN_TOOLS

APPROVAL_ARG = "_approval"
SECRET_ENV = "EVA_MCP_APPROVAL_SECRET"
_NEVER_TRUSTED_ARGS = (APPROVAL_ARG, "confirmed")


def _canonical(tool: str, args: dict[str, Any]) -> str:
    clean = {key: value for key, value in args.items() if key not in _NEVER_TRUSTED_ARGS}
    return tool + ":" + json.dumps(clean, sort_keys=True, default=str)


def mint_approval(tool: str, args: dict[str, Any], secret: str | None = None) -> str:
    key = (secret if secret is not None else os.environ.get(SECRET_ENV, "")).encode()
    if not key:
        return ""
    return hmac.new(key, _canonical(tool, args).encode(), hashlib.sha256).hexdigest()


def verify_approval(tool: str, args: dict[str, Any], token: Any, secret: str | None = None) -> bool:
    expected = mint_approval(tool, args, secret)
    return bool(expected) and bool(token) and hmac.compare_digest(expected, str(token))


def is_gated(spec: Any) -> bool:
    return bool(spec.requires_confirmation) or spec.safety_level != "safe"


def _annotations(spec: Any) -> types.ToolAnnotations:
    gated = is_gated(spec)
    read_only = (not gated) and spec.action_type in {"SAFE_LOCAL_READ", "NETWORK_ACTION"}
    return types.ToolAnnotations(readOnlyHint=read_only, destructiveHint=gated)


def _advertised_schema(spec: Any) -> dict[str, Any]:
    schema = json.loads(json.dumps(spec.args_schema))
    props = dict(schema.get("properties") or {})
    props.pop("confirmed", None)
    if is_gated(spec):
        props[APPROVAL_ARG] = {"type": "string", "description": "Approval token minted by the NOVA confirmation gate."}
    schema["properties"] = props
    schema["required"] = [name for name in schema.get("required", []) if name != "confirmed"]
    return schema


def execute(spec: Any, arguments: dict[str, Any] | None, secret: str | None = None) -> Any:
    """Run one tool the way the registry would, enforcing the approval token for gated tools."""
    from ..tools.registry import _handler_accepts_confirmed

    args = dict(arguments or {})
    token = args.pop(APPROVAL_ARG, "")
    args.pop("confirmed", None)
    if is_gated(spec):
        if not verify_approval(spec.name, args, token, secret):
            return {
                "ok": False,
                "needs_confirmation": True,
                "message": f"{spec.name} needs confirmation and no valid approval came with the call, so nothing ran.",
            }
        if _handler_accepts_confirmed(spec.handler):
            args["confirmed"] = True
    result = spec.handler(**args)
    return asdict(result) if hasattr(result, "__dataclass_fields__") else result


def build_server(domain: str, registry: Any = None) -> Server:
    from ..tools.registry import ToolRegistry

    names = DOMAIN_TOOLS[domain]
    # A server runs its tools in-process. Were routing left on, its registry would redirect every
    # tool back to a new server process, and so on without end.
    os.environ["EVA_FIRST_PARTY_MCP"] = "0"
    registry = registry or ToolRegistry()
    specs = {name: registry.get(name) for name in names}
    missing = [name for name, spec in specs.items() if spec is None]
    if missing:
        raise RuntimeError(f"eva-{domain} cannot start, tools missing from the registry: {missing}")

    server = Server(f"eva-{domain}")

    @server.list_tools()
    async def _list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name=name,
                description=spec.description,
                inputSchema=_advertised_schema(spec),
                annotations=_annotations(spec),
            )
            for name, spec in specs.items()
        ]

    @server.call_tool()
    async def _call_tool(tool_name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
        spec = specs.get(tool_name)
        if spec is None:
            raise ValueError(f"Unknown tool: {tool_name}")
        result = await asyncio.to_thread(execute, spec, arguments)
        return [types.TextContent(type="text", text=json.dumps(result, default=str))]

    return server


async def _serve(server: Server) -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def serve(domain: str) -> None:
    asyncio.run(_serve(build_server(domain)))
