from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.eva.agent.policies import describe_tool_observation
from backend.eva.core.fast_commands import maybe_handle_fast_command
from backend.eva.core.web_context import remember_web_results


MOCK_TAVILY = {
    "ok": True,
    "provider": "tavily",
    "query": "best github repos for AI agents",
    "answer": "Several open-source AI agent frameworks are popular.",
    "results": [
        {
            "title": "GitHub - microsoft/autogen",
            "url": "https://github.com/microsoft/autogen",
            "content": "A framework for multi-agent AI applications.",
            "score": 0.95,
        },
        {
            "title": "Ankit L on Instagram",
            "url": "https://www.instagram.com/example_ankit_l/",
            "content": "Instagram profile result.",
            "score": 0.9,
        },
        {
            "title": "GitHub - langchain-ai/langgraph",
            "url": "https://github.com/langchain-ai/langgraph",
            "content": "Build stateful agents as graphs.",
            "score": 0.88,
        },
    ],
}


class FakeTools:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run(self, name: str, **kwargs: Any) -> Any:
        self.calls.append((name, kwargs))
        if name == "open_url":
            return f"Opening {kwargs.get('url')}."
        if name == "analyze_screen":
            return {"ok": True, "summary": "A browser window is open.", "suggested_actions": ["Continue from the active tab."]}
        if name == "capture_screen":
            return {"image_path": "mock.jpg", "note": "mock capture"}
        if name == "web_search":
            return MOCK_TAVILY
        if name == "system_status":
            return {"os_name": "Windows 11", "shell": "PowerShell"}
        raise AssertionError(f"Unexpected tool call: {name}")


def emit(case: str, passed: bool, **payload: Any) -> int:
    print(json.dumps({"case": case, "pass": passed, **payload}, indent=2, ensure_ascii=False))
    return 0 if passed else 1


def _opened_then_verified(calls: list, url: str) -> bool:
    # The open is followed by a verify_last_action check (honest effects); nothing
    # else may run, and the open must be the one URL that was asked for.
    return bool(calls) and calls[0] == ("open_url", {"url": url}) and all(name == "verify_last_action" for name, _ in calls[1:])


def main() -> int:
    failures = 0

    context: dict[str, Any] = {}
    remember_web_results(context, MOCK_TAVILY)

    tools = FakeTools()
    reply = maybe_handle_fast_command("open first result", tools, context)
    failures += emit(
        "open_first_result",
        bool(reply and _opened_then_verified(tools.calls, "https://github.com/microsoft/autogen")),
        reply=reply,
        calls=tools.calls,
    )

    tools = FakeTools()
    reply = maybe_handle_fast_command("open the instagram one", tools, context)
    failures += emit(
        "open_instagram_result",
        bool(reply and _opened_then_verified(tools.calls, "https://www.instagram.com/example_ankit_l/")),
        reply=reply,
        calls=tools.calls,
    )

    old_profile = os.environ.pop("EVA_PROFILE_URL", None)
    try:
        tools = FakeTools()
        reply = maybe_handle_fast_command("open my profile", tools, {})
        failures += emit(
            "profile_missing_does_not_hallucinate",
            bool(reply and "don't have your profile URL saved" in reply[0] and not tools.calls),
            reply=reply,
            calls=tools.calls,
        )
    finally:
        if old_profile is not None:
            os.environ["EVA_PROFILE_URL"] = old_profile

    tools = FakeTools()
    reply = maybe_handle_fast_command("show screen", tools, {})
    failures += emit(
        "show_screen_uses_analyze_screen",
        bool(reply and tools.calls[-1][0] == "analyze_screen"),
        reply=reply,
        calls=tools.calls,
    )

    observation = describe_tool_observation("web_search", MOCK_TAVILY)
    failures += emit(
        "agent_web_observation_summarizes_results",
        "observed 5 Tavily results" not in observation and "microsoft/autogen" in observation and "Want me to open one" in observation,
        observation=observation,
    )

    print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
