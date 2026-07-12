from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .pending_actions import EvaPendingAction, EvaPendingActionResult, now_iso


DEFAULT_LEDGER_PATH = Path(__file__).resolve().parents[1] / "data" / "permissions" / "pending_actions.jsonl"


def ledger_path() -> Path:
    override = os.environ.get("EVA_PENDING_ACTION_LEDGER_PATH", "").strip()
    return Path(override) if override else DEFAULT_LEDGER_PATH


def _append(action: EvaPendingAction, note: str | None = None) -> None:
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {"created_at": now_iso(), "action": action.as_dict()}
    if note:
        event["note"] = str(note)[:500]
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")


def _read_latest() -> dict[str, EvaPendingAction]:
    path = ledger_path()
    latest: dict[str, EvaPendingAction] = {}
    if not path.exists():
        return latest
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                payload = json.loads(line)
                raw_action = payload.get("action") if isinstance(payload, dict) else None
                if isinstance(raw_action, dict):
                    action = EvaPendingAction.from_dict(raw_action)
                    latest[action.id] = action
            except Exception:
                continue
    return latest


def _with_expiration(action: EvaPendingAction) -> EvaPendingAction:
    if action.is_expired():
        action.status = "expired"
    return action


def create_pending_action(action: EvaPendingAction) -> EvaPendingActionResult:
    _append(action, note="created")
    return EvaPendingActionResult(True, action.id, action.status, "Pending action created.", action)


def list_pending_actions(include_expired: bool = False, limit: int = 10) -> list[EvaPendingAction]:
    expire_pending_actions()
    actions = list(_read_latest().values())
    if not include_expired:
        actions = [action for action in actions if action.status in {"pending_confirmation", "pending_override"}]
    actions.sort(key=lambda item: item.created_at, reverse=True)
    return actions[: max(1, int(limit))]


def get_pending_action(action_id: str) -> EvaPendingAction | None:
    action = _read_latest().get(str(action_id or "").strip())
    if not action:
        return None
    if action.is_expired():
        action.status = "expired"
        _append(action, note="expired")
    return action


def update_pending_action_status(action_id: str, status: str, note: str | None = None) -> EvaPendingActionResult:
    action = get_pending_action(action_id)
    if not action:
        return EvaPendingActionResult(False, action_id, "missing", f"I could not find pending action `{action_id}`.")
    action.status = status
    _append(action, note=note or f"status:{status}")
    return EvaPendingActionResult(True, action.id, action.status, f"Pending action `{action.id}` is now {status}.", action)


def cancel_pending_action(action_id: str) -> EvaPendingActionResult:
    action = get_pending_action(action_id)
    if not action:
        return EvaPendingActionResult(False, action_id, "missing", f"I could not find pending action `{action_id}`.")
    if action.status == "expired":
        return EvaPendingActionResult(False, action.id, action.status, f"Pending action `{action.id}` is expired and cannot be cancelled.", action)
    action.status = "cancelled"
    _append(action, note="cancelled")
    return EvaPendingActionResult(True, action.id, action.status, f"Cancelled pending action `{action.id}`. No real action was executed.", action)


def expire_pending_actions(now: datetime | None = None) -> int:
    count = 0
    for action in _read_latest().values():
        if action.status in {"pending_confirmation", "pending_override"} and action.is_expired(now or datetime.now(timezone.utc)):
            action.status = "expired"
            _append(action, note="expired")
            count += 1
    return count


def confirm_pending_action(action_id: str, override: bool = False) -> EvaPendingActionResult:
    action = get_pending_action(action_id)
    if not action:
        return EvaPendingActionResult(False, action_id, "missing", f"I could not find pending action `{action_id}`.")
    if action.status == "expired":
        return EvaPendingActionResult(False, action.id, action.status, f"Pending action `{action.id}` is expired and cannot be confirmed.", action)
    if action.status == "cancelled":
        return EvaPendingActionResult(False, action.id, action.status, f"Pending action `{action.id}` was cancelled and cannot be confirmed.", action)
    if action.status not in {"pending_confirmation", "pending_override"}:
        return EvaPendingActionResult(False, action.id, action.status, f"Pending action `{action.id}` is already {action.status}.", action)
    if action.requires_override and not override:
        return EvaPendingActionResult(False, action.id, action.status, f"Pending action `{action.id}` requires `confirm override {action.id}`.", action)
    if override and not action.requires_override:
        return EvaPendingActionResult(False, action.id, action.status, f"Pending action `{action.id}` does not require override. Use `confirm {action.id}`.", action)
    action.status = "confirmed" if action.executor_available else "confirmed_but_executor_unavailable"
    _append(action, note="confirmed")
    if action.executor_available:
        message = f"Confirmed pending action `{action.id}`. Ready to execute via the approved tool-gate handoff."
    else:
        message = f"Confirmed pending action `{action.id}`, but this build does not yet have a verified executor for it, so I did not execute anything."
    return EvaPendingActionResult(True, action.id, action.status, message, action)


def pending_action_ledger_status() -> dict[str, Any]:
    expire_pending_actions()
    all_actions = list(_read_latest().values())
    counts: dict[str, int] = {}
    for action in all_actions:
        counts[action.status] = counts.get(action.status, 0) + 1
    return {"ok": True, "path": str(ledger_path()), "total_actions": len(all_actions), "status_counts": counts}
