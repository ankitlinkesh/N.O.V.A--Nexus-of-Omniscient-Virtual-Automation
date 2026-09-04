from __future__ import annotations

import json
from typing import Any

from . import screen_controller
from .form_filler import (
    FillOutcome,
    FillStep,
    StagedForm,
    _error_of,
    _looks_like_secret,
    _ok,
    ensure_staged_window,
    is_vault_ref,
    pop_staged_form,
    vault_ref_name,
    verify_declared_domain,
    verify_staged_origin,
)
from .screen_observer import observe_screen_once
from .ui_locator import UiTarget


def screen_observe(reason: str) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "reason_required", "message": "Screen observation requires an active task reason."}
    observation = observe_screen_once(reason)
    return {**observation.as_dict(), "ui_events": [{"type": "observing_screen", "reason": reason}]}


def _try_vision_fallback(label: str, required_confidence: float):
    """Look at the screen only when BOTH switches are on. Never raises.

    Returns (target-or-None, report-or-None). A `None` report means vision was
    never consulted at all, which the caller reports differently from "vision
    looked and declined" -- an operator debugging a refusal needs to know which.

    The GUI-scope requirement is the load-bearing half. `EVA_VISION_CLICK_ENABLED`
    is a persistent operator choice, but a persistent flag alone would mean any
    planner-reachable path could eventually cause a screenshot to be sent to
    Google. Requiring a scope means a person typed `gui:` for this specific task.
    """
    try:
        from .gui_scope import gui_scope_open
        from .vision_click import locate_by_vision, vision_click_enabled

        if not vision_click_enabled() or not gui_scope_open():
            return None, None
        floor = max(float(required_confidence), 0.80)
        return locate_by_vision(label, min_confidence=floor)
    except Exception:
        # Fail closed and quiet: an unavailable fallback must look like "no
        # target found", never like an error that might tempt a retry loop.
        return None, None


def screen_click(
    x: int | None = None,
    y: int | None = None,
    reason: str = "",
    target: dict[str, Any] | None = None,
    required_confidence: float = 0.75,
    label: str | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "reason_required", "message": "Screen click requires an active task reason."}
    ui_target: UiTarget | None = None
    if target is not None:
        ui_target = UiTarget.from_dict(target)
    elif label and str(label).strip():
        # Phase 56: resolve a text label ("Submit", "email field") to a verified
        # target via GUI grounding. Still no raw coordinates. Phase 59: if the
        # label matches several controls about equally, REFUSE and list them
        # rather than risk clicking the wrong one.
        from .grounding import resolve as ground_resolve

        resolution = ground_resolve(str(label), min_confidence=float(required_confidence))
        if resolution.status == "ambiguous":
            options = "; ".join(f"{c.label} ({c.role}) at ({c.x},{c.y})" for c in resolution.candidates)
            return {
                "ok": False,
                "error": "ambiguous_target",
                "message": f"'{label}' matches several controls ({options}). Give me a more specific label; I won't guess.",
                "ui_events": [{"type": "ui_target_ambiguous", "label": str(label), "candidates": [c.as_dict() for c in resolution.candidates]}],
            }
        ui_target = resolution.target
        if ui_target is None:
            # Phase 98 vision fallback, for apps that expose no accessibility
            # tree at all (Electron, canvas UIs, games) -- exactly the case where
            # there is no shell command either. Reached ONLY after the tree has
            # declined, and only with two independent switches on: the persistent
            # EVA_VISION_CLICK_ENABLED, and a console-opened GUI scope for this
            # one task. Untrusted content can flip neither.
            vision_target, vision_report = _try_vision_fallback(str(label), float(required_confidence))
            if vision_target is not None:
                ui_target = vision_target
            else:
                message = f"I couldn't confidently find '{label}' on the screen, so I did not click."
                events: list[dict[str, Any]] = [
                    {"type": "ui_target_low_confidence", "reason": "grounding_no_match", "label": str(label)}
                ]
                if vision_report is not None:
                    message += f" Looking at the screen did not help either ({vision_report.reason or 'no match'})."
                    events.append({"type": "vision_declined", **vision_report.as_dict()})
                return {"ok": False, "error": "ui_target_not_found", "message": message, "ui_events": events}
    if ui_target is None:
        return {
            "ok": False,
            "error": "ui_target_required",
            "message": "I will not click raw coordinates. I need a verified UI target with confidence and a reason.",
            "ui_events": [{"type": "ui_target_low_confidence", "reason": "missing_target"}],
        }
    if ui_target.confidence < float(required_confidence):
        return {
            "ok": False,
            "error": "ui_target_low_confidence",
            "target": ui_target.as_dict(),
            "message": f"I found {ui_target.label}, but confidence was too low to click safely.",
            "ui_events": [{"type": "ui_target_low_confidence", "target": ui_target.as_dict()}],
        }
    obs = screen_controller.click_target(ui_target, reason)
    return {
        "ok": obs.success,
        **obs.as_dict(),
        "ui_events": [
            {"type": "ui_target_found", "target": ui_target.as_dict()},
            {"type": "executing_visible_action", "action": "click", "reason": reason},
        ],
    }


def screen_type_text(text: str, reason: str) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "reason_required", "message": "Typing requires an active task reason."}
    # Phase 98: this tool types SAFE DATA only. A live secret value reaching it
    # means the value passed through the model's context to get here, and typing
    # it would put it on screen and into whatever field happens to be focused --
    # which, on the vision path, may not be the field anyone intended. Secrets
    # have their own route: `screen.submit_form` resolves a `@vault:name` AFTER
    # approval, immediately before typing, bound to the page origin, and never
    # places the value in the model's context at all.
    #
    # The error deliberately does not echo the offending text: a refusal must not
    # become the channel that relays the secret (the Phase 68 lesson).
    try:
        from ..privacy.secrets_broker import contains_secret_leak

        leaked = bool(contains_secret_leak(text))
    except Exception:
        # Fail cautious: if the check itself is unavailable, refuse rather than
        # type something nobody could screen.
        leaked = True
    if leaked:
        return {
            "ok": False,
            "error": "secret_value_refused",
            "message": (
                "That text contains a live credential, so I did not type it. Secrets go through "
                "`fill form:` with a @vault: reference, which resolves the value after you approve "
                "and never puts it in my context."
            ),
        }
    obs = screen_controller.type_text_visible(text, reason)
    return {"ok": obs.success, **obs.as_dict()}


def screen_hotkey(keys: list[str], reason: str) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "reason_required", "message": "Hotkey requires an active task reason."}
    obs = screen_controller.hotkey_bounded(keys, reason)
    return {"ok": obs.success, **obs.as_dict()}


def screen_press(key: str, reason: str) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "reason_required", "message": "Key press requires an active task reason."}
    obs = screen_controller.press_key_bounded(key, reason)
    return {"ok": obs.success, **obs.as_dict()}


def screen_scroll(amount: int, reason: str) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "reason_required", "message": "Scroll requires an active task reason."}
    obs = screen_controller.scroll(amount, reason)
    return {"ok": obs.success, **obs.as_dict()}


def screen_wait(seconds: float, reason: str) -> dict[str, Any]:
    obs = screen_controller.wait(seconds, reason)
    return {"ok": obs.success, **obs.as_dict()}


# -- form submission (Phase 62) ----------------------------------------------
#
# See form_filler.py's module docstring for the full picture. Short version:
# screen.type_text is confirm-class, so gating a form field-by-field (as
# fill_form does) stalls forever at field 1. This tool takes only an opaque
# spec_id for a form staged from the trusted console; ONE approval of
# screen.submit_form authorizes the whole composite click/type/submit
# sequence, which this handler then performs itself.


def _open_vault():
    """Best-effort vault handle, or ``None`` if disabled/unavailable. Never raises."""
    try:
        from ..vault import open_default_vault

        return open_default_vault()
    except Exception:
        return None


def _leak_guard(payload: dict[str, Any], used_values: list[str]) -> dict[str, Any]:
    """Function-scoped self-check: does the outcome accidentally quote a value
    this call actually used (a literal field value or a resolved vault secret)?

    This is deliberately NOT a security boundary on its own -- the outcome is
    built value-free by construction (FillStep/FillOutcome carry no value
    field) -- it exists to catch a FUTURE edit that accidentally puts a value
    into the return payload. Strictly local: no module global, no persistence,
    ``used_values`` lives only in the caller's stack frame.
    """
    try:
        serialized = json.dumps(payload, default=str)
    except Exception:
        serialized = str(payload)
    for value in used_values:
        if value and value in serialized:
            return {"ok": False, "error": "value_leak_guard"}
    return payload


def screen_submit_form(spec_id: str, reason: str) -> dict[str, Any]:
    """Perform an entire staged form (Phase 62): every click, keystroke, and
    the final submit action, from a single approved ``spec_id``.

    ``screen.submit_form`` carries no field values of its own -- only the
    opaque id of a form staged from the trusted console (see
    ``form_filler.stage_form``). That is the injection defense: the tool is
    inert without an id this process actually issued, so untrusted content
    cannot manufacture one. An unknown or expired id touches nothing.

    Returns a value-free outcome dict (:class:`form_filler.FillOutcome` shape)
    -- never a field value, and vault-backed fields are always marked secret.
    """
    staged: StagedForm | None = pop_staged_form(spec_id)
    if staged is None:
        return {
            "ok": False,
            "error": "unknown_or_expired_form_spec",
            "message": "That form is no longer staged (unknown or expired spec_id); nothing was touched.",
        }

    effective_reason = str(reason or "").strip() or str(staged.reason or "").strip() or "form submission"

    # Values actually used during this call. Kept STRICTLY local to this stack
    # frame -- never stored, logged, or returned -- and only read by the leak
    # guard right before each return, never by anything else in this function.
    used_values: list[str] = []

    steps: list[FillStep] = []
    filled = 0

    def _stop(outcome: FillOutcome) -> dict[str, Any]:
        return _leak_guard(outcome.as_dict(), used_values)

    for spec_field in staged.fields:
        label = spec_field.label.strip()
        is_ref = is_vault_ref(spec_field.value)
        # Vault-backed fields are ALWAYS secret, regardless of what the
        # heuristic in _looks_like_secret would say about the reference text
        # itself (e.g. "@vault:email" does not look like a live secret).
        secret = True if is_ref else _looks_like_secret(spec_field.value)

        # 0. Re-verify the foreground window is still the one this form was
        # staged against -- BEFORE every field, not just once at the start.
        # Between staging, human approval, and execution the foreground
        # window can change (a notification, an alt-tab, or -- as happened
        # live-driving this against a real browser form -- the terminal
        # simply holding focus while the approval happened in it); a
        # notification or popup stealing focus between field 2 and field 3
        # must stop the run rather than send field 3's value somewhere
        # unintended. See form_filler.verify_staged_window for the matching
        # rule (a stable window "identity", not exact title equality, so a
        # page rewriting its own document.title mid-fill does not itself
        # abort) and why an unrecorded staged title fails safe (refuse to
        # type blind) rather than proceeding. Phase 64: ensure_staged_window
        # additionally makes ONE best-effort attempt to restore focus to the
        # staged window before giving up (focus_window can actually work now)
        # -- the abort stays the fallback, only firing if that restore fails.
        window_error = ensure_staged_window(staged)
        if window_error:
            steps.append(FillStep(label, "window_changed", secret, window_error[:200]))
            return _stop(FillOutcome(steps, filled, False, f"aborted before '{label}': {window_error}"))

        # 0b. Phase 67: re-verify the browser ORIGIN, not just the window.
        # This is the identity half of the phishing gap the window guard
        # above cannot see -- a page can be titled and styled to look exactly
        # like the real site while living at a different domain. Only binds
        # when the staged window WAS a browser (see verify_staged_origin's
        # module comment for the full rule); a native app form is untouched.
        origin_error = verify_staged_origin(staged)
        if origin_error:
            steps.append(FillStep(label, "origin_changed", secret, origin_error[:200]))
            return _stop(FillOutcome(steps, filled, False, f"aborted before '{label}': {origin_error}"))

        if not label:
            steps.append(FillStep("", "not_found", secret, "empty field label"))
            return _stop(FillOutcome(steps, filled, False, "a field had no label"))

        # 1. Focus the field.
        #
        # *** THIS CALLS screen_click() DIRECTLY, AS A PLAIN PYTHON FUNCTION ***
        # *** NOT registry.run("screen.click", ...). DO NOT "FIX" THIS.      ***
        #
        # screen.type_text is confirm-class. If this handler routed back
        # through ToolRegistry.run(...), every keystroke would re-enter the
        # gate and ask the user to confirm typing AGAIN -- reproducing the
        # exact bug Phase 62 exists to fix (a real submission stalling
        # forever at field 1). We are already PAST the gate: the user's one
        # approval of screen.submit_form authorized this entire composite
        # action. The gates below this level still run and still matter --
        # real_input_enabled() inside screen_controller, the grounding
        # confidence floor, and ambiguity refusal in grounding.resolve() are
        # all still enforced inside screen_click/screen_type_text/screen_press
        # themselves. Only the per-call REGISTRY gate is intentionally
        # bypassed here, because it was already satisfied once for the form
        # as a whole.
        click = screen_click(label=label, reason=effective_reason)
        if not _ok(click):
            err = _error_of(click).lower()
            if "ambiguous" in err:
                steps.append(FillStep(label, "ambiguous", secret, _error_of(click).strip()[:200]))
                return _stop(FillOutcome(steps, filled, False, f"'{label}' matched several fields; be more specific"))
            if "ui_target_not_found" in err or "target_required" in err or "low_confidence" in err:
                steps.append(FillStep(label, "not_found", secret, f"could not find field '{label}' on screen"))
                return _stop(FillOutcome(steps, filled, False, f"could not find field '{label}'"))
            steps.append(FillStep(label, "click_refused", secret, _error_of(click).strip()[:160]))
            return _stop(FillOutcome(steps, filled, False, f"click on '{label}' was refused"))

        # 2. Resolve the value as LATE as possible -- immediately before typing,
        #    into a local that is never stored, returned, or logged. A vault
        #    reference resolves to plaintext only right here; if it cannot be
        #    resolved we stop rather than ever typing the literal "@vault:..."
        #    text into the form (that would leak the reference into the page
        #    and fill it with garbage).
        if is_ref:
            name = vault_ref_name(spec_field.value)
            vault = _open_vault()
            if vault is None:
                steps.append(FillStep(label, "vault_unavailable", secret, "the vault is unavailable"))
                return _stop(FillOutcome(steps, filled, False, f"the vault is unavailable, so '{label}' (saved: {name}) could not be filled"))

            # Phase 67 rule (b): a vault entry that DECLARES a required domain
            # binds regardless of whether the window looked like a browser at
            # staging time -- and fails CLOSED if the current origin cannot be
            # read at all. Checked before resolve(), so an unreadable/mismatched
            # origin never even decrypts the value, let alone types it.
            required_domain = vault.entry_domain(name) if name else ""
            if required_domain:
                domain_error = verify_declared_domain(required_domain)
                if domain_error:
                    steps.append(FillStep(label, "origin_mismatch", secret, domain_error[:200]))
                    return _stop(FillOutcome(steps, filled, False, f"aborted before '{label}': {domain_error}"))

            value = vault.resolve(name) if name else None
            if value is None:
                # Distinguish a genuinely absent secret from one that EXISTS but
                # could not be decrypted (Phase 81). The latter -- most often a
                # value saved under a different Windows account -- previously read
                # as "not found" and sent the user to re-save a secret that was
                # actually there, which DPAPI would still refuse.
                reason = vault.last_resolve_error() if name else "not_found"
                if reason and reason != "not_found":
                    detail = (
                        f"saved value '{name}' exists but could not be decrypted "
                        "(it may have been saved under a different Windows account)"
                    )
                    steps.append(FillStep(label, "vault_undecryptable", secret, detail[:200]))
                    return _stop(FillOutcome(steps, filled, False, f"{detail} for '{label}'"))
                steps.append(FillStep(label, "vault_missing", secret, f"saved value '{name}' not found"))
                return _stop(FillOutcome(steps, filled, False, f"no saved value named '{name}' for '{label}'"))
        else:
            value = spec_field.value

        used_values.append(value)
        typed = screen_type_text(text=value, reason=effective_reason)
        value = None  # drop the local reference the instant it is no longer needed
        if not _ok(typed):
            steps.append(FillStep(label, "type_refused", secret, _error_of(typed).strip()[:160]))
            return _stop(FillOutcome(steps, filled, False, f"typing into '{label}' was refused"))

        steps.append(FillStep(label, "filled", secret))
        filled += 1

    # 3. The final submit action -- same direct-call rule as step 1 above.
    # Also re-verified against the window: submitting still ACTS on screen
    # (a click, a keypress), so the same focus-theft window applies here too
    # (including the Phase 64 restore-then-reverify in ensure_staged_window).
    if staged.submit.mode in ("click", "press"):
        window_error = ensure_staged_window(staged)
        if window_error:
            steps.append(FillStep(staged.submit.label or staged.submit.key, "window_changed", False, window_error[:200]))
            return _stop(FillOutcome(steps, filled, False, f"aborted before submitting: {window_error}"))

        origin_error = verify_staged_origin(staged)
        if origin_error:
            steps.append(FillStep(staged.submit.label or staged.submit.key, "origin_changed", False, origin_error[:200]))
            return _stop(FillOutcome(steps, filled, False, f"aborted before submitting: {origin_error}"))

    if staged.submit.mode == "click" and staged.submit.label:
        submitted = screen_click(label=staged.submit.label, reason=effective_reason)
        if not _ok(submitted):
            steps.append(FillStep(staged.submit.label, "submit_refused", False, _error_of(submitted).strip()[:160]))
            return _stop(FillOutcome(steps, filled, False, f"submitting via '{staged.submit.label}' was refused"))
    elif staged.submit.mode == "press" and staged.submit.key:
        submitted = screen_press(key=staged.submit.key, reason=effective_reason)
        if not _ok(submitted):
            steps.append(FillStep(staged.submit.key, "submit_refused", False, _error_of(submitted).strip()[:160]))
            return _stop(FillOutcome(steps, filled, False, f"submitting via key '{staged.submit.key}' was refused"))
    # mode == "none": nothing further to do.

    return _stop(FillOutcome(steps, filled, True, None))
