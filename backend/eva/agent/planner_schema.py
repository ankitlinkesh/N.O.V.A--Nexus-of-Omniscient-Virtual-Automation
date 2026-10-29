"""Constrain the planner's final JSON to its real decision shape (local llama.cpp only).

A small local model sometimes emits JSON the planner cannot parse, or calls a tool that is not
on the menu. llama.cpp can force the reply to match a JSON schema, which removes both. What it
cannot do is make the model's decision correct, and the 2026 studies the research notes cite
found that forcing a schema over *everything* made small models call fewer tools. So this
forces only the final decision object and keeps the free-text ``reason`` FIRST, which gives
the model room to think before it commits to a tool:

    {"reason": ..., "type": ..., "tool_calls": [{"tool": <one of the menu tools>, "args": {...}}],
     "final_response": ..., "continue_after_tools": ...}

``tool_calls`` is a union over only the tools on this step's menu (see ``tool_menu``), each with
its own small args schema, so the grammar stays small (a 90-way union was rejected by llama.cpp
in one report). Switch: ``EVA_PLANNER_SCHEMA`` = ``auto`` (default: on only for a local endpoint),
``on`` or ``off``. A server that rejects the schema is retried without it by the provider, so
this can only add structure, never block a plan.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}
# Above this many tools the per-tool union is too big for llama.cpp's grammar builder (one report saw a
# 90-way union rejected), so the shape is still enforced but the tool name is left a plain string.
MAX_UNION_TOOLS = 30
_KEEP = {"type", "properties", "required", "enum", "items", "minimum", "maximum", "description"}


def local_endpoint() -> bool:
    host = urlparse(os.environ.get("CLOD_BASE_URL", "") or "").hostname or ""
    return host.lower() in _LOCAL_HOSTS


def schema_enabled() -> bool:
    mode = os.environ.get("EVA_PLANNER_SCHEMA", "auto").strip().lower()
    if mode in {"off", "0", "false", "no"}:
        return False
    if mode in {"on", "1", "true", "yes"}:
        return True
    return local_endpoint() and os.environ.get("EVA_LLM_MODE", "").strip().lower() == "clod"


def _clean(schema: Any) -> Any:
    """Keep only the schema keywords llama.cpp's grammar builder handles reliably."""
    if isinstance(schema, list):
        return [_clean(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    cleaned: dict[str, Any] = {}
    for key, value in schema.items():
        if key == "properties" and isinstance(value, dict):
            cleaned[key] = {name: _clean(sub) for name, sub in value.items()}
        elif key in _KEEP and key != "description":
            cleaned[key] = _clean(value)
    return cleaned


def _tool_schema(spec: dict[str, Any]) -> dict[str, Any]:
    args = _clean(spec.get("args_schema") or {"type": "object", "properties": {}})
    if not isinstance(args, dict) or args.get("type") != "object":
        args = {"type": "object", "properties": {}}
    args.setdefault("properties", {})
    # Closed objects: the model can no longer invent plausible-sounding arguments.
    args["additionalProperties"] = False
    return {
        "type": "object",
        "properties": {"tool": {"const": str(spec["name"])}, "args": args},
        "required": ["tool", "args"],
    }


def _generic_call() -> dict[str, Any]:
    return {"type": "object", "properties": {"tool": {"type": "string"}, "args": {"type": "object"}}, "required": ["tool", "args"]}


def decision_schema(specs: list[dict[str, Any]], *, mode: str) -> dict[str, Any]:
    types = ["answer", "tool_calls", "confirmation_required"] + ([] if mode == "single_turn" else ["done"])
    properties: dict[str, Any] = {
        "reason": {"type": "string"},
        "type": {"enum": types},
        "tool_calls": {
            "type": "array",
            "maxItems": 3 if mode == "single_turn" else 2,
            "items": {"anyOf": [_tool_schema(spec) for spec in specs]} if 0 < len(specs) <= MAX_UNION_TOOLS else _generic_call(),
        },
        "final_response": {"type": "string"},
        "action": {"type": "string"},
        "continue_after_tools": {"type": "boolean"},
    }
    return {"type": "object", "properties": properties, "required": ["reason", "type"]}


def response_format(specs: list[dict[str, Any]], *, mode: str) -> dict[str, Any]:
    return {"type": "json_schema", "json_schema": {"name": "decision", "strict": True, "schema": decision_schema(specs, mode=mode)}}
