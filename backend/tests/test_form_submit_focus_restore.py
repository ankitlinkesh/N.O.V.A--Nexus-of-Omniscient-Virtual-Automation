"""Executable spec for the focus-restore step in the staged-form window guard
(Phase 64).

Phase 63 added ``verify_staged_window``: on any window mismatch,
``screen_submit_form`` aborted unconditionally, because
``eva.desktop.windows.focus_window`` did not reliably work (a bare
``SetForegroundWindow`` is blocked by Windows' foreground lock from a
background process) -- attempting a restore would have been pointless.

Phase 64 fixed ``focus_window`` for real (see test_windows_focus.py), so a
mismatch is no longer immediately fatal: ``form_filler.ensure_staged_window``
now makes ONE best-effort restore attempt (``restore_window_focus``) before
re-checking. The abort remains the fallback -- restoring focus makes this
usable, it must not make it permissive: nothing is typed unless the window
matches AFTER the restore attempt too.

Following this project's own rule (see test_form_submit_gate.py's module
docstring): fakes stay strictly BELOW the tool-level gate. This file adds one
more fake to that established set -- ``form_filler.restore_window_focus``,
the seam that would otherwise call the real (now-working)
``eva.desktop.windows.focus_window`` -- so these tests never touch a real
window, exactly like ``foreground_window_title`` is already faked for the
same reason.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from eva.agent.action_model import AgentObservation
from eva.permissions.ledger import confirm_pending_action
from eva.screen import form_filler, grounding, screen_controller
from eva.screen.form_filler import FormField, StagedForm, SubmitSpec, ensure_staged_window, stage_form
from eva.tools.registry import ToolRegistry


def _el(name: str, *, left: int, top: int, width: int = 80, height: int = 20, role: str = "Edit") -> grounding.RawElement:
    return grounding.RawElement(name=name, role=role, left=left, top=top, width=width, height=height)


FORM_ELEMENTS = [_el("Email", left=50, top=100)]


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
    registry = ToolRegistry()
    gate_result = registry.run("screen.submit_form", spec_id=spec_id, reason=reason)
    assert gate_result.get("requires_confirmation") is True, f"submission must still be confirm-gated: {gate_result}"
    pending_id = gate_result["pending_id"]
    confirmed = confirm_pending_action(pending_id, override=bool(gate_result.get("risk_class") == "override"))
    assert confirmed.success is True, f"ledger confirmation must succeed: {confirmed}"
    executed = registry.run_approved(pending_id)
    assert isinstance(executed, dict), f"run_approved must return the outcome dict, got {executed!r}"
    return executed


def _staged(**overrides) -> StagedForm:
    defaults = dict(
        spec_id="fs_test",
        reason="test",
        fields=(FormField("Email", "me@example.com"),),
        submit=SubmitSpec("none"),
        window_title="Target App",
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return StagedForm(**defaults)


# -- 1. Unit-level: ensure_staged_window itself --------------------------------


def test_ensure_staged_window_returns_none_immediately_when_already_matching(monkeypatch):
    monkeypatch.setattr(form_filler, "foreground_window_title", lambda: "Target App")
    restore_calls: list[str] = []
    monkeypatch.setattr(form_filler, "restore_window_focus", lambda title: restore_calls.append(title))

    error = ensure_staged_window(_staged(window_title="Target App"))

    assert error is None
    assert restore_calls == [], "no restore should be attempted when there was never a mismatch"


def test_ensure_staged_window_restores_and_reverifies_successfully(monkeypatch):
    """A successful restore flips the fake foreground window -- the
    re-verification right after must see that and return None (no error)."""
    state = {"focused": False}
    monkeypatch.setattr(form_filler, "foreground_window_title", lambda: "Target App" if state["focused"] else "Wrong App")

    def fake_restore(window_title: str) -> None:
        assert window_title == "Target App"
        state["focused"] = True

    monkeypatch.setattr(form_filler, "restore_window_focus", fake_restore)

    error = ensure_staged_window(_staged(window_title="Target App"))

    assert error is None, f"a successful restore must clear the mismatch: {error}"
    assert state["focused"] is True


def test_ensure_staged_window_still_errors_when_restore_does_not_fix_it(monkeypatch):
    monkeypatch.setattr(form_filler, "foreground_window_title", lambda: "Wrong App")
    restore_calls: list[str] = []
    monkeypatch.setattr(form_filler, "restore_window_focus", lambda title: restore_calls.append(title))

    error = ensure_staged_window(_staged(window_title="Target App"))

    assert restore_calls == ["Target App"], "a restore attempt must have been made"
    assert error is not None, "the abort must remain the fallback when the restore attempt fails"
    assert "Wrong App" in error or "Target App" in error


def test_ensure_staged_window_skips_restore_when_no_title_was_recorded(monkeypatch):
    """An empty staged window_title means there is nothing recorded to
    restore TO -- restoring must not even be attempted, matching
    verify_staged_window's existing fail-safe (refuse to type blind)."""
    monkeypatch.setattr(form_filler, "foreground_window_title", lambda: "Whatever Is Focused")
    restore_calls: list[str] = []
    monkeypatch.setattr(form_filler, "restore_window_focus", lambda title: restore_calls.append(title))

    error = ensure_staged_window(_staged(window_title=""))

    assert restore_calls == [], "nothing recorded to restore to -- must not attempt a restore"
    assert error is not None


# -- 2. End-to-end through the real gate + confirmation round-trip ----------


def test_successful_restore_lets_the_real_submission_proceed(gated_screen, monkeypatch):
    staged_title = "Sign in - Google Chrome"
    state = {"focused": False}
    monkeypatch.setattr(form_filler, "foreground_window_title", lambda: staged_title if state["focused"] else "Untitled - Notepad")
    monkeypatch.setattr(form_filler, "restore_window_focus", lambda title: state.__setitem__("focused", True))

    staged = stage_form(
        [FormField("Email", "me@example.com")],
        reason="restore succeeds end to end",
        submit=SubmitSpec("none"),
        window_title=staged_title,
    )

    outcome = _confirm(staged.spec_id, staged.reason)

    assert outcome["ok"] is True, f"a window that comes back into focus via restore must let the fill proceed: {outcome}"
    assert outcome["steps"][0]["status"] == "filled"
    assert gated_screen.clicks == [(90, 110)]
    assert gated_screen.typed == ["me@example.com"]


def test_failed_restore_still_aborts_and_types_nothing(gated_screen, monkeypatch):
    restore_calls: list[str] = []
    monkeypatch.setattr(form_filler, "foreground_window_title", lambda: "Untitled - Notepad")
    monkeypatch.setattr(form_filler, "restore_window_focus", lambda title: restore_calls.append(title))

    staged = stage_form(
        [FormField("Email", "me@example.com")],
        reason="restore fails end to end",
        submit=SubmitSpec("none"),
        window_title="Sign in - Google Chrome",
    )

    outcome = _confirm(staged.spec_id, staged.reason)

    assert restore_calls == ["Sign in - Google Chrome"], f"a restore attempt must have been made: {restore_calls}"
    assert outcome["ok"] is False, "the abort must remain the fallback when the restore attempt does not work"
    assert outcome["steps"][-1]["status"] == "window_changed"
    assert gated_screen.clicks == [] and gated_screen.typed == [], "nothing may be typed when the window is still unconfirmed"
    assert "me@example.com" not in str(outcome)
