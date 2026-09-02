"""Standalone verifier for Phase 90 (/api/health tells the truth about voice).

Driving the running app turned this up: `/api/health` reported
`"voice_enabled": false` while, in the same JSON response, `"voice": {"enabled":
true}` -- with Piper synthesising, the wake word `ready`, and speech-to-text
installed. `frontend/app.js` renders the first of those two keys as the "Voice"
status, so a fully working voice stack was labelled "Modular".

The top-level key came from `config/eva.toml`'s `[features] voice_enabled`,
which defaults to false and -- proven below -- has no other consumer anywhere in
the backend. It governed nothing and only misreported. The flag that actually
governs speech output is `EVA_VOICE_ENABLED`, which the nested key already read.

Both keys now read one source, so the payload cannot contradict itself. This is
the honest-reporting invariant this project holds elsewhere (Phases 85 and 87
were both "the status said something the system did not do"), applied to the
inverse case: a status that hides a capability that genuinely works.

Fully offline: no server is started and no network call is made.
"""

from __future__ import annotations

import inspect
import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def check(value: object, message: str) -> None:
    if not value:
        raise AssertionError(message)


def main() -> int:
    from eva.api import routes

    original = os.environ.get("EVA_VOICE_ENABLED")

    def set_flag(value: str | None) -> None:
        if value is None:
            os.environ.pop("EVA_VOICE_ENABLED", None)
        else:
            os.environ["EVA_VOICE_ENABLED"] = value

    try:
        # ------------------------------------------------------------ the flag
        set_flag(None)
        check(routes._voice_output_enabled() is True, "voice must default to ON when the flag is unset")
        for value in ("0", "false", "no", "off", "FALSE", " Off "):
            set_flag(value)
            check(routes._voice_output_enabled() is False, "%r should read as voice OFF" % value)
        for value in ("1", "true", "yes", "on"):
            set_flag(value)
            check(routes._voice_output_enabled() is True, "%r should read as voice ON" % value)
    finally:
        set_flag(original)

    # --------------------------------------------------- one answer, not two
    source = inspect.getsource(routes)
    start = source.find('"voice_enabled":')
    check(start != -1, "the health payload no longer has a voice_enabled key")
    window = source[start : start + 1600]
    check(
        "settings.features.voice_enabled" not in window,
        "REGRESSION: health reports voice from config/eva.toml's dead [features] toggle again, "
        "which defaults to false while voice ships on -- that is how the readout came to contradict "
        "the running system",
    )
    top = re.search(r'"voice_enabled":\s*([^,\n]+)', window)
    nested = re.search(r'"enabled":\s*([^,\n]+)', window)
    check(top is not None and nested is not None, "could not locate both voice keys in the health payload")
    check(
        top.group(1).strip() == nested.group(1).strip(),
        "the two voice keys in one response must be the SAME expression, else they can disagree again; "
        "got %r and %r" % (top.group(1).strip(), nested.group(1).strip()),
    )
    check(
        "EVA_VOICE_ENABLED" in inspect.getsource(routes._voice_output_enabled),
        "the helper no longer reads EVA_VOICE_ENABLED; a rename would silently revert the readout",
    )

    # -------------------------- the toml toggle really is dead (why it was wrong)
    backend_dir = ROOT / "backend"
    consumers: list[str] = []
    for path in backend_dir.rglob("*.py"):
        if "tests" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "features.voice_enabled" in text:
            consumers.append(str(path.relative_to(ROOT)))
    check(
        not consumers,
        "config/eva.toml's [features] voice_enabled is being read again by %r -- it defaults to false "
        "and governs nothing; if it is being revived it needs to actually gate voice, not just be "
        "reported" % consumers,
    )

    # A flag that DOES gate something must keep working -- proof this sweep did
    # not simply delete the feature-settings block.
    check("settings.features.screen_capture" in source, "features.screen_capture lost its real consumer")

    # ---------------------------------------------------------- registration
    import verify_eva_all

    name = "verify_eva_phase90_health_voice_truth.py"
    check(name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 90 verifier")
    check(name in verify_eva_all.QUICK_VERIFIERS, "quick profile missing the Phase 90 verifier")
    check(name in verify_eva_all.VERIFIER_DESCRIPTORS, "master descriptor missing the Phase 90 verifier")

    print(
        "PASS: Phase 90 health voice truth. /api/health reported voice_enabled=false from config/eva.toml's "
        "[features] toggle -- which has no other consumer in the backend and governs nothing -- while the same "
        "response's voice.enabled read the flag that does (EVA_VOICE_ENABLED) and said true. frontend/app.js renders "
        "the first key, so working voice was labelled \"Modular\". Both keys now read one helper, the dead toggle is "
        "proven to have no readers, and features.screen_capture (which genuinely gates a route) still has its."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
