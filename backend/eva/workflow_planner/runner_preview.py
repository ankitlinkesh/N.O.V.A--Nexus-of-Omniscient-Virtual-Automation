from __future__ import annotations

import hashlib

from ..agent_loop.runner import run_agent_loop_preview
from ..context_engine.assembler import assemble_context_preview
from ..threat_defense.guard import scan_threat_preview
from .approval_preview import build_approval_requirements
from .composer import compose_workflow_steps
from .dependency_graph import build_dependencies
from .models import WorkflowPlanPreview
from .preconditions import build_preconditions
from .risk import classify_workflow_risk
from .rollback_plan import build_rollback_plan
from .selector import select_workflow_template
from .verification_plan import build_verification_plan


def run_workflow_preview(request: str = "plan a workflow preview") -> WorkflowPlanPreview:
    summary = _summarize(request)
    template, relevance = select_workflow_template(request)
    context_packet = assemble_context_preview(request)
    threat = scan_threat_preview(request, source_type="workflow_request")
    loop = run_agent_loop_preview(request)
    steps, blocked_steps, excluded_steps = compose_workflow_steps(request, template)
    dependencies, dependency_blocks = build_dependencies(steps, request)
    blocked_steps = blocked_steps + dependency_blocks
    preconditions = build_preconditions(request)
    approvals = build_approval_requirements(steps)
    rollback = build_rollback_plan()
    verification = build_verification_plan()
    if any(not item.satisfied for item in preconditions):
        final = "needs_precondition_preview"
    elif blocked_steps or threat.blocked or any(item.status == "blocked" for item in dependencies):
        final = "blocked_preview"
    else:
        final = "ready_preview_only"
    selected_capabilities = tuple(dict.fromkeys(step.capability_id for step in steps))
    return WorkflowPlanPreview(
        workflow_id=_workflow_id(request),
        workflow_name=template.name,
        user_request_summary=summary,
        selected_template=template.template_id,
        relevance_score=round(relevance, 2),
        workflow_category=template.category,
        ordered_steps=steps,
        dependencies=dependencies,
        preconditions=preconditions,
        selected_capabilities=selected_capabilities,
        permission_classes=tuple(dict.fromkeys(step.permission_class for step in steps)),
        risk_levels=tuple(dict.fromkeys(step.risk_level for step in steps)),
        action_previews=steps,
        approval_requirements=approvals,
        rollback_plan_preview=rollback,
        verification_plan=verification,
        blocked_steps=blocked_steps,
        excluded_steps=excluded_steps,
        final_readiness_status=final,
        no_live_llm_call_statement="No live LLM call was made.",
        no_tool_execution_statement="Tools are not executed.",
        no_real_write_statement="Phase 12L remains a gated write path.",
        safety_notes=(
            "Workflow planner is local/mock preview only.",
            "Workflow steps are preview-only.",
            "Secrets/config/session data are blocked.",
            "Arbitrary file reads/writes are blocked.",
            "Browser/desktop/shell/cloud/MCP execution remains locked.",
            f"Context packet preview: {context_packet.packet_id}.",
            f"Threat preview blocked: {threat.blocked}.",
            f"Agent loop preview: {loop.loop_id}.",
            f"Workflow risk: {classify_workflow_risk(request, template.category)}.",
        ),
    )


def _workflow_id(request: str) -> str:
    return "wfp_" + hashlib.sha256(("phase19|" + str(request or "")).encode("utf-8")).hexdigest()[:12]


def _summarize(request: str) -> str:
    clean = " ".join(str(request or "").split())
    if not clean:
        return "No workflow request supplied."
    if len(clean) <= 240:
        return clean
    return clean[:220].rstrip() + " ... [trimmed]"
