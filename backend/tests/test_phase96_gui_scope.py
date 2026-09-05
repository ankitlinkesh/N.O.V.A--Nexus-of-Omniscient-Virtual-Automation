"""Phase 96: a bounded, human-opened window in which the planner may click.

Everything needed to drive the GUI has existed since Phases 56-60. None of it
was reachable by the agent: `screen.*` is absent from `planner_specs()`, and
`test_planner_reachability.py` pins that as "must never be planner-reachable ...
regardless of any flag", because a crafted window title or a poisoned page could
otherwise steer a real mouse.

This does not remove that invariant, it narrows it and writes the narrower
version down:

    screen.* is never planner-reachable UNLESS a human opened a GUI scope from
    the typed console, and then only for that one task.

The tests below are the ones that would catch the boundary being widened by
accident: default invisibility, restoration after the scope closes (including
after an exception), the fixed grant list, and the fact that a scope changes
VISIBILITY only -- never the gate.
"""

from __future__ import annotations

import pytest

from backend.eva.screen.gui_scope import (
    DEFAULT_MAX_ACTIONS,
    GUI_SCOPE_HIDDEN,
    GUI_SCOPE_TOOLS,
    actions_used,
    budget_remaining,
    gui_scope_open,
    open_gui_scope,
    record_action,
)
from backend.eva.tools.registry import ToolRegistry


def visible_names(registry: ToolRegistry) -> set[str]:
    return {spec["name"] for spec in registry.planner_specs()}


# ----------------------------------------------------- the boundary itself


def test_screen_tools_are_invisible_by_default():
    """The invariant every other test file pins, restated at this boundary."""
    names = visible_names(ToolRegistry())
    assert not [n for n in names if n.startswith("screen.")], sorted(
        n for n in names if n.startswith("screen.")
    )
    assert gui_scope_open() is False


def test_a_scope_makes_exactly_the_granted_tools_visible():
    registry = ToolRegistry()
    before = visible_names(registry)
    with open_gui_scope("click seven"):
        inside = visible_names(registry)
    granted = inside - before
    assert granted == set(GUI_SCOPE_TOOLS) - GUI_SCOPE_HIDDEN, sorted(granted)


def test_visibility_is_restored_when_the_scope_closes():
    registry = ToolRegistry()
    before = visible_names(registry)
    with open_gui_scope("click seven"):
        pass
    assert visible_names(registry) == before
    assert gui_scope_open() is False


def test_a_raising_task_does_not_leak_the_scope():
    """A leaked scope leaves the planner holding the mouse with nobody watching."""
    registry = ToolRegistry()
    before = visible_names(registry)
    with pytest.raises(RuntimeError):
        with open_gui_scope("boom"):
            raise RuntimeError("task failed")
    assert gui_scope_open() is False
    assert visible_names(registry) == before


def test_the_grant_list_is_fixed_not_a_prefix_sweep():
    """A future `screen.something` must be an intentional addition, not automatic."""
    registry = ToolRegistry()
    all_screen = {n for n in registry._tools if n.startswith("screen.")}
    granted = set(GUI_SCOPE_TOOLS)
    assert granted < all_screen, "the grant list must be a strict subset of screen.*"
    assert "screen.submit_form" not in granted, "vault-backed form submit keeps its own one-approval flow"
    assert "screen.observe" not in granted, "observe captures a screenshot; the scope supplies labels locally"


def test_cloud_vision_is_removed_inside_a_scope():
    """Told not to call analyze_screen, the model did anyway; so remove the option."""
    registry = ToolRegistry()
    assert "analyze_screen" in visible_names(registry)
    with open_gui_scope("click seven"):
        inside = visible_names(registry)
        for name in GUI_SCOPE_HIDDEN:
            assert name not in inside, f"{name} sends a screenshot to Google and must be unavailable in a GUI task"
    assert "analyze_screen" in visible_names(registry)


# ------------------------------------------------------------- the budget


def test_the_budget_counts_across_contexts():
    """The counter must be shared by reference, not copied per context.

    Stored as a plain int in a ContextVar it reported "0/12 actions used" after a
    run that had clicked twice: `run_agentic_task` runs in another context, which
    receives a COPY, so increments never reached the console.
    """
    import asyncio

    async def act_in_another_context():
        record_action()
        record_action()
        return actions_used()

    with open_gui_scope("x"):
        assert actions_used() == 0
        inner = asyncio.run(act_in_another_context())
        assert inner == 2
        assert actions_used() == 2, "increments made inside the task must be visible to the console"
        assert budget_remaining() == DEFAULT_MAX_ACTIONS - 2


def test_budget_is_zero_outside_a_scope():
    assert budget_remaining() == 0


# ------------------------------------------- a scope never lowers the gate


def test_a_scope_does_not_change_how_the_gate_classifies_anything():
    """Visibility only. Typing and hotkeys must still require confirmation."""
    from backend.eva.security import tool_gate

    registry = ToolRegistry()
    before = {name: tool_gate.classify_tool_call(registry._tools[name]) for name in GUI_SCOPE_TOOLS}
    with open_gui_scope("click seven"):
        during = {name: tool_gate.classify_tool_call(registry._tools[name]) for name in GUI_SCOPE_TOOLS}
    assert during == before
    assert before["screen.type_text"] == "confirm", "typing must keep asking"
    assert before["screen.hotkey"] == "confirm", "hotkeys must keep asking"


# ------------------------------------------------- nothing untrusted opens one


def test_only_the_console_module_opens_a_scope():
    """The security property is an ABSENCE: no tool or argument reaches it."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2] / "backend" / "eva"
    callers = []
    for path in root.rglob("*.py"):
        if path.name in {"gui_scope.py"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "open_gui_scope" in text:
            callers.append(path.name)
    assert callers == ["fast_command_gui.py"], (
        "a GUI scope may only be opened from the typed-console handler; found %r" % callers
    )


def test_no_registered_tool_can_open_a_scope():
    registry = ToolRegistry()
    for name in ("gui_scope", "open_gui_scope", "gui.open", "gui_mode"):
        assert name not in registry._tools
    assert "open_gui_scope" not in visible_names(registry)


# ------------------------------------------- Phase 97: the foreground lock


def test_the_alt_tap_fallback_is_gated_on_real_input():
    """Focus needs a real input event here, so it lives behind the real-input flag.

    Measured on this hardware: the AttachThreadInput dance leaves the foreground
    unchanged while a tap of ALT immediately before SetForegroundWindow moves it
    every time -- Windows releases the foreground lock for a process that has
    just received real input. A synthetic ALT is used rather than a synthetic
    CLICK because it needs no coordinates and so cannot land on a control; there
    is no generally safe point to click on a title bar, Chrome's being its tab
    strip.
    """
    import inspect

    from backend.eva.desktop import windows

    source = inspect.getsource(windows._try_set_foreground)
    assert "real_input_enabled" in source, (
        "the ALT tap is synthetic input and must stay behind the flag that says Eva may generate it"
    )
    assert "keybd_event" in source
    assert "VK_MENU" in source
    # A click would need coordinates and could press a control, so assert no
    # click is ever ISSUED. Checked against the calls, not the prose -- the
    # comment above the fix explains at length why a click was rejected, so a
    # naive search for the word "click" matches the explanation itself.
    assert "mouse_event" not in source
    assert "pyautogui" not in source
    assert ".click(" not in source


def test_focus_reports_the_verified_outcome_not_the_attempt():
    """Phase 64's invariant, checked by BEHAVIOUR rather than by source text.

    The first version of this test asserted on a source substring and broke on
    the assignment style (`payload["error"] = ...` vs a dict literal) while the
    property it cared about was intact. Driving the real function is both
    stronger and not hostage to formatting.
    """
    from backend.eva.desktop.windows import focus_window

    # A query with no real word in it. The first version used "a window that
    # certainly does not exist anywhere" and passed until the day `find_window`
    # matched the word "window" against WindowsTerminal.exe and focused the
    # terminal -- a test whose own input could match a real window was never
    # testing the not-found path, it was testing whatever happened to be open.
    result = focus_window("zzqx-no-such-window-7f3a9c14")
    assert result.get("ok") is False, "focus must never claim success for a window it did not find"
    assert result.get("error"), "a failure must say why"
