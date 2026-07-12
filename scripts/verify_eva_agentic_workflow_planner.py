from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


WORKFLOW_CAPABILITIES = (
    "workflow_planner.status",
    "workflow_planner.catalog",
    "workflow_planner.policy",
    "workflow_planner.preview",
    "workflow_planner.dependencies",
    "workflow_planner.approvals",
    "workflow_planner.rollback",
    "workflow_planner.readiness",
)

WORKFLOW_COMMANDS = (
    "eva workflow planner status",
    "eva workflow planner catalog",
    "eva workflow planner policy",
    "eva workflow planner preview",
    "eva workflow planner dependencies",
    "eva workflow planner approvals",
    "eva workflow planner rollback",
    "eva workflow planner readiness",
)

ASK_ROUTES = {
    "plan a workflow preview": "workflow_planner_preview",
    "show workflow planner status": "workflow_planner_status",
    "how does Eva choose workflows": "workflow_planner_policy",
    "can workflow planner execute tools": "workflow_planner_policy",
    "show workflow dependencies": "workflow_planner_dependencies",
    "show workflow approval preview": "workflow_planner_approvals",
    "show workflow rollback plan": "workflow_planner_rollback",
    "show workflow planner readiness": "workflow_planner_readiness",
}

DOCS = (
    "EVA_CURRENT_STATE.md",
    "EVA_CAPABILITIES.md",
    "EVA_AGENT_FRAMEWORK.md",
    "EVA_THREAT_MODEL.md",
    "EVA_VERIFICATION.md",
)


def check(value: object, message: str) -> None:
    if not value:
        raise AssertionError(message)


def assert_human_safe(output: str, label: str) -> None:
    lowered = output.lower()
    check("traceback" not in lowered and "{'" not in output and "dataclass" not in lowered, f"raw output leaked in {label}")
    check("c:\\users\\" not in lowered, f"private path leaked in {label}")
    check("openai_api_key" not in lowered and "token=" not in lowered and "cookie=" not in lowered, f"secret-like text leaked in {label}")
    check("no live llm call was made" in lowered, f"missing no-live-call boundary in {label}")
    check("workflow planner is local/mock preview only" in lowered, f"missing local/mock boundary in {label}")
    check("workflow steps are preview-only" in lowered, f"missing preview-only steps boundary in {label}")
    check("tools are not executed" in lowered, f"missing no-tool boundary in {label}")
    check("secrets/config/session data are blocked" in lowered, f"missing secret/session boundary in {label}")
    check("arbitrary file reads/writes are blocked" in lowered, f"missing file read/write boundary in {label}")
    check("browser/desktop/shell/cloud/mcp execution remains locked" in lowered, f"missing execution lock boundary in {label}")
    check("phase 12l remains a gated write path" in lowered, f"missing Phase 12L boundary in {label}")


def _step_types(plan: object) -> set[str]:
    return {step.step_type for step in getattr(plan, "ordered_steps", ())}


def main() -> int:
    from backend.eva.agents.team_review import format_team_review
    from backend.eva.capabilities.registry import get_capability
    from backend.eva.capabilities.resource_mapping import resolve_capability
    from backend.eva.capabilities.tool_schemas import capability_to_tool_schema
    from backend.eva.control_center.collector import collect_control_center_status
    from backend.eva.control_center.formatter import format_control_center_status, render_control_center_html
    from backend.eva.core.fast_commands import maybe_handle_fast_command
    from backend.eva.core.natural_router import route_natural_request
    from backend.eva.planner.capability_selector import select_capabilities_for_goal
    from backend.eva.planner.decomposer import create_task_plan
    from backend.eva.tools.registry import ToolRegistry
    from backend.eva.workflow_planner.formatter import (
        format_workflow_planner_approvals,
        format_workflow_planner_catalog,
        format_workflow_planner_dependencies,
        format_workflow_planner_policy,
        format_workflow_planner_preview,
        format_workflow_planner_readiness,
        format_workflow_planner_rollback,
        format_workflow_planner_status,
    )
    from backend.eva.workflow_planner.runner_preview import run_workflow_preview
    from backend.eva.workflow_planner.status import get_workflow_planner_status
    from backend.eva.workflow_planner.workflow_catalog import list_workflow_templates, workflow_catalog_text
    from backend.eva.workflow_planner.workflow_policy import workflow_policy_text
    from scripts import verify_eva_all

    status = get_workflow_planner_status()
    check(status.mode == "local/mock preview only", "unsafe workflow planner mode")
    check(not status.live_llm_calls_enabled and not status.tool_execution_enabled, "workflow planner enabled unsafe execution")
    check(not status.arbitrary_file_reads_enabled and not status.arbitrary_file_writes_enabled, "workflow planner enabled arbitrary file IO")
    for text in (workflow_catalog_text(), workflow_policy_text(), format_workflow_planner_status()):
        assert_human_safe(text, "catalog/policy/status")

    templates = list_workflow_templates()
    categories = {item.category for item in templates}
    for category in (
        "status_review",
        "project_inspection_preview",
        "fileagent_project_note_preview",
        "verification_summary",
        "safety_review",
        "context_assembly_review",
        "threat_defense_review",
        "agent_loop_preview",
        "planning_only",
        "clarification_needed",
        "refusal_or_blocked",
    ):
        check(category in categories, f"workflow category missing: {category}")

    safe_plan = run_workflow_preview("plan a safe project status workflow preview")
    required_model_fields = (
        "workflow_id",
        "workflow_name",
        "user_request_summary",
        "selected_template",
        "relevance_score",
        "workflow_category",
        "ordered_steps",
        "dependencies",
        "preconditions",
        "selected_capabilities",
        "permission_classes",
        "risk_levels",
        "action_previews",
        "approval_requirements",
        "rollback_plan_preview",
        "verification_plan",
        "blocked_steps",
        "excluded_steps",
        "final_readiness_status",
        "no_live_llm_call_statement",
        "no_tool_execution_statement",
        "no_real_write_statement",
    )
    for field_name in required_model_fields:
        check(hasattr(safe_plan, field_name), f"workflow model missing {field_name}")
    check(safe_plan.final_readiness_status == "ready_preview_only", "safe workflow not ready as preview")
    check("final_report_preview" in _step_types(safe_plan), "safe workflow missing final report step")
    assert_human_safe(safe_plan.format(), "safe workflow")

    unsafe_cases = {
        "plan workflow to execute tool and run shell": "refusal_or_blocked",
        "plan browser desktop cloud MCP workflow": "refusal_or_blocked",
        "read .env and cookies in workflow": "refusal_or_blocked",
        "read arbitrary file and write arbitrary file": "refusal_or_blocked",
        "use workflow_planner.super_execute capability": "refusal_or_blocked",
    }
    for request, expected_category in unsafe_cases.items():
        plan = run_workflow_preview(request)
        check(plan.workflow_category == expected_category, f"unsafe workflow category mismatch: {request}")
        check(plan.blocked_steps, f"unsafe workflow missing blocked steps: {request}")
        check("refusal_preview" in _step_types(plan), f"unsafe workflow missing refusal preview: {request}")
        assert_human_safe(plan.format(), request)

    cycle_plan = run_workflow_preview("plan workflow with dependency cycle")
    check(cycle_plan.final_readiness_status == "blocked_preview", "dependency cycle was not blocked")
    check("dependency cycle" in " ".join(step.reason for step in cycle_plan.blocked_steps).lower(), "cycle reason missing")
    missing_precondition = run_workflow_preview("plan workflow with missing approval precondition")
    check(any(not item.satisfied for item in missing_precondition.preconditions), "missing precondition not reported")
    high_risk = run_workflow_preview("plan future high risk fileagent project note workflow")
    check(high_risk.approval_requirements and any("future approval" in item.requirement.lower() for item in high_risk.approval_requirements), "approval preview missing for high-risk workflow")
    check(high_risk.rollback_plan_preview.steps, "rollback plan preview missing")
    check(high_risk.verification_plan.checks, "verification plan missing")

    formatter_outputs = (
        format_workflow_planner_status(),
        format_workflow_planner_catalog(),
        format_workflow_planner_policy(),
        format_workflow_planner_preview("plan a workflow preview"),
        format_workflow_planner_dependencies("show workflow dependencies"),
        format_workflow_planner_approvals("show workflow approval preview"),
        format_workflow_planner_rollback("show workflow rollback plan"),
        format_workflow_planner_readiness(),
    )
    for index, output in enumerate(formatter_outputs):
        assert_human_safe(output, f"formatter {index}")

    for command in WORKFLOW_COMMANDS:
        result = maybe_handle_fast_command(command, ToolRegistry())
        check(result is not None, f"command missing: {command}")
        assert_human_safe(result[0], command)

    for prompt, intent in ASK_ROUTES.items():
        route = route_natural_request(prompt)
        check(route.intent == intent and not route.real_execution_requested, f"bad ask route: {prompt}")
        result = maybe_handle_fast_command(f"eva ask {prompt}", ToolRegistry())
        check(result is not None and "Eva ask" in result[0], f"ask command missing: {prompt}")
        assert_human_safe(result[0], f"ask {prompt}")

    control = collect_control_center_status()
    check(control.workflow_planner_summary.get("status") == "available", "Control Center Workflow Planner summary missing")
    check("Agentic Workflow Planner" in format_control_center_status(control), "Control Center text panel missing")
    check("Agentic Workflow Planner" in render_control_center_html(control), "Control Center HTML panel missing")

    for capability_id in WORKFLOW_CAPABILITIES:
        capability = get_capability(capability_id)
        check(capability is not None and capability.read_only, f"capability missing or unsafe: {capability_id}")
        resolution = resolve_capability(capability_id)
        check(resolution.preview_only and resolution.execution_path in {"fast_command", "preview_only"}, f"resource mapping unsafe: {capability_id}")
        schema = capability_to_tool_schema(capability_id)
        check(schema and schema.get("execution_status") == "read_only_metadata", f"schema missing: {capability_id}")
        safety_notes = " ".join(str(item) for item in schema.get("safety_notes", [])).lower()
        for phrase in (
            "local/mock preview only",
            "no live llm call",
            "no tool execution",
            "no secret/config/session reads",
            "no arbitrary filesystem reads",
            "no arbitrary filesystem writes",
            "no browser/desktop/shell/cloud/mcp execution",
            "output is workflow/report/status only",
        ):
            check(phrase in safety_notes, f"schema boundary missing {phrase}: {capability_id}")

    selected = select_capabilities_for_goal("show workflow planner readiness")
    check(selected == ["workflow_planner.readiness"], "planner selected unsafe workflow planner capability")
    task_plan = create_task_plan("plan a workflow preview")
    check(any(step.capability_id == "workflow_planner.preview" for step in task_plan.steps), "planner workflow preview step missing")
    forbidden_text = " ".join(f"{step.title} {step.description} {step.capability_id}" for step in task_plan.steps).lower()
    for forbidden in ("browser action", "desktop action", "shell", "package", "provider-call", "arbitrary file-read", "arbitrary file-write", "mcp"):
        check(forbidden not in forbidden_text, f"planner decomposed workflow planner into forbidden step: {forbidden}")

    review = format_team_review("review Phase 19 workflow planner boundaries")
    for phrase in (
        "Workflow Planner v1 is local/mock only",
        "no live LLM/API calls are made",
        "workflow steps are preview-only",
        "tools are not executed",
        "secrets/config/session reads remain blocked",
        "arbitrary file reads/writes remain blocked",
        "browser/desktop execution remains locked",
        "dependency cycles and unsupported workflows fail safely",
        "Phase 20 Controlled Execution Gates is next",
    ):
        check(phrase.lower() in review.lower(), f"team review missing: {phrase}")

    required_doc_phrases = (
        "Phase 19 Agentic Workflow Planner",
        "local/mock preview only",
        "no live LLM/API/provider calls",
        "no provider SDKs are used",
        "arbitrary file reads/writes are blocked",
        "all workflow steps are preview-only",
        "workflow planner cannot execute tools",
        "browser/desktop/shell/cloud/MCP execution remains locked",
        "workflow dependency validation, precondition checks, approval previews, rollback previews, and verification plans are implemented",
        "Phase 12L narrow approved new `.md`/`.txt` creation remains a gated write path",
        "Phase 20 Controlled Execution Gates",
    )
    for doc in DOCS:
        text = (ROOT / "docs" / doc).read_text(encoding="utf-8")
        for phrase in required_doc_phrases:
            check(phrase in text, f"docs missing {phrase}: {doc}")

    check("verify_eva_agentic_workflow_planner.py" in verify_eva_all.FULL_VERIFIERS, "full master profile missing Phase 19")
    check("verify_eva_agentic_workflow_planner.py" in verify_eva_all.QUICK_VERIFIERS, "quick master profile missing Phase 19")

    source = "\n".join(path.read_text(encoding="utf-8").lower() for path in (ROOT / "backend/eva/workflow_planner").glob("*.py"))
    for forbidden in ("import requests", "httpx", "urllib.request", "subprocess", "playwright", "pyautogui", "os.system", "open("):
        check(forbidden not in source, f"forbidden runtime surface in workflow planner source: {forbidden}")

    print("PASS: Phase 19 Agentic Workflow Planner is local, deterministic, bounded, preview-only, and fully wired.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
