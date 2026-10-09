from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

NESTED_TIMEOUT_SECONDS = int(os.environ.get("EVA_VERIFY_NESTED_TIMEOUT_SECONDS", "1200"))


def emit(case: str, passed: bool, **payload: Any) -> int:
    ok = bool(passed)
    print(json.dumps({"case": case, "pass": ok, **payload}, indent=2, ensure_ascii=False))
    return 0 if ok else 1


def clean_output(text: str) -> bool:
    blocked = (
        "{'",
        "EvaTaskPlan(",
        "EvaTaskStep(",
        "EvaPlannerStatus(",
        "CapabilityResolution(",
        "Traceback",
        "C:\\Users\\",
        "C:/Users/",
        "backend/eva/data",
        ".env.local",
        "sqlite3.Row",
    )
    return bool(text and not any(marker in text for marker in blocked))


from _nested import run_nested as _shared_run_nested  # noqa: E402


def run_nested(script_name: str) -> tuple[bool, str]:
    # Shared runner: UTF-8 output, one level deep, one timeout (scripts/_nested.py).
    return _shared_run_nested(script_name)


def main() -> int:
    failures = 0
    try:
        from backend.eva.core.fast_commands import maybe_handle_fast_command
        from backend.eva.planner.capability_selector import infer_goal_intents, select_capabilities_for_goal
        from backend.eva.planner.decomposer import create_task_plan
        from backend.eva.planner.formatter import format_task_plan
        from backend.eva.planner.models import EvaPlannerStatus, EvaTaskPlan, EvaTaskStep
        from backend.eva.planner.status import format_planner_status, planner_status
        from backend.eva.tools.registry import ToolRegistry
    except Exception as exc:
        failures += emit("planner_package_imports", False, error=str(exc))
        print(json.dumps({"overall_pass": False, "failures": failures}, indent=2))
        return 1

    failures += emit("planner_package_imports", True)
    status = planner_status()
    status_text = format_planner_status()
    failures += emit(
        "planner_status_human_readable",
        isinstance(status, EvaPlannerStatus)
        and status.planning_only
        and not status.execution_enabled
        and clean_output(status_text)
        and "planning-only" in status_text.lower(),
        output=status_text,
    )

    research_plan = create_task_plan("use my saved research about Eva and summarize it")
    failures += emit(
        "create_task_plan_serializable",
        isinstance(research_plan, EvaTaskPlan)
        and isinstance(research_plan.as_dict(), dict)
        and isinstance(research_plan.steps[0], EvaTaskStep),
        plan=research_plan.as_dict(),
    )
    research_caps = set(research_plan.required_capabilities)
    failures += emit(
        "saved_research_plan_uses_research_capability",
        {"research_memory.retrieve", "research_memory.search"} & research_caps
        and any(step.resource_id == "eva-research-memory-v2" for step in research_plan.steps),
        capabilities=sorted(research_caps),
    )
    failures += emit(
        "saved_research_resource_available",
        any(step.availability_status == "available_now" and step.resource_id == "eva-research-memory-v2" for step in research_plan.steps),
        steps=[step.as_dict() for step in research_plan.steps],
    )

    whatsapp_plan = create_task_plan("send WhatsApp to mom saying hi")
    failures += emit(
        "whatsapp_plan_confirmation_or_blocked_no_execute",
        whatsapp_plan.confirmation_required
        and not whatsapp_plan.can_execute_now
        and any(step.step_type in {"external_message", "user_confirmation", "blocked"} for step in whatsapp_plan.steps),
        plan=whatsapp_plan.as_dict(),
    )

    delete_plan = create_task_plan("delete Downloads folder")
    failures += emit(
        "delete_plan_override_or_blocked_no_execute",
        (delete_plan.override_required or bool(delete_plan.blocked_capabilities))
        and not delete_plan.can_execute_now
        and any(step.permission_status in {"override_required", "blocked"} for step in delete_plan.steps),
        plan=delete_plan.as_dict(),
    )

    chatgpt_plan = create_task_plan("open ChatGPT on Chrome")
    failures += emit(
        "chatgpt_browser_plan_preview_only",
        not chatgpt_plan.can_execute_now
        and any(step.step_type == "browser_open" for step in chatgpt_plan.steps)
        and all(step.status == "planned" for step in chatgpt_plan.steps),
        plan=chatgpt_plan.as_dict(),
    )

    hackathon_plan = create_task_plan("prepare my hackathon submission")
    failures += emit(
        "hackathon_plan_multiple_steps",
        len(hackathon_plan.steps) >= 3
        and {"draft_content", "verification"} <= {step.step_type for step in hackathon_plan.steps},
        plan=hackathon_plan.as_dict(),
    )

    unknown_plan = create_task_plan("organize the quantum banana launch")
    failures += emit(
        "unknown_goal_safe_preview",
        any(step.capability_id is None for step in unknown_plan.steps)
        and unknown_plan.preview_only
        and not unknown_plan.can_execute_now,
        plan=unknown_plan.as_dict(),
    )

    formatted_outputs = [
        format_task_plan(research_plan),
        format_task_plan(whatsapp_plan),
        format_task_plan(delete_plan),
        format_task_plan(unknown_plan),
    ]
    failures += emit(
        "formatted_outputs_human_readable",
        all(clean_output(text) for text in formatted_outputs)
        and all("Eva Planner v3 preview" in text for text in formatted_outputs),
        output=formatted_outputs[0],
    )

    failures += emit(
        "capability_selector_examples",
        "research_memory.retrieve" in select_capabilities_for_goal("use my saved research")
        and "external_message" in infer_goal_intents("send WhatsApp to mom"),
    )

    tools = ToolRegistry()
    command_cases = {
        "eva planner status": "Planner v3",
        "eva plan use my saved research about Eva": "research_memory",
        "eva plan send WhatsApp to mom saying hi": "confirmation",
        "eva plan delete Downloads folder": "override",
        "eva planner explain prepare my hackathon submission": "Eva Planner v3 preview",
    }
    for command, expected in command_cases.items():
        handled = maybe_handle_fast_command(command, tools, {})
        text = handled[0] if handled else ""
        failures += emit(
            f"command_{re.sub(r'[^a-z0-9]+', '_', command.lower()).strip('_')}",
            handled is not None and expected.lower() in text.lower() and clean_output(text),
            output=text,
        )

    planner_root = ROOT / "backend" / "eva" / "planner"
    from _source_guard import (
        BROWSER_DRIVER_MODULES, SHELL_CALLS, SHELL_MODULES, no_browser_secret_reads, no_env_local_read, scan,
    )

    # Real imports/calls only; the old substring scan matched "ai_os.system_map" as os.system.
    found = scan([planner_root], modules=SHELL_MODULES + BROWSER_DRIVER_MODULES + ("mcp",), calls=SHELL_CALLS)[0]
    found += no_env_local_read([planner_root])[0] + no_browser_secret_reads([planner_root])[0]
    failures += emit("planner_no_forbidden_execution_imports", not found, found=[str(f) for f in found])

    nested_scripts = [
        "verify_eva_capability_resource_mapping.py",
        "verify_eva_capability_permissions.py",
        "verify_eva_capabilities.py",
        "verify_eva_research_memory_ranking.py",
        "verify_eva_stabilization_v1.py",
    ]
    if os.environ.get("EVA_VERIFY_SKIP_NESTED") == "1":
        for script_name in nested_scripts:
            failures += emit(f"nested_{script_name}", True, skipped=True, reason="Skipped inside master verifier profile.")
    else:
        for script_name in nested_scripts:
            ok, output = run_nested(script_name)
            failures += emit(f"nested_{script_name}", ok, tail=output)

    print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
