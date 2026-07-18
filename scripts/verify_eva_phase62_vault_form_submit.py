"""Standalone verifier for Phase 62 (encrypted vault + single gated form submission).

Phase 58 composed screen.click + screen.type_text into ``fill_form``, and every
test for it injected a fake executor that returned ``{"ok": True}`` for every
call. A fully green 90-verifier / 607-test suite shipped on top of that and
still hid two real defects, both invisible to a fake executor that was more
permissive than the real system:

  * **Defect A**: ``fill_form`` called ``registry.run("screen.type_text")`` per
    field. ``screen.type_text`` is confirm-class (it types on the user's real
    screen), so the REAL registry returned ``{"ok": False,
    "requires_confirmation": True}`` for the very first keystroke. ``fill_form``
    read that as a refusal and stopped at field 1. It could never fill a form
    for real -- only in a test that faked the gate away.
  * **Defect B**: the gate's ``_create_gated_pending`` wrote tool args straight
    into the on-disk pending-action ledger, so a real
    ``screen.type_text(text="hunter2")`` call persisted
    ``payload_summary: "text=hunter2"`` to disk in plaintext, waiting for
    anyone with filesystem access to read it back before it was ever approved.

Phase 62's fix is to gate the WHOLE form once instead of every keystroke: the
trusted console stages a form (``form_filler.stage_form``) -- literal values or
``@vault:name`` references into the new DPAPI-encrypted vault -- and gets back
an opaque ``spec_id``. The confirm-class tool ``screen.submit_form`` takes only
that id; a single approval lets ``screen_tools.screen_submit_form`` perform
every click/type/submit itself, calling the screen functions directly (already
past the gate) instead of re-entering ``ToolRegistry.run`` per field.

The governing rule for this file, learned from how both defects survived: a
test that fakes the gate away is not testing the gate. **Injection is allowed
BELOW the tool-level gate (the accessibility-tree provider that says what
controls exist, and the pyautogui actuator that would physically move the
mouse) but never ACROSS it.** Every property below drives the REAL
``ToolRegistry().run(...)`` and the REAL confirmation round-trip
(``handle_confirmation_command`` -> ``confirm_pending_action`` ->
``run_approved``), the same way ``backend/tests/test_form_submit_gate.py``
does.

What this verifies (all against the real registry/gate, fully offline):

  1. ``screen.submit_form`` classifies as confirm-class.
  2. Defect A pin: a bare ``screen.type_text`` call stalls asking for
     approval and types nothing -- documenting why per-keystroke gating of a
     multi-field form was dead on arrival.
  3. ONE approval fills every field (in order, with the right resolved
     values -- two vault refs and one literal) and fires the submit click,
     through the real confirmation round-trip.
  4. Defect B pin: after that real round-trip, the on-disk ledger's raw text
     contains no field value and no vault plaintext.
  5. The pending call's stored args are exactly ``{spec_id, reason}`` -- a
     reference, never a value, ever reaches the gate's persisted call record.
  6. A forged/never-staged ``spec_id`` is inert: it reports
     ``unknown_or_expired_form_spec`` and never touches the screen. This is
     the injection defense for a tool whose args are otherwise "just an id".
  7. Staged forms are single-use (a popped id cannot be replayed) and an aged
     entry is treated as expired.
  8. ``describe_staged_form`` -- the manifest a human approves -- shows vault
     NAMES and literal values in full, but never a vault VALUE.
  9. ``screen.submit_form`` is absent from ``planner_specs()`` and its name
     does not start with ``web.``/``mcp.`` (the two prefixes that
     auto-expose a tool to the planner) -- it is trusted-console-only.
  10. The vault's only plaintext egress is ``Vault.resolve()``; no
      show/dump/export/reveal-shaped method exists anywhere on it.
  11. Phase 51's audited gate-class counts (``EXPECTED_CLASS_COUNTS``) already
      say ``confirm == 8`` for exactly this reason (``screen.submit_form`` is
      the 8th); this file imports that verifier's module and cross-checks the
      number so the two files cannot silently drift apart.
  12. Source property: ``stage_form`` -- the console-only entry point into
      staging -- is called from exactly one production module,
      ``backend/eva/core/fast_commands.py``. This cannot be checked by
      running code (nothing prevents a second caller from also behaving
      correctly at runtime), so it is checked by reading source.

Fully offline: no network, no LLM, no real mouse/keyboard movement, and the
vault + pending-action ledger are redirected to a throwaway temp directory
before anything that reads those paths is imported, so the real vault and the
real on-disk ledger are never touched.
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


# A tiny 3-field form + a submit button, laid out so each control's center is
# distinct and easy to assert on -- mirrors backend/tests/test_form_submit_gate.py
# exactly, so a reader who already knows that file recognizes this immediately:
# Email -> (90, 110), Password -> (90, 210), Notes -> (90, 310), Submit -> (90, 410).
def _build_form_elements(grounding):
    el = grounding.RawElement
    return [
        el(name="Email", role="Edit", left=50, top=100, width=80, height=20),
        el(name="Password", role="Edit", left=50, top=200, width=80, height=20),
        el(name="Notes", role="Edit", left=50, top=300, width=80, height=20),
        el(name="Submit", role="Button", left=50, top=400, width=80, height=20),
    ]


class _InputRecorder:
    """Stands in for the physical pyautogui layer -- records what WOULD have
    happened without ever touching a real mouse or keyboard. This is BELOW
    the tool-level gate: nothing here fakes ToolRegistry.run/run_approved or
    the confirmation flow."""

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


def main() -> int:
    # Redirect the vault and the pending-action ledger to a throwaway temp
    # directory BEFORE importing anything that reads those env vars, so this
    # verifier can never touch the real vault or the real on-disk ledger.
    tmpdir = tempfile.TemporaryDirectory(prefix="eva-phase62-verify-")
    tmp_path = Path(tmpdir.name)
    os.environ["EVA_VAULT_PATH"] = str(tmp_path / "vault.json")
    os.environ["EVA_VAULT_ENABLED"] = "1"
    os.environ["EVA_PENDING_ACTION_LEDGER_PATH"] = str(tmp_path / "pending_actions.jsonl")
    os.environ["EVA_GUI_GROUNDING_ENABLED"] = "1"

    try:
        return _run()
    finally:
        tmpdir.cleanup()


def _run() -> int:
    import dataclasses
    import json
    import re
    from datetime import datetime, timedelta, timezone

    from backend.eva.agent.action_model import AgentObservation
    from backend.eva.permissions.confirmation import handle_confirmation_command
    from backend.eva.permissions.ledger import ledger_path
    from backend.eva.screen import form_filler, grounding, screen_controller
    from backend.eva.screen.form_filler import (
        FormField,
        SubmitSpec,
        describe_staged_form,
        pop_staged_form,
        stage_form,
    )
    from backend.eva.security import tool_gate
    from backend.eva.tools.registry import ToolRegistry
    from backend.eva.vault import Vault
    from scripts import verify_eva_all
    from scripts import verify_eva_phase51_action_type_audit as phase51

    registry = ToolRegistry()

    # 1. screen.submit_form classifies as confirm on the REAL registry.
    submit_spec = registry.get("screen.submit_form")
    check(submit_spec is not None, "screen.submit_form must be registered")
    check(
        tool_gate.classify_tool_call(submit_spec) == "confirm",
        f"screen.submit_form must be confirm-class, got {tool_gate.classify_tool_call(submit_spec)!r}",
    )

    # Everything below drives the real registry + real gate + real confirmation
    # round-trip. Only three things are faked, and all are BELOW the tool-level
    # gate: which controls exist on screen (the accessibility-tree provider),
    # the physical pyautogui actuator that would otherwise move the mouse, and
    # (Phase 63) the foreground-window reader -- pinned to "Test App" to match
    # every staged form's window_title below, so the new pre-type window guard
    # (see verify_eva_phase63_live_fixes.py) does not spuriously abort this
    # verifier against whatever window actually has focus on the machine
    # running it.
    recorder = _InputRecorder(AgentObservation)
    form_elements = _build_form_elements(grounding)
    saved_provider = grounding._default_provider
    saved_click = screen_controller.click
    saved_type_text = screen_controller.type_text
    saved_press = screen_controller.press
    saved_window_title_fn = form_filler.foreground_window_title
    grounding._default_provider = lambda: list(form_elements)
    screen_controller.click = recorder.click
    screen_controller.type_text = recorder.type_text
    form_filler.foreground_window_title = lambda: "Test App"
    screen_controller.press = recorder.press

    try:
        # 2. Defect A pin: screen.type_text alone stalls on confirmation and
        # types NOTHING. This is exactly what fill_form hit per field, which
        # is why it could never fill a real form past field 1.
        bare = registry.run("screen.type_text", text="x", reason="probe")
        check(bare.get("ok") is False, f"a bare screen.type_text must not execute, got {bare}")
        check(bare.get("requires_confirmation") is True, f"a bare screen.type_text must require confirmation, got {bare}")
        check(recorder.typed == [], "no keystroke may land before approval")

        # Seed the vault with the two values the staged form will reference.
        vault = Vault(Path(os.environ["EVA_VAULT_PATH"]))
        seeded_email = vault.put("email_addr", "user@example.com")
        seeded_pw = vault.put("work_pw", "hunter2xyz")
        check(seeded_email and seeded_pw, "seeding the vault must succeed (DPAPI on this Windows account)")

        # 3. One approval fills every field (2 vault refs + 1 literal) and submits.
        staged = stage_form(
            [
                FormField("Email", "@vault:email_addr"),
                FormField("Password", "@vault:work_pw"),
                FormField("Notes", "a literal note"),
            ],
            reason="fill and submit test form",
            submit=SubmitSpec("click", label="Submit"),
            window_title="Test App",
        )
        gate_result = registry.run("screen.submit_form", spec_id=staged.spec_id, reason=staged.reason)
        check(gate_result.get("requires_confirmation") is True, f"a single call must not perform the form: {gate_result}")
        check(recorder.clicks == [] and recorder.typed == [], "nothing may happen on screen before approval")

        pending_id = gate_result["pending_id"]
        reply = handle_confirmation_command(f"confirm {pending_id}")
        check("Executed" in reply, f"the single approval must actually execute the whole form: {reply!r}")

        check(
            recorder.clicks == [(90, 110), (90, 210), (90, 310), (90, 410)],
            f"fields and the submit button must be clicked in order: {recorder.clicks}",
        )
        check(
            recorder.typed == ["user@example.com", "hunter2xyz", "a literal note"],
            f"fields must be typed in order with the RIGHT resolved values: {recorder.typed}",
        )

        # 4. Defect B pin, full round-trip: nothing typed reaches the raw ledger text.
        raw_ledger_text = ledger_path().read_text(encoding="utf-8")
        for leaked in ("user@example.com", "hunter2xyz", "a literal note"):
            check(leaked not in raw_ledger_text, f"{leaked!r} must never reach the on-disk ledger: {raw_ledger_text!r}")

        # Defect B pin, direct: a lone gated screen.type_text call also leaves
        # nothing in the ledger (the sensitive_args mask applies per-call, not
        # only inside a staged-form submission).
        registry.run("screen.type_text", text="hunter2xyz-direct", reason="probe direct leak")
        raw_ledger_text = ledger_path().read_text(encoding="utf-8")
        check("hunter2xyz-direct" not in raw_ledger_text, f"a typed secret leaked into the ledger: {raw_ledger_text!r}")

        # 5. Pending-call args are exactly {spec_id, reason} -- a reference,
        # never a value, ever reaches the gate's persisted in-memory call record.
        staged2 = stage_form(
            [FormField("Email", "@vault:email_addr")],
            reason="check pending args",
            submit=SubmitSpec("none"),
        )
        args_result = registry.run("screen.submit_form", spec_id=staged2.spec_id, reason="check pending args")
        pending_id2 = args_result["pending_id"]
        stored = tool_gate.get_pending_call(pending_id2)
        check(stored is not None, "register_pending_call did not persist the call")
        check(
            stored["args"] == {"spec_id": staged2.spec_id, "reason": "check pending args"},
            f"pending call args must be exactly spec_id+reason, got {stored['args']}",
        )
        args_blob = json.dumps(stored["args"])
        check(
            "user@example.com" not in args_blob and "hunter2xyz" not in args_blob,
            "no resolved value may reach the pending call's stored args",
        )

        # 6. A forged/never-staged spec_id is inert: never touches the screen.
        forged = registry.run("screen.submit_form", spec_id="fs_never_staged_by_anyone", reason="forged spec id attempt")
        check(forged.get("requires_confirmation") is True, f"a forged spec_id must still gate normally: {forged}")
        forged_pending_id = forged["pending_id"]
        clicks_before, typed_before = list(recorder.clicks), list(recorder.typed)
        forged_reply = handle_confirmation_command(f"confirm {forged_pending_id}")
        check(
            "unknown_or_expired_form_spec" in forged_reply,
            f"a forged spec_id must be reported inert, not silently ignored: {forged_reply!r}",
        )
        check(
            recorder.clicks == clicks_before and recorder.typed == typed_before,
            "a forged spec_id must never touch the screen, even after 'confirmation'",
        )

        # 7. Staged forms are single-use, and an aged entry is expired.
        single_use = stage_form([FormField("X", "literal")], reason="single-use check", submit=SubmitSpec("none"))
        first_pop = pop_staged_form(single_use.spec_id)
        check(first_pop is not None and first_pop.spec_id == single_use.spec_id, "a freshly staged form must be poppable once")
        second_pop = pop_staged_form(single_use.spec_id)
        check(second_pop is None, "a staged form must not be poppable a second time")

        ttl_check = stage_form([FormField("X", "literal")], reason="ttl check", submit=SubmitSpec("none"))
        aged = dataclasses.replace(
            ttl_check, created_at=datetime.now(timezone.utc) - timedelta(seconds=form_filler._STAGE_TTL_SECONDS + 5)
        )
        form_filler._STAGED_FORMS[ttl_check.spec_id] = aged
        check(pop_staged_form(ttl_check.spec_id) is None, "an aged staged form must be treated as expired")

        # 8. The manifest shows vault NAMES and literal values, never a vault VALUE.
        manifest_spec = stage_form(
            [
                FormField("Email", "@vault:email_addr"),
                FormField("Notes", "a literal note visible in manifest"),
            ],
            reason="manifest check",
            submit=SubmitSpec("click", label="Submit"),
            window_title="Some App",
        )
        manifest = describe_staged_form(manifest_spec)
        check("email_addr" in manifest, "the manifest must show the vault NAME")
        check("a literal note visible in manifest" in manifest, "the manifest must show literal values in full")
        check("user@example.com" not in manifest, "the manifest must never show a vault VALUE")
    finally:
        grounding._default_provider = saved_provider
        screen_controller.click = saved_click
        screen_controller.type_text = saved_type_text
        screen_controller.press = saved_press
        form_filler.foreground_window_title = saved_window_title_fn

    # 9. screen.submit_form is not planner-reachable and is not smuggled in via
    # the web./mcp. auto-expose prefixes.
    planner_names = {str(spec.get("name", "")) for spec in registry.planner_specs()}
    check("screen.submit_form" not in planner_names, "screen.submit_form must not be planner-reachable")
    check(not "screen.submit_form".startswith("web."), "sanity: screen.submit_form is not a web.* tool")
    check(not "screen.submit_form".startswith("mcp."), "sanity: screen.submit_form is not an mcp.* tool")

    # 10. The vault's only plaintext egress is resolve(); no show/dump/export/
    # reveal-shaped method exists anywhere on it.
    forbidden_words = ("show", "dump", "export", "reveal")
    public_methods = [name for name in dir(Vault) if not name.startswith("_")]
    check("resolve" in public_methods, "Vault.resolve must exist as the (only) plaintext egress")
    for name in public_methods:
        if name == "resolve":
            continue
        lowered = name.lower()
        check(
            not any(word in lowered for word in forbidden_words),
            f"Vault.{name} looks like a plaintext egress outside resolve() -- the vault must expose no value except via resolve()",
        )

    # 11. Cross-check against Phase 51's audited gate-class counts so the two
    # files cannot silently drift: confirm == 8 counts screen.submit_form as
    # the newest confirm-class tool.
    check(
        phase51.EXPECTED_CLASS_COUNTS["confirm"] == 8,
        "Phase 51's EXPECTED_CLASS_COUNTS['confirm'] must be 8 (screen.submit_form is the 8th confirm-class "
        f"tool); got {phase51.EXPECTED_CLASS_COUNTS.get('confirm')}. If this genuinely changed, update BOTH "
        "verifiers together and say why.",
    )

    # 12. Source property: stage_form is called from exactly one production
    # module, backend/eva/core/fast_commands.py. This is the console-only
    # invariant that is Phase 62's injection defense for staging -- it cannot
    # be proven by running code (nothing at runtime stops a second caller from
    # also behaving correctly), so it is proven by reading source.
    #
    # Scope is backend/eva/ (the production tree), not backend/tests/: this
    # project's own test philosophy (see test_form_submit_gate.py's module
    # docstring) is to call internals like stage_form directly to drive the
    # real gate -- that is a deliberate, reviewed exercise of the boundary,
    # not a second reachable path into it, so it is not what this property
    # is guarding against.
    eva_dir = ROOT / "backend" / "eva"
    definition_file = (ROOT / "backend" / "eva" / "screen" / "form_filler.py").resolve()
    call_pattern = re.compile(r"\bstage_form\s*\(")
    callers: list[str] = []
    for py_file in sorted(eva_dir.rglob("*.py")):
        if "__pycache__" in py_file.parts:
            continue
        if py_file.resolve() == definition_file:
            continue
        text = py_file.read_text(encoding="utf-8", errors="replace")
        if call_pattern.search(text):
            callers.append(str(py_file.relative_to(ROOT)).replace("\\", "/"))
    expected_caller = "backend/eva/core/fast_commands.py"
    check(
        callers == [expected_caller],
        f"stage_form must be called from exactly one production module ({expected_caller}); found {callers}. "
        "A second caller would be a second, un-reviewed way to stage attacker-controlled form fields.",
    )

    # Registration.
    name = "verify_eva_phase62_vault_form_submit.py"
    check(name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 62 verifier")
    check(name in verify_eva_all.QUICK_VERIFIERS, "quick profile missing the Phase 62 verifier")
    check(name in verify_eva_all.VERIFIER_DESCRIPTORS, "master descriptor missing the Phase 62 verifier")

    print(
        "PASS: Phase 62 vault + single gated form submission -- the real gate, not a stand-in for it. Two defects "
        "survived a fully green 90-verifier/607-test suite because every prior test injected a fake executor more "
        "permissive than the real system: (A) fill_form called the confirm-class screen.type_text per field, so a "
        "real submission stalled asking for approval at field 1 and never typed anything; (B) tool args were "
        "written into the on-disk pending-action ledger in plaintext, so a typed password would have persisted to "
        "disk before it was ever approved. This file drives the REAL ToolRegistry().run and the REAL "
        "handle_confirmation_command round-trip for both regressions and pins them: a bare screen.type_text still "
        "stalls and types nothing; one approval of screen.submit_form fills every field (two vault references and "
        "a literal, resolved in the right order) and fires the submit click; and the raw ledger text contains "
        "neither field value afterward. The staged-form store is single-use and TTL-expiring, a forged spec_id is "
        "inert and never touches the screen, the pending call's persisted args are exactly {spec_id, reason} -- a "
        "reference, never a value -- and the approval manifest shows vault NAMES and literal values but never a "
        "vault VALUE. screen.submit_form stays off the planner surface, the vault exposes no value except through "
        "resolve(), Phase 51's audited confirm-class count is cross-checked at 8 so the two files cannot drift "
        "apart silently, and a source-level scan confirms stage_form -- the console-only entry point -- is called "
        "from exactly one production module, fast_commands.py."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
