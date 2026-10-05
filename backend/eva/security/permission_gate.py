from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .action_types import ActionType


@dataclass(frozen=True)
class PermissionContext:
    user_confirmed: bool = False
    override_granted: bool = False
    override_phrase: str = "confirm override"
    expires_after_seconds: int = 120
    active_task: bool = True


@dataclass(frozen=True)
class PermissionDecision:
    decision: str
    reason: str
    required_phrase: str | None = None
    expires_after_seconds: int | None = None
    risk_categories: list[str] | None = None
    safe_alternative: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


HARD_BLOCK = {ActionType.ILLEGAL_HARMFUL.value, ActionType.MALWARE_LIKE.value, ActionType.THIRD_PARTY_SPYING.value, ActionType.CREDENTIAL_ACCESS.value}
OVERRIDE = {
    ActionType.PRIVACY_SCREEN_READ.value,
    ActionType.PRIVACY_FILE_READ.value,
    ActionType.PRIVACY_CHAT_READ.value,
    ActionType.DESTRUCTIVE_FILE_ACTION.value,
    ActionType.SYSTEM_CHANGE.value,
}
CONFIRM = {ActionType.EXTERNAL_MESSAGE_SEND.value, ActionType.EXTERNAL_POST.value, ActionType.POWER_ACTION.value, ActionType.SANDBOX_TRANSFER.value}
ALLOW = {ActionType.SAFE_LOCAL_READ.value, ActionType.SAFE_LOCAL_UI.value, ActionType.NETWORK_ACTION.value, ActionType.SANDBOX_COMMAND.value}


def evaluate_action(action, context: PermissionContext) -> PermissionDecision:
    risks = [str(item) for item in (getattr(action, "risk_categories", None) or [getattr(action, "action_type", ActionType.UNKNOWN_RISK.value)])]
    action_type = str(getattr(action, "action_type", ActionType.UNKNOWN_RISK.value))
    risk_set = set(risks + [action_type])

    if risk_set & HARD_BLOCK:
        return PermissionDecision(
            "hard_block",
            "This action is illegal, harmful, credential-seeking, spying, or malware-like and cannot be overridden.",
            risk_categories=sorted(risk_set),
            safe_alternative="I can help with defensive security, account recovery, or privacy-safe education instead.",
        )

    if action_type == ActionType.SHELL_ACTION.value:
        return PermissionDecision("hard_block", "Arbitrary shell execution is blocked by default.", risk_categories=risks)

    if risk_set & OVERRIDE or bool(getattr(action, "destructive", False)) or bool(getattr(action, "privacy_sensitive", False)):
        if context.override_granted:
            return PermissionDecision("allow", "Override already granted for this action.", risk_categories=risks)
        return PermissionDecision(
            "ask_override",
            "This action is privacy-sensitive, destructive, or system-changing.",
            required_phrase=context.override_phrase,
            expires_after_seconds=context.expires_after_seconds,
            risk_categories=sorted(risk_set),
        )

    if risk_set & CONFIRM or bool(getattr(action, "external_visible", False)):
        if context.user_confirmed:
            return PermissionDecision("allow", "User confirmed this external or power action.", risk_categories=risks)
        return PermissionDecision("ask_confirmation", "This action needs explicit confirmation before it is visible externally.", risk_categories=sorted(risk_set))

    if risk_set & ALLOW:
        return PermissionDecision("allow", "Safe local bounded action.", risk_categories=sorted(risk_set))

    return PermissionDecision("ask_confirmation", "Unknown risk action needs confirmation.", risk_categories=sorted(risk_set))
