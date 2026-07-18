"""The real gate, not a stand-in for it (Phase 62).

Phase 62 fixed two defects that a fully green 90-verifier / 607-test suite
completely missed:

  * **Defect A**: ``fill_form`` called ``registry.run("screen.type_text")``
    per field. That tool is confirm-class, so the registry returned
    ``{"ok": False, "requires_confirmation": True}`` instead of typing, and
    ``fill_form`` treated that as a refusal and stopped at field 1. It could
    never fill a single form for real.
  * **Defect B**: ``_create_gated_pending`` wrote tool args into the on-disk
    ledger, so ``screen.type_text(text="hunter2")`` persisted
    ``payload_summary: "text=hunter2"`` in plaintext.

Both survived because every test that existed before this file injected a
fake executor returning ``{"ok": True}`` -- more permissive than the real
system, standing in for exactly the thing that was broken. The governing
rule here is the opposite: **injection is allowed BELOW the gate, never
ACROSS it.** Every test in this file drives the REAL ``ToolRegistry().run``
and the REAL confirmation round-trip (``handle_confirmation_command`` ->
``confirm_pending_action`` -> ``run_approved``). The only things faked are
things strictly below the tool-level gate:

  * ``eva.screen.grounding._default_provider`` -- the accessibility-tree
    reader. Faking WHICH controls exist on screen is the same category of
    substitution the rest of this project already uses for grounding tests
    (see ``test_grounding_disambiguation.py``); it is not a stand-in for the
    registry or the gate.
  * ``eva.screen.screen_controller.click`` / ``.type_text`` / ``.press`` --
    the physical pyautogui layer. Faking these is what keeps this suite from
    actually moving the mouse; nothing about the gate, the ledger, or the
    confirmation flow is touched.

``backend/tests/conftest.py``'s autouse ``eva_pending_action_ledger_path``
fixture already redirects ``EVA_PENDING_ACTION_LEDGER_PATH`` to a tmp file
for every test, so the real ledger is never touched.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from eva.agent.action_model import AgentObservation
from eva.permissions.confirmation import handle_confirmation_command
from eva.permissions.ledger import ledger_path
from eva.screen import form_filler, grounding, screen_controller
from eva.screen.form_filler import (
    FormField,
    SubmitSpec,
    describe_staged_form,
    pop_staged_form,
    stage_form,
)
from eva.security import tool_gate
from eva.tools.registry import ToolRegistry
from eva.vault import Vault


def _el(name: str, *, left: int, top: int, width: int = 80, height: int = 20, role: str = "Edit") -> grounding.RawElement:
    return grounding.RawElement(name=name, role=role, left=left, top=top, width=width, height=height)


# A tiny 3-field form + a submit button, laid out so each control's center is
# distinct and easy to assert on: Email -> (90, 110), Password -> (90, 210),
# Notes -> (90, 310), Submit -> (90, 410).
FORM_ELEMENTS = [
    _el("Email", left=50, top=100),
    _el("Password", left=50, top=200),
    _el("Notes", left=50, top=300),
    _el("Submit", left=50, top=400, role="Button"),
]


class _InputRecorder:
    """Stands in for the physical pyautogui layer -- records what WOULD have
    happened without ever touching a real mouse or keyboard."""

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
    """Real registry, real gate, real confirmation round-trip.

    Only three things are faked, and all are BELOW the tool-level gate: the
    accessibility-tree provider (what controls exist on screen), the
    screen_controller actuator (the physical pyautogui calls), and (Phase 63)
    the foreground-window reader -- pinned to "Test App" to match every staged
    form's ``window_title`` in this file, so the new pre-type window guard
    (see test_form_submit_window_guard.py) does not spuriously abort these
    tests against whatever window actually has focus on the machine running
    them. Nothing here fakes ``ToolRegistry.run``/``run_approved`` or the
    confirmation flow.
    """
    monkeypatch.setenv("EVA_GUI_GROUNDING_ENABLED", "1")
    monkeypatch.setenv("EVA_VAULT_ENABLED", "1")
    monkeypatch.setenv("EVA_VAULT_PATH", str(tmp_path / "vault.json"))
    monkeypatch.setattr(grounding, "_default_provider", lambda: list(FORM_ELEMENTS))
    monkeypatch.setattr(form_filler, "foreground_window_title", lambda: "Test App")

    recorder = _InputRecorder()
    monkeypatch.setattr(screen_controller, "click", recorder.click)
    monkeypatch.setattr(screen_controller, "type_text", recorder.type_text)
    monkeypatch.setattr(screen_controller, "press", recorder.press)

    yield recorder


def _stage_sample_form(vault_path: Path, *, reason: str = "fill and submit test form") -> "form_filler.StagedForm":
    vault = Vault(vault_path)
    assert vault.put("email_addr", "user@example.com") is True, "seeding the vault must succeed (DPAPI on this account)"
    assert vault.put("work_pw", "hunter2xyz") is True

    fields = [
        FormField("Email", "@vault:email_addr"),
        FormField("Password", "@vault:work_pw"),
        FormField("Notes", "a literal note"),
    ]
    return stage_form(fields, reason=reason, submit=SubmitSpec("click", label="Submit"), window_title="Test App")


# -- 1. screen.submit_form is confirm-class on the REAL registry ------------

def test_screen_submit_form_is_confirm_class():
    spec = ToolRegistry().get("screen.submit_form")
    assert spec is not None, "screen.submit_form must be registered"
    assert tool_gate.classify_tool_call(spec) == "confirm"


# -- 2. Defect A regression pin ----------------------------------------------

def test_defect_a_type_text_alone_stalls_and_never_types(gated_screen):
    """Documents WHY per-keystroke gating was dead: screen.type_text is
    confirm-class, so a bare call to it never types -- it just stalls asking
    for approval. fill_form used to call exactly this, per field, which is
    why a real form could never be filled past field 1."""
    result = ToolRegistry().run("screen.type_text", text="x", reason="probe")
    assert result.get("ok") is False
    assert result.get("requires_confirmation") is True
    assert gated_screen.typed == [], "no keystroke may land before approval"


# -- 3. One approval fills every field and submits ---------------------------

def test_one_approval_fills_every_field_and_submits(gated_screen, tmp_path):
    staged = _stage_sample_form(tmp_path / "vault.json")
    registry = ToolRegistry()

    gate_result = registry.run("screen.submit_form", spec_id=staged.spec_id, reason=staged.reason)
    assert gate_result.get("requires_confirmation") is True, f"one call must not perform the form: {gate_result}"
    assert gated_screen.clicks == [] and gated_screen.typed == [], "nothing may happen before approval"

    pending_id = gate_result["pending_id"]
    reply = handle_confirmation_command(f"confirm {pending_id}")
    assert "Executed" in reply, f"the single approval must actually execute the whole form: {reply!r}"

    # Every field clicked, then typed, in order, followed by the submit click.
    assert gated_screen.clicks == [(90, 110), (90, 210), (90, 310), (90, 410)], (
        f"fields (and the submit button) must be clicked in order: {gated_screen.clicks}"
    )
    assert gated_screen.typed == ["user@example.com", "hunter2xyz", "a literal note"], (
        f"fields must be typed in order with the RIGHT resolved values: {gated_screen.typed}"
    )


# -- 4. Defect B regression pin (full round-trip) ----------------------------

def test_defect_b_full_round_trip_leaks_nothing_to_the_ledger(gated_screen, tmp_path):
    staged = _stage_sample_form(tmp_path / "vault.json")
    registry = ToolRegistry()

    gate_result = registry.run("screen.submit_form", spec_id=staged.spec_id, reason=staged.reason)
    pending_id = gate_result["pending_id"]
    reply = handle_confirmation_command(f"confirm {pending_id}")
    assert "Executed" in reply

    raw_text = ledger_path().read_text(encoding="utf-8")
    for leaked in ("user@example.com", "hunter2xyz", "a literal note"):
        assert leaked not in raw_text, f"{leaked!r} must never reach the on-disk ledger: {raw_text!r}"


# -- 5. Direct Defect B pin ---------------------------------------------------

def test_defect_b_direct_type_text_leaves_no_value_in_ledger(gated_screen):
    ToolRegistry().run("screen.type_text", text="hunter2xyz", reason="probe")
    raw_text = ledger_path().read_text(encoding="utf-8")
    assert "hunter2xyz" not in raw_text, f"typed secret leaked into the ledger: {raw_text!r}"


# -- 6. Pending-call args carry refs, not values -----------------------------

def test_pending_call_args_carry_refs_not_values(gated_screen, tmp_path):
    staged = _stage_sample_form(tmp_path / "vault.json", reason="check pending args")
    result = ToolRegistry().run("screen.submit_form", spec_id=staged.spec_id, reason="check pending args")
    pending_id = result["pending_id"]

    stored = tool_gate.get_pending_call(pending_id)
    assert stored is not None, "register_pending_call did not persist the call"
    assert stored["args"] == {"spec_id": staged.spec_id, "reason": "check pending args"}

    blob = json.dumps(stored["args"])
    assert "user@example.com" not in blob and "hunter2xyz" not in blob


# -- 7. A forged/never-staged spec_id is inert -------------------------------

def test_forged_spec_id_is_inert(gated_screen):
    result = ToolRegistry().run(
        "screen.submit_form", spec_id="fs_never_staged_by_anyone", reason="forged spec id attempt"
    )
    assert result.get("requires_confirmation") is True
    pending_id = result["pending_id"]

    clicks_before, typed_before = list(gated_screen.clicks), list(gated_screen.typed)
    reply = handle_confirmation_command(f"confirm {pending_id}")
    assert "unknown_or_expired_form_spec" in reply, f"a forged spec_id must be reported inert: {reply!r}"
    assert gated_screen.clicks == clicks_before and gated_screen.typed == typed_before, (
        "a forged spec_id must never touch the screen"
    )


# -- 8. Staged forms are single-use and expire -------------------------------

def test_staged_form_is_single_use():
    spec = stage_form([FormField("X", "literal")], reason="single-use check", submit=SubmitSpec("none"))
    first = pop_staged_form(spec.spec_id)
    assert first is not None and first.spec_id == spec.spec_id
    second = pop_staged_form(spec.spec_id)
    assert second is None, "a staged form must not be poppable twice"


def test_staged_form_expires_after_ttl():
    spec = stage_form([FormField("X", "literal")], reason="ttl check", submit=SubmitSpec("none"))
    aged = dataclasses.replace(
        spec, created_at=datetime.now(timezone.utc) - timedelta(seconds=form_filler._STAGE_TTL_SECONDS + 5)
    )
    form_filler._STAGED_FORMS[spec.spec_id] = aged
    assert pop_staged_form(spec.spec_id) is None, "an aged staged form must be treated as expired"


# -- 9. The approval manifest shows bindings but never values ----------------

def test_manifest_shows_bindings_not_vault_values(tmp_path):
    vault = Vault(tmp_path / "vault.json")
    assert vault.put("email_addr", "user@example.com") is True

    fields = [
        FormField("Email", "@vault:email_addr"),
        FormField("Notes", "a literal note visible in manifest"),
    ]
    spec = stage_form(fields, reason="manifest check", submit=SubmitSpec("click", label="Submit"), window_title="Some App")
    manifest = describe_staged_form(spec)

    assert "email_addr" in manifest, "the manifest must show the vault NAME"
    assert "a literal note visible in manifest" in manifest, "the manifest must show literal values in full"
    assert "user@example.com" not in manifest, "the manifest must never show a vault VALUE"


# -- 10. screen.submit_form is not planner-reachable -------------------------

def test_screen_submit_form_is_not_planner_reachable():
    registry = ToolRegistry()
    planner_names = {str(spec.get("name", "")) for spec in registry.planner_specs()}
    assert "screen.submit_form" not in planner_names
    assert not "screen.submit_form".startswith("web.")
    assert not "screen.submit_form".startswith("mcp.")


# -- 11. Phase 55 interaction: a sensitive reason escalates to override -----

def test_sensitive_reason_escalates_to_override_confirm_phrase(gated_screen):
    from eva.permissions.risk_signals import assess_friction

    reason = r"fill credentials form using C:\Users\demo\credentials\data"
    spec = stage_form([FormField("Email", "literal@example.com")], reason=reason, submit=SubmitSpec("none"))

    # Verify the escalation actually fires for this input BEFORE asserting on
    # the registry -- this is the real behavior of risk_signals.py, not an
    # assumption: SAFE_LOCAL_UI is a mutating action type, and the reason
    # contains both a sensitive marker ("credentials") and a path separator.
    expected = assess_friction(
        base_decision="confirm", action_type="SAFE_LOCAL_UI", args={"spec_id": spec.spec_id, "reason": reason}
    )
    assert expected.escalated and expected.decision == "override", (
        f"this test's reason text is crafted to trip the Phase 55 sensitive-target escalation; got {expected}. "
        "If risk_signals.py's markers changed, update the reason text rather than deleting this assertion."
    )

    result = ToolRegistry().run("screen.submit_form", spec_id=spec.spec_id, reason=reason)
    assert result.get("requires_confirmation") is True
    assert result.get("risk_class") == "override"
    assert "confirm override" in result.get("message", ""), (
        f"an override-escalated action must quote 'confirm override', not a bare confirm: {result.get('message')!r}"
    )
