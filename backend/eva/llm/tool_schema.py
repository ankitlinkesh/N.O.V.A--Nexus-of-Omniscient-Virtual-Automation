from __future__ import annotations

import re
from typing import Any


# The OpenAI function-calling spec allows only these characters in a function
# name, and NVIDIA NIM enforces it strictly:
#
#   Validation: Function at index 73 has an invalid name: "web.click".
#   Only a-z, A-Z, 0-9, underscores, and dashes are allowed.   [HTTP 400]
#
# Eva names 25 of its tools with dots (`web.click`, `screen.observe`,
# `file.copy`...), and seven of those are planner-visible once Playwright is
# enabled. ONE of them in the payload makes the provider reject the WHOLE
# request, so NIM could never serve a planner call -- every request silently fell
# through to Gemini, which happens to tolerate dots. It stayed invisible because
# the configured NIM model was returning 410 Gone *before* the payload was ever
# validated; fixing the retired model id is what surfaced this.
#
# So the wire name is sanitized on the way out and mapped back on the way in. The
# tool's real name never changes -- this is a transport detail, not a rename, and
# nothing downstream of the planner sees a sanitized name.


class ToolNameCollision(ValueError):
    """Two tools would share one wire name -- refuse rather than guess.

    A collision would silently route a call for one tool to a DIFFERENT tool,
    which the permission gate could not catch: it classifies whatever tool it is
    handed. There are no collisions today (checked across all 25 dotted names),
    so this raises rather than picking a winner, and a future tool named into a
    collision breaks the build instead of misrouting a call.
    """


def sanitize_tool_name(name: str) -> str:
    """The wire name for a tool: dots (and anything else illegal) become `_`."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(name or ""))


def wire_name_map(specs: list[dict[str, Any]]) -> dict[str, str]:
    """wire name -> real tool name, for every spec that has one."""
    mapping: dict[str, str] = {}
    for spec in specs:
        name = spec.get("name")
        if not name:
            continue
        wire = sanitize_tool_name(name)
        existing = mapping.get(wire)
        if existing is not None and existing != name:
            raise ToolNameCollision(
                f"tools {existing!r} and {name!r} both map to the wire name {wire!r}; "
                "rename one -- a shared wire name would route a call to the wrong tool"
            )
        mapping[wire] = name
    return mapping


def resolve_tool_name(name: str, specs: list[dict[str, Any]]) -> str:
    """Turn a name the model called back into the real tool name.

    A real name is returned unchanged, so this is safe to apply to every response
    regardless of whether that provider needed the sanitized form.
    """
    known = {spec.get("name") for spec in specs}
    if name in known:
        return name
    return wire_name_map(specs).get(name, name)


def to_openai_tools(specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert registry planner specs (each: name, description, args_schema)
    into OpenAI function-tool format, with provider-legal function names."""
    wire_name_map(specs)  # raises on collision before anything is sent
    tools = []
    for spec in specs:
        name = spec.get("name")
        if not name:
            continue
        tools.append({
            "type": "function",
            "function": {
                "name": sanitize_tool_name(name),
                "description": spec.get("description", ""),
                "parameters": spec.get("args_schema") or {"type": "object", "properties": {}},
            },
        })
    return tools
