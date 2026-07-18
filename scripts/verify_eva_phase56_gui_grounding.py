"""Standalone verifier for Phase 56 (GUI grounding — the eyes).

For the whole project NOVA has been blind to GUIs: ``screen.observe`` grabbed a
screenshot but extracted nothing, ``ui_locator.locate_by_text_hint`` was a
``return None`` stub, and ``screen.click`` refuses raw coordinates and demands a
verified target nothing could produce — so "click Submit" / "fill the email
field" had no path. This is the missing bridge: a text label becomes a specific
on-screen target with coordinates and a confidence.

What this verifies (against fabricated accessibility trees — no real desktop):

  1. THE MATCHER PICKS THE RIGHT CONTROL: an exact label wins; a role word
     ("field") is stripped so "email field" matches a control named "Email".
  2. IT DECLINES RATHER THAN CLICKS THE WRONG THING: a wrong-role match falls
     below the click floor; off-screen/zero-size score zero; a disabled control
     is penalised, not chosen.
  3. IT IS OFF BY DEFAULT AND DEGRADES SAFELY: with the flag off, or the
     UIAutomation library absent, locate() returns None — byte-identical to the
     old stub, so nothing changes until the operator opts in.
  4. THE BRIDGE IS WIRED END TO END: screen.click(label="Submit") resolves a
     target through grounding, clears the confidence gate, and reaches the motor
     layer (which is itself gated behind EVA_ENABLE_REAL_INPUT); a no-match
     refuses; ui_locator.locate_by_text_hint now delegates to grounding.

Fully offline: injected trees, no network, no LLM, no real input.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def check(value: object, message: str) -> None:
    if not value:
        raise AssertionError(message)


def main() -> int:
    from backend.eva.screen import grounding, ui_locator
    from backend.eva.screen.grounding import RawElement, locate, rank_targets, score_element
    from backend.eva.screen.screen_tools import screen_click
    from scripts import verify_eva_all

    def el(name, role="button", left=100, top=200, w=80, h=30, enabled=True, on_screen=True):
        return RawElement(name=name, role=role, left=left, top=top, width=w, height=h, enabled=enabled, on_screen=on_screen)

    form = [
        el("Submit", "button", 300, 500, 100, 40),
        el("Cancel", "button", 180, 500, 100, 40),
        el("Email", "edit", 200, 200, 240, 30),
        el("Password", "edit", 200, 260, 240, 30),
        el("Remember me", "checkbox", 200, 320, 20, 20),
    ]

    saved_flag = os.environ.get("EVA_GUI_GROUNDING_ENABLED")
    saved_provider = grounding._default_provider

    try:
        # 1. The matcher picks the right control.
        check(score_element("Submit", el("Submit")) >= 0.95, "an exact label must score near-certain")
        check(score_element("email field", el("Email", "edit")) >= 0.9, "'email field' must match the Email edit control")

        ranked = rank_targets("Cancel", form, floor=0.0)
        check(ranked and ranked[0].label == "Cancel", "ranking must put the queried control first")
        check((ranked[0].x, ranked[0].y) == (230, 520), f"the target must carry the control's CENTER, got {(ranked[0].x, ranked[0].y)}")

        # 2. It declines rather than clicking the wrong thing.
        wrong_role = score_element("Submit field", el("Submit", "button"))
        right_role = score_element("Submit button", el("Submit", "button"))
        check(right_role > wrong_role, "the right control kind must outscore the wrong one")
        check(wrong_role < 0.75, "a wrong-role match must fall below the click floor")
        check(score_element("Submit", el("Submit", on_screen=False)) == 0.0, "an off-screen control must score zero")
        check(score_element("Submit", el("Submit", w=0)) == 0.0, "a zero-size control must score zero")
        disabled = score_element("Submit", el("Submit", enabled=False))
        check(0.0 < disabled < 0.75, "a disabled control must be penalised, not chosen")

        # 3. Off by default + safe degradation.
        os.environ.pop("EVA_GUI_GROUNDING_ENABLED", None)
        grounding._default_provider = lambda: list(form)
        check(locate("Submit") is None, "with the flag OFF, locate must return None (the old stub behaviour)")
        check(ui_locator.locate_by_text_hint("Submit") is None, "ui_locator must stay a no-op when grounding is off")

        os.environ["EVA_GUI_GROUNDING_ENABLED"] = "1"
        # Library-absent degradation: the REAL provider yields [] on this box.
        grounding._default_provider = grounding._uiautomation_elements
        check(grounding.enumerate_elements() == [], "no UIAutomation library must degrade to no targets, not an error")
        check(locate("Submit") is None, "no targets must yield no location, never a guess")

        # 4. The bridge, wired end to end, on an injected tree.
        grounding._default_provider = lambda: list(form)
        target = locate("email field")
        check(target is not None and target.label == "Email", "grounding must locate the email field")
        check((target.x, target.y) == (320, 215), f"located target must be the field's center, got {(target.x, target.y)}")
        check(ui_locator.locate_by_text_hint("Submit") is not None, "ui_locator must now delegate to grounding when on")

        clicked = screen_click(reason="submit the login form", label="Submit")
        check(
            clicked.get("error") not in {"ui_target_required", "ui_target_not_found", "ui_target_low_confidence"},
            f"click-by-label must ACCEPT the grounded target, got {clicked!r}",
        )
        blob = (str(clicked.get("message", "")) + str(clicked.get("error", ""))).lower()
        check("real input" in blob, "the only thing stopping the click must be the real-input gate (proving the target was accepted)")

        no_match = screen_click(reason="click the frobnicator", label="frobnicator 3000")
        check(no_match.get("error") == "ui_target_not_found", "a no-match label must refuse, not click something else")

        # 5. Registration.
        name = "verify_eva_phase56_gui_grounding.py"
        check(name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 56 verifier")
        check(name in verify_eva_all.QUICK_VERIFIERS, "quick profile missing the Phase 56 verifier")
        check(name in verify_eva_all.VERIFIER_DESCRIPTORS, "master descriptor missing the Phase 56 verifier")

    finally:
        if saved_flag is None:
            os.environ.pop("EVA_GUI_GROUNDING_ENABLED", None)
        else:
            os.environ["EVA_GUI_GROUNDING_ENABLED"] = saved_flag
        grounding._default_provider = saved_provider

    print(
        "PASS: Phase 56 GUI grounding -- the eyes NOVA never had. A text label now becomes a specific on-screen "
        "target: the matcher strips role words ('email field' -> the Email edit control), picks the right control, "
        "and DECLINES rather than clicking the wrong one (wrong-role/off-screen/zero-size fall below the floor; a "
        "disabled control is penalised not chosen). It is OFF by default and degrades to no-targets when the "
        "UIAutomation library is absent -- byte-identical to the old stub. Wired end to end: screen.click(label='Submit') "
        "resolves through grounding, clears the confidence gate, and reaches the motor layer (still behind "
        "EVA_ENABLE_REAL_INPUT); a no-match refuses; ui_locator.locate_by_text_hint delegates to grounding. Install "
        "'uiautomation' and set EVA_GUI_GROUNDING_ENABLED=1 to give NOVA real eyes."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
