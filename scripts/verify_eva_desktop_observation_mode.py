from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


CAPABILITIES = (
    "desktop_observe.status",
    "desktop_observe.policy",
    "desktop_observe.backend",
    "desktop_observe.mock",
    "desktop_observe.safety_report",
    "desktop_observe.sensitive_screens",
    "desktop_observe.redaction_policy",
    "desktop_observe.readiness",
)

COMMANDS = (
    "eva desktop observe status",
    "eva desktop observe policy",
    "eva desktop observe backend",
    "eva desktop observe mock",
    "eva desktop observe safety report",
    "eva desktop observe sensitive screens",
    "eva desktop observe redaction policy",
    "eva desktop observe readiness",
)

ASK_ROUTES = {
    "show desktop observation status": "desktop_observe_status",
    "can Eva see my screen": "desktop_observe_policy",
    "can Eva click or type on my desktop": "desktop_control_policy",
    "show desktop observation policy": "desktop_observe_policy",
    "show sensitive screen policy": "desktop_observe_sensitive_screens",
    "observe desktop read only": "desktop_observe_mock",
    "can Eva control apps or windows": "desktop_observe_boundaries",
    "show desktop observation readiness": "desktop_observe_readiness",
}

DOCS = (
    "EVA_CURRENT_STATE.md",
    "EVA_CAPABILITIES.md",
    "EVA_AGENT_FRAMEWORK.md",
    "EVA_THREAT_MODEL.md",
    "EVA_VERIFICATION.md",
)

BOUNDARIES = (
    "desktop mode is observation-only",
    "no clicking",
    "no typing",
    "no hotkeys",
    "no app or window control",
    "no continuous monitoring",
    "no saved screenshots",
    "no cookies, sessions, or browser profiles",
    "no tool execution",
    "phase 12l remains a gated write path",
)


def check(value: object, message: str) -> None:
    if not value:
        raise AssertionError(message)


def assert_human_safe(output: str, label: str) -> None:
    lowered = output.lower()
    check(output.strip(), f"empty output: {label}")
    check("traceback" not in lowered and "{'" not in output and "dataclass" not in lowered, f"raw output leaked: {label}")
    check("c:\\users\\" not in lowered and "/home/" not in lowered, f"private path leaked: {label}")
    check("token=" not in lowered and "cookie=" not in lowered and "password=" not in lowered, f"secret-like output leaked: {label}")
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
    from backend.eva.desktop_observation.backend_policy import backend_policy_text, get_backend_policy
    from backend.eva.desktop_observation.capture_gate import capture_gate_policy_text, evaluate_capture_gate
    from backend.eva.desktop_observation.formatter import (
        format_desktop_observe_backend,
        format_desktop_observe_mock,
        format_desktop_observe_policy,
        format_desktop_observe_readiness,
        format_desktop_observe_redaction_policy,
        format_desktop_observe_safety_report,
        format_desktop_observe_sensitive_screens,
        format_desktop_observe_status,
    )
    from backend.eva.desktop_observation.observation_policy import (
        evaluate_observation_request,
        observation_policy_text,
    )
    from backend.eva.desktop_observation.observer import observe_desktop, observe_mock_desktop
    from backend.eva.desktop_observation.redaction import redact_desktop_output, redaction_policy_text
    from backend.eva.desktop_observation.sensitive_screen import (
        SENSITIVE_SCREEN_CATEGORIES,
        classify_sensitive_screen,
        sensitive_screen_policy_text,
    )
    from backend.eva.desktop_observation.status import get_desktop_observation_status
    from backend.eva.planner.capability_selector import select_capabilities_for_goal
    from backend.eva.planner.decomposer import create_task_plan
    from backend.eva.tools.registry import ToolRegistry
    from scripts import verify_eva_all

    for output in (
        observation_policy_text(),
        backend_policy_text(),
        capture_gate_policy_text(),
        sensitive_screen_policy_text(),
        redaction_policy_text(),
    ):
        assert_human_safe(output, "desktop observation policy")

    backend = get_backend_policy()
    check(backend.mode == "unavailable" and not backend.available, "unexpected real desktop backend enabled")
    check(not backend.real_screen_capture_in_tests, "backend allows real capture in tests")

    allowed_gate = evaluate_capture_gate("explicit one-shot desktop observation")
    check(allowed_gate.allowed and allowed_gate.decision == "allowed_observation_only", "one-shot observation gate not allowed")
    for request in (
        "click the desktop",
        "type into the app",
        "press a hotkey",
        "move the mouse",
        "read the clipboard",
        "control an app window",
        "launch an app",
        "continuously monitor the screen",
        "start a background watcher",
        "save a screenshot to disk",
        "use browser profile cookies",
        "access the password manager",
        "control the desktop",
    ):
        decision = evaluate_observation_request(request)
        check(not decision.allowed, f"unsafe desktop request allowed: {request}")
        gate = evaluate_capture_gate(request)
        check(not gate.allowed, f"unsafe capture gate allowed: {request}")

    category_samples = {
        "password_or_login_screen": "Sign in with your password",
        "payment_or_banking_screen": "Bank transfer payment account balance",
        "private_chat_or_email": "Private chat inbox email conversation",
        "browser_session_or_cookie_context": "Browser cookies and session storage",
        "token_or_secret_context": "Bearer secret token value",
        "private_file_path_context": r"C:\Users\person\private\notes.txt",
        "system_settings_or_security_screen": "Windows security settings firewall",
        "terminal_or_command_prompt": "PowerShell terminal command prompt",
        "code_with_secret_like_content": "def handler(): API_KEY = example",
        "unknown_sensitive_screen": "Unrecognized personal workspace",
    }
    check(set(category_samples).issubset(set(SENSITIVE_SCREEN_CATEGORIES)), "sensitive-screen categories incomplete")
    for expected, text in category_samples.items():
        classification = classify_sensitive_screen(text)
        check(classification.category == expected, f"sensitive screen misclassified: {expected} -> {classification.category}")

    mock = observe_mock_desktop()
    required_fields = (
        "observation_id",
        "requested_observation_type",
        "backend_mode",
        "capture_gate_decision",
        "sensitive_screen_classification",
        "redaction_status",
        "visible_summary_preview",
        "app_window_metadata_preview",
        "blocked_content_notes",
        "threat_scan_summary",
        "execution_gate_decision",
        "final_status",
        "no_click_statement",
        "no_type_statement",
        "no_hotkey_statement",
        "no_app_control_statement",
        "no_continuous_monitoring_statement",
        "no_screenshot_save_statement",
        "no_cookie_session_profile_statement",
        "no_tool_execution_statement",
        "no_new_write_path_statement",
    )
    for field_name in required_fields:
        check(hasattr(mock, field_name), f"observation model field missing: {field_name}")
    check(mock.backend_mode == "mock_fixture", "mock observation did not use fixture backend")
    check(mock.final_status == "ready_mock_observation", "mock observation not ready")
    check("[redacted secret-like value]" in mock.visible_summary_preview, "mock secret was not redacted")
    check("[redacted private path]" in mock.visible_summary_preview, "mock private path was not redacted")
    check(mock.threat_scan_summary, "Phase 17 threat scan summary missing")
    check("observation" in mock.execution_gate_decision.lower(), "Phase 20 execution-gate decision missing")
    assert_human_safe(mock.format(), "mock desktop observation")

    unavailable = observe_desktop()
    check(unavailable.backend_mode == "unavailable", "unsafe implicit desktop backend was used")
    check(unavailable.final_status == "backend_unavailable", "backend-unavailable status missing")
    check(not unavailable.visible_summary_preview, "unavailable backend fabricated screen content")
    assert_human_safe(unavailable.format(), "unavailable desktop observation")

    redacted = redact_desktop_output(
        "API_TOKEN=top-secret C:\\Users\\person\\private\\note.txt cookie=session-value"
    )
    check("top-secret" not in redacted and "session-value" not in redacted, "secret-like text not redacted")
    check("C:\\Users\\" not in redacted, "private path not redacted")

    status = get_desktop_observation_status()
    check(status.status == "available", "desktop observation status unavailable")
    check(status.mode == "explicit one-shot observation-only gate", "unsafe desktop observation mode")
    check(not status.desktop_control_enabled and not status.tool_execution_enabled, "desktop/tool control enabled")
    check(not status.continuous_monitoring_enabled and not status.screenshot_saving_enabled, "continuous/saved capture enabled")
    check(status.next_phase == "Phase 26 Real Desktop Control Gate", "wrong next phase")

    formatter_outputs = (
        format_desktop_observe_status(),
        format_desktop_observe_policy(),
        format_desktop_observe_backend(),
        format_desktop_observe_mock(),
        format_desktop_observe_safety_report(),
        format_desktop_observe_sensitive_screens(),
        format_desktop_observe_redaction_policy(),
        format_desktop_observe_readiness(),
    )
    for index, output in enumerate(formatter_outputs):
        assert_human_safe(output, f"desktop observation formatter {index}")

    for command in COMMANDS:
        result = maybe_handle_fast_command(command, ToolRegistry())
        check(result is not None, f"command missing: {command}")
        assert_human_safe(result[0], command)

    for prompt, intent in ASK_ROUTES.items():
        route = route_natural_request(prompt)
        check(route.intent == intent, f"bad ask route: {prompt}; got {route.intent}")
        check(route.authority_category == "read" and not route.real_execution_requested, f"unsafe ask route: {prompt}")
        result = maybe_handle_fast_command(f"eva ask {prompt}", ToolRegistry())
        check(result is not None and "Eva ask" in result[0], f"ask command missing: {prompt}")
        if intent == "desktop_control_policy":
            lowered = result[0].lower()
            check("desktop control is not enabled" in lowered and "no tool execution" in lowered, "Phase 26 route weakened safety")
            check("traceback" not in lowered and "c:\\users\\" not in lowered, "Phase 26 route leaked unsafe output")
        else:
            assert_human_safe(result[0], f"ask {prompt}")

    control = collect_control_center_status()
    summary = control.desktop_observation_mode_summary
    check(summary.get("status") == "available", "Control Center desktop observation summary missing")
    text_dashboard = format_control_center_status(control)
    html_dashboard = render_control_center_html(control)
    for phrase in (
        "Real Desktop Observation Mode",
        "observation policy",
        "backend availability",
        "capture gate policy",
        "sensitive-screen policy",
        "redaction policy",
        "observation-only boundaries",
        "last/mock observation summary",
        "execution gate integration",
        "readiness",
        "Phase 26 Real Desktop Control Gate",
    ):
        check(phrase.lower() in text_dashboard.lower(), f"Control Center text missing: {phrase}")
        check(phrase.lower() in html_dashboard.lower(), f"Control Center HTML missing: {phrase}")

    from backend.eva.ai_os.capability_matrix import capability_matrix_text
    from backend.eva.ai_os.feature_states import feature_states_text, locked_features_text
    from backend.eva.ai_os.system_map import system_map_text

    ai_os_text = "\n".join((system_map_text(), capability_matrix_text(), feature_states_text(), locked_features_text()))
    check("real desktop observation mode" in ai_os_text.lower(), "AI OS desktop observation feature missing")
    check("available_observation_only" in ai_os_text, "AI OS observation-only state missing")
    check("desktop control" in ai_os_text.lower() and "locked" in ai_os_text.lower(), "AI OS desktop control not locked")

    for capability_id in CAPABILITIES:
        capability = get_capability(capability_id)
        check(capability is not None and capability.read_only, f"capability missing or unsafe: {capability_id}")
        permission = get_capability_permission(capability_id)
        check(permission.read_only and not permission.writes_local_data, f"permission unsafe: {capability_id}")
        resolution = resolve_capability(capability_id)
        check(resolution.execution_path == "fast_command", f"resource mapping missing: {capability_id}")
        schema = capability_to_tool_schema(capability_id)
        check(schema and schema.get("execution_status") == "observation_only", f"schema missing: {capability_id}")
        notes = " ".join(str(item) for item in schema.get("safety_notes", [])).lower()
        for phrase in (
            "observation-only desktop preview",
            "no click/type/hotkey",
            "no app/window control",
            "no continuous monitoring",
            "no screenshot saving",
            "no cookies/sessions/browser profile access",
            "no arbitrary filesystem reads/writes",
            "no tool execution",
            "output is observation/report/status only",
            "phase 12l is the only existing real write boundary",
        ):
            check(phrase in notes, f"schema boundary missing '{phrase}': {capability_id}")

    selected = select_capabilities_for_goal("observe desktop read only")
    check("desktop_observe.mock" in selected, "planner did not select desktop observation")
    check("desktop.control" not in selected, "planner selected desktop control")
    plan = create_task_plan("observe desktop read only")
    check(any(step.capability_id == "desktop_observe.mock" for step in plan.steps), "planner desktop-observation step missing")
    planner_text = " ".join(f"{step.title} {step.description} {step.capability_id}" for step in plan.steps).lower()
    for forbidden in (
        "desktop.control",
        "browser.control",
        "click step",
        "type step",
        "hotkey step",
        "app control step",
        "shell step",
        "cloud action",
        "mcp action",
        "package install",
        "arbitrary file-read",
        "arbitrary file-write",
        "execution step",
    ):
        check(forbidden not in planner_text, f"planner created forbidden step: {forbidden}")

    review = format_team_review("review Phase 25 Real Desktop Observation Mode")
    for phrase in (
        "Real Desktop Observation Mode is observation-only",
        "no clicking/typing/hotkeys happen",
        "no app/window control happens",
        "no continuous monitoring happens",
        "no screenshot files are saved",
        "sensitive screens are classified/redacted/blocked",
        "tools are not executed",
        "secrets/config/session reads remain blocked",
        "arbitrary file reads/writes remain blocked",
        "browser control remains locked",
        "desktop control remains locked",
        "Phase 12L narrow real-create remains a gated file write path",
        "Phase 26 Real Desktop Control Gate is next",
    ):
        check(phrase.lower() in review.lower(), f"team review missing: {phrase}")

    required_doc_phrases = (
        "Phase 25 Real Desktop Observation Mode is complete after this pass",
        "desktop mode is observation-only",
        "no clicking, typing, hotkeys, app/window control, continuous monitoring, or screenshot saving",
        "no cookie/session/browser profile/password-manager access",
        "no provider SDKs or package installs",
        "no real LLM/API/provider calls happen",
        "no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read",
        "arbitrary file reads/writes are blocked",
        "desktop observations cannot execute tools",
        "desktop control remains locked",
        "browser control remains locked",
        "shell/cloud/MCP execution remains locked",
        "Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path",
        "Phase 26 Real Desktop Control Gate",
    )
    for doc in DOCS:
        text = (ROOT / "docs" / doc).read_text(encoding="utf-8")
        for phrase in required_doc_phrases:
            check(phrase in text, f"docs missing '{phrase}': {doc}")

    verifier_name = "verify_eva_desktop_observation_mode.py"
    check(verifier_name in verify_eva_all.FULL_VERIFIERS, "full master profile missing Phase 25")
    check(verifier_name in verify_eva_all.QUICK_VERIFIERS, "quick master profile missing Phase 25")

    source = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in (ROOT / "backend/eva/desktop_observation").glob("*.py")
    )
    for forbidden in (
        "import pyautogui",
        "from pyautogui",
        "import mss",
        "from mss",
        "imagegrab",
        "pytesseract",
        "import playwright",
        "from playwright",
        "import selenium",
        "from selenium",
        "subprocess",
        "os.system",
        "pip install",
        "npm install",
        ".env.local",
        "open(",
        "screenshot(",
        "screen.grab",
    ):
        check(forbidden not in source, f"forbidden runtime surface in desktop observation source: {forbidden}")

    print("PASS: Phase 25 Real Desktop Observation Mode is one-shot, redacted, sensitive-screen-aware, and control-locked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
