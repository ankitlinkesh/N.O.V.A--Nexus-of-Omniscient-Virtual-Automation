from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


CAPABILITIES = (
    "desktop_control.status",
    "desktop_control.policy",
    "desktop_control.actions",
    "desktop_control.dry_run",
    "desktop_control.approvals",
    "desktop_control.confirmations",
    "desktop_control.blocked_actions",
    "desktop_control.readiness",
)

COMMANDS = (
    "eva desktop control status",
    "eva desktop control policy",
    "eva desktop control actions",
    "eva desktop control dry run",
    "eva desktop control approvals",
    "eva desktop control confirmations",
    "eva desktop control blocked actions",
    "eva desktop control readiness",
)

ASK_ROUTES = {
    "show desktop control status": "desktop_control_status",
    "can Eva control my desktop": "desktop_control_policy",
    "can Eva click or type": "desktop_control_policy",
    "show desktop control policy": "desktop_control_policy",
    "dry run desktop action": "desktop_control_dry_run",
    "what desktop actions are blocked": "desktop_control_blocked_actions",
    "what approval is required for desktop control": "desktop_control_approvals",
    "show desktop control readiness": "desktop_control_readiness",
}

DOCS = (
    "EVA_CURRENT_STATE.md",
    "EVA_CAPABILITIES.md",
    "EVA_AGENT_FRAMEWORK.md",
    "EVA_THREAT_MODEL.md",
    "EVA_VERIFICATION.md",
)

BOUNDARIES = (
    "desktop control is not enabled",
    "dry-run/control-gate only",
    "no clicking",
    "no typing",
    "no hotkeys",
    "no clipboard access",
    "no app/window control",
    "no shell/package/cloud/mcp execution",
    "approval alone does not execute",
    "confirmation alone does not execute",
    "phase 12l remains a gated write path",
)


def check(value: object, message: str) -> None:
    if not value:
        raise AssertionError(message)


def assert_safe(text: str, label: str) -> None:
    lowered = text.lower()
    for token in ("traceback", "{'", "c:\\users\\", ".env.local", "api_key=", "token=", "password="):
        check(token not in lowered, f"unsafe output in {label}: {token}")


def assert_boundaries(text: str, label: str) -> None:
    assert_safe(text, label)
    lowered = text.lower()
    for phrase in BOUNDARIES:
        check(phrase in lowered, f"missing boundary '{phrase}': {label}")


def main() -> int:
    from backend.eva.agents.team_review import format_team_review
    from backend.eva.capabilities.permissions import get_capability_permission
    from backend.eva.capabilities.registry import get_capability
    from backend.eva.capabilities.resource_mapping import resolve_capability
    from backend.eva.capabilities.tool_schemas import capability_to_tool_schema
    from backend.eva.control_center.collector import collect_control_center_status
    from backend.eva.control_center.formatter import format_control_center_status, render_control_center_html
    from backend.eva.core.fast_commands import maybe_handle_fast_command
    from backend.eva.core.natural_router import route_natural_request
    from backend.eva.desktop_control_gate.action_catalog import ACTION_CLASSES, classify_action, format_action_catalog
    from backend.eva.desktop_control_gate.approval_policy import approval_policy_text
    from backend.eva.desktop_control_gate.confirmation_policy import confirmation_policy_text
    from backend.eva.desktop_control_gate.control_policy import control_policy_text
    from backend.eva.desktop_control_gate.dry_run import build_desktop_control_dry_run
    from backend.eva.desktop_control_gate.eligibility import evaluate_action_eligibility, eligibility_policy_text
    from backend.eva.desktop_control_gate.formatter import (
        format_desktop_control_actions,
        format_desktop_control_approvals,
        format_desktop_control_blocked_actions,
        format_desktop_control_confirmations,
        format_desktop_control_dry_run,
        format_desktop_control_policy,
        format_desktop_control_readiness,
        format_desktop_control_status,
    )
    from backend.eva.desktop_control_gate.risk_scoring import risk_scoring_policy_text, score_action_risk
    from backend.eva.desktop_control_gate.status import get_desktop_control_gate_status
    from backend.eva.planner.capability_selector import select_capabilities_for_goal
    from backend.eva.planner.decomposer import create_task_plan
    from backend.eva.tools.registry import ToolRegistry
    from scripts import verify_eva_all

    for output in (
        control_policy_text(),
        format_action_catalog(),
        risk_scoring_policy_text(),
        eligibility_policy_text(),
        approval_policy_text(),
        confirmation_policy_text(),
        format_desktop_control_status(),
    ):
        assert_safe(output, "core policy")
        check(len(output.splitlines()) >= 2, "core policy is not human-readable")

    status = get_desktop_control_gate_status()
    check(status.available and not status.real_control_enabled, "unsafe desktop-control status")
    check(status.mode == "local/mock dry-run gate only", "wrong desktop-control mode")

    required_classes = {
        "observe_only_reference", "click_candidate", "type_candidate", "hotkey_candidate",
        "clipboard_candidate", "app_launch_candidate", "window_focus_candidate",
        "window_move_or_resize_candidate", "browser_control_candidate",
        "shell_or_terminal_candidate", "package_install_candidate", "file_write_candidate",
        "credential_or_secret_candidate", "destructive_or_irreversible_candidate",
        "unknown_or_hallucinated_action",
    }
    check(required_classes == set(ACTION_CLASSES), "action catalog incomplete")

    cases = {
        "click the submit button": "click_candidate",
        "type hello": "type_candidate",
        "press ctrl alt delete": "hotkey_candidate",
        "read clipboard": "clipboard_candidate",
        "launch calculator": "app_launch_candidate",
        "focus the editor window": "window_focus_candidate",
        "resize the window": "window_move_or_resize_candidate",
        "control the browser": "browser_control_candidate",
        "run a terminal command": "shell_or_terminal_candidate",
        "pip install package": "package_install_candidate",
        "write this file": "file_write_candidate",
        "read my password and cookie": "credential_or_secret_candidate",
        "delete everything permanently": "destructive_or_irreversible_candidate",
        "teleport the moon widget": "unknown_or_hallucinated_action",
    }
    for request, expected in cases.items():
        check(classify_action(request) == expected, f"wrong action class: {request}")
        decision = evaluate_action_eligibility(request)
        check(not decision.execution_allowed, f"execution allowed: {request}")
        check(decision.gate_decision in {
            "preview_only", "blocked_by_policy", "requires_future_desktop_control_gate",
            "requires_explicit_approval", "requires_exact_confirmation", "denied_sensitive_screen",
            "denied_secret_or_credential_risk", "denied_unknown_capability",
            "denied_destructive_action", "denied_unsupported_action",
        }, f"unknown gate state: {request}")

    low = score_action_risk("observe desktop status")
    high = score_action_risk("read password and delete account", sensitive_screen=True)
    check(low.score < high.score and high.level in {"high", "critical"}, "risk scoring unsafe")

    dry_run = build_desktop_control_dry_run("click the Save button", target_summary="Save button")
    for field in (
        "dry_run_id", "requested_action_summary", "action_class", "target_summary",
        "sensitive_screen_status", "required_observation_precondition", "risk_score",
        "risk_level", "permission_class", "gate_decision", "approval_requirement",
        "exact_confirmation_requirement", "rollback_metadata", "audit_metadata",
        "blocked_reason", "final_status", "no_click_statement", "no_type_statement",
        "no_hotkey_statement", "no_clipboard_statement", "no_app_control_statement",
        "no_window_control_statement", "no_tool_execution_statement",
        "no_new_write_path_statement",
    ):
        check(hasattr(dry_run, field), f"dry-run field missing: {field}")
    check(not dry_run.execution_performed, "dry-run executed an action")
    assert_boundaries(format_desktop_control_dry_run("click the Save button"), "dry-run")

    for output in (
        format_desktop_control_status(), format_desktop_control_policy(),
        format_desktop_control_actions(), format_desktop_control_dry_run(),
        format_desktop_control_approvals(), format_desktop_control_confirmations(),
        format_desktop_control_blocked_actions(), format_desktop_control_readiness(),
    ):
        assert_boundaries(output, "formatter")

    for command in COMMANDS:
        result = maybe_handle_fast_command(command, ToolRegistry())
        check(result is not None, f"command missing: {command}")
        assert_boundaries(result[0], command)

    for prompt, intent in ASK_ROUTES.items():
        route = route_natural_request(prompt)
        check(route.intent == intent and not route.real_execution_requested, f"bad ask route: {prompt}")
        result = maybe_handle_fast_command(f"eva ask {prompt}", ToolRegistry())
        check(result is not None, f"ask missing: {prompt}")
        assert_boundaries(result[0], prompt)

    control = collect_control_center_status()
    check(hasattr(control, "desktop_control_gate_summary"), "Control Center model missing desktop-control summary")
    text = format_control_center_status(control)
    html = render_control_center_html(control)
    for phrase in ("Real Desktop Control Gate", "Risk scoring", "Approval policy", "Confirmation policy", "Phase 27 News/Web Intelligence Dashboard"):
        check(phrase.lower() in text.lower(), f"Control Center text missing: {phrase}")
        check(phrase.lower() in html.lower(), f"Control Center HTML missing: {phrase}")

    from backend.eva.ai_os.capability_matrix import capability_matrix_text
    from backend.eva.ai_os.feature_states import feature_states_text
    from backend.eva.ai_os.system_map import system_map_text
    ai_os = "\n".join((system_map_text(), capability_matrix_text(), feature_states_text()))
    check("real desktop control gate" in ai_os.lower(), "AI OS desktop-control gate missing")
    check("dry_run_gate_only" in ai_os and "available_observation_only" in ai_os, "AI OS states wrong")

    for capability_id in CAPABILITIES:
        capability = get_capability(capability_id)
        check(capability is not None and capability.read_only, f"capability unsafe: {capability_id}")
        permission = get_capability_permission(capability_id)
        check(permission.read_only and not permission.writes_local_data, f"permission unsafe: {capability_id}")
        check(resolve_capability(capability_id).execution_path == "fast_command", f"resource missing: {capability_id}")
        schema = capability_to_tool_schema(capability_id)
        check(schema and schema.get("execution_status") == "dry_run_gate_only", f"schema missing: {capability_id}")

    selected = select_capabilities_for_goal("dry run desktop action")
    check("desktop_control.dry_run" in selected and "desktop.control" not in selected, "planner unsafe")
    plan = create_task_plan("dry run desktop action")
    check(any(step.capability_id == "desktop_control.dry_run" for step in plan.steps), "planner step missing")
    planner_text = " ".join(f"{step.title} {step.description} {step.capability_id}" for step in plan.steps).lower()
    for forbidden in ("desktop.control", "browser.control", "click step", "type step", "shell step", "execution step"):
        check(forbidden not in planner_text, f"planner created forbidden step: {forbidden}")

    review = format_team_review("review Phase 26 Real Desktop Control Gate")
    for phrase in (
        "Real Desktop Control Gate is local/mock dry-run only",
        "real desktop control is not enabled", "no clicking/typing/hotkeys happen",
        "no clipboard access happens", "no app/window control happens",
        "approval alone does not execute", "confirmation alone does not execute",
        "desktop observation remains observation-only",
        "Phase 12L narrow real-create remains a gated file write path",
        "Phase 27 News/Web Intelligence Dashboard is next",
    ):
        check(phrase.lower() in review.lower(), f"team review missing: {phrase}")

    required_doc = (
        "Phase 26 Real Desktop Control Gate is complete after this pass",
        "desktop control is dry-run/gate-only", "approval alone does not execute",
        "confirmation alone does not execute", "rollback/audit are metadata only",
        "desktop observation remains observation-only",
        "Phase 27 News/Web Intelligence Dashboard",
    )
    for doc in DOCS:
        content = (ROOT / "docs" / doc).read_text(encoding="utf-8")
        for phrase in required_doc:
            check(phrase in content, f"docs missing '{phrase}': {doc}")

    verifier = "verify_eva_desktop_control_gate.py"
    check(verifier in verify_eva_all.FULL_VERIFIERS, "full profile missing Phase 26")
    check(verifier in verify_eva_all.QUICK_VERIFIERS, "quick profile missing Phase 26")

    source = "\n".join(path.read_text(encoding="utf-8").lower() for path in (ROOT / "backend/eva/desktop_control_gate").glob("*.py"))
    for forbidden in (
        "import pyautogui", "import playwright", "import selenium", "import mss",
        "imagegrab", "pytesseract", "subprocess", "os.system", "requests.", "httpx.",
        "mouse.", "keyboard.", "clipboard.", "open(",
    ):
        check(forbidden not in source, f"forbidden runtime surface: {forbidden}")

    print("PASS: Phase 26 Real Desktop Control Gate is deterministic, dry-run-only, and execution-locked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
