from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .action_types import ActionType

# Single source of truth for the action_type -> class mapping (Phase 80). The
# hard-block set was already imported from the permission gate; OVERRIDE and
# CONFIRM used to be RE-DECLARED here as separate literals that merely happened
# to be identical -- so the tool-call gate and the action gate could silently
# drift the moment one was edited and the other forgotten (the Phase 78 shape:
# an unpinned cross-component invariant). They are now the SAME objects, so
# drift is impossible by construction. The permission gate owns the taxonomy;
# this gate imports it. The historical names are kept as aliases for the rest of
# this module, and their agreement is additionally pinned by
# verify_eva_phase80_gate_agreement / test_gate_agreement.
from .permission_gate import CONFIRM as CONFIRM_ACTION_TYPES
from .permission_gate import HARD_BLOCK
from .permission_gate import OVERRIDE as OVERRIDE_ACTION_TYPES

# In-memory store of gated tool calls awaiting ledger confirmation.
# pending_id -> {"tool": name, "args": exact kwargs dict, "created_at": datetime,
#                "target_window": {"hwnd", "title", "process_name"} | None}
_PENDING_CALLS: dict[str, dict[str, Any]] = {}

# Screen-input tools whose approved replay must land in the SAME window the
# action was PLANNED against (Phase 117 review, a live-drive finding): the
# person confirms from NOVA's chat page, so the foreground window at confirm
# time is the browser -- never the app the task opened. Before this,
# `run_approved` replayed these blindly into whatever had focus when the
# confirm arrived. `screen.observe`/`screen.wait`/`screen.submit_form` are
# deliberately NOT here: observe and wait touch no window at all, and
# submit_form carries only a console-issued spec id and resolves its own
# target from that, not from "whatever is focused".
SCREEN_INPUT_TOOLS = frozenset({"screen.type_text", "screen.press", "screen.hotkey", "screen.click", "screen.scroll"})


def register_pending_call(
    pending_id: str,
    tool: str,
    args: dict[str, Any],
    *,
    target_window: dict[str, Any] | None = None,
) -> None:
    """`target_window` is the foreground window at the moment the gate created
    this pending action -- for `SCREEN_INPUT_TOOLS` only, the window
    `run_approved` must restore before replaying the call. Stored alongside
    the call (never inside `args`): args are replayed to the handler
    verbatim, and the target window is metadata ABOUT the replay, not part of
    what was approved.
    """
    _PENDING_CALLS[pending_id] = {
        "tool": tool,
        "args": dict(args),
        "created_at": datetime.now(timezone.utc),
        "target_window": dict(target_window) if target_window else None,
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
