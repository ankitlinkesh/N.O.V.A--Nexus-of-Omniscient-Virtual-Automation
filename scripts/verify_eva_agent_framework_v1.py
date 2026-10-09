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


def emit(case: str, passed: bool, **payload: Any) -> int:
    ok = bool(passed)
    print(json.dumps({"case": case, "pass": ok, **payload}, indent=2, ensure_ascii=False))
    return 0 if ok else 1


def clean_output(text: str) -> bool:
    blocked = (
        "{'",
        "EvaAgentRequest(",
        "EvaAgentResponse(",
        "EvaAgent(",
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


def main() -> int:
    failures = 0
    try:
        from backend.eva.agents.contracts import EvaAgentRequest, EvaAgentResponse
        from backend.eva.agents.delegation import dry_run_plan_with_agents, format_agent_dry_run_result
        from backend.eva.agents.registry import (
            find_agents_for_capability,
            format_agent_capability_matrix,
            format_agent_detail,
            format_agents_status,
            get_agent,
            get_all_agents,
            list_agent_names,
            select_agent_for_step,
        )
        from backend.eva.agents.status import format_agent_framework_status
        from backend.eva.core.fast_commands import maybe_handle_fast_command
        from backend.eva.planner.decomposer import create_task_plan
        from backend.eva.tools.registry import ToolRegistry
    except Exception as exc:
        failures += emit("agent_framework_modules_import", False, error=str(exc))
        print(json.dumps({"overall_pass": False, "failures": failures}, indent=2))
        return 1

    failures += emit("agent_framework_modules_import", True)
    agents = get_all_agents()
    names = list_agent_names()
    failures += emit("registry_non_empty", bool(agents), names=names)
    for expected in ("ResearchAgent", "SafetyAgent", "BrowserAgent", "DesktopAgent"):
        failures += emit(f"{expected.lower()}_registered", get_agent(expected) is not None, names=names)

    browser = get_agent("BrowserAgent")
    desktop = get_agent("DesktopAgent")
    safety = get_agent("SafetyAgent")
    research = get_agent("ResearchAgent")
    request = EvaAgentRequest(
        request_id="req_test",
        user_goal="open ChatGPT on Chrome",
        task_step_id="step_1",
        capability_id="browser.control",
        resource_id=None,
        input_summary="open ChatGPT on Chrome",
        context={},
        dry_run=True,
        execution_allowed=False,
    )
    browser_execute = browser.execute(request) if browser else None
    desktop_execute = desktop.execute(request) if desktop else None
    failures += emit(
        "browser_and_desktop_execute_disabled",
        isinstance(browser_execute, EvaAgentResponse)
        and isinstance(desktop_execute, EvaAgentResponse)
        and browser_execute.status == "refused"
        and desktop_execute.status == "refused"
        and not browser_execute.details.get("execution_enabled", True)
        and not desktop_execute.details.get("execution_enabled", True),
        browser=browser_execute.as_dict() if browser_execute else None,
        desktop=desktop_execute.as_dict() if desktop_execute else None,
    )

    status_text = format_agents_status()
    detail_text = format_agent_detail("ResearchAgent")
    framework_text = format_agent_framework_status()
    matrix_text = format_agent_capability_matrix()
    failures += emit(
        "status_and_detail_human_readable",
        all(clean_output(text) for text in (status_text, detail_text, framework_text, matrix_text))
        and "ResearchAgent" in status_text
        and "execution disabled" in framework_text.lower(),
        status=status_text,
        detail=detail_text,
    )

    lifecycle = ("plan", "dry_run", "execute", "observe", "verify", "rollback", "explain")
    failures += emit(
        "all_agents_expose_lifecycle",
        all(all(hasattr(agent, method) for method in lifecycle) for agent in agents),
        agents=[type(agent).__name__ for agent in agents],
    )

    dry_request = EvaAgentRequest(
        request_id="req_research",
        user_goal="use my saved research about Eva",
        task_step_id="step_1",
        capability_id="research_memory.retrieve",
        resource_id="eva-research-memory-v2",
        input_summary="use my saved research about Eva",
        context={},
        dry_run=True,
        execution_allowed=False,
    )
    research_dry = research.dry_run(dry_request) if research else None
    safety_dry = safety.dry_run(dry_request) if safety else None
    failures += emit(
        "dry_run_returns_structured_response",
        isinstance(research_dry, EvaAgentResponse)
        and isinstance(safety_dry, EvaAgentResponse)
        and research_dry.status == "dry_run"
        and safety_dry.status == "dry_run",
        research=research_dry.as_dict() if research_dry else None,
    )

    saved_plan = create_task_plan("use my saved research about Eva")
    saved_result = dry_run_plan_with_agents(saved_plan)
    saved_text = format_agent_dry_run_result(saved_result)
    failures += emit(
        "dry_run_plan_saved_research_selects_research_agent",
        any(item.agent_name == "ResearchAgent" for item in saved_result.responses)
        and clean_output(saved_text)
        and "ResearchAgent" in saved_text,
        output=saved_text,
    )

    whatsapp_plan = create_task_plan("send WhatsApp to mom saying hi")
    whatsapp_result = dry_run_plan_with_agents(whatsapp_plan)
    whatsapp_text = format_agent_dry_run_result(whatsapp_result)
    failures += emit(
        "dry_run_plan_whatsapp_marks_confirmation_or_refusal",
        any(item.agent_name == "SafetyAgent" for item in whatsapp_result.responses)
        and ("confirmation" in whatsapp_text.lower() or "refused" in whatsapp_text.lower())
        and clean_output(whatsapp_text),
        output=whatsapp_text,
    )

    delete_plan = create_task_plan("delete Downloads folder")
    delete_result = dry_run_plan_with_agents(delete_plan)
    delete_text = format_agent_dry_run_result(delete_result)
    failures += emit(
        "dry_run_plan_delete_blocked_override_no_execution",
        ("override" in delete_text.lower() or "blocked" in delete_text.lower())
        and "No task was executed" in delete_text,
        output=delete_text,
    )

    failures += emit("find_agents_for_capability_works", bool(find_agents_for_capability("research_memory.retrieve")))
    failures += emit("select_agent_for_step_works", select_agent_for_step(saved_plan.steps[1]) is not None)

    tools = ToolRegistry()
    command_cases = {
        "eva agents status": "Agent Framework",
        "eva agents": "Registered agents",
        "eva agent list": "Registered agents",
        "eva agent ResearchAgent": "ResearchAgent",
        "eva agent capabilities ResearchAgent": "Capabilities",
        "eva agents matrix": "Agent capability matrix",
        "eva agent framework status": "Agent Framework v1",
        "eva agents dry run plan use my saved research about Eva": "ResearchAgent",
        "eva agent explain BrowserAgent": "BrowserAgent",
    }
    for command, expected in command_cases.items():
        handled = maybe_handle_fast_command(command, tools, {})
        text = handled[0] if handled else ""
        failures += emit(
            f"command_{re.sub(r'[^a-z0-9]+', '_', command.lower()).strip('_')}",
            handled is not None and expected.lower() in text.lower() and clean_output(text),
            output=text,
        )

    agent_root = ROOT / "backend" / "eva" / "agents"
    from _source_guard import (
        BROWSER_DRIVER_MODULES, SHELL_CALLS, SHELL_MODULES, no_browser_secret_reads, no_env_local_read, scan,
    )

    # Real imports/calls only, not words in prose.
    found = scan([agent_root], modules=SHELL_MODULES + BROWSER_DRIVER_MODULES + ("mcp",), calls=SHELL_CALLS)[0]
    found += no_env_local_read([agent_root])[0] + no_browser_secret_reads([agent_root])[0]
    failures += emit("agent_framework_no_forbidden_execution_imports", not found, found=[str(f) for f in found])

    nested_scripts = [
        "verify_eva_planner_v3_quality.py",
        "verify_eva_planner_v3.py",
        "verify_eva_capability_resource_mapping.py",
        "verify_eva_capability_permissions.py",
        "verify_eva_stabilization_v1.py",
    ]
    # Inside verify_eva_all each of these runs at top level (test_verify_all_nested_coverage
    # proves it), so re-running them here only multiplied the suite time past the timeout.
    if os.environ.get("EVA_VERIFY_SKIP_NESTED") == "1":
        for script_name in nested_scripts:
            failures += emit(f"nested_{script_name}", True, skipped=True, reason="Runs at top level of the master verifier.")
    else:
        for script_name in nested_scripts:
            ok, output = run_nested(script_name)
            failures += emit(f"nested_{script_name}", ok, tail=output)

    print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
