"""Local OCR grounding: matching, refusal when unsure, and where it sits in screen_click's fallbacks."""

from types import SimpleNamespace

from backend.eva.screen import ocr_locate as ol
from backend.eva.screen import screen_tools
from backend.eva.screen.capture import CaptureRegion
from backend.eva.screen.gui_scope import open_gui_scope
from backend.eva.screen.ui_locator import UiTarget

REGION = CaptureRegion(left=100, top=50, width=800, height=600)


def line(text, box, score=0.99):
    return (text, score, box)


def test_exact_beats_partial_beats_fuzzy():
    lines = [line("Send message", (0, 0, 100, 20)), line("Send", (200, 0, 260, 20)), line("Sand", (400, 0, 440, 20))]
    best, status, _ = ol.match_label("send", lines)
    assert status == "found" and best[0] == "Send"


def test_two_equal_matches_in_different_places_are_ambiguous():
    lines = [line("OK", (0, 0, 30, 20)), line("OK", (500, 300, 530, 320))]
    best, status, _ = ol.match_label("ok", lines)
    assert best is None and status == "ambiguous"


def test_the_same_text_split_by_the_engine_at_one_spot_is_not_ambiguous():
    lines = [line("Submit", (10, 10, 80, 30)), line("Submit", (12, 11, 82, 31), 0.97)]
    assert ol.match_label("submit", lines)[1] == "found"


def test_unrelated_text_and_long_paragraphs_do_not_match():
    lines = [line("Cancel", (0, 0, 60, 20)), line("Please review the terms and conditions before you send anything at all today", (0, 40, 700, 60))]
    assert ol.match_label("send", lines)[1] == "no_match"


def test_locate_converts_image_to_screen_coordinates():
    target, report = ol.locate_by_ocr("File", region=REGION, grab=lambda r: object(), reader=lambda img: [line("File", (20, 10, 60, 30))])
    assert report.found and target.method == "ocr" and target.role == "ocr_text"
    assert (target.x, target.y) == (REGION.left + 40, REGION.top + 20) and target.confidence >= 0.9


def test_locate_refuses_low_confidence_missing_engine_and_errors():
    target, report = ol.locate_by_ocr("File", region=REGION, grab=lambda r: object(), reader=lambda img: [line("File", (0, 0, 10, 10), score=0.5)], min_confidence=0.9)
    assert target is None and report.reason == "low_confidence"

    def missing(img):
        raise ImportError

    assert ol.locate_by_ocr("File", region=REGION, grab=lambda r: object(), reader=missing)[1].reason == "ocr_engine_missing"

    def boom(region):
        raise RuntimeError("no display")

    assert ol.locate_by_ocr("File", region=REGION, grab=boom, reader=lambda img: [])[1].reason == "ocr_error:RuntimeError"


def test_flag(monkeypatch):
    assert not ol.ocr_grounding_enabled({}) and ol.ocr_grounding_enabled({"EVA_OCR_GROUNDING_ENABLED": "1"})


# --- screen_click wiring -----------------------------------------------------------------

def _no_tree_match(monkeypatch):
    import backend.eva.screen.grounding as grounding

    monkeypatch.setattr(grounding, "resolve", lambda label, min_confidence=0.75: SimpleNamespace(status="not_found", target=None, candidates=[]))


def _ocr_target():
    return UiTarget(target_id="ocr:1", label="File (read: File)", role="ocr_text", x=300, y=200, width=40, height=20, confidence=0.96, method="ocr")


def test_ocr_runs_before_vision_only_with_flag_and_gui_scope(monkeypatch):
    _no_tree_match(monkeypatch)
    calls = []
    monkeypatch.setattr(ol, "locate_by_ocr", lambda label, min_confidence=0.8, **k: calls.append("ocr") or (_ocr_target(), ol.OcrReport(True, "found")))
    monkeypatch.setattr(screen_tools, "_try_vision_fallback", lambda *a, **k: calls.append("vision") or (None, None))
    monkeypatch.setattr(screen_tools.screen_controller, "click_target", lambda t, r: SimpleNamespace(success=True, as_dict=lambda: {"clicked": t.method}))

    monkeypatch.delenv("EVA_OCR_GROUNDING_ENABLED", raising=False)
    with open_gui_scope("click File"):
        assert screen_tools.screen_click(label="File", reason="r")["ok"] is False
    assert "ocr" not in calls  # flag off: OCR never consulted

    calls.clear()
    monkeypatch.setenv("EVA_OCR_GROUNDING_ENABLED", "1")
    assert screen_tools.screen_click(label="File", reason="r")["ok"] is False
    assert "ocr" not in calls  # no gui: scope: OCR never consulted

    calls.clear()
    with open_gui_scope("click File"):
        result = screen_tools.screen_click(label="File", reason="r")
    assert result["ok"] is True and calls == ["ocr"]  # OCR answered, so vision was never asked


def test_a_click_by_ocr_is_reported_as_read_from_the_screen_not_verified(monkeypatch):
    from backend.eva.screen import screen_controller

    monkeypatch.setattr(screen_controller, "click", lambda x, y, reason, action_id="screen.click": SimpleNamespace(success=True, summary="", as_dict=lambda: {}))
    seen = {}
    monkeypatch.setattr(screen_controller, "_obs", lambda action_id, ok, message, raw=None, error=None: seen.update(message=message, raw=raw) or SimpleNamespace(success=ok))
    screen_controller.click_target(_ocr_target(), "reason")
    assert "reading the text on the screen" in seen["message"] and seen["raw"]["verified_target"] is False
