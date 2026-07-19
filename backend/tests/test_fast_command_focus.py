"""Executable spec for the typed-console "focus"/"switch to" command wiring
(Phase 64).

``app.focus`` was registered (allow-class, SAFE_LOCAL_UI) but was reachable
from nowhere in backend/eva -- not in planner_specs(), not called by any
fast-command, not called internally. This wires it into the one console
command that already existed for the same underlying capability: "focus X" /
"switch to X" / "go to window X" / "bring up X", which used to route to the
planner-visible window_focus tool. Both tools ultimately call the same
eva.desktop.windows.focus_window, so redirecting the trusted-console command
to the console/internal-scoped tool is a behavior-preserving redirect for the
user, while finally giving app.focus a real caller.

Deliberately NOT covered here: app.focus must stay OUT of planner_specs() --
see test_planner_reachability.py / the registry's own planner_specs()
allowlist for that invariant; this file only exercises the console path.
"""

from __future__ import annotations

from eva.core.fast_commands import maybe_handle_fast_command
from eva.tools.registry import ToolRegistry


class DryRegistry(ToolRegistry):
    """A REAL ToolRegistry (so every other method/attribute maybe_handle_fast_command
    might touch keeps working) with app.focus intercepted before it would
    otherwise call eva.desktop.windows.focus_window for real. Mirrors
    scripts/verify_desktop_agent_core.py's DryRegistry pattern."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[dict] = []

    def run(self, name, **kwargs):
        self.calls.append({"tool": name, "args": dict(kwargs)})
        if name == "app.focus":
            query = str(kwargs.get("query", "")).strip().lower()
            matched = query == "chrome"
            payload = {
                "ok": matched,
                "focused": matched,
                "verified": matched,
                "window": {"title": "Google Chrome", "process_name": "chrome.exe"},
                "active_window": (
                    {"title": "Google Chrome", "process_name": "chrome.exe"}
                    if matched
                    else {"title": "Untitled - Notepad", "process_name": "notepad.exe"}
                ),
            }
            if not matched:
                payload["error"] = "focus_failed"
            return payload
        return super().run(name, **kwargs)


# -- app.focus is actually invoked, with the right query --------------------


def test_focus_app_routes_to_app_focus_tool():
    registry = DryRegistry()
    reply = maybe_handle_fast_command("focus chrome", registry, {})

    assert reply is not None
    assert registry.calls, "no tool was called at all"
    assert registry.calls[-1]["tool"] == "app.focus", (
        f"'focus chrome' must route through app.focus (console/internal-scoped), not window_focus "
        f"(planner-visible) or anything else: {registry.calls}"
    )
    assert registry.calls[-1]["args"].get("query") == "chrome"


def test_focus_window_prefix_extracts_the_app_not_the_word_window():
    """'focus window chrome' must extract 'chrome', not 'window chrome' --
    "focus window " has to be checked before the bare "focus " prefix."""
    registry = DryRegistry()
    maybe_handle_fast_command("focus window chrome", registry, {})

    assert registry.calls[-1]["tool"] == "app.focus"
    assert registry.calls[-1]["args"].get("query") == "chrome", (
        f"expected query='chrome', got {registry.calls[-1]['args']!r}"
    )


def test_switch_to_synonym_also_routes_to_app_focus():
    registry = DryRegistry()
    maybe_handle_fast_command("switch to chrome", registry, {})

    assert registry.calls[-1]["tool"] == "app.focus"
    assert registry.calls[-1]["args"].get("query") == "chrome"


def test_go_to_window_synonym_also_routes_to_app_focus():
    registry = DryRegistry()
    maybe_handle_fast_command("go to window chrome", registry, {})

    assert registry.calls[-1]["tool"] == "app.focus"
    assert registry.calls[-1]["args"].get("query") == "chrome"


def test_bring_up_synonym_also_routes_to_app_focus():
    registry = DryRegistry()
    maybe_handle_fast_command("bring up chrome", registry, {})

    assert registry.calls[-1]["tool"] == "app.focus"
    assert registry.calls[-1]["args"].get("query") == "chrome"


# -- the reply is honest about the (now honest) tool result -----------------


def test_focus_success_reply_says_done():
    registry = DryRegistry()
    reply = maybe_handle_fast_command("focus chrome", registry, {})

    assert reply is not None
    text, source = reply
    assert source == "desktop-tool"
    assert "chrome" in text.lower()
    assert "did not confirm" not in text.lower()


def test_focus_failure_reply_is_honest_not_a_bare_done():
    registry = DryRegistry()
    reply = maybe_handle_fast_command("focus something_that_never_matches", registry, {})

    assert reply is not None
    text, source = reply
    assert registry.calls[-1]["tool"] == "app.focus"
    # The DryRegistry's app.focus stub reports ok=False/error=focus_failed for
    # a non-"chrome" query -- _format_window_result must surface that as a
    # real problem, not a cheerful "Done, focused X."
    assert "done, focused" not in text.lower(), f"a failed focus must not be reported as a plain success: {text!r}"
