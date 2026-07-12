from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def assert_true(condition: object, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    from backend.eva.desktop_agent.formatter import (
        format_desktop_locked_status,
        format_desktop_phase14_final_proof,
        format_desktop_phase14_limits,
        format_desktop_phase14_ready,
        format_desktop_phase14_status,
        format_desktop_phase14_summary,
        format_desktop_readiness_gaps,
        format_desktop_readiness_proof,
    )
    from backend.eva.desktop_agent.phase14_final import get_desktop_phase14_final_limits, get_desktop_phase14_proof
    from backend.eva.desktop_agent.readiness_proof import DesktopReadinessStatus, build_desktop_readiness_proof
    from backend.eva.capabilities.permissions import get_capability_permission
    from backend.eva.capabilities.registry import get_capability
    from backend.eva.capabilities.resource_mapping import resolve_capability
    from backend.eva.capabilities.tool_schemas import capability_to_tool_schema
    from backend.eva.control_center.status import format_control_center_text
    from backend.eva.core.fast_commands import maybe_handle_fast_command
    from backend.eva.core.natural_router import route_natural_request
    from backend.eva.planner.capability_selector import select_capabilities_for_goal
    from backend.eva.planner.decomposer import create_task_plan
    from backend.eva.agents.team_review import format_team_review
    from backend.eva.tools.registry import ToolRegistry

    readiness = build_desktop_readiness_proof()
    assert_true(readiness.status == DesktopReadinessStatus.PHASE14_COMPLETE_LOCKED, "readiness proof must remain locked")
    assert_true(readiness.real_desktop_observation_enabled is False, "desktop observation must stay disabled")
    assert_true(readiness.real_desktop_control_enabled is False, "desktop control must stay disabled")
    assert_true(readiness.approvals_unlock_execution is False, "approval must not unlock execution")
    layer_text = " ".join(readiness.completed_layers).lower()
    for expected in ("safety", "session", "screen", "dry-run", "risk", "approval"):
        assert_true(expected in layer_text, f"missing readiness layer: {expected}")

    proof = get_desktop_phase14_proof()
    assert_true(proof.phase == "Phase 14G", "unexpected Phase 14 final proof")
    assert_true(proof.safety_readiness_only, "Phase 14 final proof must be status only")
    assert_true(proof.real_desktop_observation_enabled is False, "desktop observation must stay disabled")
    assert_true(proof.real_desktop_control_enabled is False, "desktop control must stay disabled")
    assert_true(proof.approvals_unlock_execution is False, "approval must never unlock execution")
    assert_true(get_desktop_phase14_final_limits(), "final limits missing")

    def assert_clean(text: str, label: str) -> None:
        for token in ("{'", "DesktopLockedReadinessProof(", "DesktopReadinessCheck(", "DesktopPhase14FinalProof(", "Traceback", "C:\\Users\\", "api_key=", "Bearer ", "sk-"):
            assert_true(token not in text, f"{label} leaked unsafe/internal token: {token}")

    def assert_proof_text(text: str, label: str) -> None:
        assert_clean(text, label)
        lower = text.lower()
        for phrase in ("phase 14", "real desktop observation is not enabled", "real desktop control is not enabled", "approvals do not unlock execution", "phase 12l narrow real create remains a gated write path"):
            assert_true(phrase in lower, f"{label} missing {phrase}")
        assert_true("no desktop" in lower or "execution:" in lower, f"{label} missing no-execution proof")

    outputs = {
        "status": format_desktop_phase14_status(),
        "summary": format_desktop_phase14_summary(),
        "limits": format_desktop_phase14_limits(),
        "ready": format_desktop_phase14_ready(),
        "final proof": format_desktop_phase14_final_proof(),
        "readiness proof": format_desktop_readiness_proof(),
        "locked status": format_desktop_locked_status(),
        "gaps": format_desktop_readiness_gaps(),
    }
    for label, output in outputs.items():
        assert_proof_text(output, label)

    commands = (
        "eva desktop phase 14 status", "eva desktop phase 14 summary", "eva desktop phase 14 limits", "eva desktop phase 14 ready",
        "eva desktop phase 14 final proof", "eva desktop readiness proof", "eva desktop locked status", "eva desktop readiness gaps",
        "eva ask is desktop phase 14 complete", "eva ask prove desktop control is still locked", "eva ask what is missing before desktop observation",
    )
    for command in commands:
        result = maybe_handle_fast_command(command, ToolRegistry())
        assert_true(result is not None, f"unhandled command: {command}")
        assert_proof_text(result[0], command)

    routes = {
        "is desktop phase 14 complete": "desktop_phase14_ready",
        "summarize desktop phase 14": "desktop_phase14_summary",
        "what are desktop phase 14 limits": "desktop_phase14_limits",
        "prove desktop control is still locked": "desktop_phase14_final_proof",
        "desktop readiness proof": "desktop_readiness_proof",
        "what is missing before desktop observation": "desktop_readiness_gaps",
    }
    for prompt, expected in routes.items():
        route = route_natural_request(prompt)
        assert_true(route.intent == expected, f"{prompt!r} routed to {route.intent}, expected {expected}")
        assert_true(route.authority_category == "read" and not route.real_execution_requested, f"{prompt!r} is not status-only")

    control = format_control_center_text()
    assert_clean(control, "Control Center")
    assert_true("DesktopAgent Phase 14 Final Proof" in control, "Control Center missing Phase 14 final panel")
    assert_true("Phase 15 LLM Router + Structured Reasoning Core" in control, "Control Center missing intelligence spine")

    capability_ids = (
        "desktop.phase14_status", "desktop.phase14_summary", "desktop.phase14_limits", "desktop.phase14_ready",
        "desktop.phase14_final_proof", "desktop.readiness_proof", "desktop.locked_status", "desktop.readiness_gaps",
    )
    for capability_id in capability_ids:
        assert_true(get_capability(capability_id) is not None, f"missing capability: {capability_id}")
        permission = get_capability_permission(capability_id)
        assert_true(permission.read_only and not permission.external_effect, f"{capability_id} must be read-only")
        assert_true(resolve_capability(capability_id).resource_id == "eva-desktop-agent-safety", f"{capability_id} missing DesktopAgent resource")
        assert_true(capability_to_tool_schema(capability_id) is not None, f"{capability_id} missing tool schema")

    selected = select_capabilities_for_goal("summarize desktop phase 14 and prove desktop control is still locked")
    assert_true("desktop.phase14_summary" in selected and "desktop.phase14_final_proof" in selected, "planner selector missed Phase 14 proof")
    plan = create_task_plan("is desktop phase 14 complete")
    assert_true(any(step.capability_id == "desktop.phase14_ready" for step in plan.steps), "planner missed Phase 14 ready")
    assert_true(all(step.permission_status in {"allowed", "preview_only"} for step in plan.steps), "readiness plan is not safely read-only")
    review = format_team_review("prove desktop control is still locked")
    assert_clean(review, "team review")
    assert_true("DesktopAgent Phase 14 readiness proof route" in review, "team review missing Phase 14 route")
    assert_true("proof/status only" in review.lower(), "team review missing status-only boundary")

    source = "\n".join(path.read_text(encoding="utf-8").lower() for path in (ROOT / "backend/eva/desktop_agent").rglob("*.py"))
    for token in ("import pyautogui", "from pyautogui", "import playwright", "from playwright", "import subprocess", "subprocess.", "os.system", "pip install", "requests.", "httpx.", "urllib.request", "imagegrab", "pytesseract", "easyocr", "mss.", "cv2.", "getwindowswithtitle", "getactivewindow", "enumwindows", "pyperclip", "clipboard."):
        assert_true(token not in source, f"forbidden execution/privacy code found: {token}")

    print("verify_eva_desktop_phase14_readiness: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
