from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.eva.agent.policies import is_agentic_intent
from backend.eva.core.config import load_local_env
from backend.eva.core.fast_commands import maybe_handle_fast_command
from backend.eva.core.fast_responses import maybe_handle_fast_response


class DryTools:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run(self, name: str, **kwargs: object) -> object:
        self.calls.append({"tool": name, "args": kwargs})
        if name == "system_status":
            return {"os_name": "Windows 11", "shell": "dry-shell"}
        if name == "open_app":
            return f"Opening {kwargs.get('app_name') or kwargs.get('app')}."
        return {"ok": True, "tool": name, "args": kwargs}


def case(name: str, passed: bool, payload: dict[str, Any]) -> int:
    print(json.dumps({"case": name, "pass": passed, **payload}, indent=2, ensure_ascii=False))
    return 0 if passed else 1


def timed_fast_response(message: str) -> tuple[tuple[str, str] | None, float]:
    started = time.perf_counter()
    result = maybe_handle_fast_response(message)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return result, elapsed_ms


def main() -> int:
    load_local_env(ROOT / ".env")
    failures = 0

    expected_casual = {
        "heyy howdy": "Yo Ankit, I'm here. What's the move?",
        "yo": "Yo Ankit, I'm here. What's the move?",
        "how are you": "Running smooth. What are we working on?",
        "thanks": "Got you.",
        "eva": "Yeah Ankit?",
    }
    for message, expected in expected_casual.items():
        result, elapsed_ms = timed_fast_response(message)
        passed = result is not None and result[0] == expected and result[1] == "fast-casual" and elapsed_ms < 100
        failures += case(
            f"casual_{message}",
            passed,
            {
                "reply": result[0] if result else None,
                "source": result[1] if result else None,
                "elapsed_ms": round(elapsed_ms, 3),
                "llm_called": False,
            },
        )

    dry_tools = DryTools()
    status = maybe_handle_fast_command("status", dry_tools)
    failures += case(
        "status_still_deterministic",
        status is not None and status[1] == "fast-command" and "Laptop is reachable" in status[0],
        {"result": status},
    )

    identity = maybe_handle_fast_command("who are you", dry_tools)
    failures += case(
        "who_are_you_still_deterministic",
        identity is not None and identity[1] == "fast-command" and "your local agent" in identity[0],
        {"result": identity},
    )

    about_me = maybe_handle_fast_command("what do u know abt me", dry_tools)
    failures += case(
        "about_me_uses_local_profile",
        about_me is not None
        and about_me[1] == "fast-command"
        and "Ankit" in about_me[0]
        and "SQLite" in about_me[0]
        and "stateless" not in about_me[0].lower(),
        {"result": about_me},
    )

    local_sqlite = maybe_handle_fast_command("u can store it locally in SQLite local right?", dry_tools)
    failures += case(
        "sqlite_memory_question_is_deterministic",
        local_sqlite is not None
        and local_sqlite[1] == "fast-command"
        and "SQLite" in local_sqlite[0]
        and "not a stateless cloud bot" in local_sqlite[0],
        {"result": local_sqlite},
    )

    agent_status = maybe_handle_fast_command("agent status", dry_tools)
    failures += case(
        "agent_status_is_deterministic",
        agent_status is not None
        and agent_status[1] == "fast-command"
        and "Agentic v2" in agent_status[0]
        and "arbitrary shell is blocked" in agent_status[0],
        {"result": agent_status},
    )

    dry_tools = DryTools()
    open_chrome = maybe_handle_fast_command("open chrome", dry_tools)
    failures += case(
        "open_chrome_uses_tool_layer",
        open_chrome is not None and open_chrome[1] == "desktop-tool" and dry_tools.calls and dry_tools.calls[0]["tool"] == "open_app",
        {"result": open_chrome, "tool_calls": dry_tools.calls},
    )

    dry_tools = DryTools()
    mistral = maybe_handle_fast_command("use mistral for fallback", dry_tools)
    failures += case(
        "use_mistral_fast_command_no_llm",
        mistral is not None and mistral[1] == "fast-command" and "Mistral" in mistral[0] and not dry_tools.calls,
        {"result": mistral, "tool_calls": dry_tools.calls},
    )

    failures += case(
        "casual_does_not_trigger_agent_mode",
        not is_agentic_intent("heyy howdy") and not is_agentic_intent("how are you"),
        {"heyy_howdy_agentic": is_agentic_intent("heyy howdy"), "how_are_you_agentic": is_agentic_intent("how are you")},
    )

    failures += case(
        "explicit_agent_mode_still_triggers",
        is_agentic_intent("agent mode: say hello in one sentence")
        and is_agentic_intent("find and summarize best github repos for AI agents")
        and is_agentic_intent("research wake word setup"),
        {
            "agent_mode_agentic": is_agentic_intent("agent mode: say hello in one sentence"),
            "find_and_summarize_agentic": is_agentic_intent("find and summarize best github repos for AI agents"),
            "research_agentic": is_agentic_intent("research wake word setup"),
        },
    )

    print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
