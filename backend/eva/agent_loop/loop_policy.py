from __future__ import annotations


ALLOWED_PREVIEW_ACTION_TYPES: tuple[str, ...] = (
    "status_check_preview",
    "context_assembly_preview",
    "threat_scan_preview",
    "validation_preview",
    "planner_preview",
    "fileagent_safe_preview",
    "approval_needed_preview",
    "refusal_preview",
    "clarification_preview",
    "final_response_preview",
)

BLOCKED_ACTION_TYPES: tuple[str, ...] = (
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
)


def loop_policy_text() -> str:
    return "\n".join(
        [
            "Agent Loop v1 policy",
            "Agent loop is local/mock preview only.",
            "No live LLM call was made.",
            "Actions are preview-only.",
            "Tools are not executed.",
            "Secrets/config/session data are blocked.",
            "Browser/desktop/shell/cloud/MCP execution remains locked.",
            "Context preview comes from Phase 16 patterns; threat preview comes from Phase 17 patterns.",
            "Structured-output checks remain local validation previews only.",
            "WorkSession awareness is sanitized status metadata only; raw runtime dumps are blocked.",
            "Phase 12L narrow approved new .md/.txt creation remains a gated write path.",
        ]
    )
