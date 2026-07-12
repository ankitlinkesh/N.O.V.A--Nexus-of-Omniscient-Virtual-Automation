from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def assert_true(condition: object, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def assert_clean(text: str, label: str) -> None:
    forbidden = [
        "{'",
        "BrowserPhase13FinalProof(",
        "BrowserPhase13Limit(",
        "BrowserPhase13CompletedLayer(",
        "Traceback",
        "C:\\Users\\",
        ".env.local",
        "api_key",
        "Bearer ",
        "sk-",
        str(ROOT),
    ]
    for token in forbidden:
        assert_true(token not in text, f"{label} leaked unsafe/internal token: {token}")


def run_fast_command(command: str) -> str:
    from backend.eva.core.fast_commands import maybe_handle_fast_command
    from backend.eva.tools.registry import ToolRegistry

    result = maybe_handle_fast_command(command, ToolRegistry())
    assert_true(result is not None, f"{command} was not handled")
    return result[0]


def assert_final_proof_text(text: str, label: str) -> None:
    assert_clean(text, label)
    lower = text.lower()
    assert_true("phase 13 is safety/readiness only" in lower, f"{label} missing Phase 13 safety/readiness boundary")
    assert_true("real browser read-only mode is not enabled" in lower, f"{label} missing read-only locked boundary")
    assert_true("real browser control is not enabled" in lower, f"{label} missing control locked boundary")
    assert_true("network/dns/live page read/dom/screenshot/action execution are locked" in lower, f"{label} missing locked execution summary")
    assert_true("separate approved gate" in lower, f"{label} missing future approved gate wording")
    assert_true("phase 12l narrow real create remains a gated write path" in lower, f"{label} missing Phase 12L boundary")
    assert_true("no browser" in lower and "no network" in lower, f"{label} missing no browser/network execution proof")


def main() -> int:
    from backend.eva.agents.team_review import format_team_review
    from backend.eva.browser_agent.formatter import (
        format_browser_phase13_final_proof,
        format_browser_phase13_limits,
        format_browser_phase13_ready,
        format_browser_phase13_status,
        format_browser_phase13_summary,
    )
    from backend.eva.browser_agent.phase13_final import (
        build_browser_phase13_final_proof,
        get_browser_phase13_final_limits,
    )
    from backend.eva.capabilities.permissions import get_capability_permission
    from backend.eva.capabilities.registry import get_capability
    from backend.eva.capabilities.resource_mapping import resolve_capability
    from backend.eva.capabilities.tool_schemas import capability_to_tool_schema
    from backend.eva.control_center.status import format_control_center_text
    from backend.eva.core.natural_router import route_natural_request
    from backend.eva.planner.capability_selector import select_capabilities_for_goal
    from backend.eva.planner.decomposer import create_task_plan

    proof = build_browser_phase13_final_proof()
    assert_true(proof.phase == "Phase 13G", "unexpected hardening phase")
    assert_true(proof.safety_readiness_only, "Phase 13 final proof should be safety/readiness only")
    assert_true(not proof.real_readonly_enabled, "real browser read-only unexpectedly enabled")
    assert_true(not proof.real_control_enabled, "real browser control unexpectedly enabled")
    assert_true("separate approved gate" in proof.future_gate.lower(), "future gate wording missing")
    assert_true("Phase 12L" in proof.phase12_boundary, "Phase 12L boundary missing")
    assert_true(get_browser_phase13_final_limits(), "final limits missing")

    outputs = {
        "status": format_browser_phase13_status(),
        "summary": format_browser_phase13_summary(),
        "limits": format_browser_phase13_limits(),
        "ready": format_browser_phase13_ready(),
        "final proof": format_browser_phase13_final_proof(),
    }
    for label, output in outputs.items():
        assert_final_proof_text(output, label)

    commands = [
        "eva browser phase 13 status",
        "eva browser phase 13 summary",
        "eva browser phase 13 limits",
        "eva browser phase 13 ready",
        "eva browser phase 13 final proof",
        "eva ask is browser phase 13 complete",
        "eva ask summarize browser phase 13",
        "eva ask what are browser phase 13 limits",
        "eva ask can Eva browse now",
    ]
    for command in commands:
        output = run_fast_command(command)
        assert_final_proof_text(output, command)

    routes = {
        "is browser phase 13 complete": "browser_phase13_ready",
        "summarize browser phase 13": "browser_phase13_summary",
        "what are browser phase 13 limits": "browser_phase13_limits",
        "browser phase 13 final proof": "browser_phase13_final_proof",
    }
    for prompt, expected_intent in routes.items():
        route = route_natural_request(prompt)
        assert_true(route.intent == expected_intent, f"{prompt!r} routed to {route.intent}, expected {expected_intent}")
        assert_true(route.authority_category == "read", f"{prompt!r} should be read/status")
        assert_true(route.real_execution_requested is False, f"{prompt!r} requested real execution")

    control = format_control_center_text()
    assert_clean(control, "control center")
    assert_true("Browser Read-Only Readiness Proof" in control, "Control Center missing readiness proof panel")
    assert_true("Phase 13 final proof" in control, "Control Center missing Phase 13 final proof wording")
    assert_true("separate approved gate" in control.lower(), "Control Center missing separate approved gate wording")
    assert_true("Phase 12L narrow real create remains a gated write path" in control, "Control Center missing Phase 12L boundary")

    for capability_id in (
        "browser.phase13_status",
        "browser.phase13_summary",
        "browser.phase13_limits",
        "browser.phase13_ready",
        "browser.phase13_final_proof",
    ):
        capability = get_capability(capability_id)
        assert_true(capability is not None, f"missing capability {capability_id}")
        permission = get_capability_permission(capability_id)
        assert_true(permission.read_only and not permission.external_effect, f"{capability_id} should be read-only")
        assert_true(resolve_capability(capability_id).resource_id == "eva-browser-agent-safety", f"missing resource for {capability_id}")
        assert_true(capability_to_tool_schema(capability_id) is not None, f"missing schema for {capability_id}")

    caps = select_capabilities_for_goal("summarize browser phase 13 and what are browser phase 13 limits")
    assert_true("browser.phase13_summary" in caps, "planner selector missed phase13 summary")
    assert_true("browser.phase13_limits" in caps, "planner selector missed phase13 limits")
    plan = create_task_plan("is browser phase 13 complete")
    assert_true(any(step.capability_id == "browser.phase13_ready" for step in plan.steps), "planner missed phase13 ready")
    assert_true(all(step.permission_status in {"allowed", "preview_only"} for step in plan.steps), "phase13 plan contains risky execution")
    review = format_team_review("is browser phase 13 complete")
    assert_clean(review, "team review")
    assert_true("BrowserAgent Phase 13 hardening route" in review, "team review missing hardening route")
    assert_true("proof/status only" in review.lower(), "team review missing proof/status wording")

    source_files = [
        ROOT / "backend/eva/browser_agent",
        ROOT / "backend/eva/core/natural_router.py",
    ]
    source_text = ""
    for path in source_files:
        if path.is_dir():
            for child in path.rglob("*.py"):
                source_text += child.read_text(encoding="utf-8").lower() + "\n"
        elif path.exists():
            source_text += path.read_text(encoding="utf-8").lower() + "\n"
    forbidden = [
        "import socket",
        "socket.",
        "gethostbyname",
        "dns.resolver",
        "import playwright",
        "from playwright",
        "import browser_use",
        "from browser_use",
        "import stagehand",
        "from stagehand",
        "import maxun",
        "from maxun",
        "import pyautogui",
        "from pyautogui",
        "import subprocess",
        "subprocess.",
        "requests.",
        "httpx.",
        "urllib.request",
        "pip install",
        ".cookies(",
        "context.cookies",
        "localstorage.getitem",
        "local_storage_state",
        "browser.launch",
        "page.goto",
        "page.click",
        "page.fill",
        "page.screenshot",
    ]
    for token in forbidden:
        assert_true(token not in source_text, f"forbidden browser/network execution/privacy code found: {token}")

    print("verify_eva_browser_phase13_hardening: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
