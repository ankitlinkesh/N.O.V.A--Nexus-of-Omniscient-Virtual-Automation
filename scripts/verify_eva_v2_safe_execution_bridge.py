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

# Intentional fake secret-pattern fixture for execution-trace tests. Not a real secret.


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


def _assert_clean(text: str) -> bool:
    return "{'" not in text and "EvaRuntimeState(" not in text and "Traceback" not in text


def main() -> int:
    failures = 0
    os.environ.setdefault("EVA_PENDING_ACTION_LEDGER_PATH", str(Path(tempfile.mkdtemp(prefix="eva_pending_")) / "pending_actions.jsonl"))

    try:
        from backend.eva.runtime.execution_bridge import execute_v2_allowlisted_action
        from backend.eva.runtime.execution_policy import (
            evaluate_v2_execution_allowed,
            is_v2_execution_command,
            normalize_v2_execute_request,
        )
        from backend.eva.runtime.feature_flags import get_v2_feature_flags
        from backend.eva.runtime.graph import run_eva_v2_execute
    except Exception as exc:
        failures += emit("v2_safe_execution_modules_import", False, error=str(exc))
        print(json.dumps({"overall_pass": False, "failures": failures}, indent=2))
        return 1

    failures += emit(
        "v2_safe_execution_modules_import",
        callable(execute_v2_allowlisted_action)
        and callable(evaluate_v2_execution_allowed)
        and is_v2_execution_command("eva v2 execute resources status")
        and normalize_v2_execute_request("eva v2 run resources status") == "resources status",
    )

    flags = get_v2_feature_flags()
    failures += emit(
        "feature_flags_remain_disabled_by_default",
        flags.runtime_enabled is False
        and flags.langgraph_enabled is False
        and flags.playwright_enabled is False
        and flags.pyautogui_enabled is False,
        flags=flags.as_dict(),
    )

    status_cases = {
        "eva v2 execute resources status": "Eva resource registry status",
        "eva v2 execute mcp status": "MCP policy status",
        "eva v2 execute resource detail github-mcp-server": "github-mcp-server",
        "eva v2 run open source tools status": "Open-source tool catalog",
    }
    for command, expected in status_cases.items():
        text = _command_text(command)
        failures += emit(
            f"allowed_status_{command.replace(' ', '_')[:42]}",
            "Eva v2 execution result" in text
            and expected in text
            and "Executed through existing Eva status command handler." in text
            and _assert_clean(text),
            response=text,
        )

    import backend.eva.browser.skills as browser_skills

    calls: list[str] = []
    original_chrome_open_web_app = browser_skills.chrome_open_web_app

    def fake_chrome_open_web_app(app: str) -> dict[str, Any]:
        calls.append(app)
        return {"ok": True, "message": f"Done, {app} is open in Chrome.", "app": app, "verified": False}

    browser_skills.chrome_open_web_app = fake_chrome_open_web_app  # type: ignore[assignment]
    try:
        chatgpt_state = run_eva_v2_execute("open ChatGPT on Chrome")
        chatgpt_text = chatgpt_state.final_response
    finally:
        browser_skills.chrome_open_web_app = original_chrome_open_web_app  # type: ignore[assignment]

    failures += emit(
        "browser_open_classified_and_delegated_without_playwright",
        calls == ["chatgpt"]
        and chatgpt_state.selected_agent == "browser"
        and chatgpt_state.execution_allowed is True
        and chatgpt_state.executed_by == "eva-chrome-execution-skills"
        and "Eva v2 execution result" in chatgpt_text
        and "Done, chatgpt is open in Chrome." in chatgpt_text
        and _assert_clean(chatgpt_text),
        calls=calls,
        response=chatgpt_text,
        state=chatgpt_state.as_dict(),
    )

    refused_cases = {
        "eva v2 execute read .env.local": "blocked",
        "eva v2 execute inspect my repo with GitHub MCP": "mcp execution is disabled",
        "eva v2 execute run powershell dir": "arbitrary shell is blocked",
    }
    for command, expected_reason in refused_cases.items():
        text = _command_text(command)
        failures += emit(
            f"refused_{command.replace(' ', '_')[:46]}",
            "Eva v2 execution refused" in text
            and expected_reason.lower() in text.lower()
            and "No real action was executed." in text
            and _assert_clean(text),
            response=text,
        )

    pending_cases = {
        "eva v2 execute send WhatsApp to mom saying hi": ("Eva v2 execution requires confirmation", "external_message"),
        "eva v2 execute delete Downloads folder": ("Eva v2 execution requires override", "destructive_file_action"),
        "eva v2 execute click this button": ("Eva v2 execution requires confirmation", "desktop_control"),
    }
    for command, (header, risk) in pending_cases.items():
        text = _command_text(command)
        failures += emit(
            f"pending_{command.replace(' ', '_')[:46]}",
            header in text
            and risk in text
            and "Pending action:" in text
            and "No real action was executed." in text
            and _assert_clean(text),
            response=text,
        )

    trace_state = run_eva_v2_execute("resources status")
    trace_id = trace_state.trace_id
    trace_path = eva_data_dir("traces") / f"{trace_id}.jsonl"
    trace_text = trace_path.read_text(encoding="utf-8") if trace_id and trace_path.exists() else ""
    redacted_state = run_eva_v2_execute("resources status with token ghp_abcdefghijklmnopqrstuvwxyz1234567890")
    redacted_path = eva_data_dir("traces") / f"{redacted_state.trace_id}.jsonl"
    redacted_text = redacted_path.read_text(encoding="utf-8") if redacted_state.trace_id and redacted_path.exists() else ""
    failures += emit(
        "local_trace_written_and_redacted",
        bool(trace_text)
        and "v2_execute" in trace_text
        and "execution_allowed" in trace_text
        and "ghp_abcdefghijklmnopqrstuvwxyz1234567890" not in redacted_text
        and "[REDACTED_TOKEN]" in redacted_text,
        trace_id=trace_id,
        redacted_trace_id=redacted_state.trace_id,
    )

    source_paths = [
        ROOT / "backend" / "eva" / "runtime" / "execution_bridge.py",
        ROOT / "backend" / "eva" / "runtime" / "execution_policy.py",
        ROOT / "backend" / "eva" / "runtime" / "nodes.py",
        ROOT / "backend" / "eva" / "runtime" / "graph.py",
    ]
    source_text = "\n".join(path.read_text(encoding="utf-8", errors="replace").lower() for path in source_paths if path.exists())
    failures += emit("no_playwright_driver_call", "playwright_driver" not in source_text and "playwright." not in source_text)
    failures += emit("no_pyautogui_driver_call", "pyautogui_driver" not in source_text and "pyautogui." not in source_text)
    failures += emit("no_mcp_execution_call", "run_mcp" not in source_text and "mcp.execute" not in source_text)
    failures += emit("no_env_local_read", "open('.env.local" not in source_text and 'open(".env.local' not in source_text)
    failures += emit("no_package_install_attempt", "pip install" not in source_text and "subprocess" not in source_text)

    print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
