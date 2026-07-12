from __future__ import annotations

from .gate_policy import BLOCKED_ACTION_CLASSES, FUTURE_GATE_ACTION_CLASSES, PREVIEW_ACTION_CLASSES, UNSAFE_ACTION_CLASSES
from .models import ActionClassification, GateEligibility


def evaluate_eligibility(classification: ActionClassification) -> GateEligibility:
    action_class = classification.action_class
    if action_class == "browser_readonly_observation":
        return _eligibility(
            "allowed_readonly_observation",
            "No approval is required for validated public-URL observation output.",
            "No confirmation is accepted because the gate cannot perform browser actions.",
            "Rollback is not applicable; no browser or file state is changed.",
            "Audit note: Phase 24 read-only observation/report metadata only.",
            "",
            "",
            "",
            "ready_readonly_observation",
            (
                "Public-URL read-only observation only.",
                "No click, type, form, download, upload, cookie, session, profile, or browser-control authority.",
            ),
        )
    if action_class == "desktop_observation_only":
        return _eligibility(
            "allowed_desktop_observation",
            "No approval is required for explicit one-shot redacted observation output.",
            "No confirmation is accepted because the gate cannot perform desktop actions.",
            "Rollback is not applicable; no desktop, screenshot, or file state is changed.",
            "Audit note: Phase 25 observation/report metadata only.",
            "",
            "",
            "",
            "ready_desktop_observation",
            (
                "Explicit one-shot desktop observation/report output only.",
                "No click, type, hotkey, app/window control, continuous monitoring, screenshot saving, or tool authority.",
            ),
        )
    if action_class in PREVIEW_ACTION_CLASSES:
        return _eligibility(
            "preview_only",
            "No approval required for status/report preview.",
            "No confirmation required for status/report preview.",
            "Rollback is not applicable to preview-only output.",
            "Audit note: local preview/report metadata only.",
            "",
            "",
            "",
            "ready_preview_only",
            ("Status/report/preview actions are preview-only.",),
        )
    if action_class == "existing_phase12l_real_create_candidate":
        return _eligibility(
            "eligible_existing_phase12l_gate",
            "Requires existing Phase 12L approval metadata before any real create is considered.",
            "Requires the exact existing Phase 12L confirmation phrase accepted by that implemented gate.",
            "Rollback only if the existing Phase 12L rollback boundary accepts an unchanged Eva-created file.",
            "Audit note: Phase 12L approval and real-create ledger metadata applies.",
            "",
            "Phase 12L narrow approved new .md/.txt real-create gate.",
            "",
            "eligible_existing_gate_only",
            ("Existing Phase 12L eligibility is recognized but not expanded.",),
        )
    if action_class in FUTURE_GATE_ACTION_CLASSES:
        return _eligibility(
            "requires_future_gate",
            "Future explicit approval policy is required; approval alone does not execute.",
            "Future confirmation phrase policy is required; confirmation alone does not execute unless an existing implemented gate accepts it.",
            "Rollback is metadata/preview only until a future gate implements and verifies it.",
            "Audit note: future gate candidate is reported as locked.",
            "Future execution gate is not implemented.",
            "",
            f"Locked future gate required for {action_class}.",
            "locked_future_candidate",
            ("Future gates may be described as locked candidates only.",),
        )
    if action_class in BLOCKED_ACTION_CLASSES:
        return _eligibility(
            "blocked_by_policy",
            "Approval is not available for policy-blocked execution surfaces.",
            "Confirmation is not accepted for policy-blocked execution surfaces.",
            "Rollback is metadata/preview only because no action may run.",
            "Audit note: blocked policy classification should be recorded by any future caller.",
            classification.reason,
            "",
            "",
            "blocked",
            ("Browser/desktop/shell/cloud/MCP/package execution remains locked.", "Arbitrary file reads/writes are blocked."),
        )
    if action_class in UNSAFE_ACTION_CLASSES:
        return _eligibility(
            "denied_unsafe_request",
            "Unsafe secret, credential, session, or runtime dump requests cannot be approved.",
            "Confirmation is not accepted for unsafe requests.",
            "Rollback is not applicable because unsafe requests are denied before execution.",
            "Audit note: unsafe request denied locally.",
            classification.reason,
            "",
            "",
            "denied",
            ("Secrets/config/session data are blocked.",),
        )
    if action_class == "unknown_or_hallucinated_action":
        return _eligibility(
            "denied_unknown_capability",
            "Unknown or hallucinated capability claims cannot be approved.",
            "Confirmation is not accepted for unknown capabilities.",
            "Rollback is not applicable because unknown capabilities are denied.",
            "Audit note: hallucinated capability denied locally.",
            classification.reason,
            "",
            "",
            "denied",
            ("Unknown or hallucinated capabilities are denied.",),
        )
    return _eligibility(
        "requires_clarification",
        "Clarification is required before any approval could be discussed.",
        "Confirmation is not applicable until the action is classified.",
        "Rollback is not applicable until the action is classified.",
        "Audit note: clarification requested.",
        "The requested action was not specific enough to classify safely.",
        "",
        "",
        "needs_clarification",
        ("Ambiguous execution requests require clarification.",),
    )


def eligibility_policy_text() -> str:
    return "\n".join(
        [
            "Controlled Execution Gates eligibility policy",
            "No live LLM call was made.",
            "Execution gates are local/mock policy preview only.",
            "Tools are not executed.",
            "Approval alone does not execute.",
            "Confirmation alone does not execute unless an existing implemented gate accepts it.",
            "Browser/desktop/shell/cloud/MCP/package execution remains locked.",
            "Secrets/config/session data are blocked.",
            "Phase 12L narrow real-create remains a gated write path.",
            "Eligibility maps preview actions to preview_only, Phase 12L candidates to eligible_existing_phase12l_gate, future candidates to requires_future_gate, and unsafe requests to denied states.",
        ]
    )


def _eligibility(
    decision_state: str,
    approval_requirement: str,
    confirmation_requirement: str,
    rollback_availability: str,
    audit_requirement: str,
    blocked_reason: str,
    eligible_existing_gate: str,
    future_gate_requirement: str,
    final_readiness_status: str,
    safety_notes: tuple[str, ...],
) -> GateEligibility:
    return GateEligibility(
        decision_state=decision_state,
        approval_requirement=approval_requirement,
        confirmation_requirement=confirmation_requirement,
        rollback_availability=rollback_availability,
        audit_requirement=audit_requirement,
        blocked_reason=blocked_reason,
        eligible_existing_gate=eligible_existing_gate,
        future_gate_requirement=future_gate_requirement,
        final_readiness_status=final_readiness_status,
        safety_notes=safety_notes,
    )
