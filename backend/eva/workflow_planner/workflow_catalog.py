from __future__ import annotations

from .models import WorkflowTemplate


def list_workflow_templates() -> tuple[WorkflowTemplate, ...]:
    return (
        WorkflowTemplate("wf_status", "Status Review", "status_review", "Summarize safe local status surfaces.", ("status", "summary"), ("status_check_preview", "final_report_preview")),
        WorkflowTemplate("wf_project", "Project Inspection Preview", "project_inspection_preview", "Preview project inspection through safe metadata.", ("project", "inspect"), ("status_check_preview", "capability_selection_preview", "final_report_preview")),
        WorkflowTemplate("wf_file_note", "FileAgent Project Note Preview", "fileagent_project_note_preview", "Preview FileAgent note workflow without writing files.", ("fileagent", "project note", "note"), ("fileagent_draft_preview", "approval_needed_preview", "rollback_plan_preview", "verification_preview", "final_report_preview")),
        WorkflowTemplate("wf_verify", "Verification Summary", "verification_summary", "Plan verification evidence without running tools from the workflow.", ("verify", "verification"), ("status_check_preview", "verification_preview", "final_report_preview")),
        WorkflowTemplate("wf_safety", "Safety Review", "safety_review", "Review locked safety boundaries.", ("safety", "policy", "blocked"), ("threat_scan_preview", "verification_preview", "final_report_preview")),
        WorkflowTemplate("wf_context", "Context Assembly Review", "context_assembly_review", "Preview context assembly workflow.", ("context",), ("context_assembly_preview", "threat_scan_preview", "final_report_preview")),
        WorkflowTemplate("wf_threat", "Threat Defense Review", "threat_defense_review", "Preview threat defense workflow.", ("threat", "prompt injection"), ("threat_scan_preview", "verification_preview", "final_report_preview")),
        WorkflowTemplate("wf_agent_loop", "Agent Loop Preview", "agent_loop_preview", "Preview bounded Agent Loop v1 composition.", ("agent loop", "loop"), ("agent_loop_preview", "verification_preview", "final_report_preview")),
        WorkflowTemplate("wf_planning", "Planning Only", "planning_only", "Compose safe planning-only workflow preview.", ("plan", "workflow"), ("capability_selection_preview", "verification_preview", "final_report_preview")),
        WorkflowTemplate("wf_clarify", "Clarification Needed", "clarification_needed", "Ask for missing safe workflow details.", ("clarify", "unknown"), ("clarification_preview", "final_report_preview")),
        WorkflowTemplate("wf_blocked", "Refusal Or Blocked", "refusal_or_blocked", "Block unsafe workflow requests.", ("execute", "secret", "shell", "browser", "desktop"), ("refusal_preview", "final_report_preview")),
    )


def workflow_catalog_text() -> str:
    lines = [
        "Agentic Workflow Planner catalog",
        "Workflow planner is local/mock preview only.",
        "No live LLM call was made.",
        "Workflow steps are preview-only.",
        "Tools are not executed.",
        "Secrets/config/session data are blocked.",
        "Arbitrary file reads/writes are blocked.",
        "Browser/desktop/shell/cloud/MCP execution remains locked.",
        "Phase 12L remains a gated write path.",
        "Workflow templates:",
    ]
    lines.extend(f"- {item.template_id}: {item.name} ({item.category}) - {item.description}" for item in list_workflow_templates())
    return "\n".join(lines)
