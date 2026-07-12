from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


AI_OS_CAPABILITIES = (
    "ai_os.status",
    "ai_os.dashboard",
    "ai_os.system_map",
    "ai_os.capability_matrix",
    "ai_os.feature_states",
    "ai_os.safety_boundaries",
    "ai_os.locked_features",
    "ai_os.next_safe_step",
    "ai_os.readiness",
)

AI_OS_COMMANDS = (
    "eva os status",
    "eva os dashboard",
    "eva os system map",
    "eva os capability matrix",
    "eva os feature states",
    "eva os safety boundaries",
    "eva os locked features",
    "eva os next safe step",
    "eva os readiness",
)

ASK_ROUTES = {
    "what can Eva do now": "ai_os_dashboard",
    "show Eva OS dashboard": "ai_os_dashboard",
    "show AI OS status": "ai_os_status",
    "show system map": "ai_os_system_map",
    "show capability matrix": "ai_os_capability_matrix",
    "what features are locked": "locked_features",
    "what is the next safe step": "next_safe_step",
    "can Eva really execute anything": "ai_os_safety_boundaries",
    "show Eva readiness": "ai_os_readiness",
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
    check("token=" not in lowered and "cookie=" not in lowered and "password=" not in lowered, f"secret-like output leaked in {label}")
    for phrase in (
        "no live llm call was made",
        "ai os dashboard is local/status only",
        "preview-only features do not execute",
        "tools are not executed",
        "browser/desktop/shell/cloud/mcp execution remains locked",
        "secrets/config/session data are blocked",
        "phase 12l remains a gated write path",
    ):
        check(phrase in lowered, f"missing boundary '{phrase}' in {label}")


def main() -> int:
    from backend.eva.agents.team_review import format_team_review
    from backend.eva.ai_os.capability_matrix import build_capability_matrix, capability_matrix_text
    from backend.eva.ai_os.feature_states import FEATURE_STATE_CLASSES, feature_states_text, locked_features_text
    from backend.eva.ai_os.formatter import (
        format_ai_os_capability_matrix,
        format_ai_os_dashboard,
        format_ai_os_feature_states,
        format_ai_os_locked_features,
        format_ai_os_next_safe_step,
        format_ai_os_readiness,
        format_ai_os_safety_boundaries,
        format_ai_os_status,
        format_ai_os_system_map,
    )
    from backend.eva.ai_os.phase_health import build_phase_health, phase_health_text
    from backend.eva.ai_os.readiness import build_ai_os_dashboard
    from backend.eva.ai_os.safety_boundaries import safety_boundaries_text
    from backend.eva.ai_os.status import get_ai_os_status
    from backend.eva.ai_os.system_map import build_system_map, system_map_text
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

    status = get_ai_os_status()
    check(status.status == "available", "AI OS status unavailable")
    check(status.mode == "local/status only", "unsafe AI OS mode")
    check(not status.live_llm_calls_enabled and not status.tool_execution_enabled, "AI OS execution enabled")
    check(not status.web_server_enabled and not status.background_daemon_enabled, "AI OS server or daemon enabled")
    assert_human_safe(format_ai_os_status(), "AI OS status")

    expected_states = {
        "available_status_only",
        "available_preview_only",
        "available_existing_narrow_gate",
        "locked_future_gate",
        "blocked_by_policy",
        "not_implemented",
        "needs_user_confirmation",
        "needs_future_safety_phase",
    }
    check(expected_states.issubset(set(FEATURE_STATE_CLASSES)), "feature state classes incomplete")

    system_map = build_system_map()
    required_systems = (
        "FileAgent / Phase 12 safety gates",
        "BrowserAgent safety foundation",
        "DesktopAgent safety foundation",
        "LLM router contracts",
        "LLM fallback/degraded mode",
        "Structured output validation",
        "Red-team/failure tests",
        "Red-team evidence lock",
        "Context assembly",
        "Threat defense",
        "Agent loop v1",
        "Workflow planner",
        "Controlled execution gates",
        "Memory v3",
        "Voice Assistant Foundation",
        "Control Center",
    )
    names = {item.feature_name for item in system_map}
    check(set(required_systems).issubset(names), "AI OS system map incomplete")
    for output in (system_map_text(), phase_health_text(), capability_matrix_text(), feature_states_text(), locked_features_text(), safety_boundaries_text()):
        assert_human_safe(output, "AI OS policy/report")

    health = build_phase_health()
    check(any(item.phase == "Phase 23" for item in health), "Phase 23 health missing")
    check(all(item.source == "known local status metadata" for item in health), "phase health ran or inferred live checks")

    matrix = build_capability_matrix()
    check(matrix, "capability matrix empty")
    for entry in matrix:
        for field_name in (
            "feature_name",
            "phase",
            "current_state",
            "allowed_mode",
            "execution_allowed",
            "write_allowed",
            "approval_behavior",
            "confirmation_behavior",
            "safety_notes",
            "next_safe_action",
        ):
            check(hasattr(entry, field_name), f"capability matrix field missing: {field_name}")
    check(any(entry.current_state == "available_existing_narrow_gate" and entry.write_allowed for entry in matrix), "Phase 12L narrow gate missing")
    check(sum(1 for entry in matrix if entry.write_allowed) == 1, "more than one real write path shown")

    dashboard = build_ai_os_dashboard()
    for field_name in (
        "dashboard_id",
        "current_phase",
        "overall_readiness",
        "master_verification_summary",
        "phase_health_summary",
        "system_map_summary",
        "capability_matrix_summary",
        "preview_only_features",
        "existing_narrow_real_gate_summary",
        "locked_future_gates",
        "blocked_action_classes",
        "safety_boundary_summary",
        "recent_limitation_summary",
        "next_recommended_safe_step",
        "no_live_llm_call_statement",
        "no_tool_execution_statement",
        "no_new_write_path_statement",
    ):
        check(hasattr(dashboard, field_name), f"dashboard model field missing: {field_name}")
    check("Phase 12L" in dashboard.existing_narrow_real_gate_summary, "Phase 12L not identified")
    check("Phase 27 News/Web Intelligence Dashboard" in dashboard.next_recommended_safe_step, "wrong next safe phase after Phase 26")
    dashboard_output = format_ai_os_dashboard()
    assert_human_safe(dashboard_output, "AI OS dashboard")
    for phrase in (
        "browser",
        "desktop",
        "shell",
        "cloud",
        "mcp",
        "voice assistant foundation",
        "memory v3",
        "controlled execution gates",
    ):
        check(phrase in dashboard_output.lower(), f"dashboard missing system boundary: {phrase}")

    formatter_outputs = (
        format_ai_os_status(),
        format_ai_os_dashboard(),
        format_ai_os_system_map(),
        format_ai_os_capability_matrix(),
        format_ai_os_feature_states(),
        format_ai_os_safety_boundaries(),
        format_ai_os_locked_features(),
        format_ai_os_next_safe_step(),
        format_ai_os_readiness(),
    )
    for index, output in enumerate(formatter_outputs):
        assert_human_safe(output, f"AI OS formatter {index}")

    for command in AI_OS_COMMANDS:
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
    check(control.ai_os_summary.get("status") == "available", "Control Center AI OS summary missing")
    text_dashboard = format_control_center_status(control)
    html_dashboard = render_control_center_html(control)
    for panel in (
        "AI OS overview",
        "Phase health",
        "System map",
        "Capability matrix",
        "Feature states",
        "Locked future gates",
        "Next safe step",
    ):
        check(panel.lower() in text_dashboard.lower(), f"Control Center text panel missing: {panel}")
        check(panel.lower() in html_dashboard.lower(), f"Control Center HTML panel missing: {panel}")
    check("Memory v3" in text_dashboard and "Voice Assistant Foundation" in text_dashboard, "existing Control Center panels removed")

    for capability_id in AI_OS_CAPABILITIES:
        capability = get_capability(capability_id)
        check(capability is not None and capability.read_only, f"capability missing or unsafe: {capability_id}")
        resolution = resolve_capability(capability_id)
        check(resolution.preview_only and resolution.execution_path == "fast_command", f"resource mapping unsafe: {capability_id}")
        schema = capability_to_tool_schema(capability_id)
        check(schema and schema.get("execution_status") == "read_only_metadata", f"schema missing: {capability_id}")
        safety_notes = " ".join(str(item) for item in schema.get("safety_notes", [])).lower()
        for phrase in (
            "local/status only",
            "no live llm call",
            "no tool execution",
            "no secret/config/session reads",
            "no arbitrary filesystem reads",
            "no arbitrary filesystem writes",
            "no browser/desktop/shell/cloud/mcp execution",
            "output is dashboard/report/status only",
            "phase 12l is the only existing real write boundary",
        ):
            check(phrase in safety_notes, f"schema boundary missing '{phrase}': {capability_id}")

    selected = select_capabilities_for_goal("show Eva OS dashboard")
    check(selected == ["ai_os.dashboard"], "planner selected unsafe AI OS capability")
    plan = create_task_plan("show capability matrix")
    check(any(step.capability_id == "ai_os.capability_matrix" for step in plan.steps), "planner AI OS matrix step missing")
    planner_text = " ".join(f"{step.title} {step.description} {step.capability_id}" for step in plan.steps).lower()
    for forbidden in ("browser action", "desktop action", "shell step", "cloud action", "mcp action", "package install", "provider-call", "arbitrary file-read", "arbitrary file-write", "execution step"):
        check(forbidden not in planner_text, f"planner decomposed AI OS into forbidden step: {forbidden}")

    review = format_team_review("review Phase 23 AI OS boundaries")
    for phrase in (
        "AI OS / Control Center Upgrade is local/status only",
        "no live LLM/API calls are made",
        "dashboard output does not execute tools",
        "preview-only features remain preview-only",
        "locked future gates remain locked",
        "secrets/config/session reads remain blocked",
        "arbitrary file reads/writes remain blocked",
        "browser/desktop execution remains locked",
        "Phase 12L narrow real-create remains a gated file write path",
        "Phase 24 Real Browser Read-Only Mode is next",
    ):
        check(phrase.lower() in review.lower(), f"team review missing: {phrase}")

    required_doc_phrases = (
        "Phase 23 AI OS / Control Center Upgrade",
        "AI OS dashboard is local/status/report only",
        "no live LLM/API/provider calls happen",
        "no provider SDKs are used",
        "no web server, browser launch, desktop UI launch, or daemon is created",
        "no `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config secrets are read",
        "arbitrary file reads/writes are blocked",
        "AI OS dashboard cannot execute tools",
        "preview-only features remain preview-only",
        "locked future gates remain locked",
        "browser/desktop/shell/cloud/MCP execution remains locked",
        "Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path",
        "Phase 24 Real Browser Read-Only Mode",
    )
    for doc in DOCS:
        text = (ROOT / "docs" / doc).read_text(encoding="utf-8")
        for phrase in required_doc_phrases:
            check(phrase in text, f"docs missing '{phrase}': {doc}")

    check("verify_eva_ai_os_control_center_upgrade.py" in verify_eva_all.FULL_VERIFIERS, "full master profile missing Phase 23")
    check("verify_eva_ai_os_control_center_upgrade.py" in verify_eva_all.QUICK_VERIFIERS, "quick master profile missing Phase 23")

    source = "\n".join(path.read_text(encoding="utf-8").lower() for path in (ROOT / "backend/eva/ai_os").glob("*.py"))
    for forbidden in (
        "import requests",
        "httpx",
        "urllib.request",
        "subprocess",
        "playwright",
        "pyautogui",
        "flask",
        "fastapi",
        "websocket",
        "electron",
        "os.system",
        "open(",
    ):
        check(forbidden not in source, f"forbidden runtime surface in AI OS source: {forbidden}")

    print("PASS: Phase 23 AI OS / Control Center Upgrade is deterministic, local/status-only, and fully wired.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
