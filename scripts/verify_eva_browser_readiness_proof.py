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
        "BrowserReadOnlyReadinessProof(",
        "BrowserReadinessCheck(",
        "BrowserReadinessGap(",
        "BrowserReadinessProofResult(",
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


def main() -> int:
    from backend.eva.browser_agent.formatter import (
        format_browser_locked_status,
        format_browser_phase13_proof,
        format_browser_read_only_readiness,
        format_browser_readiness_gaps,
        format_browser_readiness_proof,
        format_browser_safety_proof,
    )
    from backend.eva.browser_agent.readiness_proof import (
        BrowserReadinessStatus,
        build_browser_readiness_proof,
        get_browser_readiness_gaps,
    )
    from backend.eva.capabilities.permissions import get_capability_permission
    from backend.eva.capabilities.registry import get_capability
    from backend.eva.capabilities.resource_mapping import resolve_capability
    from backend.eva.capabilities.tool_schemas import capability_to_tool_schema
    from backend.eva.control_center.status import format_control_center_text
    from backend.eva.core.natural_router import route_natural_request
    from backend.eva.planner.capability_selector import select_capabilities_for_goal
    from backend.eva.planner.decomposer import create_task_plan
    from backend.eva.agents.team_review import format_team_review

    proof = build_browser_readiness_proof()
    assert_true(proof.status in {BrowserReadinessStatus.READY_FOR_DESIGN_ONLY, BrowserReadinessStatus.LOCKED_BY_POLICY}, "unexpected readiness proof status")
    check_names = " ".join(check.name.lower() for check in proof.checks)
    for layer in ("safety", "session", "observation", "action", "domain"):
        assert_true(layer in check_names, f"proof missing {layer} layer")
    assert_true(not proof.real_readonly_enabled, "real browser read-only mode unexpectedly enabled")
    assert_true("Phase 12L" in proof.phase12_boundary, "proof missing Phase 12L boundary")
    assert_true(get_browser_readiness_gaps(), "readiness gaps missing")

    outputs = {
        "readiness": format_browser_read_only_readiness(),
        "proof": format_browser_readiness_proof(),
        "safety": format_browser_safety_proof(),
        "gaps": format_browser_readiness_gaps(),
        "locked": format_browser_locked_status(),
        "phase": format_browser_phase13_proof(),
    }
    for label, output in outputs.items():
        assert_clean(output, label)
        lower = output.lower()
        assert_true("browser" in lower, f"{label} missing browser wording")
        assert_true("locked" in lower or "not enabled" in lower, f"{label} missing locked/not-enabled wording")
        assert_true("read-only" in lower or "readiness" in lower or "proof" in lower, f"{label} missing proof/readiness wording")
        assert_true("no network" in lower or "network" in lower, f"{label} missing network boundary")
        assert_true("phase 12l" in lower or "gated write path" in lower, f"{label} missing Phase 12L boundary")

    commands = [
        "eva browser read only readiness",
        "eva browser readiness proof",
        "eva browser safety proof",
        "eva browser readiness gaps",
        "eva browser locked status",
        "eva browser phase 13 proof",
        "eva ask is browser read-only mode ready",
        "eva ask prove browser control is still locked",
        "eva ask what is missing before browser read-only",
        "eva ask show browser safety proof",
        "eva ask is Phase 13 browser safe",
        "eva ask can Eva browse now",
    ]
    for command in commands:
        output = run_fast_command(command)
        assert_clean(output, command)
        lower = output.lower()
        assert_true("browser" in lower, f"{command} missing browser wording")
        assert_true("locked" in lower or "not enabled" in lower, f"{command} missing locked status")
        assert_true("no browser" in lower or "no network" in lower or "execution:" in lower, f"{command} missing no-execution boundary")

    routes = {
        "is browser read-only mode ready": "browser_readonly_readiness",
        "prove browser control is still locked": "browser_safety_proof",
        "what is missing before browser read-only": "browser_readiness_gaps",
        "show browser safety proof": "browser_safety_proof",
        "is Phase 13 browser safe": "browser_phase13_proof",
        "can Eva browse now": "browser_locked_status",
    }
    for prompt, expected_intent in routes.items():
        route = route_natural_request(prompt)
        assert_true(route.intent == expected_intent, f"{prompt!r} routed to {route.intent}, expected {expected_intent}")
        assert_true(route.authority_category == "read", f"{prompt!r} is not read/status")
        assert_true(route.real_execution_requested is False, f"{prompt!r} requested real browser execution")

    control = format_control_center_text()
    assert_clean(control, "control center")
    assert_true("Browser Read-Only Readiness Proof" in control, "Control Center missing Browser Read-Only Readiness Proof panel")
    assert_true("completed safety layers" in control.lower(), "Control Center missing completed safety layers")
    assert_true("readiness gaps" in control.lower(), "Control Center missing readiness gaps")

    for capability_id in (
        "browser.readonly_readiness",
        "browser.readiness_proof",
        "browser.safety_proof",
        "browser.readiness_gaps",
        "browser.locked_status",
        "browser.phase13_proof",
    ):
        assert_true(get_capability(capability_id) is not None, f"missing capability {capability_id}")
        permission = get_capability_permission(capability_id)
        assert_true(permission.read_only and not permission.external_effect, f"{capability_id} not read-only")
        assert_true(resolve_capability(capability_id).resource_id == "eva-browser-agent-safety", f"missing resource for {capability_id}")
        assert_true(capability_to_tool_schema(capability_id) is not None, f"missing schema for {capability_id}")

    caps = select_capabilities_for_goal("prove browser control is still locked and show browser safety proof")
    assert_true("browser.safety_proof" in caps, "planner selector missed safety proof")
    plan = create_task_plan("what is missing before browser read-only")
    assert_true(any(step.capability_id == "browser.readiness_gaps" for step in plan.steps), "planner missing readiness gaps")
    assert_true(all(step.permission_status in {"allowed", "preview_only"} for step in plan.steps), "readiness plan contains executable/risky permission")
    review = format_team_review("is Phase 13 browser safe")
    assert_clean(review, "team review")
    assert_true("BrowserAgent read-only readiness proof route" in review, "team review missing readiness proof route")
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

    print("verify_eva_browser_readiness_proof: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
