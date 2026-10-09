"""Phase 136: output of a sandbox command that FETCHED counts as outside content.

ECC security review: sandbox output was classed as trusted tool output, though NOVA
can curl a web page in the box. User decision: only a fetching command's output
counts like a web page (so the next sandbox command asks first); ordinary box work
stays autonomous.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import backend.eva.shell.sandbox_terminal as st
from backend.eva.agent import paused_tasks as paused_tasks_mod
from backend.eva.agent.executor import ToolExecutor
from backend.eva.agent.planner import PlannedToolCall, PlannerDecision
from backend.eva.agent.runner import run_agentic_task
from backend.eva.security import tool_gate
from backend.eva.shell.sandbox_terminal import fetches_external
from backend.eva.threat_defense.taint import UNTRUSTED_SOURCE_TYPES
from backend.eva.tools.registry import ToolRegistry


class FakeWsl:
    def __init__(self, returncode=0, stdout=b"ok\n"):
        self.result = SimpleNamespace(returncode=returncode, stdout=stdout, stderr=b"")
        self.calls: list[list[str]] = []

    def __call__(self, argv, timeout, env):
        self.calls.append(list(argv))
        if "--list" in argv:
            return SimpleNamespace(returncode=0, stdout=b"nova\n", stderr=b"")
        # A distinct output per command, or the runner's no-new-observation check
        # (correctly) stops a task that keeps seeing the same thing.
        n = len(self.exec_calls)
        return SimpleNamespace(returncode=self.result.returncode, stdout=self.result.stdout + b"#%d\n" % n, stderr=self.result.stderr)

    @property
    def exec_calls(self):
        return [c for c in self.calls if "--exec" in c]


@pytest.fixture
def wsl(monkeypatch):
    fake = FakeWsl()
    monkeypatch.setattr(st, "_default_runner", fake)
    tool_gate.reset_pending_calls()
    paused_tasks_mod.clear_all()
    yield fake
    tool_gate.reset_pending_calls()
    paused_tasks_mod.clear_all()


def _run(goal, commands):
    decisions = [
        PlannerDecision(type="tool_calls", reason="s", tool_calls=[PlannedToolCall(tool="sandbox_run", args={"command": c})], final_response="", continue_after_tools=True)
        for c in commands
    ] + [PlannerDecision(type="done", reason="d", tool_calls=[], final_response="ok", continue_after_tools=False)]

    class Planner:
        n = 0

        async def plan(self, goal, history, mode="agent_step", task_context=None):
            d = decisions[min(Planner.n, len(decisions) - 1)]
            Planner.n += 1
            return d

    registry = ToolRegistry()
    return asyncio.run(run_agentic_task(goal, {"planner": Planner(), "registry": registry, "executor": ToolExecutor(registry), "execute_tools": True, "session_id": "p136"}))


@pytest.mark.parametrize("command", [
    "curl -s https://example.com", "wget x", "cd /tmp && git clone https://github.com/a/b", "pip install requests",
    "python3 -m pip download x", "npm i lodash", 'python3 -c "import urllib.request"', "echo hi; curl example.com",
    "ssh user@host", "(curl x)", 'python3 -c "import requests"',
])
def test_fetching_commands_are_recognised(command):
    assert fetches_external(command)


@pytest.mark.parametrize("command", [
    "ls -la", 'python3 -c "print(2+2)"', "df -h", "cat /etc/os-release", "echo curly braces", "grep -r pipeline .",
    "mkdir pipx_notes", "git status", "git log", "pip list", "npm run build", "cat ncurses.txt",
])
def test_ordinary_box_work_is_not_a_fetch(command):
    assert not fetches_external(command)


def test_the_source_is_untrusted():
    assert "sandbox_download" in UNTRUSTED_SOURCE_TYPES


def test_after_a_download_the_next_sandbox_command_asks(wsl):
    result = _run("use your box to fetch example.com and summarize it", ["curl -s https://example.com", "ls"])
    assert result.get("requires_confirmation") is True, result
    assert len(wsl.exec_calls) == 1, "the command after the download must not run on its own"
    assert "downloaded in my sandbox" in str(result.get("final_response"))


def test_a_failed_download_still_counts(wsl):
    wsl.result = SimpleNamespace(returncode=6, stdout=b"<html>partial page</html>", stderr=b"curl: (6) error")
    result = _run("use your box to fetch it", ["curl -s https://example.com", "ls"])
    assert result.get("requires_confirmation") is True and len(wsl.exec_calls) == 1


def test_ordinary_box_work_stays_autonomous(wsl):
    result = _run("in your box list files twice", ["ls -la", "python3 -c 'print(2+2)'", "pwd"])
    assert result["status"] == "done" and not result.get("requires_confirmation")
    assert len(wsl.exec_calls) == 3
