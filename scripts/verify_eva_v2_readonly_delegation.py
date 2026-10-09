from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from backend.eva.core.data_paths import eva_data_dir  # noqa: E402  (traces live wherever the store wrote them)

def emit(case: str, passed: bool, **payload: Any) -> int:
    ok = bool(passed)
    print(json.dumps({"case": case, "pass": ok, **payload}, indent=2, ensure_ascii=False))
    return 0 if ok else 1


def _command_text(command: str) -> str:
    from backend.eva.core.fast_commands import maybe_handle_fast_command
    from backend.eva.tools.registry import ToolRegistry

    handled = maybe_handle_fast_command(command, ToolRegistry(), {})
    return handled[0] if handled else ""


def _execute_state(request: str) -> Any:
    from backend.eva.runtime.graph import run_eva_v2_execute

    return run_eva_v2_execute(request)


def _clean(text: str) -> bool:
    return (
        "{'" not in text
        and "EvaRuntimeState(" not in text
        and "EvaResource(" not in text
        and "Traceback" not in text
        and "BEGIN PRIVATE KEY" not in text
    )


def _refused(text: str, needle: str = "") -> bool:
    return (
        "Eva v2 execution refused" in text
        and "No real action was executed." in text
        and (needle.lower() in text.lower() if needle else True)
        and _clean(text)
    )


def main() -> int:
    failures = 0
    os.environ.setdefault("EVA_PENDING_ACTION_LEDGER_PATH", str(Path(tempfile.mkdtemp(prefix="eva_pending_")) / "pending_actions.jsonl"))

    try:
        from backend.eva.runtime.execution_policy import (
            is_allowlisted_code_readonly_action,
            is_allowlisted_memory_readonly_action,
            is_allowlisted_research_readonly_action,
            is_v2_readonly_action,
        )
        from backend.eva.runtime.feature_flags import get_v2_feature_flags
        from backend.eva.runtime.read_only_delegates import (
            execute_code_readonly_delegate,
            execute_memory_readonly_delegate,
            execute_research_readonly_delegate,
        )
    except Exception as exc:
        failures += emit("modules_import", False, error=str(exc))
        print(json.dumps({"overall_pass": False, "failures": failures}, indent=2))
        return 1

    failures += emit(
        "modules_import",
        callable(is_allowlisted_code_readonly_action)
        and callable(is_allowlisted_research_readonly_action)
        and callable(is_allowlisted_memory_readonly_action)
        and callable(is_v2_readonly_action)
        and callable(execute_code_readonly_delegate)
        and callable(execute_research_readonly_delegate)
        and callable(execute_memory_readonly_delegate),
    )

    flags = get_v2_feature_flags()
    failures += emit(
        "feature_flags_remain_disabled_by_default",
        flags.runtime_enabled is False
        and flags.langgraph_enabled is False
        and flags.llm_guard_enabled is False
        and flags.langfuse_enabled is False
        and flags.vector_memory_enabled is False
        and flags.playwright_enabled is False
        and flags.pyautogui_enabled is False,
        flags=flags.as_dict(),
    )

    code_state = _execute_state("inspect my project structure")
    code_text = code_state.final_response
    failures += emit(
        "code_structure_selects_code_agent_and_executes_readonly",
        code_state.selected_agent == "code"
        and code_state.execution_allowed is True
        and code_state.executed_by == "v2_read_only_delegate:code"
        and is_allowlisted_code_readonly_action(code_state)
        and "Workspace structure summary" in code_text
        and "Executed through v2 read-only delegate." in code_text
        and _clean(code_text),
        state=code_state.as_dict(),
        response=code_text,
    )
    failures += emit(
        "code_structure_summary_not_file_dump",
        "from __future__" not in code_text
        and "def main(" not in code_text
        and "class " not in code_text
        and "Safe source file counts:" in code_text,
        response=code_text,
    )
    failures += emit(
        "code_fallback_skips_sensitive_runtime_paths",
        all(item in code_text for item in (".git", ".venv", "node_modules", ".env*", "data", "models")),
        response=code_text,
    )

    code_status = _command_text("eva v2 execute check code status")
    failures += emit(
        "code_status_executes_readonly",
        "Eva v2 execution result" in code_status
        and "Code status:" in code_status
        and "secrets indexed" in code_status.lower()
        and _clean(code_status),
        response=code_status,
    )

    workspace_skills = _command_text("eva v2 execute summarize workspace skills")
    failures += emit(
        "workspace_skills_summary_executes_readonly",
        "Eva v2 execution result" in workspace_skills
        and "Workspace structure summary" in workspace_skills
        and _clean(workspace_skills),
        response=workspace_skills,
    )

    refused_cases = {
        "eva v2 execute edit backend/eva/runtime/state.py": "file modification",
        "eva v2 execute run powershell dir": "arbitrary shell",
        "eva v2 execute install numpy": "package install",
        "eva v2 execute read .env.local": "secret",
        "eva v2 execute delete memory": "memory delete",
        "eva v2 execute read logged in gmail page": "private",
        "eva v2 execute inspect my repo with GitHub MCP": "mcp execution is disabled",
        "eva v2 execute use playwright to open gmail": "playwright execution is disabled",
    }
    for command, expected in refused_cases.items():
        text = _command_text(command)
        failures += emit(f"refused_{command.replace(' ', '_')[:50]}", _refused(text, expected), response=text)

    pending_cases = {
        "eva v2 execute send WhatsApp to kutty saying hi": "external_message",
        "eva v2 execute click this button": "desktop_control",
    }
    for command, expected in pending_cases.items():
        text = _command_text(command)
        failures += emit(
            f"pending_{command.replace(' ', '_')[:50]}",
            "Eva v2 execution requires confirmation" in text
            and expected in text
            and "Pending action:" in text
            and "No real action was executed." in text
            and _clean(text),
            response=text,
        )

    research_state = _execute_state("search latest AI news")
    research_text = research_state.final_response
    failures += emit(
        "research_public_search_selects_research_agent_and_safe_result",
        research_state.selected_agent == "research"
        and research_state.executed_by == "v2_read_only_delegate:research"
        and research_state.execution_allowed is True
        and is_allowlisted_research_readonly_action(research_state)
        and ("Research public search" in research_text or "Research search unavailable" in research_text)
        and _clean(research_text),
        state=research_state.as_dict(),
        response=research_text,
    )

    research_basics = _command_text("eva v2 execute research LangGraph basics")
    failures += emit(
        "research_topic_lookup_safe_or_unavailable",
        "Eva v2 execution result" in research_basics
        and ("Research" in research_basics)
        and _clean(research_basics),
        response=research_basics,
    )

    memory_status_state = _execute_state("memory status")
    memory_status_text = memory_status_state.final_response
    failures += emit(
        "memory_status_selects_memory_agent_and_summary",
        memory_status_state.selected_agent == "memory"
        and memory_status_state.executed_by == "v2_read_only_delegate:memory"
        and memory_status_state.execution_allowed is True
        and is_allowlisted_memory_readonly_action(memory_status_state)
        and "Memory status:" in memory_status_text
        and "raw rows" not in memory_status_text.lower()
        and _clean(memory_status_text),
        state=memory_status_state.as_dict(),
        response=memory_status_text,
    )

    memory_recall = _command_text("eva v2 execute recall what you remember about Eva")
    failures += emit(
        "memory_recall_summary_or_unavailable",
        "Eva v2 execution result" in memory_recall
        and ("Memory recall" in memory_recall or "Memory store unavailable" in memory_recall)
        and "SELECT " not in memory_recall
        and _clean(memory_recall),
        response=memory_recall,
    )

    phase3_status = _command_text("eva v2 execute resources status")
    phase3_browser = _command_text("eva v2 execute open ChatGPT on Chrome")
    failures += emit("phase3_status_still_executes", "Eva resource registry status" in phase3_status and _clean(phase3_status), response=phase3_status)
    failures += emit("phase3_browser_open_still_allowed_or_clean", ("Eva v2 execution result" in phase3_browser or "Eva v2 execution refused" in phase3_browser) and _clean(phase3_browser), response=phase3_browser)

    trace_state = _execute_state("inspect my project structure")
    trace_path = eva_data_dir("traces") / f"{trace_state.trace_id}.jsonl"
    trace_text = trace_path.read_text(encoding="utf-8") if trace_state.trace_id and trace_path.exists() else ""
    failures += emit(
        "local_trace_redacted_and_readonly_marked",
        bool(trace_text)
        and "v2_read_only_delegate:code" in trace_text
        and '"read_only": true' in trace_text
        and ".env.local" not in trace_text,
        trace_id=trace_state.trace_id,
    )

    source_paths = [
        ROOT / "backend" / "eva" / "runtime" / "execution_bridge.py",
        ROOT / "backend" / "eva" / "runtime" / "execution_policy.py",
        ROOT / "backend" / "eva" / "runtime" / "read_only_delegates.py",
        ROOT / "backend" / "eva" / "agents",
    ]
    source_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace").lower()
        for root in source_paths
        if root.exists()
        for path in ([root] if root.is_file() else root.rglob("*.py"))
    )
    failures += emit("no_env_local_read", "open('.env.local" not in source_text and 'open(".env.local' not in source_text)
    failures += emit("no_package_install_attempt", "pip install" not in source_text)
    failures += emit(
        "no_arbitrary_shell_call",
        "import subprocess" not in source_text
        and "from subprocess" not in source_text
        and "os.system(" not in source_text
        and "shell=true" not in source_text,
    )
    failures += emit("no_mcp_playwright_pyautogui_execution", "run_mcp" not in source_text and "mcp.execute" not in source_text and "playwright_driver." not in source_text and "pyautogui_driver." not in source_text)

    print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
