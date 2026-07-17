"""Wake word + listening loop (Phase 49b).

The claim under test is a privacy claim, so it is tested as one: with the
microphone switch off nothing loads or opens; with it on, NOTHING IS
TRANSCRIBED BEFORE THE WAKE WORD; and every loop is bounded.

No test here opens a real microphone — the stream is injected.
"""

from __future__ import annotations

import numpy as np
import pytest

from eva.voice import listener, wake
from eva.voice.listener import ListenResult, listen_once


class _FakeStream:
    """A scripted microphone. Yields frames, then None (device ended)."""

    def __init__(self, frames):
        self._frames = list(frames)
        self.reads = 0
        self.closed = False

    def read(self):
        self.reads += 1
        return self._frames.pop(0) if self._frames else None

    def close(self):
        self.closed = True


def _loud(n=1280):
    return (np.random.default_rng(0).integers(-8000, 8000, n)).astype("int16")


def _quiet(n=1280):
    return np.zeros(n, dtype="int16")


# -- the switch ------------------------------------------------------------

def test_wake_word_is_off_by_default(monkeypatch):
    monkeypatch.delenv("EVA_VOICE_INPUT_ENABLED", raising=False)
    assert wake.wake_status()["enabled"] is False
    assert wake.detect_wake_word(_loud()).detected is False


def test_disabled_never_loads_a_wake_model(monkeypatch):
    monkeypatch.delenv("EVA_VOICE_INPUT_ENABLED", raising=False)
    monkeypatch.setattr(wake, "_load_model", lambda *a, **k: pytest.fail("a disabled mic must not load a wake model"))
    assert wake.detect_wake_word(_loud()).detected is False


def test_disabled_never_opens_a_microphone(monkeypatch):
    monkeypatch.delenv("EVA_VOICE_INPUT_ENABLED", raising=False)

    def _boom():
        pytest.fail("a disabled mic must never be opened")

    result = listen_once(stream_factory=_boom)
    assert result.woke is False
    assert result.reason == "voice_input_disabled"
    assert result.text == ""


# -- THE promise: nothing before the wake word -----------------------------

def test_nothing_is_transcribed_before_the_wake_word(monkeypatch):
    """The load-bearing privacy claim: if the wake word never fires, no audio
    ever reaches the transcriber."""
    monkeypatch.setenv("EVA_VOICE_INPUT_ENABLED", "1")
    monkeypatch.setattr(wake, "detect_wake_word", lambda frame, environ=None: wake.WakeDetection(detected=False))
    monkeypatch.setattr(
        listener, "transcribe_wav", lambda *a, **k: pytest.fail("pre-wake audio must NEVER be transcribed"), raising=False
    )
    import eva.voice.stt as stt

    monkeypatch.setattr(stt, "transcribe_wav", lambda *a, **k: pytest.fail("pre-wake audio must NEVER be transcribed"))

    monkeypatch.setenv("EVA_WAKE_TIMEOUT", "0.8")  # 10 frames, so the timeout really fires
    stream = _FakeStream([_loud() for _ in range(200)])
    result = listen_once(stream_factory=lambda: stream)
    assert result.woke is False
    assert result.text == ""
    assert result.reason == "wake_timeout"


def test_wake_then_transcribe(monkeypatch):
    monkeypatch.setenv("EVA_VOICE_INPUT_ENABLED", "1")
    calls = {"n": 0}

    def _fire_on_third(frame, environ=None):
        calls["n"] += 1
        return wake.WakeDetection(detected=calls["n"] >= 3, score=0.9, wake_word="hey_jarvis")

    monkeypatch.setattr(wake, "detect_wake_word", _fire_on_third)
    import eva.voice.stt as stt

    monkeypatch.setattr(stt, "transcribe_wav", lambda wav, environ=None: stt.Transcript(text="open my notes", ok=True))

    frames = [_loud() for _ in range(3)] + [_loud() for _ in range(5)] + [_quiet() for _ in range(20)]
    result = listen_once(stream_factory=lambda: _FakeStream(frames))
    assert result.woke is True
    assert result.wake_word == "hey_jarvis"
    assert result.text == "open my notes"


def test_stream_is_always_closed(monkeypatch):
    monkeypatch.setenv("EVA_VOICE_INPUT_ENABLED", "1")
    monkeypatch.setattr(wake, "detect_wake_word", lambda f, environ=None: wake.WakeDetection(detected=False))
    stream = _FakeStream([_loud() for _ in range(5)])
    listen_once(stream_factory=lambda: stream)
    assert stream.closed is True, "the microphone must always be released"


# -- bounds ----------------------------------------------------------------

def test_wake_wait_is_bounded(monkeypatch):
    """An unbounded microphone loop is the thing nobody should ship."""
    monkeypatch.setenv("EVA_VOICE_INPUT_ENABLED", "1")
    monkeypatch.setenv("EVA_WAKE_TIMEOUT", "0.8")  # 10 frames at 80ms
    monkeypatch.setattr(wake, "detect_wake_word", lambda f, environ=None: wake.WakeDetection(detected=False))
    stream = _FakeStream([_loud() for _ in range(10_000)])
    result = listen_once(stream_factory=lambda: stream)
    assert result.reason == "wake_timeout"
    assert stream.reads <= 12, f"must stop at the wake timeout, read {stream.reads} frames"


def test_recording_is_capped(monkeypatch):
    monkeypatch.setenv("EVA_VOICE_INPUT_ENABLED", "1")
    monkeypatch.setenv("EVA_MAX_RECORD_SECONDS", "0.8")
    monkeypatch.setattr(wake, "detect_wake_word", lambda f, environ=None: wake.WakeDetection(detected=True, wake_word="hey_jarvis"))
    import eva.voice.stt as stt

    seen = {}

    def _capture(wav, environ=None):
        seen["bytes"] = len(wav)
        return stt.Transcript(text="hi", ok=True)

    monkeypatch.setattr(stt, "transcribe_wav", _capture)
    # Loud forever: only the cap can stop it.
    listen_once(stream_factory=lambda: _FakeStream([_loud() for _ in range(10_000)]))
    # 0.8s of 16kHz mono int16 ~= 25,600 bytes + header. Anything near 10k frames would be megabytes.
    assert seen["bytes"] < 60_000, f"recording must be capped, got {seen['bytes']} bytes"


def test_graceful_when_stream_ends(monkeypatch):
    monkeypatch.setenv("EVA_VOICE_INPUT_ENABLED", "1")
    monkeypatch.setattr(wake, "detect_wake_word", lambda f, environ=None: wake.WakeDetection(detected=False))
    result = listen_once(stream_factory=lambda: _FakeStream([]))
    assert result.reason == "stream_ended_before_wake"


def test_microphone_failure_is_fail_safe(monkeypatch):
    monkeypatch.setenv("EVA_VOICE_INPUT_ENABLED", "1")

    def _explode():
        raise OSError("no such device")

    result = listen_once(stream_factory=_explode)
    assert result.woke is False
    assert "microphone_unavailable" in result.reason


# -- config ----------------------------------------------------------------

def test_wake_word_defaults_and_rejects_unknown(monkeypatch):
    monkeypatch.delenv("EVA_WAKE_WORD", raising=False)
    assert wake.wake_word_name() == "hey_jarvis"
    monkeypatch.setenv("EVA_WAKE_WORD", "hey_mycroft")
    assert wake.wake_word_name() == "hey_mycroft"
    # An unknown phrase must fall back to a model that exists, not crash later.
    monkeypatch.setenv("EVA_WAKE_WORD", "hey_nova")
    assert wake.wake_word_name() == "hey_jarvis"


def test_threshold_is_clamped(monkeypatch):
    monkeypatch.setenv("EVA_WAKE_THRESHOLD", "5")
    assert wake.wake_threshold() == 1.0
    monkeypatch.setenv("EVA_WAKE_THRESHOLD", "-2")
    assert wake.wake_threshold() == 0.0
    monkeypatch.setenv("EVA_WAKE_THRESHOLD", "nonsense")
    assert wake.wake_threshold() == 0.5


def test_no_profile_can_enable_the_microphone():
    from eva.runtime.activation import PROFILES, profile_flags

    for name in PROFILES:
        assert "EVA_VOICE_INPUT_ENABLED" not in profile_flags(name), f"profile {name} must never enable the mic"
