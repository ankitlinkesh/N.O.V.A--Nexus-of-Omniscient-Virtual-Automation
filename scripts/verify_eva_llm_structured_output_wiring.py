from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


VALIDATION_CAPABILITIES = (
    "llm.validation_status",
    "llm.schema_registry",
    "llm.validation_policy",
    "llm.repair_policy",
    "llm.validate_mock",
    "llm.validate_invalid_examples",
    "llm.validation_readiness",
)


def assert_true(condition: object, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def assert_safe_text(output: str, message: str) -> None:
    lowered = output.lower()
    assert_true("{'" not in output and "traceback" not in lowered, f"raw output: {message}")
    assert_true("c:\\users\\" not in lowered and "sk-" not in lowered, f"private or secret-like output: {message}")
    assert_true("live llm" in lowered and "locked" in lowered, f"missing live-call lock: {message}")
    assert_true("invalid llm output cannot execute tools" in lowered, f"missing execution block: {message}")


def main() -> int:
    from backend.eva.agents.team_review import format_team_review
    from backend.eva.capabilities.registry import get_capability
    from backend.eva.capabilities.resource_mapping import resolve_capability
    from backend.eva.capabilities.tool_schemas import capability_to_tool_schema
    from backend.eva.control_center.collector import collect_control_center_status
    from backend.eva.control_center.formatter import format_control_center_status, render_control_center_html
    from backend.eva.planner.capability_selector import infer_goal_intents, select_capabilities_for_goal
    from backend.eva.planner.decomposer import create_task_plan

    status = collect_control_center_status()
    validation_summary = status.llm_validation_summary
    assert_true(validation_summary.get("status") == "available", "Control Center validation summary missing")
    text = format_control_center_status(status)
    page = render_control_center_html(status)
    assert_true("LLM Structured Output Validation" in text and "LLM Structured Output Validation" in page, "Control Center validation panel missing")
    assert_safe_text(text, "Control Center text")
    assert_safe_text(page, "Control Center HTML")

    for capability_id in VALIDATION_CAPABILITIES:
        capability = get_capability(capability_id)
        assert_true(capability is not None and capability.read_only, f"capability missing or unsafe: {capability_id}")
        resolution = resolve_capability(capability_id)
        assert_true(resolution.resource_id == "eva-llm-router-contracts" and resolution.preview_only, f"resource mapping missing: {capability_id}")
        schema = capability_to_tool_schema(capability_id)
        assert_true(schema is not None and schema.get("execution_status") == "read_only_metadata", f"tool schema missing: {capability_id}")
        assert_true(schema.get("parameters") == [] and schema.get("outputs"), f"tool schema inputs/outputs incomplete: {capability_id}")
        safety_notes = " ".join(str(item) for item in schema.get("safety_notes", [])).lower()
        assert_true("mock/local" in safety_notes and "cannot execute tools" in safety_notes and "rewrite user intent" in safety_notes, f"tool schema safety boundary incomplete: {capability_id}")

    planner_cases = {
        "what happens to malformed LLM output": "llm.validation_policy",
        "how are invalid enum values handled": "llm.validation_policy",
        "how does Eva handle an unknown capability": "llm.validation_policy",
        "how does Eva handle a hallucinated capability": "llm.validation_policy",
        "how does Eva handle secret-like LLM output": "llm.validation_policy",
        "what happens if LLM output requests tool execution": "llm.validation_policy",
        "show LLM repair policy": "llm.repair_policy",
        "show LLM validation readiness": "llm.validation_readiness",
    }
    for question, capability_id in planner_cases.items():
        intents = infer_goal_intents(question)
        selected = select_capabilities_for_goal(question)
        plan = create_task_plan(question)
        assert_true(selected == [capability_id], f"planner selected unsafe/wrong capability for: {question}")
        assert_true(any(step.capability_id == capability_id and step.permission_status in {"allowed", "preview_only"} for step in plan.steps), f"planner step missing: {question}")
        assert_true(all(step.permission_status != "confirmation_required" for step in plan.steps), f"planner requested execution approval: {question}")
        assert_true(intents, f"planner intent missing: {question}")

    review = format_team_review("review malformed LLM output validation boundaries")
    assert_safe_text(review, "team review")
    for boundary in (
        "validation is mock/local only",
        "invalid LLM output cannot execute tools",
        "live LLM calls remain locked",
        "repair does not execute or rewrite user intent",
        "browser/desktop execution remains locked",
        "Phase 12L narrow real create remains a gated write path",
    ):
        assert_true(boundary.lower() in review.lower(), f"team review boundary missing: {boundary}")

    print("PASS: Phase 15C structured-output validation wiring is local, read-only, and non-executing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
