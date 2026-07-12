from __future__ import annotations

import hashlib

from .audit_policy import audit_policy_text
from .eligibility import evaluate_action_eligibility
from .models import DesktopControlDryRun
from .risk_scoring import score_action_risk
from .rollback_policy import rollback_policy_text


def build_desktop_control_dry_run(
    request: str = "review a desktop action",
    *,
    target_summary: str = "unspecified target",
    sensitive_screen: bool = False,
) -> DesktopControlDryRun:
    normalized = " ".join(str(request or "review a desktop action").split())
    decision = evaluate_action_eligibility(normalized, sensitive_screen=sensitive_screen)
    risk = score_action_risk(normalized, sensitive_screen=sensitive_screen)
    dry_run_id = "desktop-control-" + hashlib.sha256(normalized.lower().encode("utf-8")).hexdigest()[:12]
    return DesktopControlDryRun(
        dry_run_id=dry_run_id,
        requested_action_summary=normalized,
        action_class=decision.action_class,
        target_summary=target_summary,
        sensitive_screen_status="sensitive_blocked" if sensitive_screen else "not_supplied",
        required_observation_precondition="Phase 25 explicit one-shot observation would be required before any future target decision.",
        risk_score=risk.score,
        risk_level=risk.level,
        permission_class=decision.permission_class,
        gate_decision=decision.gate_decision,
        approval_requirement="future explicit approval required; approval alone does not execute" if decision.approval_required else "no approval path",
        exact_confirmation_requirement="future exact confirmation required; confirmation alone does not execute" if decision.exact_confirmation_required else "no confirmation path",
        rollback_metadata=rollback_policy_text().splitlines()[-1],
        audit_metadata=audit_policy_text().splitlines()[-1],
        blocked_reason=decision.reason,
        final_status="dry_run_only_no_execution",
        execution_performed=False,
        no_click_statement="No clicking.",
        no_type_statement="No typing.",
        no_hotkey_statement="No hotkeys.",
        no_clipboard_statement="No clipboard access.",
        no_app_control_statement="No app control.",
        no_window_control_statement="No window control.",
        no_tool_execution_statement="No tool execution.",
        no_new_write_path_statement="Phase 12L remains a gated write path.",
    )
