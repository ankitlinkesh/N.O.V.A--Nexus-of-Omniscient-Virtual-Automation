"""Locate a control by LOOKING at the screen, when the accessibility tree is blank.

Phases 56-60 click by walking the Windows UIAutomation tree and matching a
control's accessible name. That is exact, local and cheap, and it is blind: an
Electron app, a canvas UI or a game exposes no named controls, so `resolve()`
returns nothing and the click is honestly refused. For those apps there is no
shell command either -- that is the gap this closes.

**This path is strictly worse than the tree, and is only ever a fallback.** It is
worth being explicit about what it gives up, because two of the properties the
GUI arc was built on do not survive it:

  * **A screenshot leaves the machine.** The tree path sends nothing anywhere;
    this sends a JPEG to Google's Gemini API. Since Phase 108 that JPEG is the
    FOREGROUND WINDOW only, not the desktop: everything else on every display
    stays home. Phase 108 tried the desktop first and measured the cost -- a
    single validation grab swept up an unrelated live video call -- so the scope
    is now the smallest rect that can contain the target, and if the foreground
    window cannot be established the call is refused rather than widened.
  * **Coordinates are asserted by a model, not measured.** A tree target's
    bounds are facts read from the OS; these are a guess, and a confident-sounding
    wrong guess looks exactly like a right one.

So the design is: never first, never silent, never unbounded.

  * **Tree first, always.** Only called after `grounding.resolve()` has declined.
  * **Off unless asked for.** `EVA_VISION_CLICK_ENABLED` is default-off, and the
    caller must ALSO be inside a console-opened GUI scope, so two independent
    switches -- one persistent, one per-task and human-typed -- stand between a
    web page and a vision-driven click.
  * **Bounded to the screen.** Coordinates outside the display are rejected
    rather than clamped: a model that returns nonsense should fail, not click a
    corner.
  * **It declines like the tree does.** Below the confidence floor, or if the
    model reports it cannot see the control, the answer is no target -- the same
    "refuse rather than guess" the grounding path holds.
  * **It says what it saw.** The returned target carries the model's own
    description, so the reply can tell the user what was clicked and on what
    evidence, rather than presenting a guess as a measurement.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Callable

from .capture import CaptureRegion, foreground_window_region
from .ui_locator import UiTarget

# Normalised coordinate space asked of the model. Models are markedly better at
# "this is 62% across and 40% down" than at pixel counts on a screen whose size
# they cannot know, and it makes the result resolution-independent.
_GRID = 1000

# Higher than the tree path's 0.75. A tree match at 0.75 is a real control whose
# name merely scored imperfectly; a vision match at 0.75 is a model that is a bit
# unsure where something is, which is a different and worse kind of uncertain.
DEFAULT_VISION_CONFIDENCE = 0.80


def vision_click_enabled(environ: dict[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    raw = str(env.get("EVA_VISION_CLICK_ENABLED", "") or "").strip().lower()
    return raw not in {"", "0", "false", "no", "off"}


@dataclass(frozen=True)
class VisionResolution:
    """What the model reported, before it is trusted."""

    found: bool
    x: int = 0
    y: int = 0
    confidence: float = 0.0
    description: str = ""
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "found": self.found,
            "x": self.x,
            "y": self.y,
            "confidence": self.confidence,
            "description": self.description,
            "reason": self.reason,
        }


def build_prompt(query: str) -> str:
    """The instruction sent with the screenshot.

    Asks for a refusal path explicitly: a model given only "where is X" will
    invent a location for an X that is not there, and an invented location is the
    one failure mode this whole module has to avoid.
    """
    clean = " ".join(str(query or "").split())[:200]
    return (
        "You are locating one on-screen control for a desktop automation agent.\n"
        f"Find: {clean}\n\n"
        "Reply with JSON only, no prose, in exactly this shape:\n"
        '{"found": true|false, "x": 0-1000, "y": 0-1000, "confidence": 0.0-1.0, '
        '"description": "what is actually at that point"}\n\n'
        "x and y are the CENTRE of the control, on a 0-1000 grid where (0,0) is "
        "the top-left of the image and (1000,1000) the bottom-right.\n"
        "If you cannot see that control, reply {\"found\": false, \"confidence\": 0, "
        '"description": "what you see instead"}. A wrong location makes the agent '
        "click the wrong thing, so say false rather than guess. Do not describe or "
        "transcribe anything on the screen beyond the control asked for."
    )


def _first_json_object(text: str) -> dict | None:
    """The first BALANCED `{...}` in the text, or None.

    Phase 107. The old extraction was `re.search(r"\\{.*\\}", DOTALL)`, which is
    greedy: it spans from the first `{` to the LAST `}` anywhere in the string.
    The caller joins FIVE analyzer fields into one blob, so a stray brace in any
    later field made the match run past the JSON's real end and `json.loads`
    fail -- reported as `unparseable_reply`, which looks exactly like a model
    that answered badly. Measured live: the identical request parsed on one run
    and failed on the next, because the surrounding fields differed.

    Scanning for the matching brace instead makes the result depend only on the
    JSON itself. String-aware, so a `}` inside a description does not end it.
    """
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            if depth:
                depth -= 1
                if depth == 0 and start >= 0:
                    try:
                        parsed = json.loads(text[start : index + 1])
                    except (json.JSONDecodeError, TypeError):
                        # Keep looking: a later object may be the real reply.
                        start = -1
                        continue
                    if isinstance(parsed, dict):
                        return parsed
                    start = -1
    return None


def parse_vision_reply(text: str) -> VisionResolution:
    """Read the model's JSON. Anything malformed is a refusal, never a guess."""
    raw = str(text or "").strip()
    # The fence can be anywhere, not only at the start: the caller joins five
    # analyzer fields, so a reply that arrived as ```json ...``` inside `summary`
    # ends up in the middle of the blob and the old startswith() never saw it.
    raw = re.sub(r"```[a-zA-Z]*", " ", raw).replace("```", " ")
    data = _first_json_object(raw)
    if data is None:
        return VisionResolution(found=False, reason="unparseable_reply")
    if not isinstance(data, dict) or not data.get("found"):
        return VisionResolution(
            found=False,
            reason="model_did_not_find_it",
            description=str(data.get("description") or "")[:200] if isinstance(data, dict) else "",
        )
    try:
        x = int(float(data.get("x")))
        y = int(float(data.get("y")))
        confidence = float(data.get("confidence") or 0.0)
    except (TypeError, ValueError):
        return VisionResolution(found=False, reason="unparseable_coordinates")
    if not (0 <= x <= _GRID and 0 <= y <= _GRID):
        # Rejected, never clamped: a model that answers off-grid did not
        # understand the question, and clamping would turn that into a click.
        return VisionResolution(found=False, reason="coordinates_out_of_range")
    return VisionResolution(
        found=True,
        x=x,
        y=y,
        confidence=max(0.0, min(1.0, confidence)),
        description=str(data.get("description") or "")[:200],
    )


def to_target(
    resolution: VisionResolution,
    *,
    query: str,
    region: CaptureRegion,
    min_confidence: float = DEFAULT_VISION_CONFIDENCE,
) -> UiTarget | None:
    """Turn a trusted-enough reply into a clickable target, or None.

    `region` must be the region the model was actually SHOWN. Phase 107 passed
    the size of a different screenshot and clicked 1800px away.
    """
    if not resolution.found or resolution.confidence < float(min_confidence):
        return None
    if region is None or not region.valid:
        return None

    # Two steps, deliberately not collapsed into one expression. The model
    # answers in IMAGE space; the click happens in SCREEN space; the offset
    # between them is the entire reason the region is carried around. Phase 60's
    # double-centering bug read exactly like a collapsed coordinate line.
    x_in_image = resolution.x * region.width / _GRID
    y_in_image = resolution.y * region.height / _GRID
    if not (0 <= x_in_image < region.width and 0 <= y_in_image < region.height):
        return None
    x, y = region.to_screen(x_in_image, y_in_image)

    return UiTarget(
        target_id=f"vision:{abs(hash((query, x, y))) & 0xFFFFFFFF:08x}",
        # The label records that this was SEEN, not read from the OS, so nothing
        # downstream can mistake a model's guess for a measured control.
        label=f"{query} (seen: {resolution.description})" if resolution.description else str(query),
        role="vision",
        x=x,
        y=y,
        width=0,
        height=0,
        confidence=resolution.confidence,
        method="vision",
    )


def locate_by_vision(
    query: str,
    *,
    min_confidence: float = DEFAULT_VISION_CONFIDENCE,
    analyzer: Callable[[str, str], dict[str, Any]] | None = None,
    region: CaptureRegion | None = None,
) -> tuple[UiTarget | None, VisionResolution]:
    """Find `query` on screen by looking at it. Returns (target or None, report).

    `analyzer` and `region` are injectable so every branch is testable with no
    screenshot, no network and no display.

    Phase 108: the region comes from the SAME capture as the image, reported back
    by the analyzer. It used to come from a second, independent `ImageGrab.grab()`
    taken just to measure the screen -- so the model was answering about one
    region while its answer was converted using another's geometry.

    Phase 108 also narrows WHAT is photographed: only the foreground window, not
    every display. Sending the whole desk to find one button puts unrelated
    windows into a cloud request -- during this phase's own validation a
    desktop-wide grab captured a live video call. If the foreground window cannot
    be established, this REFUSES; widening the shot is never the safe fallback.
    """
    scope = region
    if scope is None and analyzer is None:
        scope = foreground_window_region()
        if scope is None:
            return None, VisionResolution(found=False, reason="no_window_region")

    try:
        if analyzer is not None:
            result = analyzer(build_prompt(query), "")
        else:
            from ..tools.registry import _analyze_screen

            result = _analyze_screen(question=build_prompt(query), region=scope)
    except Exception as exc:
        return None, VisionResolution(found=False, reason=f"vision_error:{type(exc).__name__}")

    if not isinstance(result, dict) or not result.get("ok", True):
        return None, VisionResolution(found=False, reason=str((result or {}).get("error") or "vision_failed"))

    capture_region = region or CaptureRegion.from_dict((result.get("capture") or {}).get("region"))
    if capture_region is None:
        # Refusing beats guessing a geometry: a wrong region does not fail, it
        # clicks somewhere else, which is the failure this phase exists to end.
        return None, VisionResolution(found=False, reason="no_capture_region")

    # The analyzer normalises Gemini's reply into named fields; the JSON we asked
    # for can land in any of them depending on how it answered.
    blob = " ".join(
        str(result.get(key) or "")
        for key in ("summary", "detected_text", "possible_issue", "raw", "text")
    )
    resolution = parse_vision_reply(blob)
    target = to_target(
        resolution,
        query=query,
        region=capture_region,
        min_confidence=min_confidence,
    )
    return target, resolution
