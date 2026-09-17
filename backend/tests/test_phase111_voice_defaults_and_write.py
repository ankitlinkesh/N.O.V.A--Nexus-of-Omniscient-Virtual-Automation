"""Phase 111: two of Phase 110's disclosed gaps, fixed.

1. `verify_voice_ui.py` was red. Two of its checks pinned designs the project
   had deliberately replaced (the female voice list, the "Eva" label). The third
   was real: `clampNumber(localStorage.getItem(...))` read a MISSING setting as
   0, because `Number(null)` is 0, so any browser without saved voice settings
   clamped rate, pitch and volume to their minimums -- measured live as
   `rate 0.85, pitch 0.9, volume 0.4` -- and NOVA spoke at 40% volume. The
   backend also defaulted the rate to 2.35, above the UI's 1.25 maximum.
2. Typing unlocked only on the word "type". "write" and "enter" now do too, but
   only with a quoted string or "into", so "write me an email and save it" does
   not put a keyboard in front of the model. The exact-words rule is unchanged.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.eva.agent import runner as runner_module
from backend.eva.agent.executor import ToolExecutor
from backend.eva.agent.planner import PlannedToolCall, PlannerDecision
from backend.eva.agent.runner import run_agentic_task
from backend.eva.desktop import verifier as desktop_verifier
from backend.eva.desktop.windows import WindowInfo
from backend.eva.screen.type_grant import user_asked_to_type
from backend.eva.security import tool_gate
from backend.eva.tools.registry import ToolRegistry

ROOT = Path(__file__).resolve().parents[2]
APP_JS = ROOT / "frontend" / "app.js"


# --- voice defaults ------------------------------------------------------------


def _clamp(value, fallback, lo, hi):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    source = APP_JS.read_text(encoding="utf-8")
    start = source.index("function clampNumber(")
    end = source.index("\n}\n", start) + 3
    script = source[start:end] + f"\nprocess.stdout.write(JSON.stringify(clampNumber({json.dumps(value)}, {fallback}, {lo}, {hi})));"
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30, check=True)
    return json.loads(out.stdout)


@pytest.mark.parametrize(("value", "expected"), [(None, 1.08), ("", 1.08), ("0.95", 0.95), ("9", 1.25), ("abc", 1.08)])
def test_a_missing_voice_setting_falls_back_to_the_default_not_the_minimum(value, expected):
    assert _clamp(value, 1.08, 0.85, 1.25) == expected


def test_backend_voice_defaults_match_the_ui_and_fit_its_bounds(monkeypatch):
    from fastapi.testclient import TestClient

    from backend.eva.main import app

    for name in ("EVA_VOICE_RATE", "EVA_VOICE_PITCH", "EVA_VOICE_VOLUME"):
        monkeypatch.delenv(name, raising=False)
    voice = TestClient(app).get("/api/health").json()["voice"]
    source = APP_JS.read_text(encoding="utf-8")

    def const(name):
        return float(source.split(f"const {name} = ", 1)[1].split(";", 1)[0])

    for key, prefix in (("rate", "VOICE_RATE"), ("pitch", "VOICE_PITCH"), ("volume", "VOICE_VOLUME")):
        assert voice[key] == const(f"DEFAULT_{prefix}"), key
        assert const(f"MIN_{prefix}") <= voice[key] <= const(f"MAX_{prefix}"), key


# --- "write" and "enter" ----------------------------------------------------------


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("open notepad and type hello", True),
        ('open notepad and write "hello" in it', True),
        ("open notepad and write hello into it", True),
        ('open calculator and enter "12+7="', True),
        ("write me an email and save it", False),
        ("enter the room", False),
        ("it's a nice day", False),
    ],
)
def test_write_and_enter_ask_for_typing_only_with_a_target(message, expected):
    assert user_asked_to_type(message) is expected


NOTEPAD = WindowInfo(hwnd=7, title="Untitled - Notepad", process_id=7, process_name="notepad.exe", executable=r"C:\Windows\notepad.exe")


class ScriptedPlanner:
    def __init__(self, decisions):
        self._decisions = list(decisions)
        self.calls = 0

    async def plan(self, goal, history, mode="agent_step", task_context=None):
        decision = self._decisions[min(self.calls, len(self._decisions) - 1)]
        self.calls += 1
        return decision


def _call(tool, **args):
    return PlannerDecision(type="tool_calls", reason="step", tool_calls=[PlannedToolCall(tool=tool, args=args)], final_response="", continue_after_tools=True)


def test_a_write_request_types_the_users_words_through_the_real_loop(monkeypatch):
    tool_gate.reset_pending_calls()
    monkeypatch.setattr(desktop_verifier, "find_window", lambda query, limit=3: [NOTEPAD] if "notepad" in str(query).lower() else [])
    monkeypatch.setattr(desktop_verifier.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(runner_module, "_target_in_front", lambda target: "notepad" in target.lower())

    registry = ToolRegistry()
    typed: list[str] = []
    registry._tools["open_app"] = dataclasses.replace(registry._tools["open_app"], handler=lambda **kwargs: "Opening notepad.")
    registry._tools["screen.type_text"] = dataclasses.replace(
        registry._tools["screen.type_text"], handler=lambda text, reason: typed.append(text) or {"ok": True, "verified": True}
    )
    decisions = [
        _call("open_app", app="notepad"),
        _call("screen.type_text", text="hello from nova", reason="asked"),
        PlannerDecision(type="done", reason="finished", tool_calls=[], final_response="done", continue_after_tools=False),
    ]
    result = asyncio.run(
        run_agentic_task(
            'open notepad and write "hello from nova" in it',
            {"planner": ScriptedPlanner(decisions), "registry": registry, "executor": ToolExecutor(registry), "execute_tools": True, "goal_from_user": True},
        )
    )
    assert typed == ["hello from nova"]
    assert result.get("status") == "done"
