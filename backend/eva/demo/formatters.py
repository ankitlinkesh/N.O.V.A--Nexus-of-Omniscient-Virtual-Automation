from __future__ import annotations

from .scenarios import DemoScenario


def format_scenario_summary(scenario: DemoScenario) -> str:
    return f"- {scenario.scenario_id}: {scenario.title} ({scenario.safety_decision})"


def format_scenario_run(scenario: DemoScenario) -> str:
    lines = [
        f"Eva demo scenario: {scenario.title}",
        "",
        "Demo mode: no real action executed.",
        f"Scenario id: {scenario.scenario_id}",
        f"Fake user request: {scenario.fake_user_request}",
        f"Expected intent: {scenario.expected_intent}",
        f"Selected agent: {scenario.selected_agent}",
        f"Safety decision: {scenario.safety_decision}",
        f"Resource decision: {scenario.resource_decision}",
        "",
        "Proposed plan:",
    ]
    lines.extend(f"- {step}" for step in scenario.proposed_plan)
    lines.extend(["", f"Final simulated result: {scenario.final_result}"])
    return "\n".join(lines)
