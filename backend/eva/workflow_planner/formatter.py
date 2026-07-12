from __future__ import annotations

from .dependency_graph import build_dependencies
from .runner_preview import run_workflow_preview
from .status import get_workflow_planner_status
from .workflow_catalog import workflow_catalog_text
from .workflow_policy import workflow_policy_text


def _boundary() -> list[str]:
    return [
        "No live LLM call was made.",
        "Workflow planner is local/mock preview only.",
        "Workflow steps are preview-only.",
        "Tools are not executed.",
        "Secrets/config/session data are blocked.",
        "Arbitrary file reads/writes are blocked.",
        "Browser/desktop/shell/cloud/MCP execution remains locked.",
        "Phase 12L remains a gated write path.",
    ]


def format_workflow_planner_status() -> str:
    status = get_workflow_planner_status()
    return "\n".join(
        [
            "Agentic Workflow Planner status",
            *_boundary(),
            f"Status: {status.status}.",
            f"Mode: {status.mode}.",
            f"Provider SDKs enabled: {status.provider_sdks_enabled}.",
            f"Arbitrary file reads enabled: {status.arbitrary_file_reads_enabled}.",
            f"Arbitrary file writes enabled: {status.arbitrary_file_writes_enabled}.",
            f"Next phase: {status.next_phase}.",
        ]
    )


def format_workflow_planner_catalog() -> str:
    return workflow_catalog_text()


def format_workflow_planner_policy() -> str:
    return workflow_policy_text()


def format_workflow_planner_preview(request: str = "plan a workflow preview") -> str:
    return run_workflow_preview(request).format()


def format_workflow_planner_dependencies(request: str = "show workflow dependencies") -> str:
    plan = run_workflow_preview(request)
    lines = ["Agentic Workflow Planner dependency validation", *_boundary(), "Dependency validation status:"]
    lines.extend(f"- {item.step_id}: {item.status}; {item.reason}" for item in plan.dependencies)
    if plan.blocked_steps:
        lines.extend(f"- blocked {item.step_id}: {item.reason}" for item in plan.blocked_steps)
    return "\n".join(lines)


def format_workflow_planner_approvals(request: str = "show workflow approval preview") -> str:
    plan = run_workflow_preview(request)
    lines = ["Agentic Workflow Planner approval preview", *_boundary(), "Approval preview policy: high-risk future actions require future approval, but no execution is unlocked."]
    if plan.approval_requirements:
        lines.extend(f"- {item.approval_id}: {item.requirement}; execution unlocked: {item.execution_unlocked}" for item in plan.approval_requirements)
    else:
        lines.append("- No extra approval requirement for this status-only preview.")
    return "\n".join(lines)


def format_workflow_planner_rollback(request: str = "show workflow rollback plan") -> str:
    plan = run_workflow_preview(request)
    return "\n".join(
        [
            "Agentic Workflow Planner rollback preview",
            *_boundary(),
            "Rollback preview policy: rollback is planning metadata only.",
            f"Rollback status: {plan.rollback_plan_preview.status}.",
            *[f"- {item}" for item in plan.rollback_plan_preview.steps],
        ]
    )


def format_workflow_planner_readiness() -> str:
    return "\n".join(
        [
            "Agentic Workflow Planner readiness",
            *_boundary(),
            "Ready for deterministic local workflow preview/status/report use.",
            "No provider SDKs are used.",
            "No .env, .env.local, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read.",
            "Workflow dependency validation, precondition checks, approval previews, rollback previews, and verification plans are implemented.",
            "Next phase: Phase 20 Controlled Execution Gates.",
        ]
    )
