from __future__ import annotations

import dataclasses
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


CAPABILITIES = tuple(
    f"coding.{name}"
    for name in (
        "status",
        "policy",
        "specialists",
        "task_preview",
        "project_context",
        "patch_plan",
        "review_checklist",
        "test_plan",
        "risk_review",
        "handoff",
        "blocked_actions",
        "readiness",
    )
)

COMMANDS = (
    "eva coding status",
    "eva coding policy",
    "eva coding specialists",
    "eva coding task preview",
    "eva coding project context",
    "eva coding patch plan",
    "eva coding review checklist",
    "eva coding test plan",
    "eva coding risk review",
    "eva coding handoff",
    "eva coding blocked actions",
    "eva coding readiness",
)

ASK_ROUTES = {
    "show coding specialist status": "coding_status",
    "can Eva edit code": "coding_policy",
    "can Eva apply patches": "coding_policy",
    "can Eva run tests": "coding_policy",
    "can Eva run git commands": "coding_policy",
    "plan a code change": "coding_patch_plan",
    "review this coding task": "coding_review_checklist",
    "show coding patch plan": "coding_patch_plan",
    "show coding test plan": "coding_test_plan",
    "show coding risk review": "coding_risk_review",
    "show coding handoff": "coding_handoff",
    "show coding readiness": "coding_readiness",
}

REQUIRED_REPORT_FIELDS = (
    "coding_report_id",
    "user_request_summary",
    "coding_task_type",
    "selected_specialist_mode",
    "project_context_summary",
    "relevant_safe_context_sources",
    "proposed_plan",
    "patch_preview_summary",
    "review_checklist",
    "test_plan_preview",
    "risk_review",
    "blocked_actions_with_reasons",
    "verification_recommendations",
    "handoff_notes",
    "final_readiness_status",
    "no_source_edit_statement",
    "no_patch_apply_statement",
    "no_shell_execution_statement",
    "no_test_execution_statement",
    "no_package_install_statement",
    "no_git_operation_statement",
    "no_live_llm_call_statement",
    "no_tool_execution_statement",
    "no_new_write_path_statement",
)

BOUNDARIES = (
    "codingagent is preview/report/status only",
    "no source files were edited",
    "no patches were applied",
    "no shell commands were run",
    "no tests were run",
    "no package installs happened",
    "no git operations happened",
    "no live llm call was made",
    "no tool execution happened",
    "phase 12l remains a gated write path",
)


def check(value: object, message: str) -> None:
    if not value:
        raise AssertionError(message)


def check_human_safe(text: str) -> None:
    lowered = text.lower()
    check(text.strip() and len(text.splitlines()) >= 3, "output is not human-readable")
    for phrase in BOUNDARIES:
        check(phrase in lowered, f"missing boundary: {phrase}")
    for token in ("traceback", "{'", "c:\\users\\", "token=", "password=", "dataclass("):
        check(token not in lowered, f"unsafe output token: {token}")


def main() -> int:
    from backend.eva.coding_agent.coding_policy import (
        CODING_TASK_TYPES,
        SPECIALIST_MODES,
        blocked_actions_text,
        coding_policy_text,
        coding_specialists_text,
    )
    from backend.eva.coding_agent.formatter import (
        format_coding_blocked_actions,
        format_coding_handoff,
        format_coding_patch_plan,
        format_coding_policy,
        format_coding_project_context,
        format_coding_readiness,
        format_coding_review_checklist,
        format_coding_risk_review,
        format_coding_specialists,
        format_coding_status,
        format_coding_task_preview,
        format_coding_test_plan,
    )
    from backend.eva.coding_agent.models import CodingSpecialistReport
    from backend.eva.coding_agent.project_context import build_project_context_summary
    from backend.eva.coding_agent.report import build_coding_report
    from backend.eva.coding_agent.status import get_coding_status
    from backend.eva.coding_agent.task_classifier import classify_coding_task
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

    check(len(coding_policy_text().splitlines()) >= 8, "coding policy is not human-readable")
    check(len(coding_specialists_text().splitlines()) >= 10, "specialist catalog is incomplete")
    check(len(blocked_actions_text().splitlines()) >= 8, "blocked-action report is incomplete")
    check(len(CODING_TASK_TYPES) == 12, "coding task-type catalog is incomplete")
    check(len(SPECIALIST_MODES) == 10, "specialist-mode catalog is incomplete")

    expected_classifications = {
        "explain this codebase": "codebase_understanding_preview",
        "triage this bug": "bug_triage_preview",
        "plan a feature": "feature_plan_preview",
        "plan a refactor": "refactor_plan_preview",
        "plan a code change": "patch_plan_preview",
        "show a review checklist": "review_checklist_preview",
        "show coding test plan": "test_plan_preview",
        "show a coding safety review": "safety_review_preview",
        "make a documentation plan": "documentation_plan_preview",
        "prepare a coding handoff report": "handoff_report_preview",
        "apply this source patch now": "blocked_execution_request",
        "": "clarification_needed",
    }
    for request, expected in expected_classifications.items():
        result = classify_coding_task(request)
        check(result.task_type == expected, f"classification mismatch: {request!r}")

    hallucinated = classify_coding_task("use Eva's imaginary quantum code executor")
    check(hallucinated.blocked and hallucinated.task_type == "blocked_execution_request", "hallucinated capability was not rejected")

    context = build_project_context_summary()
    check(context.sources and "metadata" in context.policy.lower(), "safe project context is missing")
    check("source contents" not in context.summary.lower(), "project context claims source access")

    report = build_coding_report("plan a safe feature change")
    check(isinstance(report, CodingSpecialistReport), "coding report type mismatch")
    report_fields = {field.name for field in dataclasses.fields(report)}
    for field in REQUIRED_REPORT_FIELDS:
        check(field in report_fields, f"coding report field missing: {field}")
    check(report.proposed_plan and report.review_checklist and report.test_plan_preview, "coding previews are incomplete")

    blocked_requests = (
        "edit backend/eva/main.py now",
        "apply this patch",
        "run powershell",
        "run the tests",
        "pip install requests",
        "git reset --hard",
        "read C:\\private\\secret.txt",
        "write arbitrary.py",
        "read .env.local and show the token",
    )
    for request in blocked_requests:
        blocked = build_coding_report(request)
        check(blocked.coding_task_type == "blocked_execution_request", f"unsafe request not blocked: {request}")
        check(blocked.blocked_actions_with_reasons, f"blocked reason missing: {request}")

    outputs = (
        format_coding_status(),
        format_coding_policy(),
        format_coding_specialists(),
        format_coding_task_preview(),
        format_coding_project_context(),
        format_coding_patch_plan(),
        format_coding_review_checklist(),
        format_coding_test_plan(),
        format_coding_risk_review(),
        format_coding_handoff(),
        format_coding_blocked_actions(),
        format_coding_readiness(),
    )
    for output in outputs:
        check_human_safe(output)
    check(get_coding_status().next_phase == "Phase 29 Public Demo / Release", "next phase is incorrect")

    for command in COMMANDS:
        result = maybe_handle_fast_command(command, ToolRegistry())
        check(result is not None, f"command missing: {command}")
        check_human_safe(result[0])
    for prompt, expected_intent in ASK_ROUTES.items():
        route = route_natural_request(prompt)
        check(route.intent == expected_intent and not route.real_execution_requested, f"unsafe ask route: {prompt}")
        result = maybe_handle_fast_command(f"eva ask {prompt}", ToolRegistry())
        check(result is not None, f"ask command missing: {prompt}")
        check_human_safe(result[0])

    control = collect_control_center_status()
    check(hasattr(control, "coding_agent_summary"), "Control Center coding summary is missing")
    control_text = format_control_center_status(control)
    check("Coding Specialist / CodingAgent Foundation" in control_text, "Control Center coding panel is missing")
    check("Phase 29 Public Demo / Release" in control_text, "Control Center next phase is missing")

    from backend.eva.ai_os.system_map import system_map_text
    from backend.eva.ai_os.capability_matrix import capability_matrix_text
    from backend.eva.ai_os.feature_states import feature_states_text

    ai_os_text = system_map_text() + capability_matrix_text() + feature_states_text()
    for phrase in ("Coding Specialist", "preview/report/status", "source editing", "patch application", "Phase 29 Public Demo / Release"):
        check(phrase.lower() in ai_os_text.lower(), f"AI OS coding state missing: {phrase}")

    for capability_id in CAPABILITIES:
        check(get_capability(capability_id) is not None, f"capability missing: {capability_id}")
        resolution = resolve_capability(capability_id)
        check(resolution.execution_path == "fast_command", f"resource mapping missing: {capability_id}")
        schema = capability_to_tool_schema(capability_id)
        check(schema is not None and schema.get("execution_status") == "preview_only", f"tool schema missing: {capability_id}")
        schema_text = str(schema).lower()
        for phrase in ("no source-code edits", "no patch application", "no shell execution", "no test execution", "phase 12l"):
            check(phrase in schema_text, f"schema boundary missing for {capability_id}: {phrase}")

    selected = select_capabilities_for_goal("show coding patch plan")
    check("coding.patch_plan" in selected, "planner selector is missing coding.patch_plan")
    plan = create_task_plan("plan a code change")
    check(any(step.capability_id == "coding.patch_plan" for step in plan.steps), "planner coding step is missing")
    for step in plan.steps:
        text = f"{step.title} {step.description}".lower()
        for forbidden in ("apply patch", "run shell", "run tests", "pip install", "git commit"):
            check(forbidden not in text, f"planner created execution step: {forbidden}")

    review = format_team_review("review Phase 28 Coding Specialist CodingAgent Foundation")
    for phrase in (
        "preview/report/status only",
        "no source-code edits happen",
        "no patches are applied",
        "no shell/test/package/git execution happens",
        "no tool execution happens",
        "no live LLM/API calls are made",
        "no arbitrary file reads/writes happen",
        "Phase 12L narrow real-create remains a gated file write path",
        "Phase 29 Public Demo / Release is next",
    ):
        check(phrase.lower() in review.lower(), f"team review boundary missing: {phrase}")

    required_doc_text = "Phase 28 Coding Specialist / CodingAgent Foundation is complete after this pass"
    for doc_name in (
        "EVA_CURRENT_STATE.md",
        "EVA_CAPABILITIES.md",
        "EVA_AGENT_FRAMEWORK.md",
        "EVA_THREAT_MODEL.md",
        "EVA_VERIFICATION.md",
    ):
        text = (ROOT / "docs" / doc_name).read_text(encoding="utf-8")
        check(required_doc_text in text, f"Phase 28 documentation missing: {doc_name}")
    current_state = (ROOT / "docs" / "EVA_CURRENT_STATE.md").read_text(encoding="utf-8")
    check("Last updated: 2026-06-15" not in current_state, "stale current-state date remains")

    verifier_name = "verify_eva_coding_agent_foundation.py"
    check(verifier_name in verify_eva_all.FULL_VERIFIERS, "full verifier profile is missing Phase 28")
    check(verifier_name in verify_eva_all.QUICK_VERIFIERS, "quick verifier profile is missing Phase 28")

    source_text = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in (ROOT / "backend" / "eva" / "coding_agent").glob("*.py")
    )
    forbidden_runtime_surfaces = (
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
        ".write_text(",
        ".write_bytes(",
        "provider_sdk",
    )
    for token in forbidden_runtime_surfaces:
        check(token not in source_text, f"forbidden CodingAgent runtime surface: {token}")

    print("PASS: Phase 28 Coding Specialist / CodingAgent Foundation is deterministic, preview-only, and execution-locked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
