from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .action_types import ActionType
from .permission_gate import HARD_BLOCK

# In-memory store of gated tool calls awaiting ledger confirmation.
# pending_id -> {"tool": name, "args": exact kwargs dict, "created_at": datetime}
_PENDING_CALLS: dict[str, dict[str, Any]] = {}

OVERRIDE_ACTION_TYPES = {
    ActionType.DESTRUCTIVE_FILE_ACTION.value,
    ActionType.SYSTEM_CHANGE.value,
    ActionType.PRIVACY_FILE_READ.value,
    ActionType.PRIVACY_SCREEN_READ.value,
    ActionType.PRIVACY_CHAT_READ.value,
}

CONFIRM_ACTION_TYPES = {
    ActionType.EXTERNAL_MESSAGE_SEND.value,
    ActionType.EXTERNAL_POST.value,
    ActionType.POWER_ACTION.value,
}


def register_pending_call(pending_id: str, tool: str, args: dict[str, Any]) -> None:
    _PENDING_CALLS[pending_id] = {
        "tool": tool,
        "args": dict(args),
        "created_at": datetime.now(timezone.utc),
    }


def get_pending_call(pending_id: str) -> dict[str, Any] | None:
    return _PENDING_CALLS.get(pending_id)


def pop_pending_call(pending_id: str) -> dict[str, Any] | None:
    return _PENDING_CALLS.pop(pending_id, None)


def reset_pending_calls() -> None:
    _PENDING_CALLS.clear()


def classify_tool_call(spec: Any) -> str:
    """Classify a ToolSpec into one of hard_block / override / confirm / allow."""
    action_type = str(getattr(spec, "action_type", "") or "")
    safety_level = str(getattr(spec, "safety_level", "") or "")
    risk_categories = {str(item) for item in (getattr(spec, "risk_categories", None) or ())}
    risk_set = risk_categories | {action_type}

    if action_type == ActionType.SHELL_ACTION.value or (risk_set & HARD_BLOCK):
        return "hard_block"

    if safety_level == "dangerous" or action_type in OVERRIDE_ACTION_TYPES:
        return "override"

    requires_confirmation = bool(getattr(spec, "requires_confirmation", False))
    if (requires_confirmation and safety_level != "safe") or action_type in CONFIRM_ACTION_TYPES:
        return "confirm"

    return "allow"
