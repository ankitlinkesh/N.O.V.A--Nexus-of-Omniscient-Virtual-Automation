"""The staged-window re-verification guard (Phase 63, Defect 2).

Phase 62 shipped ``screen.submit_form``: one approval performs an entire
staged form's clicks and keystrokes. ``StagedForm`` captures ``window_title``
at STAGING time and shows it in the human-readable approval manifest -- but
nothing ever checked it again at EXECUTION time. Live-driving Phase 62
against a real browser form found this for real: the terminal used to approve
the confirmation held foreground focus, and without a guard the vault value
would have been typed into the terminal instead of the browser.

The fix, in ``screen_tools.screen_submit_form``: before touching any field,
and before the final submit action, re-verify the foreground window still
matches the one this form was staged against (see
``form_filler.verify_staged_window`` for the exact matching rule -- a stable
window "identity", not exact string equality, so a page that legitimately
rewrites its own ``document.title`` mid-fill does not itself trigger a false
abort). Any mismatch aborts the WHOLE run: nothing further is typed, and the
outcome is value-free exactly like every other abort path in this file.

Following this project's own rule (see test_form_submit_gate.py's module
docstring): fakes stay strictly BELOW the tool-level gate -- the
accessibility-tree provider, the pyautogui actuator, and (new here) the
foreground-window reader. Every test drives the REAL ``ToolRegistry().run``
and the REAL confirmation round-trip.
"""

from __future__ import annotations

import pytest

from eva.agent.action_model import AgentObservation
from eva.permissions.ledger import confirm_pending_action
from eva.screen import form_filler, grounding, screen_controller
from eva.screen.form_filler import FormField, SubmitSpec, stage_form
from eva.tools.registry import ToolRegistry


def _el(name: str, *, left: int, top: int, width: int = 80, height: int = 20, role: str = "Edit") -> grounding.RawElement:
    return grounding.RawElement(name=name, role=role, left=left, top=top, width=width, height=height)


# Two fields + a submit button -- centers: Email -> (90, 110), Password ->
# (90, 210), Submit -> (90, 310).
FORM_ELEMENTS = [
    _el("Email", left=50, top=100),
    _el("Password", left=50, top=200),
    _el("Submit", left=50, top=300, role="Button"),
]


class _InputRecorder:
    def __init__(self) -> None:
        self.clicks: list[tuple[int, int]] = []
        self.typed: list[str] = []

    def click(self, x, y, reason, action_id: str = "screen.click") -> AgentObservation:
        self.clicks.append((int(x), int(y)))
        return AgentObservation(action_id=action_id, success=True, raw_observation={"x": int(x), "y": int(y)}, summary="fake click")

    def type_text(self, text, reason, action_id: str = "screen.type_text") -> AgentObservation:
        self.typed.append(str(text))
        return AgentObservation(action_id=action_id, success=True, raw_observation={"chars": len(str(text))}, summary="fake type")

    def press(self, key, reason, action_id: str = "screen.press") -> AgentObservation:
        self.typed.append(f"KEY:{key}")
        return AgentObservation(action_id=action_id, success=True, raw_observation={"key": key}, summary="fake press")


@pytest.fixture
def gated_screen(monkeypatch, tmp_path):
    """Real registry, real gate, real confirmation round-trip. Fakes stay
    below the tool-level gate: which controls exist, the pyautogui actuator,
    and (each test sets its own) the foreground-window reader."""
    monkeypatch.setenv("EVA_GUI_GROUNDING_ENABLED", "1")
    monkeypatch.setenv("EVA_VAULT_ENABLED", "1")
    monkeypatch.setenv("EVA_VAULT_PATH", str(tmp_path / "vault.json"))
    monkeypatch.setattr(grounding, "_default_provider", lambda: list(FORM_ELEMENTS))

    recorder = _InputRecorder()
    monkeypatch.setattr(screen_controller, "click", recorder.click)
    monkeypatch.setattr(screen_controller, "type_text", recorder.type_text)
    monkeypatch.setattr(screen_controller, "press", recorder.press)
    yield recorder


def _confirm(spec_id: str, reason: str) -> dict:
    """Real gate -> real ledger confirm -> real run_approved, returning the
    actual outcome dict (rather than the human-readable text reply) so tests
    can assert precisely on ``steps``/``ok``/``stopped_reason`` fields."""
    registry = ToolRegistry()
    gate_result = registry.run("screen.submit_form", spec_id=spec_id, reason=reason)
    assert gate_result.get("requires_confirmation") is True, f"submission must still be confirm-gated: {gate_result}"
    pending_id = gate_result["pending_id"]
    confirmed = confirm_pending_action(pending_id, override=bool(gate_result.get("risk_class") == "override"))
    assert confirmed.success is True, f"ledger confirmation must succeed: {confirmed}"
    executed = registry.run_approved(pending_id)
    assert isinstance(executed, dict), f"run_approved must return the outcome dict, got {executed!r}"
    return executed


# -- 1. Foreground window differs from staged -> nothing typed at all -------


def test_window_mismatch_types_nothing(gated_screen, monkeypatch):
    monkeypatch.setattr(form_filler, "foreground_window_title", lambda: "Untitled - Notepad")
    staged = stage_form(
        [FormField("Email", "me@example.com")],
        reason="window mismatch test",
        submit=SubmitSpec("none"),
        window_title="Sign in - Google Chrome",
    )

    outcome = _confirm(staged.spec_id, staged.reason)

    assert outcome["ok"] is False
    assert outcome["steps"][-1]["status"] == "window_changed", outcome
    assert outcome["filled"] == 0
    assert gated_screen.clicks == [], "a window mismatch must abort BEFORE the first click"
    assert gated_screen.typed == [], "a window mismatch must never type anything"
    assert "me@example.com" not in str(outcome), "the outcome must stay value-free even on this abort path"


# -- 2. Focus theft mid-form: field 1 typed, field 2 NOT typed --------------


def test_focus_theft_mid_form_stops_after_field_one(gated_screen, monkeypatch):
    staged_title = "Sign in - Google Chrome"
    titles = iter([staged_title, "Slack"])  # field 1 check matches, field 2 check does not
    monkeypatch.setattr(form_filler, "foreground_window_title", lambda: next(titles))

    staged = stage_form(
        [FormField("Email", "me@example.com"), FormField("Password", "hunter2xyz")],
        reason="focus theft test",
        submit=SubmitSpec("none"),
        window_title=staged_title,
    )

    outcome = _confirm(staged.spec_id, staged.reason)

    assert outcome["ok"] is False
    assert outcome["filled"] == 1, f"field 1 must have completed before the abort: {outcome}"
    statuses = [s["status"] for s in outcome["steps"]]
    assert statuses == ["filled", "window_changed"], f"field 1 filled, field 2 aborted at the window check: {outcome}"
    # Field 1 (Email) was clicked and typed; field 2 (Password) was neither.
    assert gated_screen.clicks == [(90, 110)], f"only field 1's click may have happened: {gated_screen.clicks}"
    assert gated_screen.typed == ["me@example.com"], f"only field 1's value may have been typed: {gated_screen.typed}"
    assert "hunter2xyz" not in str(outcome)


# -- 3. Empty staged title -> refuses to type, fail safe --------------------


def test_empty_staged_title_refuses_to_type(gated_screen, monkeypatch):
    # Window title was unavailable at staging time (window_title="" is the
    # StagedForm default) -- there is nothing to verify against, so this must
    # refuse rather than silently assume it is safe to proceed.
    monkeypatch.setattr(form_filler, "foreground_window_title", lambda: "Sign in - Google Chrome")
    staged = stage_form(
        [FormField("Email", "me@example.com")],
        reason="empty staged title test",
        submit=SubmitSpec("none"),
        window_title="",
    )

    outcome = _confirm(staged.spec_id, staged.reason)

    assert outcome["ok"] is False
    assert outcome["steps"][-1]["status"] == "window_changed", f"an unverifiable staged title must refuse, not proceed: {outcome}"
    assert gated_screen.clicks == [] and gated_screen.typed == []


# -- 4. A page updating its OWN title mid-fill does NOT abort ----------------


def test_page_rewriting_its_own_title_mid_fill_does_not_abort(gated_screen, monkeypatch):
    # The real page this defect was found on rewrites document.title as it is
    # typed into -- the browser's own "- Google Chrome" suffix stays stable
    # even though the leading page-title text changes on every keystroke.
    staged_title = "Sign in - Google Chrome"
    live_titles = iter(
        [
            "Sign in - Google Chrome",
            "Sign in (email entered) - Google Chrome",
            "Sign in (email, password entered) - Google Chrome",
        ]
    )
    monkeypatch.setattr(form_filler, "foreground_window_title", lambda: next(live_titles))

    staged = stage_form(
        [FormField("Email", "me@example.com"), FormField("Password", "hunter2xyz")],
        reason="live title rewrite test",
        submit=SubmitSpec("click", label="Submit"),
        window_title=staged_title,
    )

    outcome = _confirm(staged.spec_id, staged.reason)

    assert outcome["ok"] is True, f"a page rewriting its own title must NOT abort the fill: {outcome}"
    assert [s["status"] for s in outcome["steps"]] == ["filled", "filled"]
    assert gated_screen.clicks == [(90, 110), (90, 210), (90, 310)], gated_screen.clicks
    assert gated_screen.typed == ["me@example.com", "hunter2xyz"], gated_screen.typed


# -- 5. A genuine window switch (Chrome -> a terminal) aborts, even with a --
#       title that happens to contain "Chrome" as ordinary page content -----


def test_genuine_window_switch_to_a_terminal_aborts(gated_screen, monkeypatch):
    monkeypatch.setattr(form_filler, "foreground_window_title", lambda: "C:\\Users\\demo> ")
    staged = stage_form(
        [FormField("Email", "me@example.com")],
        reason="genuine switch test",
        submit=SubmitSpec("none"),
        window_title="Sign in - Google Chrome",
    )

    outcome = _confirm(staged.spec_id, staged.reason)

    assert outcome["ok"] is False
    assert outcome["steps"][-1]["status"] == "window_changed", outcome
    assert gated_screen.clicks == [] and gated_screen.typed == []


# -- 6. No value ever appears in any returned/replied outcome ---------------


def test_no_secret_leaks_into_the_reply_across_all_abort_paths(gated_screen, monkeypatch):
    scenarios = []

    monkeypatch.setattr(form_filler, "foreground_window_title", lambda: "Slack")
    staged = stage_form(
        [FormField("Password", "TotallySecretValue1")],
        reason="leak check mismatch",
        submit=SubmitSpec("none"),
        window_title="Sign in - Google Chrome",
    )
    scenarios.append(_confirm(staged.spec_id, staged.reason))

    staged2 = stage_form(
        [FormField("Password", "TotallySecretValue2")],
        reason="leak check empty title",
        submit=SubmitSpec("none"),
        window_title="",
    )
    scenarios.append(_confirm(staged2.spec_id, staged2.reason))

    for outcome in scenarios:
        assert outcome["ok"] is False
        blob = str(outcome)
        assert "TotallySecretValue1" not in blob
        assert "TotallySecretValue2" not in blob
