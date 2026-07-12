from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def assert_clean(text: str, label: str) -> None:
    forbidden = [
        "{'",
        "ControlCenterStatus(",
        "Traceback",
        "C:\\Users\\",
        ".env.local",
        "api_key",
        "Bearer ",
        "sk-",
    ]
    for token in forbidden:
        assert_true(token not in text, f"{label} leaked unsafe/internal token: {token}")


def main() -> int:
    from backend.eva.agents.team_review import format_team_review
    from backend.eva.capabilities.permissions import get_capability_permission
    from backend.eva.capabilities.registry import build_default_registry
    from backend.eva.capabilities.resource_mapping import resolve_capability
    from backend.eva.capabilities.tool_schemas import capability_to_tool_schema
    from backend.eva.control_center.collector import collect_control_center_status
    from backend.eva.control_center.formatter import (
        format_control_center_status,
        format_enabled_features,
        format_locked_features,
        format_next_safe_step,
    )
    from backend.eva.core.fast_commands import maybe_handle_fast_command
    from backend.eva.core.natural_router import route_natural_request
    from backend.eva.planner.capability_selector import select_capabilities_for_goal
    from backend.eva.planner.decomposer import create_task_plan
    from backend.eva.tools.registry import ToolRegistry

    status = collect_control_center_status()
    text = format_control_center_status(status)
    assert_clean(text, "control center status")
    for required in [
        "Eva Control Center",
        "Phase 12P",
        "Phase 12 Health / Verification",
        "Project / Reality Check",
        "Specialists / Skills / Workflows",
        "Latest Workflow State",
        "Approvals",
        "Sandbox Apply",
        "Narrow Real Apply Gate",
        "Rollback availability",
        "Locked Features",
        "Recommended Next Safe Step",
        "12L narrow real create",
    ]:
        assert_true(required in text, f"control center includes {required}")
    assert_true("Dashboard does not run verifiers automatically" in text, "dashboard does not execute verifiers")
    assert_true("create-new-text-file only" in text, "enabled real action remains narrow")

    locked = format_locked_features(status)
    enabled = format_enabled_features(status)
    next_step = format_next_safe_step(status)
    for label, output in [("locked", locked), ("enabled", enabled), ("next", next_step)]:
        assert_clean(output, label)
        assert_true("Execution: status only" in output or "No task was executed" in output, f"{label} is status-only")
    assert_true("existing file edits: locked" in locked.lower(), "locked features explain existing file edits")
    assert_true("browser control: locked" in locked.lower(), "locked features explain browser control")
    assert_true("mcp: locked" in locked.lower(), "locked features explain MCP")
    assert_true("12L narrow real create" in enabled, "enabled features name 12L narrow real create")
    assert_true("gated write path" in enabled.lower(), "enabled features states gated write path")
    assert_true("Recommended next safe step" in next_step, "next safe step formatter exists")

    tools = ToolRegistry()
    commands = [
        "eva control center",
        "eva control center status",
        "eva control center summary",
        "eva dashboard status",
        "eva locked features",
        "eva enabled features",
        "eva next safe step",
        "eva ask show control center",
        "eva ask show dashboard status",
        "eva ask what features are locked",
        "eva ask what features are enabled",
        "eva ask what is the next safe step",
        "eva ask show Eva status",
    ]
    for command in commands:
        result = maybe_handle_fast_command(command, tools)
        assert_true(result is not None, f"{command} handled")
        assert_clean(result[0], command)
        assert_true("Control Center" in result[0] or "Locked features" in result[0] or "Enabled features" in result[0] or "Next safe step" in result[0] or "Eva ask" in result[0], f"{command} returns friendly status text")

    route_expectations = {
        "show control center": "control_center_status",
        "show dashboard status": "control_center_status",
        "what features are locked": "locked_features",
        "what features are enabled": "enabled_features",
        "what is the next safe step": "next_safe_step",
        "show Eva status": "control_center_status",
    }
    for prompt, intent in route_expectations.items():
        route = route_natural_request(prompt)
        assert_true(route.intent == intent, f"{prompt!r} routes to {intent}, got {route.intent}")
        assert_true(route.authority_category == "read", f"{prompt!r} is read-only")

    registry = build_default_registry()
    for cap_id in [
        "eva.control_center_status",
        "eva.control_center_summary",
        "eva.locked_features",
        "eva.enabled_features",
        "eva.next_safe_step",
    ]:
        assert_true(registry.get(cap_id) is not None, f"{cap_id} registered")
        permission = get_capability_permission(cap_id)
        assert_true(permission.read_only, f"{cap_id} is read-only")
        assert_true(not permission.external_effect, f"{cap_id} has no external effect")
        assert_true(resolve_capability(cap_id).resource_id is not None, f"{cap_id} maps to a resource")
        assert_true(capability_to_tool_schema(cap_id) is not None, f"{cap_id} schema exists")

    caps = select_capabilities_for_goal("show dashboard status and what features are locked")
    assert_true("eva.control_center_status" in caps, "planner selects control center")
    assert_true("eva.locked_features" in caps, "planner selects locked features")
    plan = create_task_plan("what features are enabled")
    assert_true(any(step.capability_id == "eva.enabled_features" for step in plan.steps), "planner includes enabled features step")
    review = format_team_review("show control center status")
    assert_true("Control Center/status route" in review, "team review includes control-center route")
    assert_true("locked-feature explanations" in review.lower(), "team review mentions locked features")
    assert_clean(review, "team review")

    source_files = [
        ROOT / "backend/eva/control_center/collector.py",
        ROOT / "backend/eva/control_center/formatter.py",
        ROOT / "backend/eva/core/natural_router.py",
    ]
    joined = "\n".join(path.read_text(encoding="utf-8") for path in source_files if path.exists()).lower()
    for forbidden in ["import playwright", "from playwright", "import pyautogui", "from pyautogui", "import subprocess", "subprocess.", "requests.", "httpx.", "pip install"]:
        assert_true(forbidden not in joined, f"no forbidden feature code: {forbidden}")

    print("verify_eva_control_center_v1: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
