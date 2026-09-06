"""Phase 103 -- the GUI arc that was built, tested, validated, and never arrived.

Phases 56-60 and 96 built desktop clicking and typing, proved each piece on real
hardware, and shipped them behind a `gui:` scope. Driving that scope through the
actual chat endpoint for the first time showed it had never once worked there:
the scope lives in a ContextVar, `run_async` hands the task to a worker thread,
and a worker thread does not inherit the caller's context. Every errand ran with
the scope shut, the planner was offered no `screen.*` tools, and it answered --
truthfully -- that it could not click or type. Once it reached for `web.click`,
the BROWSER tool, to press a Calculator button.

Every test and every live validation had driven `registry.run` in-process, where
the ContextVar IS in scope. So the tests here assert ARRIVAL at the far side of
the thread hop, not the presence of the mechanism: the same distinction the
project has now had to make in memory, in observations, and in the actuator.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
GUI_PY = ROOT / "backend" / "eva" / "core" / "fast_command_gui.py"
WINDOWS_PY = ROOT / "backend" / "eva" / "desktop" / "windows.py"
MAIN_PY = ROOT / "backend" / "eva" / "main.py"


# --------------------------------------------------------------------------
# The scope must survive the thread hop that actually happens in production
# --------------------------------------------------------------------------


def test_the_planner_is_offered_screen_tools_where_it_actually_asks(monkeypatch) -> None:
    """The check that would have caught it, and the only one that could.

    Opening a scope and asserting `gui_scope_open()` in the SAME thread passes
    happily against the broken build -- which is precisely what the Phase 96
    tests did while the feature was dead in production. What matters is whether
    the tools are visible at the moment `run_agentic_task` asks for them, so this
    drives the real `_run_gui_task` and reports from inside the task itself.

    Note what is NOT asserted: that `run_async` propagates contexts. It does not,
    and it is not asked to. The scope arrives because it is opened on the thread
    that does the work, the way `role_scope` always was.
    """
    from eva.core import fast_command_gui
    from eva.screen.gui_scope import gui_scope_open
    from eva.tools.registry import ToolRegistry

    registry = ToolRegistry()
    seen: dict = {}

    async def fake_task(goal, context):
        seen["scope_open"] = gui_scope_open()
        seen["screen_tools"] = sorted(
            spec["name"] for spec in registry.planner_specs() if spec["name"].startswith("screen.")
        )
        return {"final_response": "done", "tools_executed": []}

    monkeypatch.setattr("eva.agent.runner.run_agentic_task", fake_task)
    monkeypatch.setattr(fast_command_gui, "_readiness", lambda: [])
    monkeypatch.setattr(fast_command_gui, "_focus_named_window", lambda goal, tools: None)
    monkeypatch.setattr("eva.screen.grounding.describe_visible", lambda limit=60: {})

    async def as_a_request_handler():
        # A loop is already running, which is what pushes run_async onto a worker
        # thread. This is the production shape, not a reconstruction of it.
        return fast_command_gui._run_gui_task("click the seven button", registry, None, None, None)

    asyncio.run(as_a_request_handler())

    assert seen.get("scope_open"), "the task ran with the GUI scope shut"
    assert "screen.click" in seen.get("screen_tools", [])
    assert "screen.type_text" in seen.get("screen_tools", [])


def test_gui_task_opens_its_scope_inside_the_coroutine() -> None:
    """Structural pin for the fix's shape.

    `role_scope` is opened inside `run_delegated` and survives; the GUI scope was
    opened around `run_async` and did not. Keeping the scope inside the coroutine
    is the invariant, so a future refactor that hoists it back out fails here
    rather than silently shutting the whole arc off again.
    """
    source = GUI_PY.read_text(encoding="utf-8")
    assert "async def _run_task_in_scope" in source
    # Scoped to the coroutine's own body. Searching the whole file matched the
    # `with open_gui_scope(...)` that the BROKEN shape leaves in `_run_gui_task`,
    # so this assertion passed against a build with the scope hoisted back out --
    # a check that cannot fail, in the test file for a bug about exactly that.
    body = source.split("async def _run_task_in_scope", 1)[1].split("\ndef ", 1)[0]
    assert "with open_gui_scope(" in body, (
        "the GUI scope is no longer opened inside the coroutine that runs the task"
    )
    assert "await run_agentic_task(" in body, "the task is no longer awaited inside the scope"
    assert source.count("with open_gui_scope(") == 1, (
        "a second scope is opened elsewhere -- the one outside the coroutine is invisible "
        "to the worker thread that runs the task, which is the bug this phase fixes"
    )


def test_scope_spend_is_read_inside_the_scope() -> None:
    """Read outside, `actions_used()` reports the request thread's empty scope --
    which is why the broken build printed a tidy `0/12` instead of failing."""
    source = GUI_PY.read_text(encoding="utf-8")
    body = source.split("async def _run_task_in_scope", 1)[1].split("\ndef ", 1)[0]
    assert "actions_used()" in body, "the spend is not read inside the scoped coroutine"
    assert "scope.max_actions" in body


# --------------------------------------------------------------------------
# Typing: what was sent is not what arrived
# --------------------------------------------------------------------------


def _fake_gui(recorder: dict, *, mangle=None):
    class FakeGui:
        def write(self, text, interval=0.0):
            recorder["typed"] = mangle(text) if mangle else text
            recorder["interval"] = interval

    return FakeGui()


@pytest.fixture()
def typing_bench(monkeypatch):
    """A field whose contents the type_text path can actually read back."""
    from eva.screen import screen_controller

    state = {"field": "", "typed": None, "interval": None}

    def install(*, mangle=None, readable=True):
        monkeypatch.setattr(
            screen_controller,
            "_pyautogui",
            lambda: (_fake_gui(state, mangle=mangle), None),
        )

        def focused_value():
            if not readable:
                return None
            # Reads whatever actually "arrived", so the check is measuring the
            # field rather than the argument it was handed.
            return state["field"] + (state["typed"] or "") if state["typed"] is not None else state["field"]

        monkeypatch.setattr(screen_controller, "_focused_value", focused_value)

    state["install"] = install
    return state


def test_typing_reports_success_when_the_field_gained_the_text(typing_bench) -> None:
    from eva.screen import screen_controller

    typing_bench["install"]()
    observation = screen_controller.type_text("hello", "test")
    assert observation.success
    assert observation.raw_observation["verified"] is True


def test_typing_fails_when_a_character_is_lost_in_transit(typing_bench) -> None:
    """The check that bites. `gui.write` was called with the full string and the
    tool reported `chars: len(text)` regardless -- the count of what was SENT.
    Measured on real hardware, three of six rounds arrived wrong."""
    from eva.screen import screen_controller

    typing_bench["install"](mangle=lambda text: text[:-1])
    observation = screen_controller.type_text("hello", "test")
    assert not observation.success
    assert observation.error == "typed_text_mismatch"
    assert observation.raw_observation["arrived_chars"] == 4


def test_typing_fails_when_characters_arrive_out_of_order(typing_bench) -> None:
    """Two of the three real failures were TRANSPOSITIONS, not drops, so a
    length check alone would have passed them."""
    from eva.screen import screen_controller

    typing_bench["install"](mangle=lambda text: text[1] + text[0] + text[2:])
    observation = screen_controller.type_text("hello", "test")
    assert not observation.success
    assert observation.error == "typed_text_mismatch"


def test_typing_never_echoes_the_text_it_could_not_verify(typing_bench) -> None:
    """`text` is a declared sensitive argument, masked everywhere else. A
    verification failure must not become the one place the value gets printed."""
    from eva.screen import screen_controller

    secret = "hunter2-correct-horse"
    typing_bench["install"](mangle=lambda text: text[:-1])
    observation = screen_controller.type_text(secret, "test")
    haystack = f"{observation.summary} {observation.error} {observation.raw_observation}"
    assert secret not in haystack
    assert secret[:-1] not in haystack


def test_unverifiable_typing_is_not_a_failure(typing_bench) -> None:
    """Most desktop controls expose no value pattern. Reporting those as failures
    would make form_filler stop at the first field of nearly every app."""
    from eva.screen import screen_controller

    typing_bench["install"](readable=False)
    observation = screen_controller.type_text("hello", "test")
    assert observation.success
    assert observation.raw_observation["verified"] is False


def test_typing_over_a_selection_is_not_reported_as_corruption(monkeypatch) -> None:
    """Typing REPLACES a selection rather than appending to it.

    An `after == before + text` check called eight consecutive perfect rounds
    failures -- the false alarm that teaches people to ignore the alarm. A field
    that had everything selected ends up holding only what was typed.
    """
    from eva.screen import screen_controller

    monkeypatch.setattr(screen_controller, "_pyautogui", lambda: (_fake_gui({}), None))
    readings = iter(["old contents", "hello"])
    monkeypatch.setattr(screen_controller, "_focused_value", lambda: next(readings))

    observation = screen_controller.type_text("hello", "test")
    assert observation.success, "replacing a selection was reported as corruption"
    assert observation.raw_observation["verified"] is True


def test_a_field_that_did_not_change_at_all_is_a_failure(monkeypatch) -> None:
    """The narrow case the endswith check would otherwise wave through: a field
    already ending in the typed characters, where nothing arrived."""
    from eva.screen import screen_controller

    monkeypatch.setattr(screen_controller, "_pyautogui", lambda: (_fake_gui({}), None))
    monkeypatch.setattr(screen_controller, "_focused_value", lambda: "77")

    observation = screen_controller.type_text("7", "test")
    assert not observation.success
    assert observation.error == "typed_text_mismatch"


# --------------------------------------------------------------------------
# Window matching: one generic word must not pick a window
# --------------------------------------------------------------------------


def _window(title: str, process: str, executable: str):
    from eva.desktop.windows import WindowInfo

    return WindowInfo(hwnd=1, title=title, process_id=1, process_name=process, executable=executable, visible=True)


def test_a_generic_word_does_not_match_a_window() -> None:
    """`focus the notepad window and type ...` matched the Calculator, because
    every packaged app lives under `C:\\Program Files\\WindowsApps\\...` and the
    single word "window" is inside that path."""
    from eva.desktop.windows import _matches

    calculator = _window(
        "Calculator",
        "CalculatorApp.exe",
        r"C:\Program Files\WindowsApps\Microsoft.WindowsCalculator_11.0\CalculatorApp.exe",
    )
    assert not _matches(calculator, "the notepad window and type nova-uitest-e4c6740a into it.")


def test_the_named_window_still_matches() -> None:
    from eva.desktop.windows import _matches

    notepad = _window("Untitled - Notepad", "Notepad.exe", r"C:\Windows\System32\notepad.exe")
    assert _matches(notepad, "notepad")
    assert _matches(notepad, "untitled - notepad")


def test_a_title_match_outranks_a_path_match() -> None:
    """find_window takes the FIRST hit, so with a flat yes/no the winner was
    whichever window the OS happened to enumerate first."""
    from eva.desktop import windows as windows_module

    calculator = _window("Calculator", "CalculatorApp.exe", r"C:\Program Files\WindowsApps\Calc\CalculatorApp.exe")
    notepad = _window("Untitled - Notepad", "Notepad.exe", r"C:\Windows\System32\notepad.exe")
    windows_module.list_open_windows = lambda: [calculator, notepad]  # type: ignore[assignment]
    try:
        assert windows_module.find_window("notepad")[0].title == "Untitled - Notepad"
    finally:
        import importlib

        importlib.reload(windows_module)


# --------------------------------------------------------------------------
# A window-name argument must not swallow a whole errand
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "the notepad window and type nova-uitest-e4c6740a into it.",
        "notepad then type hello",
        "notepad, type hello",
        "the very long name of a window that is really an instruction in disguise",
    ],
)
def test_compound_arguments_are_not_treated_as_window_names(value: str) -> None:
    from eva.core.fast_command_helpers import _looks_like_an_instruction

    assert _looks_like_an_instruction(value)


@pytest.mark.parametrize("value", ["notepad", "chrome", "untitled - notepad", "vs code", "Calculator"])
def test_real_window_names_still_pass(value: str) -> None:
    from eva.core.fast_command_helpers import _looks_like_an_instruction

    assert not _looks_like_an_instruction(value)


def test_both_copies_of_the_window_prefixes_are_guarded() -> None:
    """The rule is written down twice -- operator_commands runs first and holds
    its own copy of the same prefixes. Guarding one copy changed nothing
    measurable, because the unguarded one is the one that ran."""
    operator = (ROOT / "backend" / "eva" / "core" / "operator_commands.py").read_text(encoding="utf-8")
    fast = (ROOT / "backend" / "eva" / "core" / "fast_commands.py").read_text(encoding="utf-8")
    assert '_window_name_after(text, ("switch to ", "focus "' in operator
    assert "_looks_like_an_instruction(focus_target)" in fast


def test_focus_verification_reads_the_key_the_tool_actually_returns() -> None:
    """`window_active` returns {"window": {"title": ...}}. Reading a top-level
    "title" -- a key it has never had -- made the check report "could not confirm
    which window is in front" on EVERY errand, including ones where the right
    window demonstrably was."""
    source = GUI_PY.read_text(encoding="utf-8")
    body = source.split("def _focus_named_window", 1)[1].split("\ndef ", 1)[0]
    assert '(active or {}).get("window")' in body
    assert 'tools.run("window_focus", query=wanted)' in body, (
        "focus still targets the matched WORD rather than the window it matched"
    )


# --------------------------------------------------------------------------
# The cache-buster has to reach the browser that needs it
# --------------------------------------------------------------------------


def test_index_is_not_cacheable() -> None:
    """Phase 102 stamped the assets and left the document carrying the stamps
    served with no Cache-Control, no ETag and no Last-Modified -- so a browser
    kept the old index.html, and with it the old asset URLs, indefinitely.
    Measured: a real browser still running the pre-Phase-102 app.js."""
    from fastapi.testclient import TestClient

    from eva.main import create_app

    with TestClient(create_app()) as client:
        response = client.get("/")
        assert response.status_code == 200
        directive = response.headers.get("cache-control", "")
        assert "no-cache" in directive, "index.html is still freely cacheable: " + repr(directive)


def test_stamped_assets_are_still_allowed_to_cache() -> None:
    """The point of stamping is that the assets CAN be cached. A blanket
    no-store would trade one bug for a slower app."""
    source = MAIN_PY.read_text(encoding="utf-8")
    index_body = source.split('@app.get("/", include_in_schema=False)', 1)[1].split("app.mount", 1)[0]
    assert "no-store" not in index_body
