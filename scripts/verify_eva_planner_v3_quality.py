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
        "PlanTemplate(",
        "PlanValidationIssue(",
        "PlanValidationResult(",
        "Traceback",
        "C:\\Users\\",
        "C:/Users/",
        ".env.local",
        "sqlite3.Row",
    )
    return bool(text and not any(marker in text for marker in blocked))


from _nested import run_nested as _shared_run_nested  # noqa: E402


def run_nested(script_name: str) -> tuple[bool, str]:
    # Shared runner: UTF-8 output, one level deep, one timeout (scripts/_nested.py).
    return _shared_run_nested(script_name)


def has_step(plan: Any, *needles: str) -> bool:
    text = "\n".join(f"{step.title}\n{step.description}\n{step.notes}".lower() for step in plan.steps)
    return all(needle.lower() in text for needle in needles)


def main() -> int:
    failures = 0
    try:
        from backend.eva.core.fast_commands import maybe_handle_fast_command
        from backend.eva.planner.critique import (
            critique_task_plan,
            detect_missing_information,
            format_plan_review,
            suggest_plan_improvements,
        )
        from backend.eva.planner.decomposer import create_task_plan
        from backend.eva.planner.formatter import format_task_plan
        from backend.eva.planner.templates import (
            apply_template_to_goal,
            format_plan_templates,
            get_plan_templates,
            get_template_for_goal,
        )
        from backend.eva.planner.validation import (
            PlanValidationIssue,
            PlanValidationResult,
            compute_plan_quality_score,
            explain_plan_quality,
            format_plan_validation,
            validate_task_plan,
        )
        from backend.eva.planner.models import EvaTaskPlan, EvaTaskStep
        from backend.eva.tools.registry import ToolRegistry
    except Exception as exc:
        failures += emit("phase_10b_imports", False, error=str(exc))
        print(json.dumps({"overall_pass": False, "failures": failures}, indent=2))
        return 1

    failures += emit("templates_module_imports", True)
    failures += emit("validation_module_imports", True)
    failures += emit("critique_module_imports", True)

    templates = get_plan_templates()
    failures += emit("plan_templates_non_empty", bool(templates), count=len(templates))

    saved_template = get_template_for_goal("use my saved research about Eva")
    failures += emit(
        "saved_research_selects_template",
        saved_template is not None and saved_template.template_id == "saved_research_summary",
        template=saved_template.template_id if saved_template else None,
    )

    hackathon_plan = create_task_plan("prepare my hackathon submission")
    missing_hackathon = detect_missing_information("prepare my hackathon submission", hackathon_plan)
    failures += emit(
        "hackathon_submission_multistep_plan",
        len(hackathon_plan.steps) >= 5
        and has_step(hackathon_plan, "requirements")
        and has_step(hackathon_plan, "draft")
        and has_step(hackathon_plan, "verify"),
        plan=hackathon_plan.as_dict(),
    )
    failures += emit(
        "hackathon_missing_info_detected",
        any("project" in item.lower() for item in missing_hackathon)
        and any("submission" in item.lower() or "deadline" in item.lower() for item in missing_hackathon),
        missing=missing_hackathon,
    )

    motor_plan = create_task_plan("compare drone motors and make a report")
    failures += emit(
        "drone_motor_report_plan_has_compare_and_report_steps",
        has_step(motor_plan, "compare")
        and has_step(motor_plan, "thrust")
        and has_step(motor_plan, "report"),
        plan=motor_plan.as_dict(),
    )

    whatsapp_plan = create_task_plan("send WhatsApp to mom saying hi")
    failures += emit(
        "whatsapp_plan_confirmation_checkpoint_no_execution",
        whatsapp_plan.confirmation_required
        and not whatsapp_plan.can_execute_now
        and any(step.permission_status == "confirmation_required" for step in whatsapp_plan.steps)
        and all(step.status == "planned" for step in whatsapp_plan.steps),
        plan=whatsapp_plan.as_dict(),
    )

    delete_plan = create_task_plan("delete Downloads folder")
    failures += emit(
        "delete_downloads_blocked_or_override",
        (delete_plan.override_required or bool(delete_plan.blocked_capabilities))
        and not delete_plan.can_execute_now
        and any(step.permission_status in {"blocked", "override_required"} for step in delete_plan.steps),
        plan=delete_plan.as_dict(),
    )

    research_plan = create_task_plan("use my saved research about Eva and summarize it")
    research_validation = validate_task_plan(research_plan)
    failures += emit(
        "safe_research_plan_validation_passes",
        research_validation.passed and research_validation.quality_score >= 0.7,
        validation=research_validation.as_dict(),
    )

    bad_step = EvaTaskStep(
        step_id="step_1",
        title="Send message",
        description="Send an external message.",
        step_type="external_message",
        capability_id="whatsapp.send",
        resource_id=None,
        agent="SafetyAgent",
        input_summary="send hi",
        expected_output="sent message",
        risk_level="high",
        permission_status="allowed",
        availability_status="available_now",
        notes="Missing confirmation on purpose.",
    )
    bad_plan = EvaTaskPlan(
        plan_id="plan_bad",
        user_goal="send hi",
        normalized_goal="send hi",
        summary="bad plan",
        steps=[bad_step],
        required_capabilities=["whatsapp.send"],
        blocked_capabilities=[],
        confirmation_required=False,
        override_required=False,
        can_execute_now=False,
        preview_only=True,
        safety_summary="test",
        next_recommended_action="test",
        created_at="2026-06-07T00:00:00+00:00",
    )
    bad_validation = validate_task_plan(bad_plan)
    failures += emit(
        "validation_flags_risky_plan_missing_confirmation",
        not bad_validation.passed
        and any("confirmation" in issue.message.lower() for issue in bad_validation.issues),
        validation=bad_validation.as_dict(),
    )

    quality = compute_plan_quality_score(hackathon_plan)
    failures += emit("plan_quality_score_between_zero_and_one", 0.0 <= quality <= 1.0, score=quality)
    failures += emit(
        "multistep_output_goal_has_verification_step",
        any(step.step_type == "verification" or "verify" in step.title.lower() for step in hackathon_plan.steps),
        plan=hackathon_plan.as_dict(),
    )

    review_output = format_plan_review(hackathon_plan)
    templates_output = format_plan_templates()
    validation_output = format_plan_validation(research_validation)
    formatted_plan = format_task_plan(hackathon_plan)
    quality_text = explain_plan_quality(hackathon_plan)
    outputs = [review_output, templates_output, validation_output, formatted_plan, quality_text]
    failures += emit(
        "plan_review_and_quality_outputs_human_readable",
        all(clean_output(text) for text in outputs)
        and "Missing information" in review_output
        and "Plan quality" in formatted_plan,
        review=review_output,
        plan=formatted_plan,
    )

    failures += emit(
        "template_application_returns_steps",
        len(apply_template_to_goal("make report about Eva", "report_generation")) >= 3,
    )

    tools = ToolRegistry()
    command_cases = {
        "eva plan templates": "Plan templates",
        "eva planner templates": "Plan templates",
        "eva plan validate use my saved research about Eva": "Plan validation",
        "eva planner validate use my saved research about Eva": "Plan validation",
        "eva plan review prepare my hackathon submission": "Missing information",
        "eva planner review send WhatsApp to mom saying hi": "confirmation",
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
    source_text = "\n".join(path.read_text(encoding="utf-8", errors="replace").lower() for path in planner_root.rglob("*.py"))
    forbidden = [
        "from playwright",
        "import playwright",
        "sync_playwright",
        "async_playwright",
        "import pyautogui",
        "pyautogui.",
        "mcp.",
        "subprocess",
        "os.system(",
        "popen",
        "open('.env.local",
        'open(".env.local',
    ]
    failures += emit("planner_no_forbidden_execution_imports", not any(pattern in source_text for pattern in forbidden))

    nested_scripts = [
        "verify_eva_planner_v3.py",
        "verify_eva_capability_resource_mapping.py",
        "verify_eva_capability_permissions.py",
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
