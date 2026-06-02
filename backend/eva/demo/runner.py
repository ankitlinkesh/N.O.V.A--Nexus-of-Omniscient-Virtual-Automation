from __future__ import annotations

from .formatters import format_scenario_run, format_scenario_summary
from .scenarios import get_demo_scenario, list_demo_scenarios


def format_demo_scenarios() -> str:
    lines = [
        "Eva demo scenarios",
        "",
        "Demo mode: no real action executed.",
        "Available scenarios:",
    ]
    lines.extend(format_scenario_summary(scenario) for scenario in list_demo_scenarios())
    lines.append("")
    lines.append("Run one with `eva demo run <scenario_id>`.")
    return "\n".join(lines)


def format_demo_run(scenario_id: str) -> str:
    scenario = get_demo_scenario(scenario_id)
    if scenario is None:
        known = ", ".join(s.scenario_id for s in list_demo_scenarios())
        return f"Eva demo scenario not found: {scenario_id}. Available scenarios: {known}."
    return format_scenario_run(scenario)
