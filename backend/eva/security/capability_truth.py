"""Code-derived truth about what Eva can actually execute.

Everything here is computed from the live ToolRegistry and the central
permission gate, not from hand-maintained prose. This is the single source
of truth the safety docs and status commands should quote, so claims cannot
drift away from the code the way a separate catalog can.
"""
from __future__ import annotations

from typing import Any

from ..tools.registry import ToolRegistry
from . import tool_gate


GATE_CLASS_ORDER = ("allow", "confirm", "override", "hard_block")

GATE_CLASS_LABEL = {
    "allow": "runs immediately (safe, bounded)",
    "confirm": "requires explicit user confirmation",
    "override": "requires explicit user override (privacy/destructive/system)",
    "hard_block": "blocked by policy, cannot be overridden",
}


def build_capability_truth(registry: ToolRegistry | None = None) -> dict[str, Any]:
    """Return the real execution picture, derived from the registry + gate."""
    registry = registry or ToolRegistry()
    planner_visible = {spec["name"] for spec in registry.planner_specs()}

    tools: list[dict[str, Any]] = []
    for public in registry.list_tools():
        name = public["name"]
        spec = registry.get(name)
        gate_class = tool_gate.classify_tool_call(spec) if spec is not None else "allow"
        tools.append(
            {
                "tool": name,
                "gate_class": gate_class,
                "planner_reachable": name in planner_visible,
                "safety_level": public["safety_level"],
                "action_type": public["action_type"],
            }
        )
    tools.sort(key=lambda item: (GATE_CLASS_ORDER.index(item["gate_class"]), item["tool"]))

    by_class: dict[str, list[dict[str, Any]]] = {cls: [] for cls in GATE_CLASS_ORDER}
    for item in tools:
        by_class[item["gate_class"]].append(item)

    # Tools the LLM planner can reach that still run immediately (its real reach).
    planner_immediate = [item["tool"] for item in tools if item["planner_reachable"] and item["gate_class"] == "allow"]
    planner_gated = [item["tool"] for item in tools if item["planner_reachable"] and item["gate_class"] != "allow"]

    return {
        "total_tools": len(tools),
        "planner_reachable": sorted(item["tool"] for item in tools if item["planner_reachable"]),
        "planner_immediate": sorted(planner_immediate),
        "planner_gated": sorted(planner_gated),
        "counts": {cls: len(by_class[cls]) for cls in GATE_CLASS_ORDER},
        "by_class": by_class,
        "tools": tools,
    }


def format_capability_truth(registry: ToolRegistry | None = None) -> str:
    data = build_capability_truth(registry)
    counts = data["counts"]
    lines = [
        "Eva capability truth (derived from the tool registry + permission gate)",
        "",
        "Eva does execute tools. Enforcement is centralized in ToolRegistry.run(),",
        "which classifies every call and cannot be bypassed by a `confirmed` argument.",
        "",
        f"Registered tools: {data['total_tools']}.",
        f"- {counts['allow']} run immediately (safe, bounded local reads/observation).",
        f"- {counts['confirm']} require explicit user confirmation.",
        f"- {counts['override']} require explicit user override (privacy/destructive/system).",
        f"- {counts['hard_block']} are hard-blocked by policy.",
        "",
        f"LLM planner reach: the planner may choose {len(data['planner_reachable'])} of {data['total_tools']} tools.",
        f"- {len(data['planner_immediate'])} of those run immediately; {len(data['planner_gated'])} still need confirmation/override.",
        "- Destructive file tools and screen input tools are NOT planner-reachable;",
        "  they run only via the direct, header-guarded /api/tools endpoint, and still pass the gate.",
        "",
        "Approval flow: a gated call returns a pending-action ledger id; only a user-typed",
        "`confirm <id>` / `confirm override <id>` executes it via ToolRegistry.run_approved().",
        "",
        "Live provider calls: Eva makes real LLM API calls when keys are configured",
        "(NVIDIA NIM, Gemini, OpenRouter, Groq, CLoD) with local Ollama fallback.",
        "",
        "Tools by gate class:",
    ]
    for cls in GATE_CLASS_ORDER:
        items = data["by_class"][cls]
        if not items:
            continue
        lines.append(f"- {cls} ({GATE_CLASS_LABEL[cls]}):")
        for item in items:
            reach = "planner-reachable" if item["planner_reachable"] else "endpoint-only"
            lines.append(f"    - {item['tool']} [{reach}] ({item['action_type']})")
    return "\n".join(lines)
