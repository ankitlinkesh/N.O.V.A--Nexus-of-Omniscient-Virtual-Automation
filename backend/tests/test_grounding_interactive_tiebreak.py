"""Interactive-role tie-break in grounding disambiguation (Phase 63).

Phase 62's live drive against a real Chrome login form found that
``resolve("Sign in")`` came back AMBIGUOUS: the page's <h1> heading and its
<button> both read "Sign in" and both scored confidence 1.0, tied with a
second static text node for the same reason. Phase 59's "decline rather than
click the wrong thing" was working exactly as designed -- but a heading
sharing a button's label ("Sign in", "Log in", "Submit", ...) is an extremely
common real-world pattern, so submit-by-label failed on a large fraction of
ordinary login pages.

The fix (see ``grounding.resolve``): when tied candidates include EXACTLY ONE
interactive control (Button, Hyperlink, Edit, ...) among otherwise-static ones
(Text, Image, ...), that interactive control is the answer, not an ambiguity.
Two tied interactive candidates (two "OK" buttons) must still refuse exactly
as Phase 59 designed -- this file proves that invariant is preserved, not
weakened, alongside the fix. ``backend/tests/test_grounding_disambiguation.py``
(Phase 59) is left completely unedited; every one of its assertions must keep
passing unchanged.
"""

from __future__ import annotations

import pytest

from eva.screen import grounding
from eva.screen.grounding import RawElement, resolve


def _el(name, role, *, left, top, w, h):
    return RawElement(name=name, role=role, left=left, top=top, width=w, height=h)


@pytest.fixture()
def enabled(monkeypatch):
    monkeypatch.setenv("EVA_GUI_GROUNDING_ENABLED", "1")
    yield monkeypatch


def _use(monkeypatch, elements):
    monkeypatch.setattr(grounding, "_default_provider", lambda: list(elements))


# -- 1. The exact real-world case, real observed geometry -------------------
#
#   conf=1.0  role=Button  label='Sign in'  at=(530,361) size=114x48   <- the real target
#   conf=1.0  role=Text    label='Sign in'  at=(683,168) size=420x43   <- the <h1> heading
#   conf=1.0  role=Text    label='Sign in'  at=(525,168) size=104x43   <- the <h1> text node


def _real_sign_in_page():
    # Reconstruct left/top from the reported center + size (RawElement is
    # left/top/width/height, the live report gave center + size).
    button = _el("Sign in", "Button", left=530 - 114 // 2, top=361 - 48 // 2, w=114, h=48)
    heading_a = _el("Sign in", "Text", left=683 - 420 // 2, top=168 - 43 // 2, w=420, h=43)
    heading_b = _el("Sign in", "Text", left=525 - 104 // 2, top=168 - 43 // 2, w=104, h=43)
    return [button, heading_a, heading_b]


def test_real_sign_in_page_resolves_to_the_button(enabled):
    _use(enabled, _real_sign_in_page())
    r = resolve("Sign in")
    assert r.status == "found", f"expected the interactive tie-break to resolve this, got {r.status}: {r.reason}"
    assert r.target is not None
    assert r.target.role == "Button"
    assert (r.target.x, r.target.y) == (530, 361)


def test_locate_also_resolves_the_real_sign_in_page(enabled):
    _use(enabled, _real_sign_in_page())
    target = grounding.locate("Sign in")
    assert target is not None and target.role == "Button", "locate() must inherit the fix via resolve()"


def test_screen_click_by_label_reaches_the_button_not_the_heading(enabled):
    from eva.screen.screen_tools import screen_click

    _use(enabled, _real_sign_in_page())
    result = screen_click(reason="submit the login form", label="Sign in")
    # Grounding must not refuse as ambiguous; whatever stops it past that
    # point is the real-input gate, not an unresolved label.
    assert result.get("error") != "ambiguous_target", result
    assert result.get("error") != "ui_target_not_found", result


# -- 2. Two tied INTERACTIVE candidates must STILL be ambiguous -------------


def test_two_tied_buttons_are_still_ambiguous(enabled):
    _use(
        enabled,
        [
            _el("OK", "Button", left=100, top=100, w=80, h=30),
            _el("OK", "Button", left=400, top=100, w=80, h=30),
        ],
    )
    r = resolve("OK")
    assert r.status == "ambiguous", f"two tied interactive candidates must not be tie-broken, got {r.status}"
    assert r.target is None
    assert len(r.candidates) == 2


def test_button_and_hyperlink_tied_are_still_ambiguous(enabled):
    # Two DIFFERENT interactive roles, both named the same and tied -- still
    # ambiguous: the tie-break only fires when exactly one candidate is
    # interactive, not "prefer the first interactive one found".
    _use(
        enabled,
        [
            _el("Continue", "Button", left=100, top=100, w=80, h=30),
            _el("Continue", "Hyperlink", left=400, top=100, w=80, h=30),
        ],
    )
    r = resolve("Continue")
    assert r.status == "ambiguous", f"two tied interactive candidates (even different roles) must not be tie-broken, got {r.status}"


# -- 3. A clearly better static match is not beaten by a far worse interactive one --


def test_clear_static_winner_beats_a_much_weaker_interactive_candidate(enabled):
    # "Sign in" (exact match, static) scores 1.0. "Sign in Now" (Button) only
    # CONTAINS the query, which this project's scorer marks down to 0.9 --
    # 0.1 below the winner, which is OUTSIDE the 0.08 ambiguity margin. So
    # these two must never even enter the tied set: the tie-break must not
    # engage, and the clear (static) winner must be returned as-is.
    _use(
        enabled,
        [
            _el("Sign in", "Text", left=500, top=150, w=100, h=40),
            _el("Sign in Now", "Button", left=500, top=400, w=140, h=40),
        ],
    )
    r = resolve("Sign in")
    assert r.status == "found"
    assert r.target.role == "Text", "a clearly better static match must win outright, not lose to a weaker interactive one"
    assert len(r.candidates) >= 2, "sanity: the weaker interactive candidate was scored, just not tied"


# -- 4. Phase 59's own tests are unaffected (sanity re-import, not a copy) ---


def test_phase59_ambiguous_ok_case_still_matches_this_files_expectation(enabled):
    """Not a replacement for test_grounding_disambiguation.py -- that file is
    left untouched and must keep passing as-is. This just re-confirms the
    same scenario here so a reader of this file sees the invariant directly."""
    _use(enabled, [_el("OK", "button", left=100, top=100, w=80, h=30), _el("OK", "button", left=400, top=100, w=80, h=30)])
    r = resolve("OK")
    assert r.status == "ambiguous"
