"""Phase 108 -- a screenshot now carries the region it came from.

WHAT WENT WRONG
---------------
The vision click took TWO screenshots and mixed up their geometry:

  * `screen/capture.py` grabbed `mss().monitors[1]` -- the image sent to Gemini.
  * `locate_by_vision` separately called a bare `ImageGrab.grab()` purely to ask
    "how big is the screen", and passed THOSE dimensions to `to_target`.
  * `to_target` scaled the model's 0-1000 grid onto them and added no origin.

Two grabs, two regions, one's coordinates applied to the other. Measured on the
machine this was found on: `monitors[1]` is 1366x768 at (1920, 378);
`ImageGrab.grab()` is 1920x1080 at (0, 0). So a correct answer about a window on
the second display was converted into a point on the first one.

`monitors[1]` is not the primary monitor either. mss enumerates in
EnumDisplayMonitors order; here `monitors[1]` reports `is_primary: False` and the
real primary is `monitors[2]`. The function was called
`capture_primary_screen_jpeg`.

THIS RETIRES A CLAIM PHASE 107 SHIPPED
--------------------------------------
The Phase 107 row said the click missed because the capture covered only the
primary monitor, so "the target was never in the picture". Re-measured, that is
false: the target WAS in the picture and the model located it correctly. The row
has been corrected rather than left standing, the same way Phase 105 retired the
UWP focus claim. A wrong diagnosis in the record is worse than none, because it
is quoted.

WHAT WAS MEASURED AFTER THE FIX
-------------------------------
Driven live against the same canvas page on the same second display:

  * Vision target moved from (393, 380) -- on the OTHER display -- to (2053, 424)
    and then, once the capture was scoped to the window, to (2320, 714) and
    (2748, 898), all inside the target window.
  * THE COORDINATE PIPELINE IS VERIFIED FROM OUTSIDE. Asking for `Quarry`, NOVA
    aimed at screen (2748, 898); the page's own click log recorded
    `CLICKED:nothing @597,417 screen 2748,898`. The page independently reports
    the exact coordinate NOVA computed, so capture region -> grid -> image ->
    screen -> click is correct end to end.
  * WHAT REMAINS IS THE MODEL'S OWN PRECISION, now quantified instead of unknown:
        target      model grid    true grid     error
        Marmalade   (297, 443)    (299, 291)    ( -2, +152)
        Quarry      (608, 680)    (707, 563)    (-99, +117)
    100-150 grid units, 10-15% of the frame, biased downward. Two samples is not
    enough to fit a correction, and fitting one from two points is the
    reasoned-not-measured move this project keeps having to retire. Not attempted.
    The flag ships OFF with the inaccuracy NAMED AND NUMBERED.

AND A COST THIS PHASE MEASURED ON ITSELF
----------------------------------------
The first fix captured the whole desktop, because that is the space clicks can
reach. Driving it showed what that means in practice: the validation grab swept
up an unrelated live video call on the other display and sent it to Google. So
the vision path now captures the FOREGROUND WINDOW only -- 28% of the desktop on
the machine measured -- and REFUSES if it cannot establish one, because widening
the shot is never the safe fallback. `region` is deliberately absent from
`analyze_screen`'s args_schema so a planner cannot widen it.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

CAPTURE_PY = ROOT / "backend" / "eva" / "screen" / "capture.py"
VISION_PY = ROOT / "backend" / "eva" / "screen" / "vision_click.py"
REGISTRY_PY = ROOT / "backend" / "eva" / "tools" / "registry.py"
OBSERVER_PY = ROOT / "backend" / "eva" / "screen" / "screen_observer.py"
README = ROOT / "README.md"

failures = 0


def emit(case: str, ok: bool, **extra: object) -> int:
    payload = {"case": case, "pass": bool(ok)}
    payload.update(extra)
    print(json.dumps(payload, indent=2))
    return 0 if ok else 1


def strip_comments(source: str) -> str:
    """Checks must read CODE, not the prose explaining it.

    Phase 97's row records this trap and Phase 107 walked into it again: a check
    for `os.environ["GEMINI_API_KEY"]` passed because the string appeared only in
    a comment saying it had been removed.
    """
    out = []
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        out.append(line)
    return "\n".join(out)


capture_src = CAPTURE_PY.read_text(encoding="utf-8")
vision_src = VISION_PY.read_text(encoding="utf-8")
registry_src = REGISTRY_PY.read_text(encoding="utf-8")
observer_src = OBSERVER_PY.read_text(encoding="utf-8")

capture_code = strip_comments(capture_src)
vision_code = strip_comments(vision_src)
registry_code = strip_comments(registry_src)

# --------------------------------------------------------------------- naming
# The old name is a lie twice over and there is no alias: a compatibility
# wrapper is "one rule written in two places, and the unwatched copy decides".
failures += emit(
    "the misleading name is gone everywhere",
    "capture_primary_screen_jpeg" not in capture_code
    and "capture_primary_screen_jpeg" not in registry_code,
)
failures += emit("the replacement exists", "def capture_screen_jpeg(" in capture_code)
failures += emit(
    "no compatibility alias was left behind",
    capture_code.count("def capture_primary_screen_jpeg") == 0,
)

# The stub in test_gate_execution_honesty patches BY NAME. If the rename left it
# behind, monkeypatch would patch a dead name and the test would silently
# exercise the real capture instead of the stub.
gate_test = (ROOT / "backend" / "tests" / "test_gate_execution_honesty.py").read_text(encoding="utf-8")
failures += emit(
    "the capture stub patches the name that now exists",
    "capture_screen_jpeg" in gate_test and "capture_primary_screen_jpeg" not in strip_comments(gate_test),
)

# The same trap, in a verifier rather than a test, and it was live: phase86 used
# a BARE ATTRIBUTE ASSIGNMENT, which does not raise on a name that no longer
# exists -- it just creates a dead attribute and lets the real capture run. The
# verifier went on passing while stubbing nothing. monkeypatch(raising=True) in
# the pytest file catches this; a plain assignment cannot, so it needs a guard.
phase86 = (ROOT / "scripts" / "verify_eva_phase86_gate_execution.py").read_text(encoding="utf-8")
phase86_code = strip_comments(phase86)
failures += emit(
    "the phase86 verifier's capture stub patches a live name",
    "registry_mod.capture_screen_jpeg =" in phase86_code
    and "registry_mod.capture_primary_screen_jpeg =" not in phase86_code,
)
failures += emit(
    "the phase86 stub fails loudly if its target disappears again",
    "would patch nothing" in phase86,
    detail="a stub that silently stops stubbing is a check that cannot fail",
)

# ------------------------------------------------------------- the second grab
# This is the defect itself. locate_by_vision must not take its own screenshot.
def function_code(source: str, name: str) -> str:
    """A function's executable body: no docstring, no comments, no later defs.

    Written because the first version of the check below FAILED against correct
    code -- it searched the whole tail of the file and matched `ImageGrab.grab()`
    inside this very function's docstring, where it appears explaining what was
    removed. Phase 97's row records this trap and Phase 107 hit it too. A check
    that reads the prose about the code is not reading the code.
    """
    body = source.split(f"def {name}", 1)[1]
    # Stop at the next top-level def, so a later function's code is not scanned.
    lines = body.splitlines()
    kept: list[str] = []
    for line in lines[1:]:
        if line.startswith("def ") or line.startswith("class "):
            break
        kept.append(line)
    body = "\n".join(kept)
    # Drop docstrings.
    return re.sub(r'"""[\s\S]*?"""', "", body)


locate_body = function_code(vision_code, "locate_by_vision")
failures += emit(
    "locate_by_vision no longer takes its own screenshot",
    "ImageGrab" not in locate_body,
    detail="a second grab is a second region, which is the whole bug",
)
failures += emit(
    "the screen_size injection point is gone",
    "screen_size" not in vision_code,
    detail="a size without an origin cannot place a click",
)

# ------------------------------------------------------------ the region rides
failures += emit("CaptureRegion exists", "class CaptureRegion" in capture_code)
failures += emit(
    "the region carries an origin, not just a size",
    all(field in capture_code for field in ("left:", "top:", "width:", "height:")),
)
failures += emit(
    "the capture reports its region to callers",
    '"region": region.as_dict()' in registry_code,
)
failures += emit(
    "analyze_screen passes the region through to its caller",
    '"region": capture.get("region")' in registry_code,
)

# ------------------------------------------------- the two steps stay separate
# Collapsing scale-and-offset into one expression is how Phase 60's
# double-centering bug read; keeping them apart is what makes it reviewable.
to_target_body = vision_code.split("def to_target", 1)[1].split("def ", 1)[0]
failures += emit(
    "grid->image and image->screen are separate steps",
    "x_in_image" in to_target_body and "region.to_screen(" in to_target_body,
)
failures += emit(
    "the bounds check runs in image space, before the offset",
    to_target_body.index("x_in_image < region.width") < to_target_body.index("region.to_screen("),
)

# ------------------------------------------------------------------ the scope
failures += emit(
    "the vision path scopes the shot to the foreground window",
    "foreground_window_region" in vision_code,
)
failures += emit(
    "it refuses rather than widening when no window can be established",
    "no_window_region" in vision_code,
)
failures += emit(
    "an absent region is refused rather than guessed",
    "no_capture_region" in vision_code,
)
failures += emit("off-screen rects are trimmed", "def clamp_to_desktop" in capture_code)

# The scope control must not be reachable by a planner argument.
try:
    from eva.tools.registry import ToolRegistry

    schema = (ToolRegistry()._tools["analyze_screen"].args_schema or {})
    props = schema.get("properties") or {}
    failures += emit(
        "capture scope is not a planner-settable argument",
        "region" not in props and schema.get("additionalProperties") is not True,
        properties=sorted(props),
    )
except Exception as exc:  # pragma: no cover
    failures += emit("capture scope is not a planner-settable argument", False, error=str(exc))

# ------------------------------------------------------- observe sees them all
failures += emit(
    "screen.observe no longer silently omits a display",
    "ImageGrab.grab(all_screens=True)" in strip_comments(observer_src),
)

# ------------------------------------------------------------------ the record
readme = README.read_text(encoding="utf-8")
row_107 = next((ln for ln in readme.splitlines() if ln.startswith("| 107 |")), "")
# The row is allowed to QUOTE the retired claim -- that is how a reader knows what
# was withdrawn. What it must not do is still ASSERT it. So the test is that the
# bald assertion is gone and a retraction stands in its place.
failures += emit(
    "the Phase 107 row no longer asserts the falsified cause",
    "**The target was never in the picture.**" not in row_107,
    detail="Phase 107 blamed a primary-only capture; re-measured, that was wrong",
)
failures += emit(
    "the Phase 107 row says plainly that it was wrong",
    "was wrong" in row_107 and "retires it" in row_107,
)
failures += emit(
    "the Phase 107 row points at the corrected diagnosis",
    "108" in row_107,
)
row_108 = next((ln for ln in readme.splitlines() if ln.startswith("| 108 |")), "")
failures += emit("the Phase 108 row exists", bool(row_108))
failures += emit(
    "the row reports the outside-the-system verification",
    "2748" in row_108,
    detail="the page's own log recorded the exact coordinate NOVA aimed at",
)
failures += emit(
    "the row names the remaining inaccuracy in numbers",
    re.search(r"\+1\d\d", row_108) is not None,
    detail="an open question stated without a measurement is an assumption",
)
failures += emit(
    "the row discloses the video call the desktop-wide grab captured",
    "video call" in row_108,
)
# The phase NARROWED the vision-click upload and WIDENED the analyze_screen one.
# Recording only the first would be exactly the half-truth this phase is retiring
# a claim for, so the row has to name the tool and say it got wider.
failures += emit(
    "the row discloses that the analyze_screen upload got WIDER",
    "analyze_screen" in row_108 and "WIDER" in row_108 and "1366" in row_108,
    detail="planner-reachable, not behind the vision flag, and it now uploads every display",
)

# --------------------------------------------------------------------- behaviour
try:
    from eva.screen.capture import CaptureRegion
    from eva.screen.vision_click import VisionResolution, to_target

    region = CaptureRegion(left=1920, top=378, width=1366, height=768)
    target = to_target(
        VisionResolution(found=True, x=500, y=500, confidence=1.0), query="q", region=region
    )
    failures += emit(
        "a centre-of-image answer lands at the centre of THAT window",
        target is not None and (target.x, target.y) == (1920 + 683, 378 + 384),
        target=None if target is None else (target.x, target.y),
    )

    same_grid_other_region = to_target(
        VisionResolution(found=True, x=500, y=500, confidence=1.0),
        query="q",
        region=CaptureRegion(0, 0, 1920, 1080),
    )
    failures += emit(
        "the same grid answer means a different point in a different region",
        same_grid_other_region is not None
        and (same_grid_other_region.x, same_grid_other_region.y) != (target.x, target.y),
    )

    failures += emit(
        "a degenerate region declines instead of clicking (0,0)",
        to_target(
            VisionResolution(found=True, x=500, y=500, confidence=1.0),
            query="q",
            region=CaptureRegion(0, 0, 0, 0),
        )
        is None,
    )
except Exception as exc:  # pragma: no cover
    failures += emit("behavioural checks ran", False, error=str(exc))

print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
raise SystemExit(0 if failures == 0 else 1)
