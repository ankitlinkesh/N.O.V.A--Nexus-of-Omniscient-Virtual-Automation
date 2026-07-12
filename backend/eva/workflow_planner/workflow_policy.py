from __future__ import annotations


ALLOWED_WORKFLOW_STEP_TYPES: tuple[str, ...] = (
    "status_check_preview",
    "context_assembly_preview",
    "threat_scan_preview",
    "capability_selection_preview",
    "agent_loop_preview",
    "fileagent_draft_preview",
    "approval_needed_preview",
    "verification_preview",
    "rollback_plan_preview",
    "clarification_preview",
    "refusal_preview",
    "final_report_preview",
)

BLOCKED_WORKFLOW_STEP_TYPES: tuple[str, ...] = (
    "live_llm_call",
    "provider_api_call",
    "shell_command",
    "package_install",
    "arbitrary_file_read",
    "arbitrary_file_write",
    "browser_action",
    "desktop_action",
    "MCP_call",
    "cloud_call",
    "secret_read",
    "cookie_or_session_read",
    "credential_access",
    "raw_runtime_dump",
    "direct_real_execution",
)


def workflow_policy_text() -> str:
    return "\n".join(
        [
            "Agentic Workflow Planner policy",
            "Workflow planner is local/mock preview only.",
            "No live LLM call was made.",
            "Workflow steps are preview-only.",
            "Tools are not executed.",
            "Secrets/config/session data are blocked.",
            "Arbitrary file reads/writes are blocked.",
            "Browser/desktop/shell/cloud/MCP execution remains locked.",
            "Phase 12L remains a gated write path.",
            "Risk behavior: low status previews; medium planning/verification previews; high future approval required; critical and forbidden blocked/refusal previews.",
            "Dependency validation, precondition checks, approval previews, rollback previews, and verification plans are local metadata only.",
        ]
    )
