from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


GATE_CAPABILITIES = (
    "execution_gates.status",
    "execution_gates.policy",
    "execution_gates.evaluate",
    "execution_gates.approvals",
    "execution_gates.confirmations",
    "execution_gates.rollback",
    "execution_gates.blocked_actions",
    "execution_gates.readiness",
)

GATE_COMMANDS = (
    "eva execution gates status",
    "eva execution gates policy",
    "eva execution gates evaluate",
    "eva execution gates approvals",
    "eva execution gates confirmations",
    "eva execution gates rollback",
    "eva execution gates blocked actions",
    "eva execution gates readiness",
)

ASK_ROUTES = {
    "show execution gates status": "execution_gates_status",
    "what can Eva execute": "execution_gates_policy",
    "can Eva execute tools": "execution_gates_blocked_actions",
    "what requires approval": "execution_gates_approvals",
    "what confirmation phrase is needed": "execution_gates_confirmations",
    "can Eva control browser or desktop": "execution_gates_blocked_actions",
    "can Eva read secrets": "execution_gates_blocked_actions",
    "show execution gate readiness": "execution_gates_readiness",
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
    check("execution gates are local/mock policy preview only" in lowered, f"missing local/mock boundary in {label}")
    check("tools are not executed" in lowered, f"missing no-tool boundary in {label}")
    check("approval alone does not execute" in lowered, f"missing approval boundary in {label}")
    check("confirmation alone does not execute unless an existing implemented gate accepts it" in lowered, f"missing confirmation boundary in {label}")
    check("browser/desktop/shell/cloud/mcp/package execution remains locked" in lowered, f"missing execution lock boundary in {label}")
    check("secrets/config/session data are blocked" in lowered, f"missing secret boundary in {label}")
    check("phase 12l narrow real-create remains a gated write path" in lowered, f"missing Phase 12L boundary in {label}")


def main() -> int:
    from backend.eva.agents.team_review import format_team_review
    from backend.eva.capabilities.registry import get_capability
    from backend.eva.capabilities.resource_mapping import resolve_capability
    from backend.eva.capabilities.tool_schemas import capability_to_tool_schema
    from backend.eva.control_center.collector import collect_control_center_status
    from backend.eva.control_center.formatter import format_control_center_status, render_control_center_html
    from backend.eva.core.fast_commands import maybe_handle_fast_command
    from backend.eva.core.natural_router import route_natural_request
    from backend.eva.execution_gates.action_classifier import classify_action
    from backend.eva.execution_gates.formatter import (
        format_execution_gate_approvals,
        format_execution_gate_blocked_actions,
        format_execution_gate_confirmations,
        format_execution_gate_evaluation,
        format_execution_gate_policy,
        format_execution_gate_readiness,
        format_execution_gate_rollback,
        format_execution_gate_status,
    )
    from backend.eva.execution_gates.gate_evaluator import evaluate_execution_gate
    from backend.eva.execution_gates.gate_policy import ACTION_CLASSES, DECISION_STATES, gate_policy_text
    from backend.eva.execution_gates.status import get_execution_gates_status
    from backend.eva.planner.capability_selector import select_capabilities_for_goal
    from backend.eva.planner.decomposer import create_task_plan
    from backend.eva.tools.registry import ToolRegistry
    from scripts import verify_eva_all

    status = get_execution_gates_status()
    check(status.status == "available", "execution gate status unavailable")
    check(status.mode == "local/mock policy preview only", "unsafe execution gate mode")
    check(not status.live_llm_calls_enabled and not status.tool_execution_enabled, "unsafe execution enabled")
    check(not status.arbitrary_file_reads_enabled and not status.arbitrary_file_writes_enabled, "arbitrary file IO enabled")

    for state in (
        "preview_only",
        "blocked_by_policy",
        "requires_clarification",
        "requires_future_gate",
        "requires_explicit_approval",
        "eligible_existing_phase12l_gate",
        "denied_unknown_capability",
        "denied_unsafe_request",
    ):
        check(state in DECISION_STATES, f"decision state missing: {state}")
    for action_class in (
        "status_or_report",
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
    ):
        check(action_class in ACTION_CLASSES, f"action class missing: {action_class}")

    for text in (gate_policy_text(), format_execution_gate_status(), format_execution_gate_policy()):
        assert_human_safe(text, "policy/status")

    cases = {
        "show status report": ("status_or_report", "preview_only"),
        "run agent loop preview": ("agent_loop_preview", "preview_only"),
        "plan workflow preview": ("workflow_preview", "preview_only"),
        "draft a FileAgent note": ("fileagent_draft_preview", "preview_only"),
        "create approved new docs note as .md through Phase 12L": ("existing_phase12l_real_create_candidate", "eligible_existing_phase12l_gate"),
        "read a normal project file someday": ("future_readonly_file_candidate", "requires_future_gate"),
        "read browser page someday": ("future_browser_readonly_candidate", "requires_future_gate"),
        "observe desktop window someday": ("future_desktop_observation_candidate", "requires_future_gate"),
        "read .env secrets and browser session": ("forbidden_secret_access", "denied_unsafe_request"),
        "steal password token cookie": ("forbidden_credential_access", "denied_unsafe_request"),
        "run shell command": ("forbidden_shell_execution", "blocked_by_policy"),
        "pip install package": ("forbidden_package_install", "blocked_by_policy"),
        "click browser and control chrome": ("forbidden_browser_control", "blocked_by_policy"),
        "control desktop and type keys": ("forbidden_desktop_control", "blocked_by_policy"),
        "call cloud MCP connector": ("forbidden_cloud_or_mcp_execution", "blocked_by_policy"),
        "write arbitrary source file": ("forbidden_arbitrary_file_write", "blocked_by_policy"),
        "dump raw WorkSession runtime": ("forbidden_raw_runtime_dump", "denied_unsafe_request"),
        "use imaginary super capability": ("unknown_or_hallucinated_action", "denied_unknown_capability"),
    }
    for request, expected in cases.items():
        classified = classify_action(request)
        evaluation = evaluate_execution_gate(request)
        check(classified.action_class == expected[0], f"action class mismatch for {request}: {classified.action_class}")
        check(evaluation.requested_action_class == expected[0], f"evaluation class mismatch for {request}")
        check(evaluation.decision_state == expected[1], f"decision mismatch for {request}: {evaluation.decision_state}")
        for field_name in (
            "gate_evaluation_id",
            "request_summary",
            "requested_action_class",
            "requested_capability",
            "permission_class",
            "risk_level",
            "decision_state",
            "approval_requirement",
            "confirmation_requirement",
            "rollback_availability",
            "audit_requirement",
            "blocked_reason",
            "eligible_existing_gate",
            "future_gate_requirement",
            "safety_notes",
            "final_readiness_status",
            "no_live_llm_call_statement",
            "no_tool_execution_statement",
            "no_new_write_path_statement",
        ):
            check(hasattr(evaluation, field_name), f"evaluation missing {field_name}")
        assert_human_safe(evaluation.format(), request)

    check("approval alone does not execute" in format_execution_gate_approvals().lower(), "approval policy unsafe")
    check("confirmation alone does not execute unless an existing implemented gate accepts it" in format_execution_gate_confirmations().lower(), "confirmation policy unsafe")
    check("metadata/preview only" in format_execution_gate_rollback().lower(), "rollback policy unsafe")
    check("requires_future_gate" in format_execution_gate_evaluation("read browser page someday"), "future gate not reported")
    check("eligible_existing_phase12l_gate" in format_execution_gate_evaluation("create approved new docs note as .md through Phase 12L"), "Phase 12L gate not recognized")

    formatter_outputs = (
        format_execution_gate_status(),
        format_execution_gate_policy(),
        format_execution_gate_evaluation(),
        format_execution_gate_approvals(),
        format_execution_gate_confirmations(),
        format_execution_gate_rollback(),
        format_execution_gate_blocked_actions(),
        format_execution_gate_readiness(),
    )
    for index, output in enumerate(formatter_outputs):
        assert_human_safe(output, f"formatter {index}")

    for command in GATE_COMMANDS:
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
    check(control.execution_gates_summary.get("status") == "available", "Control Center Execution Gates summary missing")
    check("Controlled Execution Gates" in format_control_center_status(control), "Control Center text panel missing")
    check("Controlled Execution Gates" in render_control_center_html(control), "Control Center HTML panel missing")

    for capability_id in GATE_CAPABILITIES:
        capability = get_capability(capability_id)
        check(capability is not None and capability.read_only, f"capability missing or unsafe: {capability_id}")
        resolution = resolve_capability(capability_id)
        check(resolution.preview_only and resolution.execution_path == "fast_command", f"resource mapping unsafe: {capability_id}")
        schema = capability_to_tool_schema(capability_id)
        check(schema and schema.get("execution_status") == "read_only_metadata", f"schema missing: {capability_id}")
        safety_notes = " ".join(str(item) for item in schema.get("safety_notes", [])).lower()
        for phrase in (
            "local/mock policy preview only",
            "no live llm call",
            "no tool execution",
            "no secret/config/session reads",
            "no arbitrary filesystem reads",
            "no arbitrary filesystem writes",
            "no browser/desktop/shell/cloud/mcp execution",
            "output is gate/report/status only",
            "phase 12l is the only existing real write boundary",
        ):
            check(phrase in safety_notes, f"schema boundary missing {phrase}: {capability_id}")

    selected = select_capabilities_for_goal("show execution gate readiness")
    check(selected == ["execution_gates.readiness"], "planner selected unsafe execution gate capability")
    task_plan = create_task_plan("what can Eva execute")
    check(any(step.capability_id == "execution_gates.policy" for step in task_plan.steps), "planner execution gate step missing")
    forbidden_text = " ".join(f"{step.title} {step.description} {step.capability_id}" for step in task_plan.steps).lower()
    for forbidden in ("browser action", "desktop action", "shell step", "package install", "provider-call", "arbitrary file-read", "arbitrary file-write", "mcp action"):
        check(forbidden not in forbidden_text, f"planner decomposed execution gate into forbidden step: {forbidden}")

    review = format_team_review("review Phase 20 controlled execution gates")
    for phrase in (
        "Controlled Execution Gates are local/mock policy preview only",
        "no live LLM/API calls are made",
        "tools are not executed",
        "approval alone does not execute",
        "confirmation alone does not execute unless an existing implemented gate accepts it",
        "secrets/config/session reads remain blocked",
        "arbitrary file reads/writes remain blocked",
        "browser/desktop/shell/cloud/MCP execution remains locked",
        "Phase 12L narrow real-create remains a gated write path",
        "Phase 21 Memory v3 is next",
    ):
        check(phrase.lower() in review.lower(), f"team review missing: {phrase}")

    required_doc_phrases = (
        "Phase 20 Controlled Execution Gates",
        "execution gates are local/mock policy preview only",
        "no live LLM/API/provider calls happen",
        "no provider SDKs are used",
        "no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read",
        "arbitrary file reads/writes are blocked",
        "tools are not executed",
        "approval alone does not execute",
        "confirmation alone does not execute unless an existing implemented gate accepts it",
        "browser/desktop/shell/cloud/MCP execution remains locked",
        "future gates are described but locked",
        "Phase 12L narrow approved new `.md`/`.txt` creation remains a gated write path",
        "Phase 21 Memory v3",
    )
    for doc in DOCS:
        text = (ROOT / "docs" / doc).read_text(encoding="utf-8")
        for phrase in required_doc_phrases:
            check(phrase in text, f"docs missing {phrase}: {doc}")

    check("verify_eva_controlled_execution_gates.py" in verify_eva_all.FULL_VERIFIERS, "full master profile missing Phase 20")
    check("verify_eva_controlled_execution_gates.py" in verify_eva_all.QUICK_VERIFIERS, "quick master profile missing Phase 20")
    listed = "\n".join(verify_eva_all.FULL_VERIFIERS + verify_eva_all.QUICK_VERIFIERS)
    check("verify_eva_controlled_execution_gates.py" in listed, "Phase 20 missing from master list data")

    source = "\n".join(path.read_text(encoding="utf-8").lower() for path in (ROOT / "backend/eva/execution_gates").glob("*.py"))
    for forbidden in ("import requests", "httpx", "urllib.request", "subprocess", "playwright", "pyautogui", "os.system", "open("):
        check(forbidden not in source, f"forbidden runtime surface in execution gates source: {forbidden}")

    print("PASS: Phase 20 Controlled Execution Gates are local/mock, deterministic, preview-only, and fully wired.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
