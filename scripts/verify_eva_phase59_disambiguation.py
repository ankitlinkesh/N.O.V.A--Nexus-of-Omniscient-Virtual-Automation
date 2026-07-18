"""Standalone verifier for Phase 59 (grounding disambiguation).

Phase 56's matcher promised "decline rather than click the wrong thing", but
locate() still silently picked the top of a near-tie — so two identically named
controls (two "OK" buttons) would resolve to whichever sorted first. This closes
that: a near-tie is AMBIGUOUS, and grounding refuses and surfaces the candidates
instead of guessing.

What this verifies (against fabricated trees — no real desktop):

  1. resolve() classifies: one clear match -> "found"; two equal matches ->
     "ambiguous" (target is None, both candidates listed); nothing above the
     floor -> "none".
  2. A clear winner over a weak second is NOT ambiguous (the margin is tight, so
     it does not over-refuse).
  3. locate() returns None for an ambiguous query — a safer no-op than a
     coin-flip click — and a MORE SPECIFIC label resolves the ambiguity.
  4. screen.click refuses an ambiguous label with the candidates, but a unique
     label still reaches the motor layer.

Fully offline: injected trees, no network, no real input.
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
    from backend.eva.screen import grounding
    from backend.eva.screen.grounding import RawElement, locate, resolve
    from backend.eva.screen.screen_tools import screen_click
    from scripts import verify_eva_all

    def el(name, role="button", left=100, top=100, w=80, h=30):
        return RawElement(name=name, role=role, left=left, top=top, width=w, height=h)

    saved_flag = os.environ.get("EVA_GUI_GROUNDING_ENABLED")
    saved_provider = grounding._default_provider

    try:
        os.environ["EVA_GUI_GROUNDING_ENABLED"] = "1"

        def use(elements):
            grounding._default_provider = lambda: list(elements)

        # 1. found / ambiguous / none.
        use([el("Submit"), el("Cancel")])
        found = resolve("Submit")
        check(found.status == "found" and found.target.label == "Submit", "one clear match must be 'found'")

        use([el("OK", left=100), el("OK", left=400)])
        amb = resolve("OK")
        check(amb.status == "ambiguous" and amb.target is None, "two equal matches must be 'ambiguous' with no target")
        check(len(amb.candidates) == 2, "both tied candidates must be surfaced")

        use([el("Frobnicate")])
        none = resolve("totally unrelated label")
        check(none.status == "none" and none.target is None, "nothing above the floor must be 'none'")

        # 2. A clear winner is not over-refused.
        use([el("Save"), el("Save As")])
        clear = resolve("Save")
        check(clear.status == "found" and clear.target.label == "Save", "a clear winner over a weak second must stay 'found'")

        # 3. locate() is safe on ambiguity; a specific label resolves it.
        use([el("OK", left=100), el("OK", left=400)])
        check(locate("OK") is None, "locate must return None for an ambiguous query, not a coin-flip click")
        use([el("Save"), el("Save and Close")])
        check(locate("Save and Close").label == "Save and Close", "a more specific label must resolve the ambiguity")

        # 4. screen.click refuses ambiguity, accepts a unique label.
        use([el("OK", left=100), el("OK", left=400)])
        refused = screen_click(reason="confirm the dialog", label="OK")
        check(refused.get("error") == "ambiguous_target", f"an ambiguous label must be refused, got {refused!r}")
        check("several controls" in refused.get("message", ""), "the refusal must list the ambiguous candidates")

        use([el("Submit"), el("Cancel")])
        unique = screen_click(reason="submit", label="Submit")
        check(unique.get("error") not in {"ambiguous_target", "ui_target_not_found"}, "a unique label must be accepted")
        blob = (str(unique.get("message", "")) + str(unique.get("error", ""))).lower()
        check("real input" in blob, "an accepted unique target must reach the real-input gate")

        # 5. Registration.
        name = "verify_eva_phase59_disambiguation.py"
        check(name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 59 verifier")
        check(name in verify_eva_all.QUICK_VERIFIERS, "quick profile missing the Phase 59 verifier")
        check(name in verify_eva_all.VERIFIER_DESCRIPTORS, "master descriptor missing the Phase 59 verifier")

    finally:
        if saved_flag is None:
            os.environ.pop("EVA_GUI_GROUNDING_ENABLED", None)
        else:
            os.environ["EVA_GUI_GROUNDING_ENABLED"] = saved_flag
        grounding._default_provider = saved_provider

    print(
        "PASS: Phase 59 grounding disambiguation -- the matcher's 'decline rather than click the wrong thing' now "
        "holds at the ambiguity level. resolve() returns 'found' only for one clear match; two controls that match a "
        "label about equally (two 'OK' buttons) are 'ambiguous' -- grounding refuses and surfaces both rather than "
        "guessing, and a clear winner over a weak second is NOT over-refused. locate() returns None on ambiguity (a "
        "safer no-op than a coin-flip), a more specific label resolves it, and screen.click refuses an ambiguous "
        "label with the candidates while still accepting a unique one."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
