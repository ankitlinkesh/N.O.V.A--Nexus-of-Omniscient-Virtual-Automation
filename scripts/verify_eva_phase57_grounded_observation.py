"""Standalone verifier for Phase 57 (grounded screen observation).

Phase 56 gave NOVA the ability to ACT on a known label. But screen.observe still
returned the window title and an empty ui_targets list — NOVA could not SEE what
labels exist to act on. This closes the observe->act loop: screen.observe now
reports the clickable controls on screen, from the same accessibility tree Phase
56 clicks through.

What this verifies (against fabricated trees — no real desktop, no screenshot):

  1. describe_visible lists only REAL clickable controls: unnamed, zero-size and
     off-screen controls are dropped; each target carries its center coordinates.
  2. It is OFF by default: with the flag off it returns an empty report, so
     observation is byte-identical to before until the operator opts in.
  3. It is INDEPENDENT OF PIXELS: observe_screen_once attaches the UI report even
     when the screenshot grab fails (the tree is not the screenshot).
  4. It STAYS INSIDE THE GATE: screen.observe is still override-class
     (PRIVACY_SCREEN_READ) — reading the UI tree opens no new lowered-friction
     path, and there is deliberately no fast-command that reads the screen.

Fully offline: injected trees, monkeypatched capture, no network, no LLM.
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
    from backend.eva.screen import grounding, screen_observer
    from backend.eva.screen.grounding import RawElement, describe_visible
    from backend.eva.security import tool_gate
    from backend.eva.tools.registry import ToolRegistry
    from scripts import verify_eva_all

    form = [
        RawElement("Submit", "button", 300, 500, 100, 40),
        RawElement("Email", "edit", 200, 200, 240, 30),
        RawElement("Password", "edit", 200, 260, 240, 30),
        RawElement("", "text", 0, 0, 0, 0),                          # unnamed/zero
        RawElement("Offscreen", "button", 10, 10, 40, 20, on_screen=False),
    ]

    saved_flag = os.environ.get("EVA_GUI_GROUNDING_ENABLED")
    saved_provider = grounding._default_provider
    saved_capture = screen_observer.capture_screen

    try:
        os.environ["EVA_GUI_GROUNDING_ENABLED"] = "1"
        grounding._default_provider = lambda: list(form)

        # 1. Only real clickable controls, with center coordinates.
        report = describe_visible()
        labels = [t["label"] for t in report["ui_targets"]]
        check(labels == ["Submit", "Email", "Password"], f"unnamed/zero/offscreen must be dropped, got {labels}")
        check(report["count"] == 3, "count must match the reported targets")
        submit = report["ui_targets"][0]
        check((submit["x"], submit["y"]) == (350, 520), f"targets must carry center coords, got {(submit['x'], submit['y'])}")
        check("Submit (button)" in report["summary"], "the summary must name the controls")

        # 2. Off by default.
        os.environ.pop("EVA_GUI_GROUNDING_ENABLED", None)
        empty = describe_visible()
        check(empty == {"ui_targets": [], "count": 0, "summary": ""}, "with the flag OFF the report must be empty")
        os.environ["EVA_GUI_GROUNDING_ENABLED"] = "1"

        # 3. Independent of pixels: attached even when the screenshot fails.
        def boom(_reason):
            raise RuntimeError("no display")

        screen_observer.capture_screen = boom
        obs = screen_observer.observe_screen_once("check the login form")
        check(obs.ok is False and obs.error == "screen_observation_unavailable", "a failed grab must still report unavailable")
        check([t["label"] for t in obs.ui_targets] == ["Submit", "Email", "Password"], "the UI report must survive a failed screenshot")
        check("Visible controls" in obs.local_summary, "the summary must include the grounded controls")

        # ...and merged into the summary on a successful grab.
        from backend.eva.screen.screen_observer import ScreenFrame

        screen_observer.capture_screen = lambda _r: ScreenFrame("f1", "C:/tmp/f1.png", 1920, 1080, "2026-07-17T00:00:00+00:00", "Login")
        ok_obs = screen_observer.observe_screen_once("check the login form")
        check(ok_obs.ok is True, "a successful grab must observe ok")
        check([t["label"] for t in ok_obs.ui_targets] == ["Submit", "Email", "Password"], "targets must be attached on success too")
        check("Active window" in ok_obs.local_summary and "Visible controls" in ok_obs.local_summary, "summary must combine window + controls")

        # 4. Reading the screen stays override-class, and no fast-command reads it.
        tool_gate.reset_pending_calls()
        spec = ToolRegistry().get("screen.observe")
        decision = tool_gate.classify_tool_call(spec)
        check(decision == "override", f"screen.observe must remain override-class, got {decision!r}")

        fc_source = (ROOT / "backend" / "eva" / "core" / "fast_commands.py").read_text(encoding="utf-8")
        check("describe_visible" not in fc_source, "screen reading must NOT be exposed via a gate-bypassing fast-command")

        # 5. Registration.
        name = "verify_eva_phase57_grounded_observation.py"
        check(name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 57 verifier")
        check(name in verify_eva_all.QUICK_VERIFIERS, "quick profile missing the Phase 57 verifier")
        check(name in verify_eva_all.VERIFIER_DESCRIPTORS, "master descriptor missing the Phase 57 verifier")

    finally:
        if saved_flag is None:
            os.environ.pop("EVA_GUI_GROUNDING_ENABLED", None)
        else:
            os.environ["EVA_GUI_GROUNDING_ENABLED"] = saved_flag
        grounding._default_provider = saved_provider
        screen_observer.capture_screen = saved_capture
        tool_gate.reset_pending_calls()

    print(
        "PASS: Phase 57 grounded screen observation -- screen.observe now reports the clickable controls on screen, "
        "not just the window title, closing the observe->act loop from the same accessibility tree Phase 56 clicks "
        "through. It lists only real controls (unnamed/zero-size/off-screen dropped) with center coordinates, is OFF "
        "by default (byte-identical observation until opt-in), survives a failed screenshot (the tree is not the "
        "pixels), and stays inside the existing override-class screen.observe gate -- reading the UI opens no new "
        "lowered-friction path and no fast-command reads the screen."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
