"""Standalone verifier for Phase 63 (two defects found by LIVE-DRIVING Phase 62).

Phase 62 shipped an encrypted vault plus single-approval form submission, and
passed a fully green 91-verifier / 619-test suite. Driving it against a REAL
Chrome login form then found two defects, exactly this project's most-repeated
lesson: a green offline suite proves the code does what the tests imagined,
never that it does what a real screen does.

  * **Defect 1 -- submit-by-label is ambiguous on ordinary login pages.**
    ``grounding.resolve("Sign in")`` came back "ambiguous" on the real page,
    with three candidates all at confidence 1.0: the actual <button>, and TWO
    static text nodes for the page's own <h1> heading (the heading text node
    and its wrapping element both matched). Phase 59's "decline rather than
    click the wrong thing" was behaving exactly as designed -- but a heading
    sharing a button's label ("Sign in", "Log in", "Submit", ...) is an
    extremely common pattern, so submit-by-label failed on a large fraction
    of real forms. The fix is an INTERACTIVE-ROLE tie-break inside the
    existing ambiguity margin: when tied candidates include exactly one
    interactive control (Button, Hyperlink, Edit, ...) among otherwise-static
    ones (Text, Image, ...), that is the answer -- a heading is not a click
    target. Two tied interactive candidates (two "OK" buttons) still refuse,
    unchanged from Phase 59.

  * **Defect 2 -- the staged window was never re-verified before typing.**
    ``StagedForm`` captures ``window_title`` at STAGING time and shows it in
    the approval manifest, but nothing ever checked it again at EXECUTION
    time. Live-driving hit this for real: the terminal used to approve the
    confirmation held foreground focus, and without a guard the decrypted
    vault value would have been typed into the terminal instead of the
    browser. The fix, in ``screen_tools.screen_submit_form``: re-verify the
    foreground window against the staged one before EVERY field (not just
    once at the start) and before the final submit action; any mismatch
    aborts the WHOLE run, typing nothing further. The matching rule is a
    STABLE window "identity" (the trailing "- App Name" segment of the
    title), not exact string equality, because the real page under test
    rewrites its own ``document.title`` while being filled in -- an exact
    match would have aborted spuriously on a page merely updating itself. An
    empty staged title (unknown at staging time) fails safe: refuse to type
    rather than proceed blind.

Following Phase 62's rule for this test surface: injection is allowed BELOW
the tool-level gate (which controls exist on screen, the pyautogui actuator)
but never ACROSS it. This file drives the REAL ``ToolRegistry().run``, the
REAL ledger confirmation (``confirm_pending_action``), and the REAL
``run_approved`` execution -- the only things faked are the accessibility-tree
provider, the physical input actuator, and (new here) the foreground-window
reader, exactly mirroring ``backend/tests/test_form_submit_gate.py`` and
``backend/tests/test_form_submit_window_guard.py``.

Fully offline: no network, no LLM, no real mouse/keyboard movement, and the
vault + pending-action ledger are redirected to a throwaway temp directory
before anything that reads those env vars is imported.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def check(value: object, message: str) -> None:
    if not value:
        raise AssertionError(message)


def main() -> int:
    tmpdir = tempfile.TemporaryDirectory(prefix="eva-phase63-verify-")
    tmp_path = Path(tmpdir.name)
    os.environ["EVA_VAULT_PATH"] = str(tmp_path / "vault.json")
    os.environ["EVA_VAULT_ENABLED"] = "1"
    os.environ["EVA_PENDING_ACTION_LEDGER_PATH"] = str(tmp_path / "pending_actions.jsonl")
    os.environ["EVA_GUI_GROUNDING_ENABLED"] = "1"
    try:
        return _run()
    finally:
        tmpdir.cleanup()


# -- Defect 1: interactive-role tie-break ------------------------------------


def _el(grounding, name, role, *, left, top, w, h):
    return grounding.RawElement(name=name, role=role, left=left, top=top, width=w, height=h)


def _real_sign_in_page(grounding):
    """The exact real-world geometry from the live drive: one Button and two
    Text nodes, all named "Sign in", all confidence 1.0.

      conf=1.0  role=Button  label='Sign in'  at=(530,361) size=114x48   <- the real target
      conf=1.0  role=Text    label='Sign in'  at=(683,168) size=420x43   <- the <h1> heading
      conf=1.0  role=Text    label='Sign in'  at=(525,168) size=104x43   <- the <h1> text node
    """
    button = _el(grounding, "Sign in", "Button", left=530 - 114 // 2, top=361 - 48 // 2, w=114, h=48)
    heading_a = _el(grounding, "Sign in", "Text", left=683 - 420 // 2, top=168 - 43 // 2, w=420, h=43)
    heading_b = _el(grounding, "Sign in", "Text", left=525 - 104 // 2, top=168 - 43 // 2, w=104, h=43)
    return [button, heading_a, heading_b]


def _verify_interactive_tiebreak() -> None:
    from backend.eva.screen import grounding
    from backend.eva.screen.screen_tools import screen_click

    saved_provider = grounding._default_provider
    try:
        # 1. The exact real-world case resolves to the BUTTON, not a heading.
        grounding._default_provider = lambda: list(_real_sign_in_page(grounding))
        resolution = grounding.resolve("Sign in")
        check(resolution.status == "found", f"the real Sign-in geometry must resolve, got {resolution.status}: {resolution.reason}")
        check(resolution.target.role == "Button", f"the tie-break must pick the button, got role={resolution.target.role!r}")
        check((resolution.target.x, resolution.target.y) == (530, 361), f"wrong target: {resolution.target}")

        located = grounding.locate("Sign in")
        check(located is not None and located.role == "Button", "locate() must inherit the fix via resolve()")

        clicked = screen_click(reason="submit the login form", label="Sign in")
        check(clicked.get("error") != "ambiguous_target", f"the real Sign-in page must no longer be ambiguous: {clicked}")

        # 2. Two tied INTERACTIVE candidates (two "OK" buttons) must STILL be
        # ambiguous -- Phase 59's rule is preserved, not weakened.
        grounding._default_provider = lambda: [
            _el(grounding, "OK", "Button", left=100, top=100, w=80, h=30),
            _el(grounding, "OK", "Button", left=400, top=100, w=80, h=30),
        ]
        two_buttons = grounding.resolve("OK")
        check(two_buttons.status == "ambiguous", f"two tied buttons must still refuse, got {two_buttons.status}")
        check(len(two_buttons.candidates) == 2, "both tied buttons must be surfaced")

        # 3. A clearly better STATIC match is not beaten by a far worse
        # interactive one -- the tie-break only fires WITHIN the existing
        # ambiguity margin, never as a global role preference.
        grounding._default_provider = lambda: [
            _el(grounding, "Sign in", "Text", left=500, top=150, w=100, h=40),
            _el(grounding, "Sign in Now", "Button", left=500, top=400, w=140, h=40),
        ]
        clear_static = grounding.resolve("Sign in")
        check(clear_static.status == "found", f"a clear static winner must resolve outright, got {clear_static.status}")
        check(
            clear_static.target.role == "Text",
            f"a clear static winner must not lose to a much weaker interactive candidate, got role={clear_static.target.role!r}",
        )
    finally:
        grounding._default_provider = saved_provider


# -- Defect 2: staged-window re-verification ---------------------------------


class _InputRecorder:
    def __init__(self, AgentObservation) -> None:
        self._obs = AgentObservation
        self.clicks: list[tuple[int, int]] = []
        self.typed: list[str] = []

    def click(self, x, y, reason, action_id: str = "screen.click"):
        self.clicks.append((int(x), int(y)))
        return self._obs(action_id=action_id, success=True, raw_observation={"x": int(x), "y": int(y)}, summary="fake click")

    def type_text(self, text, reason, action_id: str = "screen.type_text"):
        self.typed.append(str(text))
        return self._obs(action_id=action_id, success=True, raw_observation={"chars": len(str(text))}, summary="fake type")

    def press(self, key, reason, action_id: str = "screen.press"):
        self.typed.append(f"KEY:{key}")
        return self._obs(action_id=action_id, success=True, raw_observation={"key": key}, summary="fake press")


def _run() -> int:
    _verify_interactive_tiebreak()

    from backend.eva.agent.action_model import AgentObservation
    from backend.eva.permissions.ledger import confirm_pending_action
    from backend.eva.screen import form_filler, grounding, screen_controller
    from backend.eva.screen.form_filler import FormField, SubmitSpec, stage_form
    from backend.eva.tools.registry import ToolRegistry
    from scripts import verify_eva_all

    registry = ToolRegistry()

    # Two fields + a submit button -- centers: Email -> (90, 110),
    # Password -> (90, 210), Submit -> (90, 310).
    form_elements = [
        grounding.RawElement(name="Email", role="Edit", left=50, top=100, width=80, height=20),
        grounding.RawElement(name="Password", role="Edit", left=50, top=200, width=80, height=20),
        grounding.RawElement(name="Submit", role="Button", left=50, top=300, width=80, height=20),
    ]

    recorder = _InputRecorder(AgentObservation)
    saved_provider = grounding._default_provider
    saved_click = screen_controller.click
    saved_type_text = screen_controller.type_text
    saved_press = screen_controller.press
    saved_window_title_fn = form_filler.foreground_window_title
    grounding._default_provider = lambda: list(form_elements)
    screen_controller.click = recorder.click
    screen_controller.type_text = recorder.type_text
    screen_controller.press = recorder.press

    def confirm_and_execute(spec_id: str, reason: str) -> dict:
        gate_result = registry.run("screen.submit_form", spec_id=spec_id, reason=reason)
        check(gate_result.get("requires_confirmation") is True, f"submission must stay confirm-gated: {gate_result}")
        pending_id = gate_result["pending_id"]
        confirmed = confirm_pending_action(pending_id, override=bool(gate_result.get("risk_class") == "override"))
        check(confirmed.success is True, f"ledger confirmation must succeed: {confirmed}")
        executed = registry.run_approved(pending_id)
        check(isinstance(executed, dict), f"run_approved must return the outcome dict, got {executed!r}")
        return executed

    try:
        # 1. Foreground window differs from staged -> nothing typed at all.
        form_filler.foreground_window_title = lambda: "Untitled - Notepad"
        staged = stage_form(
            [FormField("Email", "me@example.com")],
            reason="phase63 window mismatch",
            submit=SubmitSpec("none"),
            window_title="Sign in - Google Chrome",
        )
        outcome = confirm_and_execute(staged.spec_id, staged.reason)
        check(outcome["ok"] is False, f"a window mismatch must abort: {outcome}")
        check(outcome["steps"][-1]["status"] == "window_changed", f"must be reported as window_changed: {outcome}")
        check(recorder.clicks == [] and recorder.typed == [], "a window mismatch must abort BEFORE the first click, nothing typed")
        check("me@example.com" not in str(outcome), "the outcome must stay value-free on this abort path")

        # 2. Mid-form focus theft: field 1 typed, field 2 NOT typed. This is
        # the focus-theft test -- a notification stealing focus between
        # fields must stop the run, not send the next value somewhere else.
        recorder.clicks.clear()
        recorder.typed.clear()
        staged_title = "Sign in - Google Chrome"
        titles = iter([staged_title, "Slack"])
        form_filler.foreground_window_title = lambda: next(titles)
        staged = stage_form(
            [FormField("Email", "me@example.com"), FormField("Password", "hunter2xyz")],
            reason="phase63 focus theft",
            submit=SubmitSpec("none"),
            window_title=staged_title,
        )
        outcome = confirm_and_execute(staged.spec_id, staged.reason)
        check(outcome["ok"] is False, f"mid-form focus theft must abort: {outcome}")
        check(outcome["filled"] == 1, f"field 1 must have completed before the abort: {outcome}")
        check(
            [s["status"] for s in outcome["steps"]] == ["filled", "window_changed"],
            f"field 1 filled, field 2 must abort at the window check: {outcome}",
        )
        check(recorder.clicks == [(90, 110)], f"only field 1's click may have happened: {recorder.clicks}")
        check(recorder.typed == ["me@example.com"], f"only field 1's value may have been typed: {recorder.typed}")
        check("hunter2xyz" not in str(outcome), "the never-typed field 2 value must not leak into the outcome")

        # 3. Empty staged title -> refuses to type, fail safe.
        recorder.clicks.clear()
        recorder.typed.clear()
        form_filler.foreground_window_title = lambda: "Sign in - Google Chrome"
        staged = stage_form(
            [FormField("Email", "me@example.com")],
            reason="phase63 empty staged title",
            submit=SubmitSpec("none"),
            window_title="",
        )
        outcome = confirm_and_execute(staged.spec_id, staged.reason)
        check(outcome["ok"] is False, f"an unverifiable staged title must refuse: {outcome}")
        check(outcome["steps"][-1]["status"] == "window_changed", outcome)
        check(recorder.clicks == [] and recorder.typed == [], "an unverifiable window must never type")

        # 4. A page updating ITS OWN title mid-fill does NOT abort -- the real
        # page this defect was found on rewrites document.title as it is
        # typed into; the browser's own "- Google Chrome" suffix stays
        # stable even as the leading page-title text changes.
        recorder.clicks.clear()
        recorder.typed.clear()
        live_titles = iter(
            [
                "Sign in - Google Chrome",
                "Sign in (email entered) - Google Chrome",
                "Sign in (email, password entered) - Google Chrome",
            ]
        )
        form_filler.foreground_window_title = lambda: next(live_titles)
        staged = stage_form(
            [FormField("Email", "me@example.com"), FormField("Password", "hunter2xyz")],
            reason="phase63 live title rewrite",
            submit=SubmitSpec("click", label="Submit"),
            window_title="Sign in - Google Chrome",
        )
        outcome = confirm_and_execute(staged.spec_id, staged.reason)
        check(outcome["ok"] is True, f"a page rewriting its own title must NOT abort the fill: {outcome}")
        check([s["status"] for s in outcome["steps"]] == ["filled", "filled"], outcome)
        check(recorder.clicks == [(90, 110), (90, 210), (90, 310)], recorder.clicks)
        check(recorder.typed == ["me@example.com", "hunter2xyz"], recorder.typed)
    finally:
        grounding._default_provider = saved_provider
        screen_controller.click = saved_click
        screen_controller.type_text = saved_type_text
        screen_controller.press = saved_press
        form_filler.foreground_window_title = saved_window_title_fn

    # Registration.
    name = "verify_eva_phase63_live_fixes.py"
    check(name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 63 verifier")
    check(name in verify_eva_all.QUICK_VERIFIERS, "quick profile missing the Phase 63 verifier")
    check(name in verify_eva_all.VERIFIER_DESCRIPTORS, "master descriptor missing the Phase 63 verifier")

    print(
        "PASS: Phase 63 live-drive fixes -- two defects a fully green 91-verifier/619-test suite missed because no "
        "offline test drove a real screen. (1) grounding.resolve() now breaks a tie in favor of an INTERACTIVE "
        "control (Button, Hyperlink, Edit, ...) over a STATIC one (Text, Image, ...) among otherwise-tied candidates "
        "-- the real Sign-in-page geometry (one Button + two Text nodes, all confidence 1.0) now resolves to the "
        "button, not a heading -- while two tied interactive candidates (two 'OK' buttons) still refuse exactly as "
        "Phase 59 designed, and a clear static winner still beats a far weaker interactive one outright. (2) "
        "screen_submit_form now re-verifies the foreground window against the one this form was staged against "
        "before EVERY field and before the final submit action, using a stable window IDENTITY (the trailing '- App "
        "Name' segment) rather than exact title equality -- a genuine window switch (Chrome -> a terminal) aborts "
        "the whole run and types nothing, a notification stealing focus mid-form stops the run after the field "
        "already filled (the focus-theft test), an unrecorded staged title refuses to type blind, and a real page "
        "rewriting its own document.title while being filled in does NOT spuriously abort."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
