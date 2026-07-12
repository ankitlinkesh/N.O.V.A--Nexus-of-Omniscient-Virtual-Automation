from __future__ import annotations


DECISION_STATES: tuple[str, ...] = (
    "preview_only",
    "allowed_readonly_observation",
    "allowed_desktop_observation",
    "blocked_by_policy",
    "requires_clarification",
    "requires_future_gate",
    "requires_explicit_approval",
    "eligible_existing_phase12l_gate",
    "denied_unknown_capability",
    "denied_unsafe_request",
)

ACTION_CLASSES: tuple[str, ...] = (
    "status_or_report",
    "browser_readonly_observation",
    "desktop_observation_only",
    "local_preview",
    "context_preview",
    "threat_scan_preview",
    "agent_loop_preview",
    "workflow_preview",
    "fileagent_draft_preview",
    "existing_phase12l_real_create_candidate",
    "future_readonly_file_candidate",
    "future_browser_readonly_candidate",
    "future_desktop_observation_candidate",
    "forbidden_secret_access",
    "forbidden_credential_access",
    "forbidden_shell_execution",
    "forbidden_package_install",
    "forbidden_browser_control",
    "forbidden_desktop_control",
    "forbidden_cloud_or_mcp_execution",
    "forbidden_arbitrary_file_write",
    "forbidden_raw_runtime_dump",
    "unknown_or_hallucinated_action",
)

PREVIEW_ACTION_CLASSES = {
    "status_or_report",
    "local_preview",
    "context_preview",
    "threat_scan_preview",
    "agent_loop_preview",
    "workflow_preview",
    "fileagent_draft_preview",
}

FUTURE_GATE_ACTION_CLASSES = {
    "future_readonly_file_candidate",
    "future_browser_readonly_candidate",
    "future_desktop_observation_candidate",
}

BLOCKED_ACTION_CLASSES = {
    "forbidden_shell_execution",
    "forbidden_package_install",
    "forbidden_browser_control",
    "forbidden_desktop_control",
    "forbidden_cloud_or_mcp_execution",
    "forbidden_arbitrary_file_write",
}

UNSAFE_ACTION_CLASSES = {
    "forbidden_secret_access",
    "forbidden_credential_access",
    "forbidden_raw_runtime_dump",
}


def boundary_lines() -> list[str]:
    return [
        "No live LLM call was made.",
        "Execution gates are local/mock policy preview only.",
        "Tools are not executed.",
        "Approval alone does not execute.",
        "Confirmation alone does not execute unless an existing implemented gate accepts it.",
        "Browser/desktop/shell/cloud/MCP/package execution remains locked.",
        "Secrets/config/session data are blocked.",
        "Phase 12L narrow real-create remains a gated write path.",
    ]


def gate_policy_text() -> str:
    lines = [
        "Controlled Execution Gates policy",
        *boundary_lines(),
        "Policy behavior:",
        "- Status, report, and preview actions become preview_only.",
        "- Existing Phase 12L eligibility is recognized but not expanded.",
        "- Phase 12L remains narrow: brand-new .md or .txt only, approved locations only, exact confirmation only, rollback only if unchanged.",
        "- Future read-only file, browser read-only, and desktop observation gates are described as locked candidates.",
        "- Browser, desktop, shell, cloud, MCP, package, provider, secret, credential, broad write, and raw runtime dump requests remain locked or denied.",
        "- Unknown or hallucinated capabilities are denied.",
        "- Rollback is metadata/preview only except the existing Phase 12L rollback boundary if already implemented.",
        "Decision states:",
    ]
    lines.extend(f"- {state}" for state in DECISION_STATES)
    lines.append("Action classes:")
    lines.extend(f"- {item}" for item in ACTION_CLASSES)
    return "\n".join(lines)
