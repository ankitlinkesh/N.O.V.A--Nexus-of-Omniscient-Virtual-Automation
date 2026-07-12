from __future__ import annotations

import hashlib

from .action_classifier import classify_action
from .eligibility import evaluate_eligibility
from .gate_policy import boundary_lines
from .models import GateEvaluation


def evaluate_execution_gate(request: str = "show execution gates status", requested_capability: str | None = None) -> GateEvaluation:
    classification = classify_action(request, requested_capability)
    eligibility = evaluate_eligibility(classification)
    return GateEvaluation(
        gate_evaluation_id=_gate_id(request, requested_capability),
        request_summary=classification.request_summary,
        requested_action_class=classification.action_class,
        requested_capability=classification.requested_capability,
        permission_class=classification.permission_class,
        risk_level=classification.risk_level,
        decision_state=eligibility.decision_state,
        approval_requirement=eligibility.approval_requirement,
        confirmation_requirement=eligibility.confirmation_requirement,
        rollback_availability=eligibility.rollback_availability,
        audit_requirement=eligibility.audit_requirement,
        blocked_reason=eligibility.blocked_reason,
        eligible_existing_gate=eligibility.eligible_existing_gate,
        future_gate_requirement=eligibility.future_gate_requirement,
        safety_notes=tuple(boundary_lines()) + eligibility.safety_notes + (classification.reason,),
        final_readiness_status=eligibility.final_readiness_status,
        no_live_llm_call_statement="No live LLM call was made.",
        no_tool_execution_statement="Tools are not executed.",
        no_new_write_path_statement="Phase 12L narrow real-create remains a gated write path.",
    )


def _gate_id(request: str, requested_capability: str | None) -> str:
    seed = f"phase20|{request or ''}|{requested_capability or ''}"
    return "eg_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
