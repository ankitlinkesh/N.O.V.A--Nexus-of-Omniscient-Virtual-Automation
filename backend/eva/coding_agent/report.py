from __future__ import annotations

import hashlib

from .handoff_report import build_handoff_notes
from .models import CodingSpecialistReport
from .patch_planner import build_patch_plan
from .project_context import build_project_context_summary
from .review_checklist import build_review_checklist
from .risk_review import build_risk_review
from .task_classifier import classify_coding_task
from .test_plan import build_test_plan_preview


def build_coding_report(request: str = "plan a code change") -> CodingSpecialistReport:
    normalized = " ".join(str(request or "").strip().split())
    classification = classify_coding_task(normalized)
    context = build_project_context_summary()
    proposed_plan, patch_summary = build_patch_plan(classification.task_type)
    risk_review, blocked_actions = build_risk_review(classification)
    readiness = (
        "blocked_preview_only"
        if classification.blocked
        else "clarification_required"
        if classification.task_type == "clarification_needed"
        else "ready_for_human_review"
    )
    summary = (
        "Execution-seeking or sensitive coding request withheld from the report."
        if classification.blocked
        else f"Deterministic {classification.task_type.replace('_', ' ')} request."
    )
    report_id = "coding-" + hashlib.sha256(normalized.lower().encode("utf-8")).hexdigest()[:12]
    return CodingSpecialistReport(
        coding_report_id=report_id,
        user_request_summary=summary,
        coding_task_type=classification.task_type,
        selected_specialist_mode=classification.specialist_mode,
        project_context_summary=context.summary,
        relevant_safe_context_sources=context.sources,
        proposed_plan=proposed_plan,
        patch_preview_summary=patch_summary,
        review_checklist=build_review_checklist(),
        test_plan_preview=build_test_plan_preview(),
        risk_review=risk_review,
        blocked_actions_with_reasons=blocked_actions,
        verification_recommendations=(
            "A developer should run the focused verifier manually.",
            "A developer should run quick and full regression profiles manually.",
            "Completion requires fresh compilation and diff-integrity evidence.",
        ),
        handoff_notes=build_handoff_notes(classification.task_type, classification.specialist_mode),
        final_readiness_status=readiness,
        no_source_edit_statement="No source files were edited.",
        no_patch_apply_statement="No patches were applied.",
        no_shell_execution_statement="No shell commands were run.",
        no_test_execution_statement="No tests were run.",
        no_package_install_statement="No package installs happened.",
        no_git_operation_statement="No git operations happened.",
        no_live_llm_call_statement="No live LLM call was made.",
        no_tool_execution_statement="No tool execution happened.",
        no_new_write_path_statement="Phase 12L remains a gated write path.",
    )
