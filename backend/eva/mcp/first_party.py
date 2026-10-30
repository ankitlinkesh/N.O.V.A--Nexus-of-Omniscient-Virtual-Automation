"""Route native tools through NOVA's own MCP servers (Phase 160).

Off unless EVA_FIRST_PARTY_MCP is set ("1"/"all" for every domain, or a list such as
"spotify,youtube"). When on, each tool a domain owns keeps its ToolSpec -- name, description,
schema, gate class, planner visibility, verifiers -- and only its handler changes: it now calls
the domain's MCP server. The gate in ToolRegistry is untouched, so a send still stops at a pending
action; the server then re-checks with an approval token that this module mints only when the
call arrives with the registry's own post-approval ``confirmed`` flag.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from . import client
from ..core.data_paths import data_path
from .config import REPO_ROOT, McpServerConfig
from .domain_server import APPROVAL_ARG, SECRET_ENV, is_gated, mint_approval
from .domains import DOMAIN_TOOLS

_FALSY = {"", "0", "false", "no", "off"}
# One secret per NOVA process. It is handed to each server at spawn and never written anywhere.
_SECRET = secrets.token_hex(32)


def enabled_domains() -> list[str]:
    raw = os.environ.get("EVA_FIRST_PARTY_MCP", "").strip().lower()
    if raw in _FALSY:
        return []
    if raw in {"1", "true", "yes", "on", "all"}:
        return list(DOMAIN_TOOLS)
    wanted = {part for part in raw.replace(",", " ").split() if part}
    return [domain for domain in DOMAIN_TOOLS if domain in wanted]


def draft_state_path() -> Path:
    raw = os.environ.get("EVA_DRAFT_STATE_PATH", "").strip()
    return Path(raw) if raw else data_path(Path("mcp_gmail_draft.json"))


def server_config(domain: str) -> McpServerConfig:
    # A stdio child gets only the SDK's default environment plus what is named here, so carry the
    # EVA_* settings across (real-input switch, data paths) along with the secret.
    env = {key: value for key, value in os.environ.items() if key.startswith("EVA_") and key != "EVA_FIRST_PARTY_MCP"}
    env["EVA_FIRST_PARTY_MCP"] = "0"
    env.update({"PYTHONPATH": str(REPO_ROOT), SECRET_ENV: _SECRET, "EVA_DRAFT_STATE_PATH": str(draft_state_path())})
    return McpServerConfig(
        name=f"eva-{domain}",
        transport="stdio",
        command=sys.executable,
        args=("-m", f"backend.eva.mcp.servers.{domain}"),
        env=env,
        trusted=True,
    )


def _unwrap(response: dict[str, Any]) -> dict[str, Any]:
    """Turn the client's transport result back into the dict the native handler returned."""
    text = response.get("content")
    if isinstance(text, str):
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed
        return {"ok": bool(response.get("ok")), "message": text}
    return {"ok": False, "mcp_transport_failed": True, "error": str(response.get("error") or "MCP server gave no result.")}


def _dispatcher(domain: str, spec: Any, accepts_confirmed: bool) -> Callable[..., Any]:
    gated = is_gated(spec)
    original = spec.handler

    def handler(**kwargs: Any) -> Any:
        confirmed = bool(kwargs.pop("confirmed", False))
        # A handler that checks `confirmed` itself is only approved when the registry's
        # post-approval replay set it; one that does not is only reachable after approval anyway.
        approved = confirmed if accepts_confirmed else True
        payload = dict(kwargs)
        if gated and approved:
            payload[APPROVAL_ARG] = mint_approval(spec.name, kwargs, _SECRET)
        result = _unwrap(client.call_tool(server_config(domain), spec.name, payload))
        # A server that would not start must not take Spotify down with it. Only never-run,
        # non-gated tools fall back to the in-process handler: a gated one may already have acted.
        if result.get("mcp_transport_failed") and not gated:
            return original(**kwargs)
        return result

    if accepts_confirmed:
        # Expose `confirmed` so the registry's approved-replay still injects it.
        def handler_with_confirmed(confirmed: bool = False, **kwargs: Any) -> Any:
            return handler(confirmed=confirmed, **kwargs)

        return handler_with_confirmed
    return handler


def apply_first_party(tools: dict[str, Any]) -> list[str]:
    """Swap the handler of every enabled domain's tools for an MCP call; returns the tool names."""
    from ..tools.registry import _handler_accepts_confirmed

    redirected: list[str] = []
    domains = enabled_domains()
    if "gmail" in domains:
        # NOVA reads the draft too (the "send" shortcut), so both processes share it through a file.
        from ..tools import email_tools

        email_tools.share_draft_state(draft_state_path())
    for domain in domains:
        for name in DOMAIN_TOOLS[domain]:
            spec = tools.get(name)
            if spec is None:
                continue
            accepts = _handler_accepts_confirmed(spec.handler)
            tools[name] = replace(spec, handler=_dispatcher(domain, spec, accepts))
            redirected.append(name)
    return redirected
