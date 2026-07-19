"""Executable spec for backend/eva/tools/postconditions.py (Phase 38, honesty
fixes in Phase 64).

Covers the provenance contract that makes verification-first execution honest:

  * a written file whose content really is on disk is ``independent`` proof;
  * a claimed write whose content is *not* on disk is caught, not trusted;
  * a delete's real post-condition is file-absence, even though the tool's
    declared ``verification_method`` metadata says ``file_exists``;
  * a bare self-reported read only ever earns ``self_reported`` provenance,
    never ``independent``;
  * a screen/UI effect nothing here can actually check (screen_state_changed,
    text_field_contains, url_opened, ...) is honestly ``unverified`` --
    Phase 64 found it used to claim ``provenance="observed"`` with `verified`
    silently borrowed from the tool's own self-reported ``ok``, which is
    exactly how a lying tool's lie got laundered into an apparently
    independent-looking confirmation (see the ``focus_window``/
    ``app_window_active`` tests below for the concrete case this was found
    from);
  * ``app_window_active`` (Phase 64) is the one exception: focusing a window
    genuinely IS independently checkable (read the real foreground window
    ourselves), so it gets a real ``independent`` check instead;
  * ``app_window_open`` (Phase 64 follow-up) is the mirror-image lesson:
    giving ``app_window_active`` a real check initially broke ``app.open``,
    because "opened" is not "focused" -- an app can launch correctly without
    taking the foreground. Each of ``app.open``/``app.focus``/
    ``app.close_request`` now declares the ``verification_method`` that
    actually describes its own postcondition, rather than one method
    growing a tool-name heuristic to cover three different meanings; and
  * the executor wires all of this through so an allow-class tool call
    attaches a ``verification`` dict without demoting ``ok`` unless the
    verification is both independent and failed.
"""

from __future__ import annotations

from backend.eva.agent.executor import ToolExecutor
from backend.eva.agent.planner import PlannedToolCall
from backend.eva.desktop import verifier as desktop_verifier
from backend.eva.desktop.windows import WindowInfo
from backend.eva.tools import app_control_tools
from backend.eva.tools.postconditions import derive_postcondition, verify_tool_effect
from backend.eva.tools.registry import ToolRegistry

CHROME = WindowInfo(hwnd=1, title="Google Chrome", process_id=1, process_name="chrome.exe", executable=r"C:\chrome.exe")
NOTEPAD = WindowInfo(hwnd=2, title="Untitled - Notepad", process_id=2, process_name="notepad.exe", executable=r"C:\Windows\notepad.exe")


def test_file_write_with_matching_content_is_independent_and_verified(tmp_path):
    target = tmp_path / "written.txt"
    target.write_text("hello phase38", encoding="utf-8")

    outcome = verify_tool_effect(
        "file.write_text", "file_contains", {"path": str(target), "content": "hello phase38"}, {"ok": True}
    )

    assert outcome.provenance == "independent"
    assert outcome.independent is True
    assert outcome.verified is True


def test_file_write_with_content_absent_is_independent_but_not_verified(tmp_path):
    target = tmp_path / "written.txt"
    target.write_text("something else entirely", encoding="utf-8")

    outcome = verify_tool_effect(
        "file.write_text", "file_contains", {"path": str(target), "content": "hello phase38"}, {"ok": True}
    )

    assert outcome.independent is True
    assert outcome.verified is False


def test_delete_tool_on_path_that_still_exists_is_not_verified(tmp_path):
    target = tmp_path / "victim.txt"
    target.write_text("still here", encoding="utf-8")

    outcome = verify_tool_effect("file.delete", "file_exists", {"path": str(target)}, {"ok": True})

    assert outcome.method == "file_absent"
    assert outcome.verified is False


def test_delete_tool_on_removed_path_is_verified(tmp_path):
    target = tmp_path / "victim.txt"
    target.write_text("about to go", encoding="utf-8")
    target.unlink()

    outcome = verify_tool_effect("file.delete", "file_exists", {"path": str(target)}, {"ok": True})

    assert outcome.method == "file_absent"
    assert outcome.verified is True


def test_read_tool_success_is_self_reported_not_independent():
    outcome = verify_tool_effect("workspace_status", "command_result_success", {}, {"ok": True})

    assert outcome.provenance == "self_reported"
    assert outcome.verified is True
    assert outcome.independent is False


def test_read_tool_failure_is_self_reported_and_not_verified():
    outcome = verify_tool_effect("workspace_status", "command_result_success", {}, {"ok": False})

    assert outcome.verified is False


def test_screen_tool_is_unverified_with_remediation_not_falsely_observed():
    """Phase 64: this used to assert provenance == "observed" -- i.e. that a
    screen effect nothing here can actually check was reported as if it had
    been independently confirmed. Nothing in this codebase has a perception
    capability wired up to look at the screen, so claiming "observed" was
    never true; it is honestly "unverified" now. Still carries a remediation
    string telling the operator to look, unchanged."""
    outcome = verify_tool_effect("screen.type_text", "text_field_contains", {"text": "hi", "reason": "eval"}, {"ok": True})

    assert outcome.provenance == "unverified"
    assert outcome.independent is False
    assert outcome.verified is False, "must not claim verified=True on the strength of a self-report alone"
    assert outcome.remediation


def test_unverifiable_ui_methods_never_claim_observed_or_verified_regardless_of_self_report():
    """Every _OBSERVED_METHODS entry (except app_window_active, tested
    separately below) must be honestly unverified -- and, crucially, this
    must hold even when the tool SELF-REPORTS success, because that
    self-report is exactly what cannot be trusted (see the focus_window
    lying-payload tests below for why)."""
    for method in ("screen_state_changed", "text_field_contains", "url_opened", "message_draft_prepared", "message_sent_likely"):
        outcome = verify_tool_effect("screen.type_text", method, {"text": "hi", "reason": "eval"}, {"ok": True})
        assert outcome.provenance == "unverified", f"{method}: expected unverified, got {outcome.provenance!r}"
        assert outcome.verified is False, f"{method}: must not claim verified=True from a self-report alone"
        assert outcome.independent is False, f"{method}: must not claim independent"


# -- Phase 64, Defect 3: app_window_active gets a REAL independent check ----
#
# The exact CONFIRMED scenario: focus_window's old/broken return value
# claimed ok=True while the foreground window never actually changed (Notepad
# stayed foreground; Chrome was requested). Handed that literal lying
# payload, app_window_active must independently discover the real foreground
# window does not match and report failure -- it must not trust the payload's
# ok flag, or any of its other fields, at all. Only the underlying OS read
# (eva.desktop.verifier.get_active_window, and transitively
# eva.desktop.windows.get_active_window) is monkeypatched; nothing about
# verify_tool_effect's own logic is faked.

LYING_FOCUS_PAYLOAD = {
    "ok": True,
    "focused": False,
    "verified": False,
    "window": {"title": "Google Chrome"},
    "active_window": {"title": "Untitled - Notepad"},
}


def test_app_window_active_fails_for_the_exact_lying_focus_payload(monkeypatch):
    monkeypatch.setattr(desktop_verifier, "get_active_window", lambda: NOTEPAD)

    outcome = verify_tool_effect("app.focus", "app_window_active", {"query": "chrome"}, LYING_FOCUS_PAYLOAD)

    assert outcome.provenance == "independent"
    assert outcome.independent is True
    assert outcome.verified is False, (
        f"the real foreground window (Notepad) does not match the requested query (chrome); this must fail "
        f"regardless of the payload's own ok=True: {outcome}"
    )


def test_app_window_active_passes_when_focus_really_happened(monkeypatch):
    monkeypatch.setattr(desktop_verifier, "get_active_window", lambda: CHROME)

    honest_payload = {"ok": True, "focused": True, "verified": True, "window": {"title": "Google Chrome"}, "active_window": {"title": "Google Chrome"}}
    outcome = verify_tool_effect("app.focus", "app_window_active", {"query": "chrome"}, honest_payload)

    assert outcome.provenance == "independent"
    assert outcome.independent is True
    assert outcome.verified is True


def test_app_window_active_ignores_the_tool_self_report_entirely(monkeypatch):
    """Proves real independence in BOTH directions: a tool that self-reports
    failure is still marked verified=True if the real foreground window
    genuinely matches, and (the case above) a tool claiming ok=True is still
    marked verified=False if it does not. app_window_active must never defer
    to the tool's own claim either way."""
    monkeypatch.setattr(desktop_verifier, "get_active_window", lambda: CHROME)

    outcome = verify_tool_effect("app.focus", "app_window_active", {"query": "chrome"}, {"ok": False, "error": "whatever"})

    assert outcome.verified is True


def test_app_window_active_derives_query_from_app_arg_too(monkeypatch):
    """app.open uses arg name "app", not "query"."""
    monkeypatch.setattr(desktop_verifier, "get_active_window", lambda: CHROME)

    post = derive_postcondition("app.open", "app_window_active", {"app": "chrome"})
    assert post.params["query"] == "chrome"

    outcome = verify_tool_effect("app.open", "app_window_active", {"app": "chrome"}, {"ok": True})
    assert outcome.verified is True


def test_app_window_active_with_no_recorded_target_is_unverified_not_a_fabricated_failure():
    """Defensive-only path (every currently-registered app_window_active tool
    requires query/app as an arg): with nothing to check, this must be
    "we don't know" (unverified), not "we proved it failed" (independent
    False-would-demote) -- see the ToolExecutor non-fabrication test below
    for why that distinction matters."""
    outcome = verify_tool_effect("some.weird.tool", "app_window_active", {}, {"ok": True})

    assert outcome.independent is False
    assert outcome.provenance == "unverified"
    assert outcome.verified is False


# -- Phase 64 follow-up: three tools, three distinct verification_method ----
#
# The original fix special-cased "close" by tool NAME inside the
# app_window_active branch. That was already one heuristic case; app.open's
# regression (below) would have been a second, different-shaped case on the
# same method. Rather than grow the heuristic to cover three meanings on one
# method name, each tool now declares the verification_method that actually
# describes its own postcondition. These three tests pin that directly at
# the registry -- the level where the decision now actually lives.


def test_app_open_declares_app_window_open_not_app_window_active():
    spec = ToolRegistry().get("app.open")
    assert spec is not None
    assert spec.verification_method == "app_window_open", (
        f"app.open's postcondition is 'a window now exists', not 'is it foreground' -- got {spec.verification_method!r}"
    )


def test_app_focus_declares_app_window_active():
    spec = ToolRegistry().get("app.focus")
    assert spec is not None
    assert spec.verification_method == "app_window_active", "for focus specifically, foreground IS the postcondition"


def test_app_close_request_declares_command_result_success():
    spec = ToolRegistry().get("app.close_request")
    assert spec is not None
    assert spec.verification_method == "command_result_success", (
        "a successful close's real postcondition (window now ABSENT) is not independently checked yet, so this "
        f"must declare what it actually gets rather than routing through app_window_active: got {spec.verification_method!r}"
    )


def test_derive_postcondition_app_window_open_extracts_app_arg():
    post = derive_postcondition("app.open", "app_window_open", {"app": "notepad"})
    assert post.method == "app_window_open"
    assert post.params["query"] == "notepad"


# -- Phase 64 follow-up: app_window_open is a REAL independent check, of the
#    RIGHT thing (open, not focus) --------------------------------------------


def test_app_window_open_verifies_when_a_window_exists_regardless_of_foreground(monkeypatch):
    notepad = WindowInfo(hwnd=3, title="Untitled - Notepad", process_id=3, process_name="notepad.exe", executable=r"C:\Windows\notepad.exe")
    monkeypatch.setattr(desktop_verifier, "find_window", lambda query, limit=3: [notepad])

    outcome = verify_tool_effect("app.open", "app_window_open", {"app": "notepad"}, {"ok": True})

    assert outcome.provenance == "independent"
    assert outcome.independent is True
    assert outcome.verified is True


def test_app_window_open_fails_when_no_window_was_ever_found():
    outcome = verify_tool_effect("app.open", "app_window_open", {"app": "definitely_not_a_real_app_xyz"}, {"ok": True})

    assert outcome.independent is True
    assert outcome.verified is False


# -- Phase 64 follow-up: the exact regression, driven through the real ------
#    executor + registry, with only the process-launch and window-read seams
#    stubbed out. This is the centerpiece: a successful app.open, measured on
#    a real machine, that was being reported to the agent as a failure.


def test_app_open_succeeding_without_foreground_is_not_demoted(monkeypatch):
    """The exact regression: app.open succeeds (the app's window genuinely
    exists) but another process holds the foreground lock, so the app is NOT
    the foreground window. This must NOT be treated as a failure -- "opened"
    is not "focused". Never launches a real process: app_control_tools.open_app
    (the seam app.open's handler actually calls) is stubbed out."""
    notepad = WindowInfo(hwnd=3, title="Untitled - Notepad", process_id=3, process_name="notepad.exe", executable=r"C:\Windows\notepad.exe")
    monkeypatch.setattr(app_control_tools, "open_app", lambda app: f"Opening {app}.")
    monkeypatch.setattr(desktop_verifier, "find_window", lambda query, limit=3: [notepad])
    # Deliberately NOT patching get_active_window: app_window_open must never
    # call it at all. If it did, this test would still pass by accident
    # (nothing asserts get_active_window was untouched) -- the real proof is
    # the verification method recorded below.

    executor = ToolExecutor(ToolRegistry())
    result = executor.execute(PlannedToolCall(tool="app.open", args={"app": "notepad"}))

    assert result.verification is not None
    assert result.verification["method"] == "app_window_open"
    assert result.verification["independent"] is True
    assert result.verification["verified"] is True, f"the window exists, so this must verify even though it is not foreground: {result.as_dict()}"
    assert result.ok is True, f"a successful open must not be demoted just because the app is not foreground: {result.as_dict()}"


# -- Phase 64 follow-up: the other direction, app.focus that genuinely did --
#    not focus must STILL be demoted -- proving the app.open fix did not
#    weaken the original Phase 64 focus-honesty fix.


def test_app_focus_that_genuinely_did_not_focus_is_still_demoted(monkeypatch):
    from backend.eva.desktop import windows as windows_module

    monkeypatch.setattr(windows_module, "find_window", lambda query, limit=1: [])
    monkeypatch.setattr(desktop_verifier, "get_active_window", lambda: NOTEPAD)

    executor = ToolExecutor(ToolRegistry())
    result = executor.execute(PlannedToolCall(tool="app.focus", args={"query": "chrome"}))

    assert result.verification is not None
    assert result.verification["method"] == "app_window_active"
    assert result.verification["independent"] is True
    assert result.verification["verified"] is False
    assert result.ok is False, f"app.focus genuinely not focusing must still demote ok -- Phase 64's original intent: {result.as_dict()}"


# -- Phase 64 follow-up: verify_window_focused now retries, so a focus that -
#    lands a moment late is not a false failure -----------------------------


def test_app_window_active_focus_landing_late_is_not_a_false_failure(monkeypatch):
    """verify_window_focused now retries (matching verify_app_opened's
    already-established pattern) -- a focus change that lands on a LATER
    read must not be reported as a false failure just because the first
    read was too early."""
    reads = {"n": 0}

    def flaky_get_active_window():
        reads["n"] += 1
        return NOTEPAD if reads["n"] == 1 else CHROME

    monkeypatch.setattr(desktop_verifier, "get_active_window", flaky_get_active_window)

    outcome = verify_tool_effect("app.focus", "app_window_active", {"query": "chrome"}, {"ok": True})

    assert outcome.verified is True, f"a focus that lands on the 2nd read must not be reported as failed: {outcome}"
    assert reads["n"] >= 2, "must have re-read after the first (stale) miss"


def test_derive_postcondition_for_delete_is_file_absent():
    post = derive_postcondition("file.delete", "file_exists", {"path": "C:/tmp/whatever.txt"})

    assert post.method == "file_absent"


def test_executor_attaches_self_reported_verification_for_workspace_status():
    executor = ToolExecutor(ToolRegistry())
    result = executor.execute(PlannedToolCall(tool="workspace_status", args={}))

    assert result.ok is True
    assert result.verification is not None
    assert result.verification["provenance"] == "self_reported"


# -- Phase 64: ToolExecutor still does not fabricate failures for -----------
#    unverifiable methods (no demotion when independent=False)


def test_executor_does_not_demote_ok_for_an_unverifiable_screen_method():
    """screen.click is allow-class with verification_method="screen_state_changed"
    (Phase 64: now honestly unverified, independent=False). Called with no
    target/label at all, the REAL handler self-reports failure
    (ui_target_required) before touching grounding or pyautogui -- fully
    offline, no mocking needed. Even though the tool itself refused, the
    executor must NOT demote ok on the strength of an unverifiable
    postcondition: only an INDEPENDENT failure may demote (see executor.py's
    Phase 38 comment, which Phase 64 was told to leave alone)."""
    executor = ToolExecutor(ToolRegistry())
    result = executor.execute(PlannedToolCall(tool="screen.click", args={"reason": "test probe"}))

    assert result.verification is not None
    assert result.verification["provenance"] == "unverified"
    assert result.verification["independent"] is False
    assert result.ok is True, (
        f"ToolExecutor must not fabricate a demotion for a non-independent verification method: {result.as_dict()}"
    )


def test_executor_demotes_ok_for_a_genuine_independent_app_window_active_failure(monkeypatch):
    """The other half of the same invariant: when a postcondition IS
    independent (app_window_active, Phase 64) and genuinely fails, ok SHOULD
    be demoted -- this is what makes the non-fabrication test above
    meaningful rather than the executor simply never demoting anything.

    find_window is also stubbed to "not found": without it, a query fuzzy-
    matches any 3+ char word against real window titles/process names (e.g.
    "not" is a substring of "notepad.exe"), which could accidentally focus a
    real window on whatever machine runs this test. Stubbing it keeps this
    fully offline regardless of what happens to be open."""
    from backend.eva.desktop import windows as windows_module

    monkeypatch.setattr(windows_module, "find_window", lambda query, limit=1: [])
    monkeypatch.setattr(desktop_verifier, "get_active_window", lambda: NOTEPAD)
    executor = ToolExecutor(ToolRegistry())

    result = executor.execute(PlannedToolCall(tool="app.focus", args={"query": "chrome"}))

    assert result.verification is not None
    assert result.verification["independent"] is True
    assert result.verification["verified"] is False
    assert result.ok is False, f"a genuine independent postcondition failure must demote ok: {result.as_dict()}"
