"""Calibrated autonomy — trust policies learned from the approval ledger (Phase 42).

Every gated action the user has approved is recorded in the pending-action
ledger. Phase 42 reads that history to calibrate how much friction the *next*
similar action deserves — the goal is autonomy that scales with earned trust,
without ever loosening the hard safety boundary.

Two calibrations, deliberately asymmetric:

  * Escalation (adding friction) is always safe, so it is unconditional: when a
    step's confidence is low, an otherwise-auto action is escalated to explicit
    confirmation.
  * De-escalation (removing friction — "approvals that scale") is dangerous, so
    it is hemmed in on every side: OFF by default (``EVA_TRUST_POLICIES_ENABLED``),
    applied ONLY to a narrow allowlist of action types (never destructive,
    system, privacy, external-send/post, or power actions — those keep their
    gate class no matter how often approved), and ONLY after the same action has
    been explicitly approved at least ``EVA_TRUST_APPROVAL_THRESHOLD`` times.
    It is always revocable by disabling the flag.

Pure and fail-safe: any error reading history yields zero approvals (i.e. no
de-escalation), so a broken ledger can only ever make Eva *more* cautious.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

_FALSY = {"", "0", "false", "no", "off"}
_DEFAULT_THRESHOLD = 3
_DEFAULT_LOW_CONFIDENCE = 0.4

_CONFIRMED_STATUSES = {"confirmed", "confirmed_but_executor_unavailable", "executed", "completed"}

# The ONLY gate action types a trust policy may ever auto-allow. A strict
# allowlist (not a denylist) so a newly added confirm-class action type is never
# silently trust-eligible. Destructive/system/privacy actions are override-class
# and never reach here; external message/post and power actions are excluded on
# purpose even though they are confirm-class.
TRUST_ELIGIBLE_ACTION_TYPES = frozenset({"MCP_TOOL_CALL"})


def trust_policies_enabled() -> bool:
    """Whether learned trust de-escalation is active. Default OFF (fail safe)."""
    return os.environ.get("EVA_TRUST_POLICIES_ENABLED", "").strip().lower() not in _FALSY


def approval_threshold() -> int:
    raw = os.environ.get("EVA_TRUST_APPROVAL_THRESHOLD", "")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_THRESHOLD
    return value if value >= 1 else _DEFAULT_THRESHOLD


def low_confidence_threshold() -> float:
    raw = os.environ.get("EVA_LOW_CONFIDENCE_THRESHOLD", "")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return _DEFAULT_LOW_CONFIDENCE
    return value if 0.0 <= value <= 1.0 else _DEFAULT_LOW_CONFIDENCE


def approval_signature(tool: str, target: object) -> str:
    """A stable key for "this tool against this target" used to match history."""
    return f"{str(tool or '').strip().lower()}::{str(target or '').strip().lower()}"


def count_approvals(tool: str, target: object) -> int:
    """How many times this exact action has been explicitly approved before.

    Reads the pending-action ledger's latest state per action and counts those
    that reached a confirmed/executed status with a matching signature.
    Fail-safe: returns 0 on any error (so history can only reduce autonomy).
    """
    try:
        from .ledger import _read_latest

        signature = approval_signature(tool, target)
        count = 0
        for action in _read_latest().values():
            if str(getattr(action, "status", "")) in _CONFIRMED_STATUSES and approval_signature(
                getattr(action, "action_type", ""), getattr(action, "target", "")
            ) == signature:
                count += 1
        return count
    except Exception:
        return 0


@dataclass(frozen=True)
class CalibratedDecision:
    """A gate decision after trust/confidence calibration."""

    decision: str
    escalated: bool
    auto_allowed: bool
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {"decision": self.decision, "escalated": self.escalated, "auto_allowed": self.auto_allowed, "reason": self.reason}


def calibrate(*, base_decision: str, action_type: str, approvals: int = 0, confidence: float | None = None) -> CalibratedDecision:
    """Adjust a base gate decision for confidence and earned trust.

    Escalation wins over de-escalation and is unconditional (adding friction is
    always safe). De-escalation is applied only under the flag, to allowlisted
    action types, after enough approvals — and never to override/hard_block.
    """
    # Confidence-aware escalation: an unsure auto action asks first. Always on.
    if confidence is not None and confidence < low_confidence_threshold() and base_decision == "allow":
        return CalibratedDecision(
            "confirm", True, False,
            f"Low confidence ({confidence:.2f} < {low_confidence_threshold():.2f}); escalating to confirmation.",
        )

    # Trust de-escalation: only confirm-class, allowlisted, sufficiently approved.
    if (
        base_decision == "confirm"
        and trust_policies_enabled()
        and action_type in TRUST_ELIGIBLE_ACTION_TYPES
        and approvals >= approval_threshold()
    ):
        return CalibratedDecision(
            "allow", False, True,
            f"Trusted: {approvals} prior approvals of this action (>= {approval_threshold()}); auto-allowing (revocable).",
        )

    return CalibratedDecision(base_decision, False, False, "No calibration change.")
