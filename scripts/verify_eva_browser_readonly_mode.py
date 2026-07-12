from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


BROWSER_READ_CAPABILITIES = (
    "browser_read.status",
    "browser_read.policy",
    "browser_read.url_policy",
    "browser_read.observe",
    "browser_read.mock_observe",
    "browser_read.safety_report",
    "browser_read.blocked_urls",
    "browser_read.readiness",
)

BROWSER_READ_COMMANDS = (
    "eva browser read status",
    "eva browser read policy",
    "eva browser read url policy",
    "eva browser read observe",
    "eva browser read mock observe",
    "eva browser read safety report",
    "eva browser read blocked urls",
    "eva browser read readiness",
)

ASK_ROUTES = {
    "show browser read-only status": "browser_read_status",
    "can Eva read a webpage": "browser_read_policy",
    "can Eva click or type in the browser": "browser_read_boundaries",
    "show browser read-only policy": "browser_read_policy",
    "show blocked browser URLs": "browser_read_blocked_urls",
    "observe a webpage read only": "browser_read_observe",
    "can Eva use my logged-in browser": "browser_read_session_boundary",
    "show browser read-only readiness": "browser_read_readiness",
}

DOCS = (
    "EVA_CURRENT_STATE.md",
    "EVA_CAPABILITIES.md",
    "EVA_AGENT_FRAMEWORK.md",
    "EVA_THREAT_MODEL.md",
    "EVA_VERIFICATION.md",
)

BOUNDARIES = (
    "browser mode is read-only",
    "no clicking",
    "no typing",
    "no form submission",
    "no downloads or uploads",
    "no cookies, sessions, or browser profiles",
    "no logged-in browser access",
    "no browser control",
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
    from backend.eva.browser_readonly.backend_policy import backend_policy_text, get_backend_policy
    from backend.eva.browser_readonly.formatter import (
        format_browser_read_blocked_urls,
        format_browser_read_mock_observe,
        format_browser_read_observe,
        format_browser_read_policy,
        format_browser_read_readiness,
        format_browser_read_safety_report,
        format_browser_read_status,
        format_browser_read_url_policy,
    )
    from backend.eva.browser_readonly.observation_policy import (
        evaluate_observation_request,
        observation_policy_text,
    )
    from backend.eva.browser_readonly.observer import observe_mock_page, observe_public_url
    from backend.eva.browser_readonly.safety_filter import redact_browser_output
    from backend.eva.browser_readonly.session_policy import get_session_policy, session_policy_text
    from backend.eva.browser_readonly.status import get_browser_readonly_status
    from backend.eva.browser_readonly.url_policy import blocked_url_classes_text, url_policy_text, validate_url
    from backend.eva.capabilities.permissions import get_capability_permission
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
    from scripts import verify_eva_all

    for output in (
        url_policy_text(),
        session_policy_text(),
        backend_policy_text(),
        observation_policy_text(),
        blocked_url_classes_text(),
    ):
        assert_human_safe(output, "browser read-only policy")

    allowed = validate_url("HTTPS://Example.COM:443/docs?q=public#intro")
    check(allowed.allowed, "public HTTPS URL was blocked")
    check(allowed.normalized_url == "https://example.com/docs?q=public#intro", "safe URL normalization failed")

    blocked_cases = {
        "file:///etc/passwd": "scheme",
        "ftp://example.com/file": "scheme",
        "data:text/plain,hello": "scheme",
        "javascript:alert(1)": "scheme",
        "chrome://settings": "scheme",
        "edge://settings": "scheme",
        "about:blank": "scheme",
        "http://localhost/admin": "local",
        "http://127.0.0.1/": "private",
        "http://0.0.0.0/": "private",
        "http://192.168.1.10/": "private",
        "http://169.254.169.254/latest/meta-data/": "metadata",
        "http://service.internal/": "internal",
        "https://user:pass@example.com/": "credentials",
        "https://example.com/?token=secret-value": "sensitive",
        "https://example.com/path/password/reset": "sensitive",
        "https://example.com/?q=test;rm%20-rf%20x": "command",
    }
    for url, reason_hint in blocked_cases.items():
        decision = validate_url(url)
        check(not decision.allowed, f"unsafe URL allowed: {url}")
        check(reason_hint in decision.reason.lower(), f"unclear block reason for {url}: {decision.reason}")
        check("secret-value" not in decision.requested_url, f"secret value retained for {url}")

    for request in (
        "click the link",
        "type into the browser",
        "submit the form",
        "download the file",
        "upload this document",
        "log in with my browser session",
        "use my browser profile cookies",
        "control the browser",
    ):
        decision = evaluate_observation_request(request)
        check(not decision.allowed, f"browser action request allowed: {request}")

    session = get_session_policy()
    check(session.ephemeral and session.sessionless and session.credentialless, "session isolation is incomplete")
    check(not session.cookies_allowed and not session.profile_access_allowed, "cookie/profile access enabled")
    backend = get_backend_policy()
    check(backend.mode == "unavailable" and not backend.available, "unexpected real browser backend enabled")

    mock = observe_mock_page()
    required_fields = (
        "observation_id",
        "requested_url",
        "normalized_url",
        "url_safety_decision",
        "backend_mode",
        "session_policy",
        "title_preview",
        "visible_text_summary",
        "link_summary",
        "blocked_content_notes",
        "redaction_status",
        "threat_scan_summary",
        "execution_gate_decision",
        "final_status",
        "no_click_statement",
        "no_type_statement",
        "no_form_submit_statement",
        "no_download_statement",
        "no_cookie_session_profile_statement",
        "no_tool_execution_statement",
        "no_new_write_path_statement",
    )
    for field_name in required_fields:
        check(hasattr(mock, field_name), f"observation model field missing: {field_name}")
    check(mock.backend_mode == "mock_fixture", "mock observation did not use fixture backend")
    check(mock.final_status == "ready_mock_observation", "mock observation not ready")
    check("[redacted secret-like value]" in mock.visible_text_summary, "mock secret was not redacted")
    check("[redacted private path]" in mock.visible_text_summary, "mock private path was not redacted")
    check(mock.threat_scan_summary, "Phase 17 threat scan summary missing")
    check("readonly" in mock.execution_gate_decision.lower(), "Phase 20 execution-gate decision missing")
    assert_human_safe(mock.format(), "mock observation")

    unavailable = observe_public_url("https://example.com/")
    check(unavailable.backend_mode == "unavailable", "unsafe implicit backend was used")
    check(unavailable.final_status == "backend_unavailable", "backend-unavailable status missing")
    check(not unavailable.title_preview and not unavailable.link_summary, "unavailable backend fabricated page content")
    assert_human_safe(unavailable.format(), "unavailable observation")

    blocked = observe_public_url("http://localhost/private")
    check(blocked.final_status == "blocked_url", "blocked URL did not fail closed")
    check(blocked.backend_mode == "unavailable", "blocked URL reached a backend")
    assert_human_safe(blocked.format(), "blocked observation")

    redacted = redact_browser_output(
        "API_TOKEN=top-secret C:\\Users\\person\\private\\note.txt cookie=session-value"
    )
    check("top-secret" not in redacted and "session-value" not in redacted, "secret-like text not redacted")
    check("C:\\Users\\" not in redacted, "private path not redacted")

    status = get_browser_readonly_status()
    check(status.status == "available", "browser read-only status unavailable")
    check(status.mode == "public URL read-only observation gate", "unsafe browser mode")
    check(not status.browser_control_enabled and not status.tool_execution_enabled, "browser/tool control enabled")
    check(status.next_phase == "Phase 25 Real Desktop Observation Mode", "wrong next phase")

    formatter_outputs = (
        format_browser_read_status(),
        format_browser_read_policy(),
        format_browser_read_url_policy(),
        format_browser_read_observe(),
        format_browser_read_mock_observe(),
        format_browser_read_safety_report(),
        format_browser_read_blocked_urls(),
        format_browser_read_readiness(),
    )
    for index, output in enumerate(formatter_outputs):
        assert_human_safe(output, f"browser read formatter {index}")

    for command in BROWSER_READ_COMMANDS:
        result = maybe_handle_fast_command(command, ToolRegistry())
        check(result is not None, f"command missing: {command}")
        assert_human_safe(result[0], command)

    direct_observe = maybe_handle_fast_command("eva browser read observe https://example.com/", ToolRegistry())
    check(direct_observe is not None and "backend unavailable" in direct_observe[0].lower(), "URL observe command failed")
    assert_human_safe(direct_observe[0], "URL observe command")

    for prompt, intent in ASK_ROUTES.items():
        route = route_natural_request(prompt)
        check(route.intent == intent, f"bad ask route: {prompt}; got {route.intent}")
        check(route.authority_category == "read" and not route.real_execution_requested, f"unsafe ask route: {prompt}")
        result = maybe_handle_fast_command(f"eva ask {prompt}", ToolRegistry())
        check(result is not None and "Eva ask" in result[0], f"ask command missing: {prompt}")
        assert_human_safe(result[0], f"ask {prompt}")

    control = collect_control_center_status()
    summary = control.browser_readonly_summary
    check(summary.get("status") == "available", "Control Center browser read-only summary missing")
    text_dashboard = format_control_center_status(control)
    html_dashboard = render_control_center_html(control)
    for phrase in (
        "Real Browser Read-Only Mode",
        "URL policy",
        "backend availability",
        "session isolation policy",
        "read-only boundaries",
        "blocked URL classes",
        "last/mock observation summary",
        "execution gate integration",
        "readiness",
        "Phase 25 Real Desktop Observation Mode",
    ):
        check(phrase.lower() in text_dashboard.lower(), f"Control Center text missing: {phrase}")
        check(phrase.lower() in html_dashboard.lower(), f"Control Center HTML missing: {phrase}")

    from backend.eva.ai_os.capability_matrix import capability_matrix_text
    from backend.eva.ai_os.feature_states import feature_states_text, locked_features_text
    from backend.eva.ai_os.system_map import system_map_text

    ai_os_text = "\n".join((system_map_text(), capability_matrix_text(), feature_states_text(), locked_features_text()))
    check("real browser read-only mode" in ai_os_text.lower(), "AI OS browser read-only feature missing")
    check("available_readonly_observation" in ai_os_text, "AI OS read-only state missing")
    check("browser control" in ai_os_text.lower() and "locked" in ai_os_text.lower(), "AI OS browser control not locked")

    for capability_id in BROWSER_READ_CAPABILITIES:
        capability = get_capability(capability_id)
        check(capability is not None and capability.read_only, f"capability missing or unsafe: {capability_id}")
        permission = get_capability_permission(capability_id)
        check(permission.read_only and not permission.writes_local_data, f"permission unsafe: {capability_id}")
        resolution = resolve_capability(capability_id)
        check(resolution.execution_path == "fast_command", f"resource mapping missing: {capability_id}")
        schema = capability_to_tool_schema(capability_id)
        check(schema and schema.get("execution_status") == "read_only_observation", f"schema missing: {capability_id}")
        notes = " ".join(str(item) for item in schema.get("safety_notes", [])).lower()
        for phrase in (
            "read-only browser observation only",
            "public url only",
            "no click/type/forms/download/upload",
            "no cookies/sessions/browser profile access",
            "no logged-in browser access",
            "no browser control",
            "no arbitrary filesystem reads/writes",
            "no tool execution",
            "output is observation/report/status only",
            "phase 12l is the only existing real write boundary",
        ):
            check(phrase in notes, f"schema boundary missing '{phrase}': {capability_id}")

    selected = select_capabilities_for_goal("observe a webpage read only")
    check("browser_read.observe" in selected, "planner did not select browser read-only observation")
    check("browser.control" not in selected, "planner selected browser control")
    plan = create_task_plan("observe a webpage read only")
    check(any(step.capability_id == "browser_read.observe" for step in plan.steps), "planner browser-read step missing")
    planner_text = " ".join(f"{step.title} {step.description} {step.capability_id}" for step in plan.steps).lower()
    for forbidden in (
        "browser.control",
        "click step",
        "type step",
        "form submit",
        "download step",
        "upload step",
        "login step",
        "desktop action",
        "shell step",
        "cloud action",
        "mcp action",
        "package install",
        "arbitrary file-read",
        "arbitrary file-write",
        "execution step",
    ):
        check(forbidden not in planner_text, f"planner created forbidden step: {forbidden}")

    review = format_team_review("review Phase 24 Real Browser Read-Only Mode")
    for phrase in (
        "Real Browser Read-Only Mode is public-URL read-only observation only",
        "no clicking/typing/forms/downloads/uploads happen",
        "no cookies/sessions/browser profiles are accessed",
        "logged-in browser access remains blocked",
        "browser control remains locked",
        "tools are not executed",
        "secrets/config/session reads remain blocked",
        "arbitrary file reads/writes remain blocked",
        "desktop execution remains locked",
        "Phase 12L narrow real-create remains a gated file write path",
        "Phase 25 Real Desktop Observation Mode is next",
    ):
        check(phrase.lower() in review.lower(), f"team review missing: {phrase}")

    required_doc_phrases = (
        "Phase 24 Real Browser Read-Only Mode is complete",
        "public-URL read-only observation only",
        "no clicking, typing, forms, downloads, uploads, login, or browser control",
        "no logged-in browser profile/session/cookie access",
        "no provider SDKs or package installs",
        "no real LLM/API/provider calls happen",
        "no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read",
        "arbitrary file reads/writes are blocked",
        "browser read-only observations cannot execute tools",
        "browser control remains locked",
        "desktop/shell/cloud/MCP execution remains locked",
        "Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path",
        "Phase 25 Real Desktop Observation Mode",
    )
    for doc in DOCS:
        text = (ROOT / "docs" / doc).read_text(encoding="utf-8")
        for phrase in required_doc_phrases:
            check(phrase in text, f"docs missing '{phrase}': {doc}")

    verifier_name = "verify_eva_browser_readonly_mode.py"
    check(verifier_name in verify_eva_all.FULL_VERIFIERS, "full master profile missing Phase 24")
    check(verifier_name in verify_eva_all.QUICK_VERIFIERS, "quick master profile missing Phase 24")

    source = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in (ROOT / "backend/eva/browser_readonly").glob("*.py")
    )
    for forbidden in (
        "import requests",
        "import httpx",
        "urllib.request",
        "subprocess",
        "import playwright",
        "from playwright",
        "import selenium",
        "from selenium",
        "import pyautogui",
        "os.system",
        "pip install",
        "npm install",
        ".env.local",
        "open(",
    ):
        check(forbidden not in source, f"forbidden runtime surface in browser read-only source: {forbidden}")

    print("PASS: Phase 24 Real Browser Read-Only Mode is public-URL-only, sessionless, redacted, and action-locked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
