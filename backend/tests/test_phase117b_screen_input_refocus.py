"""Executable spec for the Phase 117 orchestrator live-drive findings (rounds 3 & 4).

Round 3: "open calculator and type the sum of five and six into it, then tell
me the answer" opened Calculator, planned `screen.type_text` with "5+6="
(not verbatim in the user's message, so no Phase 110 grant), and paused
correctly with a real pending id. But at the moment of confirming from NOVA's
chat page the foreground window was the browser/terminal, not Calculator --
`ToolRegistry.run_approved` replayed `screen.type_text` blindly into whatever
was focused. Fixed by recording a `target_window` when the pending action is
created and restoring + independently verifying that exact window before the
handler ever runs (`run_approved`'s refuse-if-not-restored-and-verified
logic -- untouched by round 4, see the tests in the first half of this file).

Round 4: a live in-process spy on `tool_gate.register_pending_call` found
round 3's SOURCE for that recorded window was itself wrong: it read
`desktop.windows.get_active_window()` -- "whatever is foreground right now"
-- at the moment the pending was CREATED. Calculator was open and verified,
but the user was working in Chrome when `screen.type_text` was planned, so
`runner._target_in_front` correctly saw Chrome had focus and the call fell
through to the ordinary gate, which recorded Chrome's window. Approving would
have typed "11" into Chrome. Fixed by never trusting the foreground at gate
time at all: the runner exposes the TASK-VERIFIED app name
(`loop_vars["typing_target"]`, set only after an `open_app`/`window_focus`
call's result was independently verified) to the gate via a ContextVar scope
(`screen.target_app`, opened around exactly one `executor.execute` call, no
thread hop), and `_create_gated_pending` resolves THAT app's window with
`desktop.windows.find_window` -- never `get_active_window`. No verified app,
or that app's window cannot be found, records `target_window=None`, which
`run_approved` already refuses rather than guessing.

Round 5: round 4's fix closed the hole for the ordinary chat route, but a
`gui:` console task verifies its target window through a COMPLETELY
different mechanism -- `fast_command_gui.py::_focus_named_window` focuses
and verifies the app the goal names BEFORE `run_agentic_task` is even
called, entirely outside the runner loop, so `loop_vars["typing_target"]`
was never set for a `gui:` task and every screen-input approval inside one
would refuse with `no_target_window_recorded` even when the console had
already verified the exact right window. Fixed by mirroring `open_gui_scope`
exactly: `_run_task_in_scope` now also opens `open_target_app_scope
(verified_app)`, on the SAME coroutine, at the SAME placement (inside the
`run_async` hop, not around it -- the Phase 103 lesson this project keeps
re-learning), only when `_focus_named_window` reported a VERIFIED focus (not
`None`, not a `!`-prefixed mismatch). The runner's OWN in-loop verification
(from an `open_app`/`window_focus` tool call the task itself made) still
takes precedence when present -- `runner._run_step` only opens its inner
scope when `loop_vars["typing_target"]` is actually set, so a `None` there
never overwrites the outer `gui:` scope for that call.

Nothing here touches the real desktop: `get_active_window`, `find_window`,
`focus_window_handle` and `wait_for_input_ready` are all faked, and the
screen-input tool handlers themselves are replaced with recording stand-ins
via `dataclasses.replace` (the technique `test_phase110_typing_and_one_shot.py`
and `test_gate_execution_honesty.py` use).

IMPORTANT (the orchestrator's note from round 4): this project's package
imports as two separate module copies depending on whether it is reached as
`eva.*` or `backend.eva.*`. Everything here patches the `backend.eva.*`
copy, because that is the one `backend.eva.agent.runner` and
`backend.eva.tools.registry` actually import from at call time (both use a
plain `from ..desktop.windows import ...` / `from ..screen.target_app import
...` INSIDE the function body, re-resolved fresh on every call, so patching
the module attribute on `backend.eva.desktop.windows` etc. is what reaches
them). `desktop.verifier` is DIFFERENT again: it imports `find_window` at
MODULE level (`from .windows import find_window`), binding its own separate
name at import time, so verifying `open_app`'s own postcondition needs
`desktop.verifier.find_window` patched too, exactly as
`test_phase110_typing_and_one_shot.py` already does.
"""

from __future__ import annotations

import asyncio
import dataclasses

import pytest

import backend.eva.agent.runner as runner_module
import backend.eva.core.fast_command_gui as fast_command_gui
import backend.eva.desktop.verifier as desktop_verifier
import backend.eva.desktop.windows as windows_mod
import backend.eva.screen.input_ready as input_ready_mod
import backend.eva.screen.target_app as target_app_mod
import backend.eva.tools.registry as registry_mod
from backend.eva.agent import paused_tasks as paused_tasks_mod
from backend.eva.agent.executor import ToolExecutor
from backend.eva.agent.planner import PlannedToolCall, PlannerDecision
from backend.eva.agent.runner import resume_agentic_task, run_agentic_task
from backend.eva.desktop.windows import WindowInfo
from backend.eva.mcp.runner import run_async
from backend.eva.permissions.confirmation import handle_confirmation_command
from backend.eva.permissions.ledger import confirm_pending_action
from backend.eva.screen.target_app import open_target_app_scope
from backend.eva.security import tool_gate
from backend.eva.tools.registry import ToolRegistry

CALCULATOR = WindowInfo(hwnd=4242, title="Calculator", process_id=99, process_name="calculator.exe", executable=r"C:\Program Files\WindowsApps\Calculator.exe")
BROWSER = WindowInfo(hwnd=7777, title="... - Google Search - Google Chrome", process_id=55, process_name="chrome.exe", executable=r"C:\Program Files\Google\Chrome\chrome.exe")


class ScriptedPlanner:
    def __init__(self, decisions):
        self._decisions = list(decisions)
        self.calls = 0

    async def plan(self, goal, history, mode="agent_step", task_context=None):
        decision = self._decisions[min(self.calls, len(self._decisions) - 1)]
        self.calls += 1
        return decision


def _call(tool: str, **args) -> PlannerDecision:
    return PlannerDecision(type="tool_calls", reason="step", tool_calls=[PlannedToolCall(tool=tool, args=args)], final_response="", continue_after_tools=True)


def _done(text: str = "done") -> PlannerDecision:
    return PlannerDecision(type="done", reason="finished", tool_calls=[], final_response=text, continue_after_tools=False)


def _find_window_for(*named: WindowInfo):
    """A fake `find_window(query, limit=...)` that matches a window whose
    title contains `query` (case-insensitive) -- good enough for these
    fixtures, and deliberately dumb so it never accidentally "resolves"
    something the test did not name."""

    def _find(query: str, limit: int = 10):
        q = str(query or "").lower()
        return [w for w in named if q and q in w.title.lower()][:limit]

    return _find


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    tool_gate.reset_pending_calls()
    paused_tasks_mod.clear_all()
    # The foreground window is ALWAYS the browser in this fixture -- proving
    # it is never consulted is the point of round 4. Tests that need a
    # target window open `open_target_app_scope` and fake `find_window`
    # explicitly; nothing here does that by default.
    monkeypatch.setattr(windows_mod, "get_active_window", lambda: BROWSER)
    monkeypatch.setattr(windows_mod, "find_window", lambda query, limit=10: [])
    typed: list[str] = []
    opened: list[str] = []
    spec = ToolRegistry()._tools["screen.type_text"]
    open_app_spec = ToolRegistry()._tools["open_app"]

    def _fake_type_text(text, reason):
        typed.append(text)
        return {"ok": True, "verified": True, "chars": len(text)}

    def _fake_open_app(app=None, app_name=None):
        opened.append(str(app or app_name))
        return "Opening the app."

    def _install_fakes(registry: ToolRegistry) -> None:
        registry._tools["screen.type_text"] = dataclasses.replace(spec, handler=_fake_type_text)
        registry._tools["open_app"] = dataclasses.replace(open_app_spec, handler=_fake_open_app)

    yield {"typed": typed, "opened": opened, "install_fakes": _install_fakes}
    tool_gate.reset_pending_calls()
    paused_tasks_mod.clear_all()


def _fresh_registry(fixtures) -> ToolRegistry:
    registry = ToolRegistry()
    fixtures["install_fakes"](registry)
    return registry


def _create_pending(registry: ToolRegistry, **type_args) -> str:
    result = registry.run("screen.type_text", **type_args)
    assert result.get("requires_confirmation") is True, result
    pid = result.get("pending_id")
    assert pid
    return pid


def _create_pending_for_app(registry: ToolRegistry, app: str | None, **type_args) -> str:
    """Simulates the runner: opens the task-verified-app scope around the one
    call that creates the pending, exactly as `_run_step` does around
    `executor.execute`."""
    with open_target_app_scope(app):
        return _create_pending(registry, **type_args)


# =====================================================================
# Round 4: the RECORDED target is the task's verified app, never the
# foreground window.
# =====================================================================


def test_the_recorded_target_is_the_verified_app_not_the_foreground_browser(monkeypatch, _clean_state):
    """The exact round-4 finding: foreground is the browser, the task's
    verified app is Calculator -- the recorded target must be Calculator's
    window, not the browser's."""
    monkeypatch.setattr(windows_mod, "find_window", _find_window_for(CALCULATOR))
    registry = _fresh_registry(_clean_state)

    pid = _create_pending_for_app(registry, "calculator", text="5+6=", reason="the sum")

    stored = tool_gate.get_pending_call(pid)
    target_window = stored.get("target_window")
    assert target_window is not None
    assert target_window["hwnd"] == CALCULATOR.hwnd
    assert target_window["hwnd"] != BROWSER.hwnd


def test_no_verified_app_records_no_target_and_approval_refuses(_clean_state):
    """No `open_target_app_scope` in force at all (the ordinary case for a
    console/allow-class call, or a task that has not yet verified an app) ->
    `target_window` is None, and approval refuses -- it never falls back to
    the foreground."""
    registry = _fresh_registry(_clean_state)

    pid = _create_pending(registry, text="5+6=", reason="r")  # no scope opened

    stored = tool_gate.get_pending_call(pid)
    assert stored.get("target_window") is None

    confirm_pending_action(pid, override=False)
    result = registry.run_approved(pid)
    assert result.get("ok") is False
    assert result.get("error") == "no_target_window_recorded"
    assert _clean_state["typed"] == []


def test_verified_apps_window_missing_records_no_target_and_approval_refuses(monkeypatch, _clean_state):
    """The task verified an app, but by the time the pending is created that
    app's window cannot be found (closed, crashed, never actually opened
    despite the earlier verification window) -- `find_window` returns
    nothing, so `target_window` stays None rather than guessing."""
    monkeypatch.setattr(windows_mod, "find_window", lambda query, limit=10: [])
    registry = _fresh_registry(_clean_state)

    pid = _create_pending_for_app(registry, "ghost_app", text="5+6=", reason="r")

    stored = tool_gate.get_pending_call(pid)
    assert stored.get("target_window") is None

    confirm_pending_action(pid, override=False)
    result = registry.run_approved(pid)
    assert result.get("ok") is False
    assert result.get("error") == "no_target_window_recorded"
    assert _clean_state["typed"] == []


def test_the_foreground_window_is_never_read_at_all(monkeypatch, _clean_state):
    """A stronger version of the two tests above: `get_active_window` must
    not even be CALLED while creating a screen-input pending, regardless of
    whether a verified app is in scope. There is deliberately no fallback
    path left that would call it."""
    calls: list[None] = []
    monkeypatch.setattr(windows_mod, "get_active_window", lambda: calls.append(None) or BROWSER)
    monkeypatch.setattr(windows_mod, "find_window", _find_window_for(CALCULATOR))
    registry = _fresh_registry(_clean_state)

    _create_pending_for_app(registry, "calculator", text="5+6=", reason="r")
    _create_pending(registry, text="more", reason="r")  # no verified app either

    assert calls == [], "get_active_window must never be consulted by pending creation"


# =====================================================================
# Round 3: once a target IS recorded, approval restores and verifies it
# before ever running the handler. Unchanged by round 4 -- these tests only
# switch to `_create_pending_for_app` for how the target gets recorded.
# =====================================================================


def test_approved_typing_refocuses_the_recorded_window_and_types_only_after_verified(monkeypatch, _clean_state):
    order: list[str] = []
    monkeypatch.setattr(windows_mod, "find_window", _find_window_for(CALCULATOR))
    registry = _fresh_registry(_clean_state)
    pid = _create_pending_for_app(registry, "calculator", text="5+6=", reason="the user asked for the sum")

    def fake_focus(hwnd, **kwargs):
        order.append(f"focus:{hwnd}")
        assert hwnd == CALCULATOR.hwnd
        return {"ok": True, "focused": True, "verified": True, "window": CALCULATOR.as_dict()}

    def fake_ready(hwnd, **kwargs):
        order.append(f"ready:{hwnd}")
        assert hwnd == CALCULATOR.hwnd
        return True

    monkeypatch.setattr(windows_mod, "focus_window_handle", fake_focus)
    monkeypatch.setattr(input_ready_mod, "wait_for_input_ready", fake_ready)

    confirm_pending_action(pid, override=False)
    result = registry.run_approved(pid)

    assert result.get("ok") is True
    assert _clean_state["typed"] == ["5+6="]
    # Refocus and readiness happened, and happened BEFORE the type landed.
    assert order == [f"focus:{CALCULATOR.hwnd}", f"ready:{CALCULATOR.hwnd}"]


def test_when_the_recorded_window_cannot_be_restored_nothing_is_typed(monkeypatch, _clean_state):
    monkeypatch.setattr(windows_mod, "find_window", _find_window_for(CALCULATOR))
    registry = _fresh_registry(_clean_state)
    pid = _create_pending_for_app(registry, "calculator", text="5+6=", reason="r")

    monkeypatch.setattr(windows_mod, "focus_window_handle", lambda hwnd, **kw: {"ok": False, "error": "focus_failed"})
    monkeypatch.setattr(input_ready_mod, "wait_for_input_ready", lambda hwnd, **kw: pytest.fail("must not check readiness once focus failed"))

    confirm_pending_action(pid, override=False)
    result = registry.run_approved(pid)

    assert result.get("ok") is False
    assert result.get("error") == "target_window_not_restored"
    assert _clean_state["typed"] == []


def test_when_the_window_is_foreground_but_not_input_ready_nothing_is_typed(monkeypatch, _clean_state):
    monkeypatch.setattr(windows_mod, "find_window", _find_window_for(CALCULATOR))
    registry = _fresh_registry(_clean_state)
    pid = _create_pending_for_app(registry, "calculator", text="5+6=", reason="r")

    monkeypatch.setattr(windows_mod, "focus_window_handle", lambda hwnd, **kw: {"ok": True, "verified": True})
    monkeypatch.setattr(input_ready_mod, "wait_for_input_ready", lambda hwnd, **kw: False)

    confirm_pending_action(pid, override=False)
    result = registry.run_approved(pid)

    assert result.get("ok") is False
    assert result.get("error") == "target_window_not_ready"
    assert _clean_state["typed"] == []


def test_a_legacy_pending_call_with_no_target_window_field_also_refuses():
    """Directly exercises the in-memory store shape from before round 3
    (`register_pending_call` called without `target_window`), rather than
    going through `_create_gated_pending`."""
    tool_gate.register_pending_call("act_legacy000001", "screen.type_text", {"text": "hi", "reason": "r"})
    from eva.permissions.pending_actions import EvaPendingAction
    from eva.permissions.ledger import create_pending_action

    action = EvaPendingAction.new(
        action_type="screen.type_text",
        risk_level="medium",
        risk_category="SAFE_LOCAL_UI",
        summary="legacy pending",
        requires_confirmation=True,
        source="tool_gate",
        executor_available=True,
        executor_name="screen.type_text",
        safety_reason="legacy",
    )
    action.id = "act_legacy000001"
    create_pending_action(action)
    confirm_pending_action("act_legacy000001", override=False)

    registry = ToolRegistry()
    result = registry.run_approved("act_legacy000001")

    assert result.get("ok") is False
    assert result.get("error") == "no_target_window_recorded"


def test_non_screen_tools_are_unaffected_by_the_refocus_check(monkeypatch, _clean_state):
    """A gated non-screen tool (file.delete) must never touch the
    focus/readiness machinery at all -- confirming that this check is scoped
    to `tool_gate.SCREEN_INPUT_TOOLS` and nothing wider."""
    focus_calls: list[int] = []
    ready_calls: list[int] = []
    monkeypatch.setattr(windows_mod, "focus_window_handle", lambda hwnd, **kw: focus_calls.append(hwnd) or {"ok": True})
    monkeypatch.setattr(input_ready_mod, "wait_for_input_ready", lambda hwnd, **kw: ready_calls.append(hwnd) or True)

    deleted: list[str] = []
    monkeypatch.setattr(registry_mod, "file_delete", lambda path: (deleted.append(path), {"ok": True, "deleted": path})[1])

    registry = ToolRegistry()
    ghost = "C:/Users/HP/Documents/eva_phase117b_ghost.txt"
    result = registry.run("file.delete", path=ghost)
    pid = result.get("pending_id")
    assert pid

    confirm_pending_action(pid, override=True)
    executed = registry.run_approved(pid)

    assert executed.get("ok") is True
    assert deleted == [ghost]
    assert focus_calls == []
    assert ready_calls == []


def test_screen_observe_and_wait_are_not_screen_input_tools():
    """screen.observe touches no window (it only reads), and screen.wait
    touches nothing at all; screen.submit_form resolves its own console-issued
    target rather than 'whatever is focused'. None belong in the set this fix
    gates on."""
    assert "screen.observe" not in tool_gate.SCREEN_INPUT_TOOLS
    assert "screen.wait" not in tool_gate.SCREEN_INPUT_TOOLS
    assert "screen.submit_form" not in tool_gate.SCREEN_INPUT_TOOLS
    assert tool_gate.SCREEN_INPUT_TOOLS == {"screen.type_text", "screen.press", "screen.hotkey", "screen.click", "screen.scroll"}


# =====================================================================
# Integration with the real runner, and with Phase 117 resume.
# =====================================================================


def test_the_runner_records_the_opened_apps_window_even_while_a_browser_has_focus(monkeypatch, _clean_state):
    """The exact live scenario, end to end through `run_agentic_task`: the
    task opens and verifies Calculator, then plans `screen.type_text` while
    the (faked) foreground window is a browser. The pending action's
    recorded target must be Calculator's window."""
    monkeypatch.setattr(desktop_verifier, "find_window", _find_window_for(CALCULATOR))
    monkeypatch.setattr(windows_mod, "find_window", _find_window_for(CALCULATOR))
    registry = _fresh_registry(_clean_state)
    decisions = [_call("open_app", app="calculator"), _call("screen.type_text", text="5+6=", reason="the sum"), _done("The answer is 11.")]

    result = asyncio.run(
        run_agentic_task(
            "open calculator and type the sum of five and six into it, then tell me the answer",
            {
                "planner": ScriptedPlanner(decisions),
                "registry": registry,
                "executor": ToolExecutor(registry),
                "execute_tools": True,
                "session_id": "live-2",
            },
        )
    )
    assert _clean_state["opened"] == ["calculator"]
    pid = result.get("action")
    assert pid and pid.startswith("act_")

    stored = tool_gate.get_pending_call(pid)
    target_window = stored.get("target_window")
    assert target_window is not None
    assert target_window["hwnd"] == CALCULATOR.hwnd, "must record Calculator's window, not the foreground browser's"


def test_a_resumed_task_sees_the_refocus_refusal_as_an_ordinary_observation(monkeypatch, _clean_state):
    """Ties both fixes to Phase 117: the exact live scenario is a task that
    opened Calculator, planned screen.type_text, paused with Calculator
    correctly recorded as the target, and is confirmed from the chat page (a
    different window in front, unable to be restored). The refusal below
    must flow through `resume_agentic_task` as this step's observation --
    ordinary recovery, not an unhandled crash -- and the task keeps going.
    """
    monkeypatch.setattr(desktop_verifier, "find_window", _find_window_for(CALCULATOR))
    monkeypatch.setattr(windows_mod, "find_window", _find_window_for(CALCULATOR))
    registry = _fresh_registry(_clean_state)
    decisions = [_call("open_app", app="calculator"), _call("screen.type_text", text="5+6=", reason="the sum"), _done("The answer is 11.")]
    result = asyncio.run(
        run_agentic_task(
            "open calculator and type the sum of five and six into it, then tell me the answer",
            {
                "planner": ScriptedPlanner(decisions),
                "registry": registry,
                "executor": ToolExecutor(registry),
                "execute_tools": True,
                "session_id": "live-1",
            },
        )
    )
    pid = result.get("action")
    assert pid and pid.startswith("act_")

    # At confirm time the recorded window (Calculator) cannot be restored --
    # e.g. it was closed, or Windows' foreground lock is engaged.
    monkeypatch.setattr(windows_mod, "focus_window_handle", lambda hwnd, **kw: {"ok": False, "error": "focus_failed"})

    reply = handle_confirmation_command(f"confirm {pid}", session_id="live-1")

    assert _clean_state["typed"] == [], "nothing should have been typed into the wrong window"
    # confirmation.py's `_failure_reason` prefers the short `error` code over
    # the friendlier `message` (an existing, pre-Phase-117 convention -- see
    # other gated tools' refusal dicts), so the console text names the code,
    # not the prose; both are present on the raw dict this comes from.
    assert "target_window_not_restored" in reply.lower()
    # The task did not crash; it resumed past the failed step and reported
    # what the `_done` step said next -- ordinary recovery, not an unhandled
    # exception bubbling out of confirm.
    assert "resuming the task" in reply.lower()


# =====================================================================
# Round 5: `gui:` console tasks -- a target verified OUTSIDE the runner
# loop, before the run_async thread hop, must still reach the gate.
# =====================================================================


def _make_fake_run_agentic_task(state: dict):
    """Replaces `agent.runner.run_agentic_task` for these tests: instead of
    running a real plan->act->observe loop (irrelevant to what round 5
    fixes), it directly creates ONE screen-input pending through the REAL
    `ToolRegistry`/gate, so `verified_target_app()` and `_create_gated_pending`
    are exercised for real, on whatever thread this fake actually runs on."""

    async def _fake(user_message, context):
        registry = ToolRegistry()
        registry._tools["screen.type_text"] = dataclasses.replace(
            registry._tools["screen.type_text"], handler=lambda text, reason: {"ok": True}
        )
        result = registry.run("screen.type_text", text="hi", reason="r")
        state["registry"] = registry
        state["pid"] = result.get("pending_id")
        return {
            "ok": False,
            "task_id": "fake",
            "status": "waiting_for_confirmation",
            "final_response": "",
            "requires_confirmation": True,
            "action": state["pid"],
            "steps_count": 0,
            "tools_planned": [],
            "tools_executed": [],
            "safety_stops": [],
            "critic": None,
            "task": {"steps": []},
            "events": [],
        }

    return _fake


def _run_gui_scope_via_real_thread_hop(verified_app):
    """Calls `run_async` from INSIDE a running event loop, exactly the
    condition the Phase 103 docstring describes ("always true inside a
    FastAPI handler") and the one that made the original gui-scope bug
    possible: `run_async` then ships the coroutine to a ThreadPoolExecutor
    worker thread rather than running it in place. If `open_target_app_scope`
    were opened around this call instead of inside `_run_task_in_scope`, the
    worker thread would see an empty ContextVar -- a silent no-op, same as
    the bug `open_gui_scope` was built to fix."""

    async def _driver():
        return run_async(
            fast_command_gui._run_task_in_scope(
                "gui: type into the app",
                "gui: type into the app",
                {},
                None,
                "s1",
                verified_app,
            )
        )

    return asyncio.run(_driver())


def test_a_verified_gui_focus_survives_the_thread_hop_and_is_recorded_as_the_target(monkeypatch, _clean_state):
    """A `gui:` task whose app was pre-focused and VERIFIED by
    `_focus_named_window`, with a browser in front at gate-creation time: the
    recorded target must be that app's window, not the browser's -- and
    `verified_target_app()` must have actually been called (and returned the
    right value) from INSIDE `_create_gated_pending`, on the far side of the
    `run_async` hop.
    """
    monkeypatch.setattr(windows_mod, "get_active_window", lambda: BROWSER)
    monkeypatch.setattr(windows_mod, "find_window", _find_window_for(CALCULATOR))

    state: dict = {}
    monkeypatch.setattr(runner_module, "run_agentic_task", _make_fake_run_agentic_task(state))

    real_verified_target_app = target_app_mod.verified_target_app
    spy_calls: list[str | None] = []

    def _spy():
        value = real_verified_target_app()
        spy_calls.append(value)
        return value

    monkeypatch.setattr(target_app_mod, "verified_target_app", _spy)

    _run_gui_scope_via_real_thread_hop("Calculator")

    assert "Calculator" in spy_calls, "verified_target_app() must be read (with the right value) inside _create_gated_pending, across the thread hop"
    pid = state.get("pid")
    assert pid
    stored = tool_gate.get_pending_call(pid)
    assert stored is not None
    target_window = stored.get("target_window")
    assert target_window is not None
    assert target_window["hwnd"] == CALCULATOR.hwnd
    assert target_window["hwnd"] != BROWSER.hwnd


def test_a_gui_task_with_no_verified_focus_records_no_target_and_approval_refuses(monkeypatch, _clean_state):
    """`_focus_named_window` found nothing recognizable, or could not verify
    the focus (a `!`-prefixed result, collapsed to `None` before
    `_run_task_in_scope` is ever called -- see `_run_gui_task`): no scope
    opens, so the pending action records no target, and approval refuses
    exactly as it does for the ordinary chat route with no verified app.
    """
    monkeypatch.setattr(windows_mod, "get_active_window", lambda: BROWSER)
    monkeypatch.setattr(windows_mod, "find_window", _find_window_for(CALCULATOR))

    state: dict = {}
    monkeypatch.setattr(runner_module, "run_agentic_task", _make_fake_run_agentic_task(state))

    _run_gui_scope_via_real_thread_hop(None)

    pid = state.get("pid")
    assert pid
    stored = tool_gate.get_pending_call(pid)
    assert stored is not None
    assert stored.get("target_window") is None

    confirm_pending_action(pid, override=False)
    result = state["registry"].run_approved(pid)
    assert result.get("ok") is False
    assert result.get("error") == "no_target_window_recorded"
