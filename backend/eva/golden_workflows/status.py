from __future__ import annotations

from .formatter import format_golden_workflow_status
from .runner import get_golden_workflow_status


def format_golden_workflows_text() -> str:
    return format_golden_workflow_status(get_golden_workflow_status())


def format_golden_workflow_test_plan() -> str:
    return "\n".join(
        [
            "Golden workflow test plan",
            "",
            "1. Natural request selects FileAgent project-note workflow.",
            "2. Draft and approval metadata are created; no real file is created.",
            "3. Approval must be reviewed and approved with its exact phrase.",
            "4. Sandbox apply verifies the approved record without touching real project files.",
            "5. Phase 12L real create requires `confirm real create <approval_id>`.",
            "6. Verification checks the created file content hash.",
            "7. Rollback remains guarded by `confirm rollback real create <approval_id>` and only removes unchanged Eva-created files.",
            "",
            "Scope: status/test-plan only. This command does not execute any workflow step.",
        ]
    )


def format_golden_workflow_latest() -> str:
    from ..skills.workflow_state import format_workflow_state_summary, summarize_fileagent_workflow_state

    return "\n\n".join(
        [
            "Golden workflow latest",
            format_golden_workflows_text(),
            format_workflow_state_summary(summarize_fileagent_workflow_state()),
        ]
    )


def format_golden_workflow_proof() -> str:
    from ..work_sessions.formatter import summarize_recent_work_sessions
    from ..skills.workflow_state import summarize_fileagent_workflow_state

    status = get_golden_workflow_status()
    state = summarize_fileagent_workflow_state()
    rollback_phrase = f"confirm rollback real create {status.latest_approval_id}" if status.latest_approval_id else "confirm rollback real create <approval_id>"
    lines = [
        "Golden workflow proof",
        "",
        f"Latest stage: {status.latest_stage}",
        f"Latest approval: {status.latest_approval_id or 'none'}",
        f"Approval state: pending {status.pending_approvals}; approved {status.approved_for_future_apply}",
        f"Real create state: {status.latest_real_create_status}",
        f"Verification state: {state.latest_real_create.message}",
        f"Rollback availability: {'yes' if status.rollback_available else 'no'}",
        f"Rollback exact phrase: {rollback_phrase}",
        "Gated write path: Phase 12L narrow real create for approved new .md/.txt files under docs/ or samples/.",
        "",
        "Latest WorkSession evidence:",
        summarize_recent_work_sessions(limit=3),
        "",
        "Blocked/locked actions:",
        "- existing file edits",
        "- source/config/runtime writes",
        "- broad apply",
        "- browser/desktop/shell/MCP/package/cloud execution",
        "",
        "Scope: proof/status only. No workflow step was executed.",
    ]
    return "\n".join(lines)
