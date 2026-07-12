from __future__ import annotations

from .models import WorkflowPlanPreview


def format_workflow_report(plan: WorkflowPlanPreview) -> str:
    lines = [
        "Agentic Workflow Planner preview report",
        "Workflow planner is local/mock preview only.",
        "No live LLM call was made.",
        "Workflow steps are preview-only.",
        "Tools are not executed.",
        "Secrets/config/session data are blocked.",
        "Arbitrary file reads/writes are blocked.",
        "Browser/desktop/shell/cloud/MCP execution remains locked.",
        "Phase 12L remains a gated write path.",
        "",
        f"Workflow ID: {plan.workflow_id}",
        f"Workflow name: {plan.workflow_name}",
        f"Request summary: {plan.user_request_summary}",
        f"Selected template: {plan.selected_template}",
        f"Relevance score: {plan.relevance_score}",
        f"Workflow category: {plan.workflow_category}",
        f"Final readiness: {plan.final_readiness_status}",
        "",
        "Ordered preview steps:",
    ]
    for step in plan.ordered_steps:
        lines.append(f"- {step.step_id}: {step.step_type}; capability: {step.capability_id}; risk: {step.risk_level}; permission: {step.permission_class}; executed: {step.executed}")
    lines.append("")
    lines.append("Dependencies:")
    for item in plan.dependencies:
        depends = ", ".join(item.depends_on) if item.depends_on else "none"
        lines.append(f"- {item.step_id}: depends on {depends}; status: {item.status}; reason: {item.reason}")
    lines.append("")
    lines.append("Preconditions:")
    for item in plan.preconditions:
        lines.append(f"- {item.precondition_id}: {'satisfied' if item.satisfied else 'missing'} - {item.reason}")
    lines.append("")
    lines.append("Approval requirements:")
    if plan.approval_requirements:
        lines.extend(f"- {item.approval_id}: {item.requirement}; risk: {item.risk_level}; execution unlocked: {item.execution_unlocked}" for item in plan.approval_requirements)
    else:
        lines.append("- none for this preview.")
    lines.append("")
    lines.append("Rollback plan preview:")
    lines.append(f"- status: {plan.rollback_plan_preview.status}; execution unlocked: {plan.rollback_plan_preview.execution_unlocked}")
    lines.extend(f"- {item}" for item in plan.rollback_plan_preview.steps)
    lines.append("")
    lines.append("Verification plan:")
    lines.append(f"- status: {plan.verification_plan.status}; execution unlocked: {plan.verification_plan.execution_unlocked}")
    lines.extend(f"- {item}" for item in plan.verification_plan.checks)
    if plan.blocked_steps:
        lines.append("")
        lines.append("Blocked steps:")
        lines.extend(f"- {item.step_id}: {item.step_type}; reason: {item.reason}" for item in plan.blocked_steps)
    if plan.excluded_steps:
        lines.append("")
        lines.append("Excluded steps:")
        lines.extend(f"- {item.step_type}: {item.reason}" for item in plan.excluded_steps)
    lines.append("")
    lines.append(plan.no_live_llm_call_statement)
    lines.append(plan.no_tool_execution_statement)
    lines.append(plan.no_real_write_statement)
    return "\n".join(lines)
