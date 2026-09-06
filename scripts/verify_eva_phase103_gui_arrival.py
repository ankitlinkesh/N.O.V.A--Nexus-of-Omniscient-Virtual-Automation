"""Standalone verifier for Phase 103 (the GUI arc that never arrived).

Phases 56-60 and 96 built desktop clicking and typing: accessibility-tree
grounding, a DPI-correct click, a confidence floor that declines rather than
guessing, an ambiguity refusal, a bounded `gui:` scope that makes `screen.*`
visible to the planner for exactly one errand. Every piece was tested. Several
were validated live on real hardware. None of it had ever worked through the
chat UI or the API, and nothing noticed.

The scope lives in a ContextVar. `_run_gui_task` opened it and then called
`run_async`, which -- whenever a loop is already running, i.e. always inside a
FastAPI handler -- submits the coroutine to a ThreadPoolExecutor. A worker
thread does not inherit the caller's context. So the scope was set in the
request thread and the entire task ran in another one with the scope SHUT:

  * `screen.*` was never offered to the planner;
  * the action budget never decremented, so every errand closed with a tidy
    `0/12 actions used` rather than failing loudly;
  * asked to type into Notepad the model answered, truthfully, that it had no
    tool for it -- and in one measured run reached instead for `web.type`, the
    BROWSER automation tool, gate-classified EXTERNAL_POST, for an errand about
    a desktop application.

Every test and every live validation had driven `registry.run` in-process, where
the ContextVar IS in scope. A green suite proved the mechanism and never its
arrival -- this project's signature defect, now in its ninth costume, and the
reason the load-bearing check here asserts that the screen tools are visible at
the point `run_agentic_task` asks for them, on the far side of the thread hop,
rather than that a scope can be opened.

`role_scope` had the shape right the whole time: it is opened inside
`run_delegated`, on the thread that does the work. The fix mirrors it rather
than teaching `run_async` to copy contexts, which would change the rules for
five other callers to fix one.

Four more defects found by the same drive, each verified from OUTSIDE the
system's own account of itself -- Notepad's text and Calculator's display read
through UIAutomation, with the same read run before the errand so a passing
check could actually fail:

  * **Typing corrupted text in three of six rounds and reported success every
    time.** `gui.write(text, interval=0.01)` dropped a character once and
    TRANSPOSED a pair twice -- the keystrokes were racing, not merely being
    lost -- while the tool returned `{"chars": len(text)}`, the count of what
    was SENT. `form_filler` types passwords through this path.
  * **`app.focus` fuzzy-matched an arbitrary sentence to whatever window was
    open.** "focus the notepad window and type NOVA-... into it" was taken whole
    as a window name; the single word "window" matched the Calculator through
    the `WindowsApps` in its executable path; the typing clause was discarded;
    the reply was "Done, focused Calculator."
  * **The focus verification could never confirm anything.** It read
    `active["title"]` from `window_active`, which returns
    `{"window": {"title": ...}}` -- a key it has never had -- so `actual` was
    always empty and every errand reported "could not confirm which window is in
    front", including ones where the right window demonstrably was. And it
    focused by the matched WORD rather than the window it had just chosen,
    deciding twice from different evidence.
  * **Phase 102's cache-buster could not reach a returning browser.** `/` was
    served with no Cache-Control, no ETag and no Last-Modified, so the document
    CARRYING the stamps was itself cached indefinitely. Measured: a real browser
    still running the pre-Phase-102 app.js while the server served the new
    stamp.

Source-level checks here are mutation-tested against an in-memory copy: the
mutation is applied, the check must go red, and the original is never written.
The behavioural checks -- scope arrival across the real thread hop, and typing
verification driven with a fault injected into the keystroke path -- are driven
rather than mutated, because mutating them would only restate the source text
they deliberately do not read.
Fully offline: no network, no LLM, no provider, no browser, no real input.
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

GUI_PY = BACKEND / "eva" / "core" / "fast_command_gui.py"
OPERATOR_PY = BACKEND / "eva" / "core" / "operator_commands.py"
FAST_PY = BACKEND / "eva" / "core" / "fast_commands.py"
WINDOWS_PY = BACKEND / "eva" / "desktop" / "windows.py"
MAIN_PY = BACKEND / "eva" / "main.py"
CONTROLLER_PY = BACKEND / "eva" / "screen" / "screen_controller.py"


def check(value: object, message: str) -> None:
    if not value:
        raise AssertionError(message)


def check_raises(fn, message: str) -> None:
    """A check that cannot fail is not a check -- so prove this one can."""
    try:
        fn()
    except AssertionError:
        return
    raise AssertionError("MUTATION SURVIVED: " + message)


# ------------------------------------------------- the checks, over sources


def _function_body(source: str, header: str) -> str:
    check(header in source, header + " not found")
    return source.split(header, 1)[1].split("\ndef ", 1)[0]


def assert_scope_is_opened_inside_the_coroutine(gui: str) -> None:
    body = _function_body(gui, "async def _run_task_in_scope")
    check(
        "with open_gui_scope(" in body,
        "the GUI scope is not opened inside the coroutine that runs the task, so the worker "
        "thread run_async hands it to cannot see it and screen.* is never offered",
    )
    check("await run_agentic_task(" in body, "the task is not awaited inside the scope")
    # Scoped to the body on purpose. Searching the whole file matches the
    # `with open_gui_scope(...)` that the BROKEN shape leaves behind in
    # `_run_gui_task`, so a file-wide search passes against the bug.
    check(
        gui.count("with open_gui_scope(") == 1,
        "a second GUI scope is opened outside the coroutine, where the worker thread cannot "
        "see it -- which is the whole defect",
    )


def assert_spend_is_read_inside_the_scope(gui: str) -> None:
    body = _function_body(gui, "async def _run_task_in_scope")
    check(
        "actions_used()" in body and "scope.max_actions" in body,
        "the action spend is read outside the scope, where it reports the request thread's "
        "empty scope -- which is why the broken build printed a tidy 0/12 instead of failing",
    )


def assert_focus_reads_the_key_the_tool_returns(gui: str) -> None:
    body = _function_body(gui, "def _focus_named_window")
    check(
        '(active or {}).get("window")' in body,
        "focus verification still reads a top-level `title` from window_active, a key it has "
        "never had, so it can only ever report that it could not tell",
    )
    check(
        'tools.run("window_focus", query=wanted)' in body,
        "focus still targets the matched WORD rather than the window it matched, deciding "
        "twice from different evidence",
    )


def assert_generic_words_cannot_pick_a_window(windows: str) -> None:
    check("_GENERIC_WORDS" in windows, "no generic-word list guards the single-word fallback")
    for word in ("window", "windows", "the", "open", "type"):
        check(
            f'"{word}"' in windows.split("_GENERIC_WORDS", 1)[1].split(")", 1)[0],
            f"'{word}' is not treated as too generic to identify a window",
        )
    body = _function_body(windows, "def _match_score")
    check(
        "basename" in body,
        "single words are still matched against the full executable PATH, which every "
        "packaged app shares -- `WindowsApps` is how 'window' matched the Calculator",
    )


def assert_both_window_prefix_copies_are_guarded(operator: str, fast: str) -> None:
    check(
        '_window_name_after(text, ("switch to ", "focus "' in operator,
        "operator_commands still takes everything after `focus ` as a window name -- and it "
        "runs FIRST, so guarding only the fast_commands copy changes nothing measurable",
    )
    check(
        "_looks_like_an_instruction(focus_target)" in fast,
        "fast_commands still takes a whole compound errand as a window name",
    )


def assert_typing_reports_what_arrived(controller: str) -> None:
    body = _function_body(controller, "def type_text")
    check("_focused_value()" in body, "typing never reads the field back")
    check(
        "typed_text_mismatch" in body,
        "typing has no way to report that what arrived is not what was sent",
    )
    check(
        '"verified"' in body,
        "typing does not distinguish a verified type from one it could not check",
    )
    for echo in ("{payload}", "{text}", "+ payload", "+ text"):
        check(
            echo not in body.split("typed_text_mismatch", 1)[0].split("raw[\"arrived_chars\"]", 1)[-1],
            "the failure path may echo the typed text, which is a declared sensitive argument",
        )


def assert_index_is_not_cacheable(main: str) -> None:
    body = main.split('@app.get("/", include_in_schema=False)', 1)[1].split("app.mount", 1)[0]
    check(
        "Cache-Control" in body and "no-cache" in body,
        "index.html is served with no cache directive, so the document CARRYING the asset "
        "stamps is itself cached indefinitely and the cache-buster cannot arrive",
    )
    check(
        "no-store" not in body,
        "a blanket no-store trades the stale-asset bug for a slower app; the stamped assets "
        "are supposed to be cacheable, which is the entire point of stamping them",
    )


# ------------------------------------------------------ the driven checks


def drive_scope_arrival() -> tuple[bool, list[str]]:
    """Are the screen tools visible where the planner actually asks for them?

    Driven, not mutated: the question is what happens on the far side of
    `run_async`'s thread hop, which no reading of the source can answer.
    """
    from eva.core import fast_command_gui
    from eva.screen.gui_scope import gui_scope_open
    from eva.tools.registry import ToolRegistry

    registry = ToolRegistry()
    seen: dict = {}

    async def fake_task(goal, context):
        seen["open"] = gui_scope_open()
        seen["tools"] = sorted(
            spec["name"] for spec in registry.planner_specs() if spec["name"].startswith("screen.")
        )
        return {"final_response": "done", "tools_executed": []}

    import eva.agent.runner as runner_module
    import eva.screen.grounding as grounding_module

    real_task = runner_module.run_agentic_task
    real_ready = fast_command_gui._readiness
    real_focus = fast_command_gui._focus_named_window
    real_describe = grounding_module.describe_visible
    runner_module.run_agentic_task = fake_task
    fast_command_gui._readiness = lambda: []
    fast_command_gui._focus_named_window = lambda goal, tools: None
    grounding_module.describe_visible = lambda limit=60: {}
    try:

        async def as_a_request_handler():
            # A loop is running here, which is what pushes run_async onto a
            # worker thread. The production shape, not a reconstruction of it.
            return fast_command_gui._run_gui_task("click the seven button", registry, None, None, None)

        asyncio.run(as_a_request_handler())
    finally:
        runner_module.run_agentic_task = real_task
        fast_command_gui._readiness = real_ready
        fast_command_gui._focus_named_window = real_focus
        grounding_module.describe_visible = real_describe

    return bool(seen.get("open")), list(seen.get("tools") or [])


def drive_typing_verification() -> None:
    """Type through the real path with a fault injected into the keystrokes.

    Nothing here touches real input: the pyautogui shim and the field read are
    both replaced, so the only thing simulated is the corruption.
    """
    from eva.screen import screen_controller

    real_gui = screen_controller._pyautogui
    real_read = screen_controller._focused_value

    def bench(mangle=None, readable=True):
        state = {"typed": ""}

        class FakeGui:
            def write(self, text, interval=0.0):
                state["typed"] = mangle(text) if mangle else text

        screen_controller._pyautogui = lambda: (FakeGui(), None)
        screen_controller._focused_value = (lambda: state["typed"]) if readable else (lambda: None)

    try:
        bench()
        clean = screen_controller.type_text("hello", "verifier")
        check(clean.success, "an intact type was reported as a failure")
        check(clean.raw_observation.get("verified") is True, "an intact type was not marked verified")

        bench(mangle=lambda text: text[:-1])
        dropped = screen_controller.type_text("hello", "verifier")
        check(not dropped.success, "a DROPPED character was reported as a successful type")
        check(dropped.error == "typed_text_mismatch", "the drop was not reported as a mismatch")

        bench(mangle=lambda text: text[1] + text[0] + text[2:])
        swapped = screen_controller.type_text("hello", "verifier")
        check(not swapped.success, "TRANSPOSED characters were reported as a successful type")

        secret = "hunter2-correct-horse"
        bench(mangle=lambda text: text[:-1])
        leaky = screen_controller.type_text(secret, "verifier")
        haystack = f"{leaky.summary} {leaky.error} {leaky.raw_observation}"
        check(secret not in haystack, "the failure summary echoed the typed text")
        check(secret[:-1] not in haystack, "the failure summary echoed what arrived")

        bench(readable=False)
        blind = screen_controller.type_text("hello", "verifier")
        check(blind.success, "a type that simply could not be checked was reported as a failure")
        check(
            blind.raw_observation.get("verified") is False,
            "an unverifiable type claims to have been verified",
        )
    finally:
        screen_controller._pyautogui = real_gui
        screen_controller._focused_value = real_read


def drive_window_matching() -> None:
    from eva.desktop.windows import WindowInfo, _matches

    calculator = WindowInfo(
        hwnd=1,
        title="Calculator",
        process_id=1,
        process_name="CalculatorApp.exe",
        executable=r"C:\Program Files\WindowsApps\Microsoft.WindowsCalculator_11.0\CalculatorApp.exe",
        visible=True,
    )
    notepad = WindowInfo(
        hwnd=2,
        title="Untitled - Notepad",
        process_id=2,
        process_name="Notepad.exe",
        executable=r"C:\Windows\System32\notepad.exe",
        visible=True,
    )
    check(
        not _matches(calculator, "the notepad window and type nova-uitest-e4c6740a into it."),
        "a sentence still matches the Calculator through the `WindowsApps` in its path -- the "
        "exact match that focused the wrong window and answered 'Done, focused Calculator.'",
    )
    check(_matches(notepad, "notepad"), "the named window no longer matches")
    check(_matches(notepad, "untitled - notepad"), "an exact title no longer matches")


def main() -> int:
    gui = GUI_PY.read_text(encoding="utf-8")
    operator = OPERATOR_PY.read_text(encoding="utf-8")
    fast = FAST_PY.read_text(encoding="utf-8")
    windows = WINDOWS_PY.read_text(encoding="utf-8")
    main_py = MAIN_PY.read_text(encoding="utf-8-sig")
    controller = CONTROLLER_PY.read_text(encoding="utf-8")

    # ------------------------------------------------------- source checks
    assert_scope_is_opened_inside_the_coroutine(gui)
    check_raises(
        lambda: assert_scope_is_opened_inside_the_coroutine(
            gui.replace("with open_gui_scope(goal) as scope:", "if True:  # scope hoisted out")
        ),
        "the scope-placement check passes with the scope no longer opened inside the coroutine",
    )
    # The load-bearing mutation: the broken shape did not DELETE the scope, it
    # moved it outward and left a `with open_gui_scope(...)` in the file. A
    # file-wide search for that string is green against the bug.
    check_raises(
        lambda: assert_scope_is_opened_inside_the_coroutine(
            gui.replace(
                "    result, spent, budget = run_async(",
                "    with open_gui_scope(goal):\n        result, spent, budget = run_async(",
            )
        ),
        "a scope opened OUTSIDE the coroutine as well as inside it survives the check, so the "
        "pre-103 shape would pass",
    )

    assert_spend_is_read_inside_the_scope(gui)
    check_raises(
        lambda: assert_spend_is_read_inside_the_scope(gui.replace("actions_used(), scope.max_actions", "0, 12")),
        "the spend check passes when the budget is no longer read from the live scope",
    )

    assert_focus_reads_the_key_the_tool_returns(gui)
    check_raises(
        lambda: assert_focus_reads_the_key_the_tool_returns(
            gui.replace('(active or {}).get("window")', '(active or {}).get("titel")')
        ),
        "focus verification passes while reading a key window_active does not return",
    )
    check_raises(
        lambda: assert_focus_reads_the_key_the_tool_returns(
            gui.replace('tools.run("window_focus", query=wanted)', 'tools.run("window_focus", query=word)')
        ),
        "focusing by the matched WORD rather than the matched window survives the check",
    )

    assert_generic_words_cannot_pick_a_window(windows)
    check_raises(
        lambda: assert_generic_words_cannot_pick_a_window(windows.replace('"window", "windows",', "")),
        "'window' being absent from the generic-word list survives the check",
    )
    check_raises(
        lambda: assert_generic_words_cannot_pick_a_window(windows.replace("basename", "fullpath_")),
        "matching single words against the whole executable path survives the check",
    )

    assert_both_window_prefix_copies_are_guarded(operator, fast)
    check_raises(
        lambda: assert_both_window_prefix_copies_are_guarded(
            operator.replace('_window_name_after(text, ("switch to ", "focus "', '_after_prefix(text, ("switch to ", "focus "'),
            fast,
        ),
        "the FIRST dispatcher losing its guard survives the check -- the copy that actually ran",
    )
    check_raises(
        lambda: assert_both_window_prefix_copies_are_guarded(
            operator, fast.replace("_looks_like_an_instruction(focus_target)", "focus_target")
        ),
        "the fast-command copy losing its guard survives the check",
    )

    assert_typing_reports_what_arrived(controller)
    check_raises(
        lambda: assert_typing_reports_what_arrived(controller.replace("_focused_value()", "None  # no readback")),
        "typing verification passes when the field is never read back",
    )
    check_raises(
        lambda: assert_typing_reports_what_arrived(controller.replace("typed_text_mismatch", "ok_anyway")),
        "typing passes with no way to report that what arrived is not what was sent",
    )

    assert_index_is_not_cacheable(main_py)
    check_raises(
        lambda: assert_index_is_not_cacheable(main_py.replace('"Cache-Control": "no-cache, must-revalidate"', "")),
        "the index cache check passes with no cache directive at all",
    )
    check_raises(
        lambda: assert_index_is_not_cacheable(main_py.replace("no-cache, must-revalidate", "no-store")),
        "a blanket no-store survives the check",
    )

    # ----------------------------------------------------- driven checks
    scope_open, screen_tools = drive_scope_arrival()
    check(
        scope_open,
        "the GUI task ran with the scope SHUT. This is the defect: the scope is a ContextVar, "
        "run_async hands the task to a worker thread, and a worker thread does not inherit the "
        "caller's context -- so every `gui:` errand ran with screen.* invisible while the tests "
        "that drove registry.run in-process stayed green.",
    )
    for tool in ("screen.click", "screen.type_text"):
        check(
            tool in screen_tools,
            f"{tool} is not offered to the planner at the point it asks -- the mechanism exists "
            "and does not arrive, which is this project's signature defect",
        )

    drive_typing_verification()
    drive_window_matching()

    # ---------------------------------------------------------- registration
    import verify_eva_all

    name = "verify_eva_phase103_gui_arrival.py"
    check(name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 103 verifier")
    check(name in verify_eva_all.QUICK_VERIFIERS, "quick profile missing the Phase 103 verifier")
    check(name in verify_eva_all.VERIFIER_DESCRIPTORS, "master descriptor missing the Phase 103 verifier")

    print(
        "PASS: Phase 103 GUI arrival. The desktop clicking and typing built across Phases 56-60 "
        "and 96 had never once worked through the chat UI or the API: the `gui:` scope lives in "
        "a ContextVar, run_async hands the task to a worker thread, and a worker thread does not "
        "inherit the caller's context -- so every errand ran with screen.* invisible, the budget "
        "frozen at 0/12, and the planner truthfully answering that it could not type, once "
        "reaching for web.type (the BROWSER tool) to act on a desktop app. Every test and every "
        "live validation had driven registry.run in-process, where the ContextVar is in scope: a "
        "green suite proved the mechanism and never its arrival. The scope is now opened on the "
        "thread that runs the task, the way role_scope always was, and the load-bearing check "
        "here asserts the tools are visible where the planner asks rather than that a scope can "
        "be opened. Alongside it: typing reads the field back and reports what ARRIVED instead "
        "of the character count it sent (three of six measured rounds were corrupted -- one drop "
        "and two transpositions -- every one reported as success); a generic word like 'window' "
        "can no longer match a window through the WindowsApps in its path; a compound errand is "
        "no longer swallowed whole as a window name by EITHER of the two dispatchers that "
        "accepted one; focus verification reads the key window_active actually returns, so it "
        "can confirm something for the first time; and the index carries a cache directive, "
        "without which Phase 102's derived stamp could not reach a returning browser. Source "
        "checks mutation-tested; scope arrival, typing verification and window matching driven."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
