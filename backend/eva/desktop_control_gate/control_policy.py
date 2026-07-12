from __future__ import annotations


BOUNDARY_LINES = (
    "Desktop control is not enabled.",
    "This is a dry-run/control-gate only.",
    "Desktop mode is observation-only outside this dry-run gate.",
    "No clicking.",
    "No typing.",
    "No hotkeys.",
    "No clipboard access.",
    "No app/window control.",
    "No continuous monitoring.",
    "No saved screenshots.",
    "No cookies, sessions, or browser profiles.",
    "No tool execution.",
    "No shell/package/cloud/MCP execution.",
    "Approval alone does not execute.",
    "Confirmation alone does not execute.",
    "Phase 12L remains a gated write path.",
)


def control_policy_text() -> str:
    return "\n".join(("Real Desktop Control Gate policy", *BOUNDARY_LINES))
