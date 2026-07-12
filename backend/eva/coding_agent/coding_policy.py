from __future__ import annotations


CODING_TASK_TYPES = (
    "codebase_understanding_preview",
    "bug_triage_preview",
    "feature_plan_preview",
    "refactor_plan_preview",
    "patch_plan_preview",
    "review_checklist_preview",
    "test_plan_preview",
    "safety_review_preview",
    "documentation_plan_preview",
    "handoff_report_preview",
    "blocked_execution_request",
    "clarification_needed",
)

SPECIALIST_MODES = (
    "codebase_reader_preview",
    "bug_triage_specialist",
    "feature_planning_specialist",
    "refactor_planning_specialist",
    "patch_planning_specialist",
    "reviewer_specialist",
    "test_planning_specialist",
    "safety_reviewer_specialist",
    "documentation_specialist",
    "handoff_specialist",
)

BOUNDARY_LINES = (
    "CodingAgent is preview/report/status only.",
    "No source files were edited.",
    "No patches were applied.",
    "No shell commands were run.",
    "No tests were run.",
    "No package installs happened.",
    "No git operations happened.",
    "No live LLM call was made.",
    "No tool execution happened.",
    "Phase 12L remains a gated write path.",
)


def coding_policy_text() -> str:
    return "\n".join(
        (
            "Coding Specialist policy",
            "- Deterministic local classification and planning previews are allowed.",
            "- Safe context is limited to existing metadata, status, and documentation summaries.",
            "- Patch plans, reviews, test plans, risk reviews, and handoffs are text previews.",
            "- Source editing and direct patch application are blocked.",
            "- Shell, test, package, git, browser, desktop, cloud, and MCP execution are blocked.",
            "- Arbitrary filesystem reads and writes are blocked.",
            "- Secret, configuration, session, raw source, memory-database, and WorkSession dumps are blocked.",
            "- Unknown or hallucinated coding capabilities are rejected.",
            "- No new write path is introduced.",
        )
    )


def coding_specialists_text() -> str:
    labels = {
        "codebase_reader_preview": "summarizes safe project metadata",
        "bug_triage_specialist": "organizes reproduction and diagnosis questions",
        "feature_planning_specialist": "builds a bounded feature plan",
        "refactor_planning_specialist": "builds a behavior-preserving refactor plan",
        "patch_planning_specialist": "describes a patch plan without applying it",
        "reviewer_specialist": "prepares a review checklist",
        "test_planning_specialist": "prepares test instructions without running them",
        "safety_reviewer_specialist": "reviews coding risk and blocked actions",
        "documentation_specialist": "prepares documentation-change plans",
        "handoff_specialist": "prepares a concise implementation handoff",
    }
    return "\n".join(
        ["Coding Specialist modes"]
        + [f"- {mode}: {labels[mode]}." for mode in SPECIALIST_MODES]
    )


def blocked_actions_text() -> str:
    return "\n".join(
        (
            "CodingAgent blocked actions",
            "- Source-code edit: blocked; planning text only.",
            "- Patch application: blocked; patch previews are never applied.",
            "- Shell or command execution: blocked.",
            "- Test execution: blocked; test plans are instructions only.",
            "- Package installation: blocked.",
            "- Git operations: blocked.",
            "- Arbitrary filesystem read or write: blocked.",
            "- Secret, configuration, session, or raw private dump access: blocked.",
            "- Live LLM, API, provider, tool, browser, desktop, cloud, or MCP execution: blocked.",
            "- New write paths: blocked; the existing Phase 12L narrow gate is unchanged.",
        )
    )
