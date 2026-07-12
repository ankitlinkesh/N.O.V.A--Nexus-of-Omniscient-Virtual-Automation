from __future__ import annotations

import dataclasses
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


CAPABILITIES = tuple(
    f"rc.{name}"
    for name in (
        "status",
        "manifest",
        "commit_plan",
        "hardening_report",
        "checklist",
        "readiness",
        "safety_proof",
        "verification",
    )
)

COMMANDS = (
    "eva rc status",
    "eva rc manifest",
    "eva rc commit plan",
    "eva rc hardening report",
    "eva rc checklist",
    "eva rc readiness",
    "eva rc safety proof",
    "eva rc verification",
)

ASK_ROUTES = {
    "show release candidate status": "rc_status",
    "show rc status": "rc_status",
    "show dirty tree manifest": "rc_manifest",
    "show commit plan": "rc_commit_plan",
    "show hardening report": "rc_hardening_report",
    "show rc checklist": "rc_checklist",
    "is Eva safe to commit": "rc_readiness",
    "show rc verification": "rc_verification",
    "what should I commit": "rc_commit_plan",
    "is Eva ready for release candidate": "rc_readiness",
}

REQUIRED_MODEL_FIELDS = (
    "release_candidate_id",
    "phase",
    "head_reference",
    "dirty_tree_summary",
    "milestone_summary",
    "changed_area_groups",
    "untracked_area_groups",
    "commit_grouping_plan",
    "verification_status",
    "docs_consistency_status",
    "safety_boundary_status",
    "known_warnings",
    "blocking_issues",
    "non_blocking_warnings",
    "release_candidate_checklist",
    "recommended_next_action",
    "final_readiness_status",
    "no_commit_statement",
    "no_tag_statement",
    "no_push_statement",
    "no_publish_statement",
    "no_secret_read_statement",
    "no_runtime_execution_unlock_statement",
    "no_new_write_path_statement",
)

BOUNDARIES = (
    "no commit was made",
    "no tag was made",
    "no push was made",
    "no publishing/uploading was performed",
    "no secrets were read or exposed",
    "no live llm/api/provider call was made",
    "no browser control is enabled",
    "no desktop control is enabled",
    "no codingagent source editing is enabled",
    "no shell/test/package/git execution is enabled through eva",
    "no unrestricted crawler is enabled",
    "phase 12l remains a gated write path",
)


def check(value: object, message: str) -> None:
    if not value:
        raise AssertionError(message)


def check_human_safe(text: str) -> None:
    lowered = text.lower()
    check(text.strip() and len(text.splitlines()) >= 8, "RC output is not human-readable")
    for phrase in BOUNDARIES:
        check(phrase in lowered, f"RC output boundary missing: {phrase}")
    for token in ("traceback", "{'", "c:\\users\\", "token=", "password=", "dataclass("):
        check(token not in lowered, f"unsafe RC output token: {token}")


def main() -> int:
    from backend.eva.release_candidate.checklist import checklist_text
    from backend.eva.release_candidate.commit_plan import commit_plan_text
    from backend.eva.release_candidate.formatter import (
        format_rc_checklist,
        format_rc_commit_plan,
        format_rc_hardening_report,
        format_rc_manifest,
        format_rc_readiness,
        format_rc_safety_proof,
        format_rc_status,
        format_rc_verification,
    )
    from backend.eva.release_candidate.hardening import hardening_report_text
    from backend.eva.release_candidate.manifest import dirty_tree_manifest_text
    from backend.eva.release_candidate.models import ReleaseCandidateReport
    from backend.eva.release_candidate.readiness import readiness_text
    from backend.eva.release_candidate.report import build_release_candidate_report
    from backend.eva.release_candidate.status import get_release_candidate_status
    from backend.eva.core.fast_commands import maybe_handle_fast_command
    from backend.eva.core.natural_router import route_natural_request
    from backend.eva.tools.registry import ToolRegistry
    from backend.eva.control_center.collector import collect_control_center_status
    from backend.eva.control_center.formatter import format_control_center_status
    from backend.eva.capabilities.registry import get_capability
    from backend.eva.capabilities.resource_mapping import resolve_capability
    from backend.eva.capabilities.tool_schemas import capability_to_tool_schema
    from backend.eva.planner.capability_selector import select_capabilities_for_goal
    from backend.eva.planner.decomposer import create_task_plan
    from backend.eva.agents.team_review import format_team_review
    from scripts import verify_eva_all

    for text in (
        dirty_tree_manifest_text(),
        commit_plan_text(),
        hardening_report_text(),
        checklist_text(),
        readiness_text(),
    ):
        check(len(text.splitlines()) >= 6, "RC component is not human-readable")

    report = build_release_candidate_report()
    check(isinstance(report, ReleaseCandidateReport), "RC report type mismatch")
    fields = {field.name for field in dataclasses.fields(report)}
    for field in REQUIRED_MODEL_FIELDS:
        check(field in fields, f"RC model field missing: {field}")
    check(report.head_reference == "4f364d2", "RC HEAD reference does not match the audited baseline")
    check(report.commit_grouping_plan, "RC commit grouping plan is empty")
    check(report.release_candidate_checklist, "RC checklist is empty")
    check(report.blocking_issues == (), "RC report has unresolved blocking issues")

    status = get_release_candidate_status()
    check(status.available is True, "RC status must be available")
    check(status.mode == "report/status/planning only", "RC status mode is unsafe")
    check(status.git_operations_enabled is False, "RC git operations must remain disabled")
    check(status.publishing_enabled is False, "RC publishing must remain disabled")
    check(status.runtime_execution_enabled is False, "RC runtime execution must remain disabled")

    outputs = (
        format_rc_status(),
        format_rc_manifest(),
        format_rc_commit_plan(),
        format_rc_hardening_report(),
        format_rc_checklist(),
        format_rc_readiness(),
        format_rc_safety_proof(),
        format_rc_verification(),
    )
    for output in outputs:
        check_human_safe(output)

    for command in COMMANDS:
        result = maybe_handle_fast_command(command, ToolRegistry())
        check(result is not None, f"RC command missing: {command}")
        check_human_safe(result[0])
    for prompt, expected_intent in ASK_ROUTES.items():
        route = route_natural_request(prompt)
        check(
            route.intent == expected_intent and not route.real_execution_requested,
            f"unsafe RC ask route: {prompt}",
        )
        result = maybe_handle_fast_command(f"eva ask {prompt}", ToolRegistry())
        check(result is not None, f"RC ask command missing: {prompt}")
        check_human_safe(result[0])

    control = collect_control_center_status()
    check(hasattr(control, "release_candidate_summary"), "Control Center RC summary is missing")
    control_text = format_control_center_status(control)
    for phrase in (
        "Release Candidate Hardening",
        "Dirty tree summary",
        "Commit-plan summary",
        "No-commit/no-publish boundary",
        "user-approved commit execution outside Eva",
    ):
        check(phrase.lower() in control_text.lower(), f"Control Center RC panel missing: {phrase}")

    from backend.eva.ai_os.system_map import system_map_text
    from backend.eva.ai_os.capability_matrix import capability_matrix_text
    from backend.eva.ai_os.feature_states import feature_states_text

    ai_os_text = system_map_text() + capability_matrix_text() + feature_states_text()
    for phrase in (
        "Release Candidate Hardening",
        "report/status/planning only",
        "commit planning is text-only",
        "no git operations",
        "no publishing",
        "user-approved commit execution outside Eva",
    ):
        check(phrase.lower() in ai_os_text.lower(), f"AI OS RC state missing: {phrase}")

    for capability_id in CAPABILITIES:
        check(get_capability(capability_id) is not None, f"RC capability missing: {capability_id}")
        resolution = resolve_capability(capability_id)
        check(resolution.execution_path == "fast_command", f"RC mapping missing: {capability_id}")
        schema = capability_to_tool_schema(capability_id)
        check(
            schema is not None and schema.get("execution_status") == "report_only",
            f"RC schema missing: {capability_id}",
        )
        schema_text = str(schema).lower()
        for phrase in (
            "report/status/planning only",
            "no git commit/tag/push",
            "no staging",
            "no publish/upload",
            "no shell/package/cloud/mcp execution",
            "no browser/desktop control",
            "no source-code edits",
            "no arbitrary filesystem reads/writes",
            "no secret/config/session reads",
            "no live llm/api/provider calls",
            "no tool execution",
            "phase 12l",
        ):
            check(phrase in schema_text, f"RC schema boundary missing for {capability_id}: {phrase}")

    selected = select_capabilities_for_goal("is Eva ready for release candidate")
    check("rc.readiness" in selected, "planner selector is missing rc.readiness")
    plan = create_task_plan("show commit plan")
    check(any(step.capability_id == "rc.commit_plan" for step in plan.steps), "planner RC step is missing")
    for step in plan.steps:
        text = f"{step.title} {step.description}".lower()
        for forbidden in (
            "execute git",
            "stage files",
            "publish package",
            "run shell",
            "browser control",
            "desktop control",
            "edit source",
            "call mcp",
        ):
            check(forbidden not in text, f"planner created RC execution step: {forbidden}")

    review = format_team_review("review Phase 30 Release Candidate Hardening")
    for phrase in (
        "report/status/planning only",
        "commit plan is text only",
        "no git commit/add/tag/push happens",
        "no publishing happens",
        "no source-code edits happen through CodingAgent",
        "no browser/desktop control happens",
        "no shell/test/package/git execution happens through Eva",
        "no tool execution happens",
        "no live LLM/API calls are made",
        "no arbitrary file reads/writes happen",
        "no secret/config/session reads happen",
        "Phase 12L narrow real-create remains a gated file write path",
        "user-approved commit execution outside Eva",
    ):
        check(phrase.lower() in review.lower(), f"team review RC boundary missing: {phrase}")

    required_phase_text = "Phase 30 Release Candidate Hardening / Commit Planning is complete after this pass"
    for doc_name in (
        "EVA_RELEASE_CANDIDATE.md",
        "EVA_COMMIT_PLAN.md",
        "EVA_RC_HARDENING_REPORT.md",
        "EVA_RC_CHECKLIST.md",
        "EVA_DIRTY_TREE_MANIFEST.md",
        "EVA_CURRENT_STATE.md",
        "EVA_VERIFICATION.md",
        "EVA_BUG_QUEUE.md",
        "EVA_RELEASE_READINESS.md",
        "EVA_SAFETY_PROOF.md",
        "EVA_LIMITATIONS.md",
        "EVA_CAPABILITY_MAP.md",
    ):
        text = (ROOT / "docs" / doc_name).read_text(encoding="utf-8")
        check(required_phase_text in text, f"Phase 30 documentation missing: {doc_name}")
        lowered = text.lower()
        for phrase in (
            "report/status/planning only",
            "commit plan is text only",
            "phase 12l",
            "no publishing/uploading",
            "no real llm/api/provider calls",
        ):
            check(phrase in lowered, f"Phase 30 doc boundary missing in {doc_name}: {phrase}")
        check("c:\\users\\" not in lowered, f"Phase 30 doc exposes a private path: {doc_name}")

    verifier_name = "verify_eva_release_candidate_hardening.py"
    check(verifier_name in verify_eva_all.FULL_VERIFIERS, "full profile is missing Phase 30")
    check(verifier_name in verify_eva_all.QUICK_VERIFIERS, "quick profile is missing Phase 30")

    source_text = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in (ROOT / "backend" / "eva" / "release_candidate").glob("*.py")
    )
    for token in (
        "import subprocess",
        "from subprocess",
        "os.system(",
        "requests.",
        "httpx.",
        "urllib.request",
        "playwright",
        "selenium",
        "pyautogui",
        "open(",
        ".read_text(",
        ".write_text(",
        ".write_bytes(",
        "provider_sdk",
        "pip install",
    ):
        check(token not in source_text, f"forbidden RC runtime surface: {token}")

    print("PASS: Phase 30 Release Candidate Hardening is deterministic, report-only, and commit-locked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
