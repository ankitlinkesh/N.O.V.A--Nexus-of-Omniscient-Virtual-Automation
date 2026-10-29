"""Find a control by reading the text on screen (local OCR), for apps with no accessibility tree.

The Windows accessibility tree (UI Automation) is NOVA's first and most trustworthy way to find a
control. Some apps (Electron, canvas UIs, games) expose none, and the next fallback used to be
asking the vision model to guess a coordinate. A button that carries a visible word ("Submit",
"Send", "Next") can be found much more cheaply and exactly by reading the pixels: run OCR over the
foreground window, match the label against the lines it read, and click the centre of the matching
text box.

Local only: the screenshot of the foreground window is read by an on-device OCR engine and never
sent anywhere. It is reached only from ``screen_click`` after grounding has declined, and only with
a ``gui:`` scope open and ``EVA_OCR_GROUNDING_ENABLED`` set, exactly like the vision fallback.

It is conservative: it needs a clear text match and refuses when two different places match about
equally ("ambiguous") instead of guessing. A target found this way is reported as read from the
screen, not verified against the window's own controls (see ``screen_controller.click_target``).
"""

from __future__ import annotations

import difflib
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from .capture import CaptureRegion, foreground_window_region
from .ui_locator import UiTarget

DEFAULT_OCR_CONFIDENCE = 0.80
AMBIGUITY_MARGIN = 0.05
_FUZZY_FLOOR = 0.88

# One OCR line: (text, engine score 0-1, (left, top, right, bottom) in image pixels)
OcrLine = tuple[str, float, tuple[float, float, float, float]]


def ocr_grounding_enabled(environ: dict[str, str] | None = None) -> bool:
    raw = (environ if environ is not None else os.environ).get("EVA_OCR_GROUNDING_ENABLED", "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class OcrReport:
    found: bool
    reason: str = ""
    matches: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"found": self.found, "reason": self.reason, "matches": self.matches[:5]}


def _norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(text or "").lower()))


def _score_line(label: str, line_text: str, engine_score: float) -> float:
    """How well one OCR line matches the label, 0 for no match. Exact beats partial beats fuzzy."""
    want, got = _norm(label), _norm(line_text)
    if not want or not got:
        return 0.0
    if want == got:
        base = 0.97
    elif f" {want} " in f" {got} " and len(got) <= max(3 * len(want), len(want) + 12):
        base = 0.85  # the label is a whole word/phrase inside a short line ("Send message")
    else:
        ratio = difflib.SequenceMatcher(None, want, got).ratio()
        if ratio < _FUZZY_FLOOR:
            return 0.0
        base = ratio * 0.9
    return base * max(0.5, min(1.0, float(engine_score)))


def match_label(label: str, lines: Sequence[OcrLine]) -> tuple[OcrLine | None, str, list[dict[str, Any]]]:
    """(best line, status, ranked matches). status: found | no_match | ambiguous."""
    ranked = sorted(
        ((_score_line(label, text, score), (text, score, box)) for text, score, box in lines),
        key=lambda item: -item[0],
    )
    ranked = [(s, line) for s, line in ranked if s > 0]
    summary = [{"text": line[0], "score": round(s, 3)} for s, line in ranked[:5]]
    if not ranked:
        return None, "no_match", summary
    best_score, best_line = ranked[0]
    for other_score, other_line in ranked[1:]:
        far_apart = abs(((other_line[2][0] + other_line[2][2]) - (best_line[2][0] + best_line[2][2])) / 2) > 20 or \
            abs(((other_line[2][1] + other_line[2][3]) - (best_line[2][1] + best_line[2][3])) / 2) > 20
        if far_apart and best_score - other_score < AMBIGUITY_MARGIN:
            return None, "ambiguous", summary
    return best_line, "found", summary


def _engine_lines(image: Any) -> list[OcrLine]:
    """Read text lines from a PIL image with RapidOCR (local ONNX). Raises ImportError if absent."""
    import numpy as np

    result, _elapsed = _engine()(np.array(image.convert("RGB")))
    lines: list[OcrLine] = []
    for row in result or []:
        if len(row) < 3:
            continue
        points, text, score = row[0], str(row[1]), float(row[2])
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        lines.append((text, score, (min(xs), min(ys), max(xs), max(ys))))
    return lines


_ENGINE: Any = None


def _engine() -> Any:
    global _ENGINE
    if _ENGINE is None:
        from rapidocr_onnxruntime import RapidOCR

        _ENGINE = RapidOCR()
    return _ENGINE


def _grab(region: CaptureRegion) -> Any:
    from PIL import ImageGrab

    return ImageGrab.grab(bbox=(region.left, region.top, region.left + region.width, region.top + region.height), all_screens=True)


def locate_by_ocr(
    label: str,
    *,
    min_confidence: float = DEFAULT_OCR_CONFIDENCE,
    region: CaptureRegion | None = None,
    grab: Callable[[CaptureRegion], Any] | None = None,
    reader: Callable[[Any], list[OcrLine]] | None = None,
) -> tuple[UiTarget | None, OcrReport]:
    """Find `label` by reading the foreground window. Never raises; (None, report) when unsure."""
    scope = region or foreground_window_region()
    if scope is None or not scope.valid:
        return None, OcrReport(False, "no_window_region")
    try:
        image = (grab or _grab)(scope)
        lines = (reader or _engine_lines)(image)
    except ImportError:
        return None, OcrReport(False, "ocr_engine_missing")
    except Exception as exc:
        return None, OcrReport(False, f"ocr_error:{type(exc).__name__}")

    best, status, summary = match_label(label, lines)
    if best is None:
        return None, OcrReport(False, status, summary)
    text, engine_score, (left, top, right, bottom) = best
    confidence = _score_line(label, text, engine_score)
    if confidence < float(min_confidence):
        return None, OcrReport(False, "low_confidence", summary)
    x, y = scope.to_screen((left + right) / 2, (top + bottom) / 2)
    target = UiTarget(
        target_id=f"ocr:{abs(hash((label, x, y))) & 0xFFFFFFFF:08x}",
        label=f"{label} (read: {text.strip()[:40]})",
        role="ocr_text",
        x=x,
        y=y,
        width=max(1, int(right - left)),
        height=max(1, int(bottom - top)),
        confidence=round(confidence, 3),
        method="ocr",
    )
    return target, OcrReport(True, "found", summary)
