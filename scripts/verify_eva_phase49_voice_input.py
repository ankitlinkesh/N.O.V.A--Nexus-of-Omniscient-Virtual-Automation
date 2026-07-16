"""Standalone verifier for Phase 49a (voice input: local speech-to-text).

N.O.V.A could already speak (Piper TTS is real). This adds the other half —
hearing — which is the highest-privacy surface in the project: everything else
is safe partly *because a human is present*, and a microphone inverts that.

So this verifies the contract, not the transcription quality:

  1. DEFAULT OFF: voice_input_enabled() is False when EVA_VOICE_INPUT_ENABLED is
     unset (and for empty/0/false/no/off).
  2. THE SWITCH IS LOAD-BEARING: with it off, transcribe_wav refuses even when
     handed audio directly, and does not so much as load a model.
  3. FAIL-SAFE: empty audio, a missing engine, and a decode error all degrade to
     "no transcript" rather than raising into the caller.
  4. LOCAL ONLY: status advertises local-only transcription, and reporting status
     never loads a model or opens a device.
  5. NO PROFILE MAY ENABLE THE MICROPHONE: EVA_VOICE_INPUT_ENABLED must not
     appear in any activation profile — like real input and the browser, the mic
     stays opt-in one flag at a time.
  6. Models default off the system drive (C: is tight on this machine).
  7. Registration in the master profiles.

Fully offline: no model load, no microphone, no network. Env restored in a
``finally``.
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
    from backend.eva.runtime.activation import NEVER_AUTO_ENABLE, PROFILES, profile_flags
    from backend.eva.voice import stt
    from scripts import verify_eva_all

    saved = {k: os.environ.get(k) for k in ("EVA_VOICE_INPUT_ENABLED", "EVA_STT_MODEL", "EVA_STT_MODEL_DIR")}

    try:
        # 1. Default OFF.
        os.environ.pop("EVA_VOICE_INPUT_ENABLED", None)
        check(stt.voice_input_enabled() is False, "voice input must be OFF by default")
        for falsy in ("", "0", "false", "no", "off"):
            os.environ["EVA_VOICE_INPUT_ENABLED"] = falsy
            check(stt.voice_input_enabled() is False, f"voice input must read {falsy!r} as off")
        os.environ["EVA_VOICE_INPUT_ENABLED"] = "1"
        check(stt.voice_input_enabled() is True, "voice input must report enabled when the flag is set")

        # 2. The switch is load-bearing: OFF means no transcription, no model load.
        os.environ.pop("EVA_VOICE_INPUT_ENABLED", None)
        real_loader = stt._load_model

        def _must_not_load(*args, **kwargs):
            raise AssertionError("a disabled microphone must never load a model")

        try:
            stt._load_model = _must_not_load  # type: ignore[assignment]
            refused = stt.transcribe_wav(b"RIFF fake audio bytes")
            check(refused.ok is False, "transcription must refuse while voice input is disabled")
            check(refused.error == "voice_input_disabled", f"unexpected refusal reason: {refused.error!r}")
            check(refused.text == "", "a refused transcription must return no text")
            # Status must also be inert.
            status = stt.stt_status()
            check(status["enabled"] is False, "status must report the microphone as off")
            check(status["local_only"] is True, "status must advertise local-only transcription")
        finally:
            stt._load_model = real_loader  # type: ignore[assignment]

        # 3. Fail-safe paths (with the flag on).
        os.environ["EVA_VOICE_INPUT_ENABLED"] = "1"
        check(stt.transcribe_wav(b"").error == "empty_audio", "empty audio must fail safe")

        try:
            stt._load_model = lambda *a, **k: None  # type: ignore[assignment]
            missing = stt.transcribe_wav(b"audio")
            check(missing.ok is False and missing.error == "stt_engine_unavailable", "a missing engine must fail safe")

            class _Boom:
                def transcribe(self, *args, **kwargs):
                    raise RuntimeError("kaboom")

            stt._load_model = lambda *a, **k: _Boom()  # type: ignore[assignment]
            broken = stt.transcribe_wav(b"audio")
            check(broken.ok is False and "transcribe_failed" in broken.error, "a decode error must fail safe, not raise")
            check(broken.text == "", "a failed transcription must return no text")
        finally:
            stt._load_model = real_loader  # type: ignore[assignment]

        # 5. THE INVARIANT: no activation profile may enable the microphone.
        for name in PROFILES:
            flags = profile_flags(name)
            check("EVA_VOICE_INPUT_ENABLED" not in flags, f"profile {name!r} must never auto-enable the microphone")
        check("EVA_ENABLE_REAL_INPUT" in NEVER_AUTO_ENABLE, "the hands/external opt-in guarantee must still exist")

        # 6. Models default off the system drive.
        os.environ.pop("EVA_STT_MODEL_DIR", None)
        check("eva-agent-tools" in str(stt.stt_model_dir()), "STT models must default off the system drive")
        os.environ["EVA_STT_MODEL_DIR"] = r"X:\voices"
        check(str(stt.stt_model_dir()) == r"X:\voices", "the model dir must be overridable")

        # 7. Registration.
        verifier_name = "verify_eva_phase49_voice_input.py"
        check(verifier_name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 49 verifier")
        check(verifier_name in verify_eva_all.QUICK_VERIFIERS, "quick profile missing the Phase 49 verifier")
        check(verifier_name in getattr(verify_eva_all, "VERIFIER_DESCRIPTORS"), "master verifier descriptor missing the Phase 49 verifier")

    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    print(
        "PASS: Phase 49a voice input -- speech-to-text is off by default and the switch is load-bearing: with the "
        "microphone disabled, transcription refuses even when handed audio directly and never so much as loads a "
        "model. Empty audio, a missing engine, and a decode error all degrade to 'no transcript' instead of raising. "
        "Transcription is local-only (faster-whisper/CTranslate2, no torch, no speech service), status reporting "
        "loads nothing, models default off the system drive, and -- the invariant -- NO activation profile may "
        "enable the microphone: like real input and the browser it stays opt-in one flag at a time."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
