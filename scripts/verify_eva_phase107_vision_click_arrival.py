"""Standalone verifier for Phase 107 (vision clicking, driven for the first time).

Phase 98 built a vision fallback for apps that publish no accessibility tree --
Electron windows, canvas UIs, games -- and it was never driven against one. It
was carried on the open-issues list for several sessions as "unvalidated", which
turned out to be generous: driving it against a canvas page whose buttons exist
only as pixels found four defects, of two different kinds.

**Validated end to end (the arrival proof):**

  * The planner never called `screen.click` at all. `gui: click the Kestrel
    button` returned "I don't see a Kestrel button among the available click
    targets", with `0/12 actions used`. The scaffolding hands the planner the
    window's control list and tells it to click a label EXACTLY as listed --
    and, when no names can be read, that "clicking by label will not work here,
    say so rather than guessing". For a tree-less app that sentence is false the
    moment the fallback is switched on, and it is precisely the case the
    fallback exists for. The tool was reachable by grep and unreachable in fact
    -- Phase 103's shape one layer up: there the tools were missing, here they
    were present and the prompt talked the model out of them. After the fix,
    measured: `1/12 actions used, GUI actions: screen.click`.

**Measured cause, fix applied, click not yet confirmed to land:**

  * **A confident success for an action that did not happen.** `screen.click`
    returned `ok: True` with "Clicked verified UI target Kestrel" while the page
    recorded no click. Nothing was verified: a tree target's bounds are read
    from the OS, a vision target's are asserted by a model, cannot be checked
    afterwards -- a canvas has nothing to read back -- and varied between runs
    on the identical screen (x=1349, then x=1125). The two are now reported
    differently and the guess says it is one.
  * **A token cap that ate the answer.** `finishReason: MAX_TOKENS`,
    `thoughtsTokenCount: 861` of a 900 budget, `candidatesTokenCount: 35`: the
    reasoning took 96% and the JSON was cut mid-string at `"description":`,
    surfacing as `unparseable_reply`. A healthy model and a correct answer,
    discarded by our own cap -- INTERMITTENTLY, since whether the reply fit
    depended on how long the model happened to think. Third time this project
    has been bitten by a reasoning model spending a budget meant for the reply
    (Phase 92's `probe_max_tokens`, Phase 101's nemotron).
  * **A greedy JSON span.** `re.search(r"\\{.*\\}", DOTALL)` runs from the first
    brace to the LAST one anywhere in a blob joined from five analyzer fields,
    so one stray brace made a good reply unparseable. Demonstrated on the exact
    shapes; distinct from the truncation above, which is what the live failures
    were.

Two more, found while trying to confirm a landing:

  * **The vision path used one API key while the chat path rotated four.** It
    read `os.environ["GEMINI_API_KEY"]` directly, so it exhausted a single key
    and declared itself rate-limited with three unused keys configured in the
    same file. That is what actually blocked vision clicking in practice. The
    key loader is now shared and vision rotates on 429.
  * **The analyzer's normaliser deleted the answer.** `_clean_nested_json_field`
    requires a reply shaped `{summary, detected_text, possible_issue,
    suggested_actions}` and returned the EMPTY STRING for anything else -- so
    the localisation JSON this module itself asks the model for was destroyed on
    arrival, and a complete, correct answer reached the caller as
    `unparseable_reply`. A normaliser that cannot recognise a payload must pass
    it through, never delete it.

**What the end-to-end runs establish, and what they do not.** The pipeline
works: vision located `Marmalade`, `screen.click` fired, and it reported
"Clicked where Marmalade appeared to be ... I cannot confirm the click landed on
it" with `verified_target: False`. Asked for a control that had scrolled out of
view it declined and named what it saw instead -- refusing rather than guessing,
as designed. **But the click did not reach the target**: the test page records
every click including misses, and recorded nothing, so the pointer went outside
it. Accuracy is therefore the open question, named rather than assumed, and
`EVA_VISION_CLICK_ENABLED` ships OFF -- a click aimed by asserted coordinates can
land on an unrelated window, which on the machine under test had a live video
call on it. The honesty fix is what makes the capability safe to have at all.

Source checks are mutation-tested. The behavioural checks -- the guessed-versus-
verified reporting, and the parser against the shapes seen live -- are driven,
and need no screenshot, no network and no display.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

GUI_PY = BACKEND / "eva" / "core" / "fast_command_gui.py"
VISION_PY = BACKEND / "eva" / "screen" / "vision_click.py"
CONTROLLER_PY = BACKEND / "eva" / "screen" / "screen_controller.py"
SCREEN_VISION_PY = BACKEND / "eva" / "vision" / "screen_vision.py"

# Measured 2026-09-06 on a real localisation call.
MEASURED_THINKING_TOKENS = 861


def check(value: object, message: str) -> None:
    if not value:
        raise AssertionError(message)


def check_raises(fn, message: str) -> None:
    """A check that cannot fail is not a check -- so prove this one can."""
    try:
        fn()
    except AssertionError:
        return
    raise AssertionError("MUTATION SURVIVED: " + message)


# ------------------------------------------------- the checks, over sources


def assert_scaffolding_admits_incompleteness(gui: str) -> None:
    check(
        "vision_click_enabled" in gui,
        "the GUI scaffolding does not know whether the vision fallback is on, so it cannot "
        "stop telling the planner the control list is exhaustive",
    )
    check(
        "is not always complete" in gui,
        "the planner is still told the control list is exhaustive; on a tree-less app it then "
        "declines before ever calling screen.click, and the fallback inside it cannot run",
    )
    check(
        "clicking by label will not work here -- say so rather than guessing" in gui,
        "the vision-off wording is gone; without the fallback that sentence is TRUE, and "
        "inviting an attempt that has no second chance would burn actions for nothing",
    )
    note = gui.split("unlisted_note = (", 1)[1].split("if vision_available", 1)[0]
    # The TOOL NAME is not screen-request language, and the note has to be able
    # to name the tool it is telling the planner to call. Everything else that
    # says "screen" is the hazard. Checked as plain "screen" rather than
    # "screen " -- the trailing space let "on screen," through, the same
    # near-miss this file is otherwise about.
    note = note.lower().replace("screen.click", "<tool>")
    for word in ("screenshot", "screen"):
        check(
            word not in note,
            f"the injected note contains {word!r}; the planner's _forced_decision matches "
            "screen-request language in the GOAL TEXT before any tool list is read, so this "
            "would force a cloud vision call on every GUI task",
        )


def assert_guessed_clicks_are_labelled(controller: str) -> None:
    body = controller.split("def click_target", 1)[1].split("\ndef ", 1)[0]
    check('"vision"' in body, "click_target no longer distinguishes a guessed target from a read one")
    check("verified_target" in body, "the observation does not record whether the target was verified")
    check(
        "cannot confirm" in body,
        "a vision click still claims more than it knows -- it was reporting 'Clicked verified UI "
        "target' for coordinates a model asserted, while the page recorded no click at all",
    )


def assert_parser_is_not_greedy(vision: str) -> None:
    check(
        "_first_json_object" in vision,
        "the reply parser no longer scans for a balanced object",
    )
    check(
        'r"\\{.*\\}"' not in vision and "{.*}" not in vision,
        "the greedy first-brace-to-last-brace span is back; one stray brace anywhere in the "
        "blob joined from five analyzer fields makes a good reply unparseable",
    )


def assert_vision_budget_survives_thinking(screen_vision: str) -> None:
    match = re.search(r'"maxOutputTokens":\s*(\d+)', screen_vision)
    check(match is not None, "the vision request has no output cap at all")
    cap = int(match.group(1))
    check(
        cap >= MEASURED_THINKING_TOKENS * 2,
        f"maxOutputTokens is {cap}; measured reasoning alone was {MEASURED_THINKING_TOKENS} tokens, "
        "and the cap bounds thinking PLUS answer -- at 900 the JSON was cut mid-string and read "
        "as a parse failure",
    )


def assert_vision_rotates_keys(screen_vision: str) -> None:
    check(
        "gemini_api_keys()" in screen_vision,
        "the vision path does not use the shared key list; it read GEMINI_API_KEY directly and "
        "exhausted one key while the chat path rotated four, declaring itself rate-limited with "
        "three unused keys configured in the same file",
    )
    # CODE only. Checked against the raw file, this matched the comment that
    # EXPLAINS the fix -- a check failing on its own documentation, which is
    # exactly what Phase 97 had to fix twice in its own tests.
    code = "\n".join(
        line for line in screen_vision.splitlines() if not line.lstrip().startswith("#")
    )
    check(
        'os.environ["GEMINI_API_KEY"]' not in code,
        "the vision path still indexes a single key directly",
    )
    # BOTH copies. The request is written out twice, once sync and once async,
    # and fixing only the first would leave every async caller on a single key --
    # the failure this check exists to stop.
    check(
        screen_vision.count("for api_key in keys") == 2,
        "only one of the two vision request paths rotates keys; the other is still stuck on the "
        "first key, which is how this bug looked before it was fixed",
    )


def assert_normaliser_never_deletes(screen_vision: str) -> None:
    body = screen_vision.split("def _clean_nested_json_field", 1)[1].split("\ndef ", 1)[0]
    check(
        "extracted or text" in body,
        "the normaliser still returns the empty string for a reply it does not recognise, which "
        "DESTROYS the localisation JSON this module itself asks the model for -- a complete "
        "correct answer then reaches the caller as `unparseable_reply`",
    )


# ------------------------------------------------------- the driven checks


def _target(method: str):
    from eva.screen.ui_locator import UiTarget

    return UiTarget(
        target_id=f"{method}:verify",
        label="Kestrel",
        role=method,
        x=1125,
        y=349,
        width=0,
        height=0,
        confidence=1.0,
        method=method,
    )


def drive_guessed_versus_verified() -> None:
    """The load-bearing behavioural check, and it needs no screen at all.

    Only the physical click is replaced; the reporting under test is real.
    """
    from eva.agent.action_model import AgentObservation
    from eva.screen import screen_controller

    seen: dict = {}

    def fake_click(x, y, reason, action_id="screen.click"):
        seen["xy"] = (x, y)
        return AgentObservation(action_id=action_id, success=True, raw_observation={}, summary="clicked", error=None)

    real = screen_controller.click
    screen_controller.click = fake_click
    try:
        guessed = screen_controller.click_target(_target("vision"), "verifier")
        read = screen_controller.click_target(_target("grounding"), "verifier")
    finally:
        screen_controller.click = real

    check(guessed.success, "a vision click that fired was reported as a failure")
    check(
        guessed.raw_observation.get("verified_target") is False,
        "a model-asserted location was recorded as a verified target",
    )
    check(
        "cannot confirm" in guessed.summary.lower(),
        "a guessed click still claims the certainty of a read one: " + guessed.summary,
    )
    check(
        read.raw_observation.get("verified_target") is True and "verified" in read.summary.lower(),
        "a tree-read target lost its verified status -- the distinction has to cut both ways, "
        "or it is just a blanket downgrade",
    )
    check(seen.get("xy") == (1125, 349), "the click no longer lands on the point it was given")


def drive_parser_shapes() -> None:
    from eva.screen.vision_click import parse_vision_reply

    good = [
        '```json\n{"found": true, "x": 725, "y": 330, "confidence": 1.0, "description": "Blue"}\n```',
        'summary ```json {"found": true, "x": 725, "y": 330, "confidence": 1.0, "description": "b"} ``` trailing }',
        '{"found": true, "x": 725, "y": 330, "confidence": 1.0, "description": "a"} and later } junk',
        '{"found": true, "x": 725, "y": 330, "confidence": 1.0, "description": "the } button"}',
    ]
    for blob in good:
        resolution = parse_vision_reply(blob)
        check(resolution.found, f"a well-formed reply was rejected ({resolution.reason}): {blob[:60]}")
        check((resolution.x, resolution.y) == (725, 330), "the coordinates were misread")

    # The live failure. Refusing is right: half a coordinate pair must never
    # become a click.
    truncated = parse_vision_reply(
        '{"found": true, "x": 785, "y": 270, "confidence": 1.0, "description": "Blue rect'
    )
    check(not truncated.found, "a TRUNCATED reply was salvaged into a click target")
    check(truncated.reason == "unparseable_reply", "a truncated reply was not named as unreadable")

    # "I looked and it is not there" is a different fact from "I could not read
    # the reply", and an operator debugging a refusal needs to know which.
    absent = parse_vision_reply('{"found": false, "confidence": 0, "description": "no such control"}')
    check(absent.reason == "model_did_not_find_it", "a negative answer was reported as a parse failure")


def drive_two_switches_still_guard_it() -> None:
    """Neither switch alone may open this path: a persistent flag plus a scope a
    person typed `gui:` to open."""
    from eva.screen import screen_tools

    source = Path(screen_tools.__file__).read_text(encoding="utf-8")
    body = source.split("def _try_vision_fallback", 1)[1].split("\ndef ", 1)[0]
    check("vision_click_enabled()" in body, "the persistent flag no longer guards the vision path")
    check("gui_scope_open()" in body, "a console-opened GUI scope no longer guards the vision path")


def main() -> int:
    gui = GUI_PY.read_text(encoding="utf-8")
    vision = VISION_PY.read_text(encoding="utf-8")
    controller = CONTROLLER_PY.read_text(encoding="utf-8")
    screen_vision = SCREEN_VISION_PY.read_text(encoding="utf-8")

    # ------------------------------------------------------- source checks
    assert_scaffolding_admits_incompleteness(gui)
    check_raises(
        lambda: assert_scaffolding_admits_incompleteness(gui.replace("is not always complete", "is complete")),
        "telling the planner the control list is exhaustive survives the check -- the state in "
        "which it never called screen.click at all",
    )
    check_raises(
        lambda: assert_scaffolding_admits_incompleteness(
            gui.replace(
                "publishes no names, so a control you can plainly see may be missing here",
                "publishes no names on screen, so a control may be missing here",
            )
        ),
        "screen-request wording in the injected note survives the check",
    )

    assert_guessed_clicks_are_labelled(controller)
    check_raises(
        lambda: assert_guessed_clicks_are_labelled(controller.replace("cannot confirm", "definitely landed")),
        "a guessed click claiming certainty survives the check",
    )
    check_raises(
        lambda: assert_guessed_clicks_are_labelled(controller.replace("verified_target", "unused_flag")),
        "dropping the verified/guessed distinction survives the check",
    )

    assert_parser_is_not_greedy(vision)
    check_raises(
        lambda: assert_parser_is_not_greedy(vision.replace("_first_json_object", "_greedy_span")),
        "removing the balanced-object scan survives the check",
    )

    assert_vision_rotates_keys(screen_vision)
    check_raises(
        lambda: assert_vision_rotates_keys(
            screen_vision.replace("keys = gemini_api_keys() or [os.environ.get(\"GEMINI_API_KEY\", \"\")]",
                                  "keys = [os.environ[\"GEMINI_API_KEY\"]]", 1)
        ),
        "the SYNC path going back to a single key survives the check -- and the async copy would "
        "still be stuck on one, which is the failure this fixes",
    )

    assert_normaliser_never_deletes(screen_vision)
    check_raises(
        lambda: assert_normaliser_never_deletes(screen_vision.replace("extracted or text", "extracted")),
        "the normaliser deleting an unrecognised payload survives the check",
    )

    assert_vision_budget_survives_thinking(screen_vision)
    check_raises(
        lambda: assert_vision_budget_survives_thinking(
            screen_vision.replace('"maxOutputTokens": 2400', '"maxOutputTokens": 900')
        ),
        "the original 900-token cap survives the check, though 861 of it went on thinking",
    )

    # ----------------------------------------------------- driven checks
    drive_guessed_versus_verified()
    drive_parser_shapes()
    drive_two_switches_still_guard_it()

    # ---------------------------------------------------------- registration
    import verify_eva_all

    name = "verify_eva_phase107_vision_click_arrival.py"
    check(name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 107 verifier")
    check(name in verify_eva_all.QUICK_VERIFIERS, "quick profile missing the Phase 107 verifier")
    check(name in verify_eva_all.VERIFIER_DESCRIPTORS, "master descriptor missing the Phase 107 verifier")

    print(
        "PASS: Phase 107 vision-click arrival. The fallback for apps that publish no "
        "accessibility tree had never been driven against one; a canvas page whose buttons exist "
        "only as pixels found four defects. VALIDATED END TO END: the planner never called "
        "screen.click at all -- the scaffolding presents the control list as exhaustive and tells "
        "it to say so rather than guess, which is false for exactly the app the fallback exists "
        "for, so `0/12 actions used` and a polite refusal; after the fix, `1/12 actions used, GUI "
        "actions: screen.click`. MEASURED CAUSE, FIX APPLIED, LANDING NOT YET CONFIRMED: "
        "screen.click reported ok=True and 'Clicked verified UI target' while the page recorded "
        "no click -- a model-asserted coordinate is now reported as the guess it is, and says it "
        "cannot confirm; the vision call's 900-token cap bounds thinking PLUS answer and a "
        "measured 861 tokens went on thinking, cutting the JSON mid-string and surfacing as "
        "`unparseable_reply` intermittently (the third time a reasoning model has spent a budget "
        "meant for the reply here); and the reply parser's greedy first-to-last brace span "
        "misread any blob containing a stray brace. Two more surfaced while trying to confirm a "
        "landing: the vision path read ONE api key while the chat path rotated four, so it "
        "exhausted that one and declared itself blocked with three unused keys in the same file; "
        "and the analyzer's normaliser returned the empty string for any reply not shaped like "
        "its own schema, destroying the very JSON this module asks the model for. End to end the "
        "pipeline now works and reports honestly -- vision located a button, the click fired, and "
        "it said it could not confirm the landing -- but the click did NOT reach the target, the "
        "test page recording no event at all. Accuracy is the open question, named rather than "
        "assumed, and EVA_VISION_CLICK_ENABLED ships OFF. "
        "Source checks mutation-tested; the guessed-versus-verified reporting and the parser "
        "shapes are driven, with no screenshot, network or display."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
