"""Standalone verifier for Phase 115 (analyze_screen uploads the window in front).

The user's decision (2026-09-20). Phase 108 widened this tool to the whole
desktop because it had been photographing one arbitrary non-primary monitor; the
cost was that "what's on my screen?" sent every other app and display to Google.
Measured here: the foreground window is 1129x502 against a 3286x1146 desktop.

Pinned: the default scope is the foreground window; no window means REFUSE (never
widen); the reply names the window photographed; a trusted in-process caller (the
vision click) may still pass its own region; `region` is still not a planner
argument, so nothing the model emits can widen what leaves the machine.

Nothing is photographed: the capture and the vision call are faked.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

failures = 0


def emit(case: str, ok: bool, **extra: object) -> int:
    payload = {"case": case, "pass": bool(ok)}
    payload.update(extra)
    print(json.dumps(payload, indent=2, default=str))
    return 0 if ok else 1


try:
    from eva.desktop import windows as windows_module
    from eva.screen import capture as capture_module
    from eva.screen.capture import CaptureRegion
    from eva.tools import registry as registry_module
    from eva.tools.registry import ToolRegistry

    WINDOW = CaptureRegion(left=100, top=50, width=800, height=600)
    seen: dict = {}

    def fake_capture(region=None):
        seen["region"] = region
        return {
            "ok": True,
            "image_path": "fake.jpg",
            "bytes": 1,
            "region": None if region is None else {"left": region.left, "top": region.top, "width": region.width, "height": region.height},
            "captured_at": "now",
            "note": "fake",
        }

    originals = (registry_module._capture_screen, registry_module.analyze_screen_image_sync, capture_module.foreground_window_region, windows_module.get_active_window)
    registry_module._capture_screen = fake_capture
    registry_module.analyze_screen_image_sync = lambda path, user_question=None: {"ok": True, "summary": "a description"}
    windows_module.get_active_window = lambda: type("W", (), {"title": "Calculator"})()
    try:
        capture_module.foreground_window_region = lambda: WINDOW
        result = registry_module._analyze_screen(question="what is this?")
        failures += emit(
            "the default upload is the foreground window, named in the reply",
            seen.get("region") == WINDOW and result["capture"]["scope"] == "foreground_window" and "Calculator" in result["summary"],
            region=result["capture"]["region"],
        )

        seen.clear()
        registry_module._analyze_screen(question="where is the button?", region=WINDOW)
        failures += emit("a trusted in-process caller may still pass its own region", seen.get("region") == WINDOW)

        seen.clear()
        capture_module.foreground_window_region = lambda: None
        refused = registry_module._analyze_screen(question="what is this?")
        failures += emit(
            "no foreground window REFUSES rather than widening to the desktop",
            refused.get("ok") is False and refused.get("error") == "no_foreground_window" and "region" not in seen,
        )
    finally:
        (
            registry_module._capture_screen,
            registry_module.analyze_screen_image_sync,
            capture_module.foreground_window_region,
            windows_module.get_active_window,
        ) = originals

    schema = ToolRegistry().get("analyze_screen").args_schema or {}
    failures += emit("region is still not a planner argument", "region" not in (schema.get("properties") or {}))

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    failures += emit("README records Phase 115", "| 115 |" in readme)
except Exception as exc:  # pragma: no cover
    failures += emit("behavioural checks ran", False, error=f"{type(exc).__name__}: {exc}")

print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
raise SystemExit(0 if failures == 0 else 1)
