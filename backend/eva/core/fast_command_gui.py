"""Typed-console entry point for agent-driven GUI control (Phase 96).

    gui: pause the music
    gui status

WHY THIS IS CONSOLE-ONLY AND NOT A PLANNER TOOL:

This is the command that opens the door. Everything else in the GUI stack --
grounding, the confidence floor, the ambiguity refusal, the permission gate --
still runs exactly as before; what a scope changes is only whether the planner
can *see* `screen.*` at all.

So the whole safety argument reduces to one question: who can open a scope? The
answer has to be "a person typing", because the alternative is that a web page,
a window title or a tool result can decide the agent should start clicking --
which is precisely the boundary `threat_defense/authorization.py` exists to
hold ("untrusted content proposes, it never authorizes"). Rule creation (54),
form filling (58), delegation (73) and the bounded command runner (74) are all
console-only for this same reason; this is one more entry in that list, not a
new kind of trust.

The prefix is `gui:` with a colon, chosen the way Phase 74 chose `$ `: it
cannot occur at the start of ordinary prose, so this cannot begin swallowing
requests meant for the LLM. A refactor that *starts* handling a phrase is as
much a regression as one that stops.

What the scope does NOT do: it does not lower the gate. `screen.type_text`,
`screen.press` and `screen.hotkey` remain confirm-class and still stop to ask,
so a GUI task that needs to type will pause for approval exactly as it does
today. Clicking flows, keystrokes ask. That is a deliberate v1 boundary rather
than an oversight -- generalising one-approval-for-a-sequence (the
`screen.submit_form` model) is a bigger change and belongs in its own phase.
"""

from __future__ import annotations

import time
from typing import Any

from ..mcp.runner import run_async
from ..screen.gui_scope import DEFAULT_MAX_ACTIONS, actions_used, open_gui_scope
from .fast_command_helpers import _after_prefix

# A control is named "Seven" or "New tab". Anything longer is a document title,
# a tab title or a sentence -- i.e. content, which must not ride in the prompt.
_MAX_LABEL_CHARS = 40
_MAX_LABELS = 25


def _readiness() -> list[str]:
    """What is actually switched on, in the order it would bite."""
    from ..screen.grounding import grounding_enabled
    from ..screen.screen_controller import real_input_enabled

    notes: list[str] = []
    if not grounding_enabled():
        notes.append(
            "- EVA_GUI_GROUNDING_ENABLED is off, so I cannot find controls by name and every click will refuse."
        )
    if not real_input_enabled():
        notes.append(
            "- EVA_ENABLE_REAL_INPUT is off, so nothing will physically move. I can plan and refuse, not act."
        )
    try:
        import uiautomation  # noqa: F401
    except Exception:
        notes.append(
            "- the `uiautomation` package is not importable, so the accessibility tree will read as empty."
        )
    return notes


def _status_report() -> str:
    lines = ["GUI control status", ""]
    notes = _readiness()
    if notes:
        lines.append("Not ready:")
        lines.extend(notes)
    else:
        lines.append("Ready: grounding on, real input on, accessibility tree available.")
    lines += [
        "",
        f"A `gui:` task opens a scope for up to {DEFAULT_MAX_ACTIONS} GUI actions, then closes it.",
        "Inside the scope the planner may click, scroll and observe; typing and hotkeys still ask first.",
        "Outside a scope the screen tools are invisible to the planner, which is the default.",
        "",
        "Usage: gui: <what you want done>    e.g.  gui: click the seven button",
    ]
    return "\n".join(lines)


_STOPWORDS = frozenset(
    {
        "the", "and", "then", "click", "press", "type", "open", "close", "in", "on", "to", "a", "an",
        "my", "please", "window", "button", "app", "into", "with", "of", "it", "this", "that", "for",
    }
)


def _focus_named_window(goal: str, tools: Any) -> str | None:
    """Focus an open window the goal names, and report which. None if no match.

    Deliberately conservative: it only ever focuses a window that is ALREADY
    open and whose title or process name contains a word from the goal. It never
    launches anything, and a goal that names nothing recognisable leaves the
    foreground exactly as the user left it.
    """
    words = [
        w.strip(".,!?'\"")
        for w in str(goal or "").lower().split()
        if len(w.strip(".,!?'\"")) >= 3 and w.strip(".,!?'\"") not in _STOPWORDS
    ]
    if not words:
        return None
    try:
        listing = tools.run("window_list")
        windows = listing.get("windows") or []
    except Exception:
        return None

    for window in windows:
        title = str(window.get("title") or "").lower()
        process = str(window.get("process_name") or "").lower()
        haystack = f"{title} {process}"
        for word in words:
            if word in haystack:
                wanted = str(window.get("title") or word)
                try:
                    # Focus the window that MATCHED, not the word that matched
                    # it. Passing the bare word sent the query back through
                    # find_window a second time, where it could easily land on a
                    # different window than the one just chosen here -- the
                    # decision was made twice, from different evidence, and only
                    # the second one moved the foreground.
                    tools.run("window_focus", query=wanted)
                except Exception:
                    return None
                # VERIFY, do not assume. `focus_window_safe` reports success from
                # its own call, but this machine's foreground lock can refuse
                # SetForegroundWindow (the Phase 64/68 finding), leaving the old
                # window in front while the call looks fine. Reading the controls
                # of the WRONG window and handing them to the planner as "what
                # you can click" is worse than not focusing at all, so the caller
                # is told what actually ended up in front.
                time.sleep(0.4)
                try:
                    active = tools.run("window_active")
                    # `window_active` returns {"ok":..., "window": {"title":...}}.
                    # Reading `active["title"]` -- a key it has never had -- meant
                    # `actual` was ALWAYS empty, so this reported "could not
                    # confirm which window is in front" on every single errand,
                    # including ones where the right window was demonstrably in
                    # front. The fail-safe below was therefore the only branch
                    # that ever ran, and the verification was decorative. The
                    # top-level key is still read as a fallback rather than
                    # replaced: the point is to read every name the source
                    # actually emits, which is how this class of bug was missed
                    # twice before.
                    window_payload = (active or {}).get("window") or {}
                    actual = str(window_payload.get("title") or (active or {}).get("title") or "")
                except Exception:
                    actual = ""
                # UNKNOWN IS NOT SUCCESS. The first version only reported a
                # mismatch when `actual` was truthy, so a `window_active` that
                # returned no title -- which is what happens here -- silently
                # counted as "focused", and the console then offered the planner
                # the WRONG window's controls while claiming it had focused the
                # right one. Verification that treats "I could not tell" as "yes"
                # is not verification; it is the honest-effects bug this project
                # has fixed four times.
                if not actual:
                    return "!unknown (could not confirm which window is in front)"
                if actual.strip().lower() != wanted.strip().lower():
                    return f"!{actual}"
                return wanted
    return None


async def _run_task_in_scope(
    goal: str,
    grounded_goal: str,
    session_context: Any,
    memory: Any,
    session_id: str | None,
) -> tuple[dict, int, int]:
    """Open the GUI scope on the thread that actually runs the task.

    The scope wraps the ENTIRE task, so every planner iteration inside it sees
    the GUI tools and every iteration outside it does not. Opening it around the
    run (rather than around a single call) is what lets the agent observe,
    decide and act as one errand.

    Phase 103, and this placement IS the fix. The scope lives in a ContextVar.
    `run_async` hands the coroutine to a ThreadPoolExecutor whenever a loop is
    already running -- always true inside a FastAPI handler -- and a worker
    thread does not inherit the caller's context. Opening the scope around
    `run_async` therefore set it in the request thread and ran the whole task in
    another one with the scope SHUT: `screen.*` was never offered to the
    planner, the budget never decremented (every errand reported `0/12 actions
    used`), and the model answered, truthfully, that it had no way to type or
    click. In one measured run it reached for `web.click` -- the BROWSER
    automation tool, gate-classified EXTERNAL_POST -- to press a Calculator
    button. Phases 56-60 and 96 were unreachable through the chat UI and the
    API for as long as they had existed, while every test and every live
    validation drove `registry.run` in-process, where the ContextVar IS in
    scope. A green suite proved the mechanism and never its arrival.

    `role_scope` had the shape right all along: it is opened inside
    `run_delegated`, on the thread that does the work. This mirrors it rather
    than teaching `run_async` to copy contexts, which would change the rules for
    five other callers to fix one.

    The spend and the budget are read INSIDE the scope and returned out. Read
    outside, `actions_used()` reports the request thread's empty scope -- which
    is why the broken build printed a tidy `0/12` instead of failing loudly.
    """
    from ..agent.runner import run_agentic_task

    with open_gui_scope(goal) as scope:
        result = await run_agentic_task(
            grounded_goal,
            {
                "session_id": session_id,
                "session_context": session_context,
                "memory": memory,
            },
        )
        return result, actions_used(), scope.max_actions


def _run_gui_task(goal: str, tools: Any, session_context: Any, memory: Any, session_id: str | None) -> str:
    notes = _readiness()
    if notes:
        return (
            "I can't drive the GUI right now:\n"
            + "\n".join(notes)
            + "\n\nNothing was attempted. Type `gui status` after fixing that."
        )

    # Hand the planner the control labels UP FRONT rather than making it call
    # screen.observe to discover them. Two reasons, one practical and one about
    # friction. Practical: grounding matches on a control's ACCESSIBLE NAME, and
    # models guess the visible glyph -- the first live run asked for "7" when the
    # Calculator button is named "Seven", found nothing, and burned its steps.
    # Friction: screen.observe is override-class because it captures pixels, so
    # telling the planner to always observe first would stall every GUI task on
    # the heaviest approval in the system. This read is local, tree-only, takes no
    # screenshot and sends nothing anywhere -- and it is the same tree that
    # screen.click already walks on every click. Listing what the click path is
    # about to search is not a new disclosure; it is the one the user asked for
    # by typing `gui:`.
    from ..screen.grounding import describe_visible

    # Focus the window the goal names, BEFORE reading the tree. Grounding always
    # reads the FOREGROUND window, so `gui: click Seven in Calculator` typed
    # while Chrome is in front read Chrome's controls and offered the planner a
    # list that could not satisfy the goal. Focusing first is also why the
    # privacy filter matters less in practice: a named target app's tree is its
    # own controls, not a browser's tab titles.
    focused = _focus_named_window(goal, tools)

    try:
        seen = describe_visible(limit=60)
    except Exception:
        seen = {}
    # ONLY short labels, and this is a privacy filter rather than a tidiness one.
    # The first version injected every label, and a live run against Chrome put
    # the user's Gmail address, their search query and a YouTube title into the
    # goal -- which then rides in EVERY planner call and, in that same run, was
    # copied into an `analyze_screen(question=...)` argument bound for Google.
    # Filtering by ROLE does not fix it: Chrome's per-tab "Close"/"Mute tab"
    # buttons carry the tab title inside their accessible NAME. Length is the
    # crude but effective discriminator -- a control is called "Seven" or "New
    # tab"; a label long enough to be a sentence is content, not a control.
    controls = [
        label
        for label in (str(t.get("label") or "").strip() for t in (seen.get("ui_targets") or []))
        if label and len(label) <= _MAX_LABEL_CHARS
    ]
    if controls:
        grounded_goal = (
            f"{goal}\n\n"
            # Deliberately avoids the words "screen"/"screenshot". The planner's
            # `_forced_decision` matches screen-request language in the GOAL TEXT
            # before any tool list is consulted, so scaffolding that merely
            # mentions the screen made every GUI task force a cloud vision call --
            # this text describing itself was enough to trigger it.
            f"Controls you can click right now, by exact label:\n"
            + "\n".join(f"- {label}" for label in controls[:_MAX_LABELS])
            + "\n\nUse these only to choose a click target, and never copy them into another tool's arguments."
        )
    else:
        grounded_goal = (
            f"{goal}\n\n"
            "(No named controls could be read from the foreground window. It may be an app that exposes "
            "no accessibility tree, so clicking by label will not work here -- say so rather than guessing.)"
        )

    result, spent, budget = run_async(_run_task_in_scope(goal, grounded_goal, session_context, memory, session_id))

    reply = str(result.get("final_response") or "").strip() or "I finished without producing an answer."
    tools = result.get("tools_executed") or []
    gui_tools = [t for t in tools if str(t).startswith("screen.")]

    trailer = [f"(GUI scope closed — {spent}/{budget} actions used"]
    if focused:
        trailer.append(
            f", focus NOT changed (still {focused[1:]})" if focused.startswith("!") else f", focused: {focused}"
        )
    if gui_tools:
        trailer.append(f", GUI actions: {', '.join(gui_tools)}")
    trailer.append(".)")
    return reply + "\n\n" + "".join(trailer)


def maybe_handle_gui_command(
    normalized: str,
    original: str,
    tools: Any,
    session_context: Any = None,
    memory: Any = None,
    session_id: str | None = None,
) -> tuple[str, str] | None:
    """`gui status` and `gui: <goal>`; None for anything else."""
    if normalized in {"gui status", "gui mode status", "gui control status"}:
        return _status_report(), "fast-command"

    goal = _after_prefix(original, ("gui: ", "gui : "))
    if goal is None:
        return None
    goal = goal.strip()
    if not goal:
        return (
            "Tell me what to do, e.g. `gui: click the seven button`. "
            "Type `gui status` to see whether GUI control is switched on.",
            "fast-command",
        )
    return _run_gui_task(goal, tools, session_context, memory, session_id), "fast-command"
