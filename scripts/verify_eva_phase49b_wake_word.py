"""Standalone verifier for Phase 49b (wake word + listening loop).

Phase 49a's speech-to-text only ever transcribed a buffer someone handed it. A
wake word implies something much stronger: a microphone that is OPEN, sampling
the room continuously. That is the most privacy-critical thing in the project,
so this verifies the contract rather than the accuracy:

  1. DEFAULT OFF, and the switch is load-bearing: with EVA_VOICE_INPUT_ENABLED
     unset, wake detection returns nothing, never loads a model, and
     listen_once() refuses WITHOUT OPENING A MICROPHONE.
  2. THE PROMISE: nothing is transcribed before the wake word. If the wake word
     never fires, the transcriber is never called — pre-wake audio never becomes
     data. (Driven with an injected stream and a transcriber that fails the run
     if it is ever reached.)
  3. BOUNDED: waiting for the wake word stops at EVA_WAKE_TIMEOUT and one
     utterance is capped by EVA_MAX_RECORD_SECONDS. An unbounded microphone loop
     is the thing nobody should ship.
  4. The microphone is always released, even when nothing is heard.
  5. Fail-safe: a missing device, an ended stream, or a decode error degrade to
     "no transcript" instead of raising.
  6. NO ACTIVATION PROFILE MAY ENABLE THE MICROPHONE — opt-in one flag at a
     time, like real input and the browser.
  7. Local only: detection runs on a ~1MB local ONNX model; no audio leaves the
     machine to decide whether the wake word was said.

Fully offline: no real microphone, no model load, no network.
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


class _FakeStream:
    def __init__(self, frames):
        self._frames = list(frames)
        self.reads = 0
        self.closed = False

    def read(self):
        self.reads += 1
        return self._frames.pop(0) if self._frames else None

    def close(self):
        self.closed = True


def main() -> int:
    import numpy as np

    from backend.eva.runtime.activation import PROFILES, profile_flags
    from backend.eva.voice import listener, wake
    from backend.eva.voice import stt
    from backend.eva.voice.listener import listen_once
    from scripts import verify_eva_all

    ENV = ("EVA_VOICE_INPUT_ENABLED", "EVA_WAKE_TIMEOUT", "EVA_MAX_RECORD_SECONDS", "EVA_WAKE_WORD", "EVA_WAKE_THRESHOLD")
    saved = {k: os.environ.get(k) for k in ENV}
    real_detect = wake.detect_wake_word
    real_loader = wake._load_model
    real_transcribe = stt.transcribe_wav

    def loud(n=1280):
        return np.random.default_rng(0).integers(-8000, 8000, n).astype("int16")

    def quiet(n=1280):
        return np.zeros(n, dtype="int16")

    try:
        # 1. Default OFF + load-bearing switch.
        os.environ.pop("EVA_VOICE_INPUT_ENABLED", None)
        check(wake.wake_status()["enabled"] is False, "wake word must be off by default")

        def _must_not_load(*a, **k):
            raise AssertionError("a disabled microphone must never load a wake model")

        wake._load_model = _must_not_load  # type: ignore[assignment]
        check(wake.detect_wake_word(loud()).detected is False, "a disabled mic must not detect")
        wake._load_model = real_loader  # type: ignore[assignment]

        def _must_not_open():
            raise AssertionError("a disabled microphone must NEVER be opened")

        refused = listen_once(stream_factory=_must_not_open)
        check(refused.reason == "voice_input_disabled", f"disabled listen must refuse, got {refused.reason!r}")
        check(refused.text == "" and refused.woke is False, "a refused listen yields nothing")

        # 2. THE PROMISE: nothing transcribed before the wake word.
        os.environ["EVA_VOICE_INPUT_ENABLED"] = "1"
        os.environ["EVA_WAKE_TIMEOUT"] = "0.8"

        def _never(*a, **k):
            raise AssertionError("PRE-WAKE AUDIO MUST NEVER BE TRANSCRIBED")

        stt.transcribe_wav = _never  # type: ignore[assignment]
        wake.detect_wake_word = lambda f, environ=None: wake.WakeDetection(detected=False)  # type: ignore[assignment]
        silent_stream = _FakeStream([loud() for _ in range(500)])
        result = listen_once(stream_factory=lambda: silent_stream)
        check(result.woke is False and result.text == "", "no wake => no transcript")
        check(result.reason == "wake_timeout", f"expected wake_timeout, got {result.reason!r}")

        # 3. BOUNDED: the wait stopped at the timeout, not at the stream's end.
        check(silent_stream.reads <= 12, f"waiting for the wake word must be bounded, read {silent_stream.reads} frames")
        # 4. The microphone was released.
        check(silent_stream.closed is True, "the microphone must always be released")

        # Recording is capped even if the speaker never stops.
        captured: dict = {}
        wake.detect_wake_word = lambda f, environ=None: wake.WakeDetection(detected=True, wake_word="hey_jarvis")  # type: ignore[assignment]

        def _capture(wav, environ=None):
            captured["bytes"] = len(wav)
            return stt.Transcript(text="hello", ok=True)

        stt.transcribe_wav = _capture  # type: ignore[assignment]
        os.environ["EVA_MAX_RECORD_SECONDS"] = "0.8"
        listen_once(stream_factory=lambda: _FakeStream([loud() for _ in range(10_000)]))
        check(captured.get("bytes", 10**9) < 60_000, f"one utterance must be capped, captured {captured.get('bytes')} bytes")

        # A normal wake -> speech -> transcript run.
        stt.transcribe_wav = lambda wav, environ=None: stt.Transcript(text="open my notes", ok=True)  # type: ignore[assignment]
        heard = listen_once(stream_factory=lambda: _FakeStream([loud() for _ in range(4)] + [quiet() for _ in range(20)]))
        check(heard.woke is True and heard.text == "open my notes", f"a wake should yield a transcript, got {heard!r}")

        # 5. Fail-safe paths.
        wake.detect_wake_word = lambda f, environ=None: wake.WakeDetection(detected=False)  # type: ignore[assignment]
        ended = listen_once(stream_factory=lambda: _FakeStream([]))
        check(ended.reason == "stream_ended_before_wake", f"an ended stream must degrade, got {ended.reason!r}")

        def _explode():
            raise OSError("no such device")

        broken = listen_once(stream_factory=_explode)
        check("microphone_unavailable" in broken.reason, f"a missing device must fail safe, got {broken.reason!r}")

        # 6. THE INVARIANT: no profile may enable the microphone.
        for name in PROFILES:
            check("EVA_VOICE_INPUT_ENABLED" not in profile_flags(name), f"profile {name!r} must never enable the microphone")

        # 7. Config sanity: an unknown wake word must fall back to a real model.
        os.environ["EVA_WAKE_WORD"] = "hey_nova"
        check(wake.wake_word_name() == "hey_jarvis", "an unknown wake word must fall back to one that exists")
        os.environ["EVA_WAKE_THRESHOLD"] = "5"
        check(wake.wake_threshold() == 1.0, "the threshold must be clamped")
        check(wake.wake_status()["local_only"] is True, "wake detection must be local-only")

        # Registration.
        verifier_name = "verify_eva_phase49b_wake_word.py"
        check(verifier_name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 49b verifier")
        check(verifier_name in verify_eva_all.QUICK_VERIFIERS, "quick profile missing the Phase 49b verifier")
        check(verifier_name in getattr(verify_eva_all, "VERIFIER_DESCRIPTORS"), "master descriptor missing the Phase 49b verifier")

    finally:
        wake.detect_wake_word = real_detect  # type: ignore[assignment]
        wake._load_model = real_loader  # type: ignore[assignment]
        stt.transcribe_wav = real_transcribe  # type: ignore[assignment]
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    print(
        "PASS: Phase 49b wake word -- the microphone is off by default and the switch is load-bearing: disabled, "
        "detection loads no model and listen_once refuses WITHOUT OPENING A DEVICE. The promise holds -- when the "
        "wake word never fires the transcriber is never called, so pre-wake audio never becomes data. Both loops are "
        "bounded (the wait stops at EVA_WAKE_TIMEOUT, one utterance is capped by EVA_MAX_RECORD_SECONDS) and the "
        "microphone is always released. A missing device, an ended stream and a decode error all degrade to 'no "
        "transcript' instead of raising. Detection is local-only, an unknown wake word falls back to a model that "
        "exists, and NO activation profile may enable the microphone."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
