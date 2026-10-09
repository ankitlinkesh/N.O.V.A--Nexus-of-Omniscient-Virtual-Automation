from __future__ import annotations

import importlib
import json
import os
import sys
from types import SimpleNamespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def emit(case: str, passed: bool, **extra: object) -> int:
    payload = {"case": case, "pass": bool(passed), **extra}
    print(json.dumps(payload, indent=2, default=str))
    return 0 if passed else 1


def clean_output(text: object) -> bool:
    value = str(text)
    blocked = [
        "{'",
        "FileUnderstanding(",
        "ProjectInventory(",
        "ProjectInventoryItem(",
        "Traceback",
        "sqlite3.Row",
        "C:\\",
        str(ROOT),
        "sk-",
        "ghp_",
        "Bearer ",
    ]
    return not any(marker in value for marker in blocked)


def command_text(command: str) -> str:
    from backend.eva.core.fast_commands import maybe_handle_fast_command

    result = maybe_handle_fast_command(command, tools=None, memory=None)
    if result is None:
        return ""
    return str(result[0])


from _nested import run_nested as _shared_run_nested  # noqa: E402


def run_verifier(script_name: str) -> tuple[bool, str]:
    # Shared runner: UTF-8 output, one level deep, one timeout (scripts/_nested.py).
    return _shared_run_nested(script_name)


def main() -> int:
    failures = 0

    modules = [
        "backend.eva.file_agent.understanding",
        "backend.eva.file_agent.project_inventory",
    ]
    imported: list[str] = []
    try:
        for module_name in modules:
            imported.append(importlib.import_module(module_name).__name__)
        failures += emit("understanding_modules_import", True, imported=imported)
    except Exception as exc:
        failures += emit("understanding_modules_import", False, error=str(exc), imported=imported)
        print(json.dumps({"overall_pass": False, "failures": failures}))
        return 1

    from backend.eva.agents.registry import select_agent_for_step
    from backend.eva.agents.team_review import review_plan_with_agent_team
    from backend.eva.capabilities.registry import build_default_registry
    from backend.eva.capabilities.resource_mapping import resolve_capability
    from backend.eva.capabilities.tool_schemas import capability_to_tool_schema
    from backend.eva.file_agent.inspector import explain_project, understand_file
    from backend.eva.file_agent.project_inventory import build_project_inventory
    from backend.eva.file_agent.understanding import (
        detect_config_type,
        detect_file_purpose,
        extract_headings,
        extract_imports_or_dependencies,
        summarize_markdown_file,
        summarize_text_content,
    )
    from backend.eva.planner.capability_selector import select_capabilities_for_goal
    from backend.eva.planner.decomposer import create_task_plan

    status_output = command_text("eva file status")
    failures += emit(
        "file_status_mentions_understanding_inventory",
        all(marker in status_output.lower() for marker in ["read-only", "understanding", "project inventory", "no cloud"]),
        output=status_output,
    )

    sample_md = "# Title\n\n- local agent\n- safe file review\n\nTODO: keep this read-only"
    summary = summarize_text_content(sample_md, filename="README.md")
    markdown = summarize_markdown_file(sample_md, filename="README.md")
    failures += emit("text_summary_heuristic", "summary" in summary and clean_output(json.dumps(summary)), summary=summary)
    failures += emit("markdown_headings_detected", "Title" in extract_headings(sample_md), markdown=markdown)
    failures += emit("dependency_detection_python", "os" in extract_imports_or_dependencies("import os\nfrom pathlib import Path\n", "x.py"), imports=extract_imports_or_dependencies("import os\nfrom pathlib import Path\n", "x.py"))
    failures += emit("config_type_detected", detect_config_type("pyproject.toml") == "Python project configuration")
    failures += emit("file_purpose_detected", "documentation" in detect_file_purpose("README.md", sample_md).lower())

    understand_readme = command_text("eva file understand README.md")
    summarize_planner = command_text("eva file summarize docs/EVA_PLANNER.md")
    blocked_env = command_text("eva file understand .env.local")
    blocked_db = command_text("eva file summarize backend/eva/data/research_memory/research_memory.sqlite3")
    failures += emit("fast_file_understand_readme", "file understanding" in understand_readme.lower() and clean_output(understand_readme), output=understand_readme[:1200])
    failures += emit("fast_file_summarize_planner", "file understanding" in summarize_planner.lower() and "heuristic" in summarize_planner.lower() and clean_output(summarize_planner), output=summarize_planner[:1200])
    failures += emit("fast_file_understand_env_refused", "refused" in blocked_env.lower() and ".env.local" in blocked_env and clean_output(blocked_env), output=blocked_env)
    failures += emit("fast_file_summarize_runtime_refused", "refused" in blocked_db.lower() and clean_output(blocked_db), output=blocked_db)

    direct_understand = understand_file("docs/EVA_PLANNER.md")
    failures += emit("direct_understand_file_ok", getattr(direct_understand, "ok", False) and clean_output(direct_understand), result=direct_understand)

    inventory_output = command_text("eva project inventory")
    explain_output = command_text("eva project explain")
    missing_output = command_text("eva project missing")
    dependencies_output = command_text("eva project dependencies")
    key_files_output = command_text("eva project key files")
    blocked_drive_inventory = command_text("eva project inventory C:\\Users\\HP")
    failures += emit("fast_project_inventory_human", "project inventory" in inventory_output.lower() and "key files" in inventory_output.lower() and clean_output(inventory_output), output=inventory_output[:1500])
    failures += emit("fast_project_explain_human", "project explanation" in explain_output.lower() and "project type" in explain_output.lower() and clean_output(explain_output), output=explain_output[:1500])
    failures += emit("fast_project_missing_human", "missing" in missing_output.lower() and clean_output(missing_output), output=missing_output[:1200])
    failures += emit("fast_project_dependencies_human", "dependencies" in dependencies_output.lower() and clean_output(dependencies_output), output=dependencies_output[:1200])
    failures += emit("fast_project_key_files_human", "key files" in key_files_output.lower() and clean_output(key_files_output), output=key_files_output[:1200])
    failures += emit("project_inventory_outside_repo_refused", "refused" in blocked_drive_inventory.lower() and clean_output(blocked_drive_inventory), output=blocked_drive_inventory)

    inventory = build_project_inventory(".")
    inventory_text = str(inventory)
    failures += emit("inventory_skips_runtime_dirs", "backend/eva/data" not in inventory_text.replace("\\", "/"), total=getattr(inventory, "total_items", None))
    failures += emit("inventory_detects_common_files", any(path.endswith("README.md") for path in getattr(inventory, "key_files", {}).get("docs", [])) or "README.md" in inventory_text, inventory=inventory)

    project = explain_project(".")
    failures += emit("direct_project_explain_ok", getattr(project, "ok", False) and clean_output(project), result=project)

    file_agent_explain = command_text("eva agent explain FileAgent")
    failures += emit("file_agent_explain_no_writes", all(marker in file_agent_explain.lower() for marker in ["writes", "edits", "deletes", "not enabled"]) and clean_output(file_agent_explain), output=file_agent_explain[:1200])

    caps = select_capabilities_for_goal("what is this project?")
    cap_ids = [str(cap) for cap in caps]
    failures += emit("planner_project_goal_selects_file_capability", any(cap_id.startswith("file.project") for cap_id in cap_ids), capabilities=cap_ids)

    selected_agent = select_agent_for_step(SimpleNamespace(capability_id="file.project_inventory", step_type="project_understanding", agent=None, title="", description="", input_summary="", notes=""))
    failures += emit("agent_selection_project_inventory_file_agent", selected_agent is not None and selected_agent.name in {"file", "code"}, agent=type(selected_agent).__name__ if selected_agent else None)

    review = review_plan_with_agent_team(create_task_plan("explain this repo"))
    review_text = " ".join(f.reviewer for f in review.findings)
    failures += emit("team_review_explain_repo_assigns_file_or_code", "FileAgent" in review_text or "CodeAgent" in review_text, agents=sorted({f.reviewer for f in review.findings}))

    registry = build_default_registry()
    failures += emit("capability_registry_project_inventory", registry.get("file.project_inventory") is not None)
    resolution = resolve_capability("file.project_inventory")
    failures += emit("resource_mapping_project_inventory", resolution.resource_id == "eva-file-agent-v1" and resolution.agent == "FileAgent", resolution=resolution.as_dict())
    failures += emit("tool_schema_understand_inventory", capability_to_tool_schema("file.understand_text") is not None and capability_to_tool_schema("file.project_inventory") is not None)

    source_files = [
        ROOT / "backend" / "eva" / "file_agent" / "understanding.py",
        ROOT / "backend" / "eva" / "file_agent" / "project_inventory.py",
        ROOT / "backend" / "eva" / "file_agent" / "inspector.py",
    ]
    source_text = "\n".join(path.read_text(encoding="utf-8") for path in source_files if path.exists()).lower()
    forbidden = [
        "subprocess.",
        "os.system",
        "popen(",
        "import playwright",
        "import pyautogui",
        "from playwright",
        "from pyautogui",
        "import mcp",
        "from mcp",
        ".env.local).read",
    ]
    failures += emit("no_forbidden_execution_imports", not any(marker in source_text for marker in forbidden))

    nested_scripts = [
        "scripts/verify_eva_file_agent_readonly.py",
        "scripts/verify_eva_agent_framework_quality.py",
        "scripts/verify_eva_planner_v3_quality.py",
        "scripts/verify_eva_capability_resource_mapping.py",
        "scripts/verify_eva_stabilization_v1.py",
    ]
    if os.environ.get("EVA_VERIFY_SKIP_NESTED") == "1":
        for script in nested_scripts:
            failures += emit(f"nested_{Path(script).name}", True, skipped=True, reason="Skipped inside master verifier profile.")
    else:
        for script in nested_scripts:
            ok, tail = run_verifier(script)
            failures += emit(f"nested_{Path(script).name}", ok, tail=tail)

    overall = failures == 0
    print(json.dumps({"overall_pass": overall, "failures": failures}, indent=2))
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
