"""The listening loop — wake word in, transcript out (Phase 49b).

This is where the privacy promise is actually kept rather than merely stated.
:mod:`eva.voice.wake` decides *when* NOVA is listening; this module is what
holds the microphone open, and it is the only place in the project that does.

The shape of the loop:

    open mic -> [ring buffer, continuously overwritten, never stored ]
             -> wake word fires
             -> record until you stop talking (or the cap)
             -> transcribe locally
             -> hand the TEXT to the ordinary chat path
             -> close mic

What matters is what is absent. Pre-wake audio lives in a fixed-size in-memory
buffer that is overwritten forever and handed to nobody: not the STT engine, not
the disk, not the network. If the wake word never fires, nothing you said in the
room ever became data. Post-wake audio is transcribed locally and the audio is
dropped — only the text survives, and that text goes through the same planner and
the same permission gate as something you typed. Speech earns no privilege.

Every loop here is BOUNDED (a wake timeout and a hard recording cap), because an
unbounded microphone loop is exactly the thing nobody should ship. Nothing opens
an audio device unless ``EVA_VOICE_INPUT_ENABLED`` is set, and no activation
profile may set it.
"""

from __future__ import annotations

import io
import os
import wave
from dataclasses import dataclass
from typing import Any, Callable

# openWakeWord expects 16kHz mono; faster-whisper is happy with it too.
SAMPLE_RATE = 16_000
FRAME_SAMPLES = 1_280  # 80ms at 16kHz — openWakeWord's expected chunk

# Bounds. A microphone loop must never be open-ended.
_DEFAULT_WAKE_TIMEOUT = 30.0     # give up waiting for the wake word
_DEFAULT_MAX_RECORD = 15.0       # hard cap on one utterance
_DEFAULT_SILENCE_HANG = 1.0      # stop after this much trailing quiet
_SILENCE_RMS = 500               # int16 RMS below this counts as silence


@dataclass(frozen=True)
class ListenResult:
    """What one listen produced. ``text`` is empty unless a wake word fired AND
    speech was transcribed."""

    text: str = ""
    woke: bool = False
    wake_word: str = ""
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"text": self.text, "woke": self.woke, "wake_word": self.wake_word, "reason": self.reason}


def _env_float(name: str, default: float) -> float:
    try:
        return float(str(os.environ.get(name, "") or default))
    except (TypeError, ValueError):
        return default


def _rms(frame: Any) -> float:
    """Rough loudness of an int16 frame, used only to notice you stopped talking."""
    try:
        import numpy as np

        data = np.asarray(frame, dtype="float64")
        if data.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(data * data)))
    except Exception:
        return 0.0


def _frames_to_wav(frames: list, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Pack int16 frames into an in-memory WAV. Never touches the disk."""
    try:
        import numpy as np

        if not frames:
            return b""
        audio = np.concatenate([np.asarray(f, dtype="int16").reshape(-1) for f in frames])
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(sample_rate)
            handle.writeframes(audio.tobytes())
        return buffer.getvalue()
    except Exception:
        return b""


def microphone_available() -> bool:
    """Whether an input device exists — without opening one."""
    try:
        import sounddevice as sd

        return any(int(d.get("max_input_channels", 0)) > 0 for d in sd.query_devices())
    except Exception:
        return False


def listen_status() -> dict[str, Any]:
    """Report the listening stack. Opens no device, loads no model."""
    from .stt import stt_status
    from .wake import wake_status

    status = wake_status()
    status["stt"] = stt_status()
    status["microphone_available"] = microphone_available() if status.get("enabled") else False
    status["bounds"] = {
        "wake_timeout_seconds": _env_float("EVA_WAKE_TIMEOUT", _DEFAULT_WAKE_TIMEOUT),
        "max_record_seconds": _env_float("EVA_MAX_RECORD_SECONDS", _DEFAULT_MAX_RECORD),
        "silence_hang_seconds": _env_float("EVA_SILENCE_HANG_SECONDS", _DEFAULT_SILENCE_HANG),
    }
    return status


def listen_once(
    *,
    stream_factory: Callable[[], Any] | None = None,
    environ: dict[str, str] | None = None,
) -> ListenResult:
    """Wait for the wake word, capture one utterance, return its transcript.

    Bounded on both ends: gives up after the wake timeout, and caps a single
    utterance. ``stream_factory`` is an injection seam so the loop can be driven
    in tests without a microphone; production passes nothing and a real device is
    opened. Refuses outright unless voice input is enabled. Never raises.
    """
    from .stt import transcribe_wav, voice_input_enabled
    from .wake import detect_wake_word

    if not voice_input_enabled(environ):
        return ListenResult(reason="voice_input_disabled")

    wake_timeout = _env_float("EVA_WAKE_TIMEOUT", _DEFAULT_WAKE_TIMEOUT)
    max_record = _env_float("EVA_MAX_RECORD_SECONDS", _DEFAULT_MAX_RECORD)
    silence_hang = _env_float("EVA_SILENCE_HANG_SECONDS", _DEFAULT_SILENCE_HANG)
    frame_seconds = FRAME_SAMPLES / SAMPLE_RATE
    max_wake_frames = int(wake_timeout / frame_seconds)
    max_record_frames = int(max_record / frame_seconds)
    silence_frames_needed = max(1, int(silence_hang / frame_seconds))

    try:
        stream = (stream_factory or _default_stream)()
    except Exception as exc:
        return ListenResult(reason=f"microphone_unavailable:{str(exc)[:80]}")

    try:
        # --- Phase 1: wait for the wake word. NOTHING here is kept. ---------
        # Each frame is scored and discarded. There is deliberately no buffer of
        # pre-wake audio to hand to anything: if the wake word never fires, what
        # you said never became data.
        detection = None
        for _ in range(max_wake_frames):
            frame = stream.read()
            if frame is None:
                return ListenResult(reason="stream_ended_before_wake")
            found = detect_wake_word(frame, environ)
            if found.detected:
                detection = found
                break
        if detection is None:
            return ListenResult(reason="wake_timeout")

        # --- Phase 2: record the utterance, bounded. ------------------------
        frames: list = []
        quiet_run = 0
        for _ in range(max_record_frames):
            frame = stream.read()
            if frame is None:
                break
            frames.append(frame)
            if _rms(frame) < _SILENCE_RMS:
                quiet_run += 1
                if quiet_run >= silence_frames_needed and len(frames) > silence_frames_needed:
                    break  # you stopped talking
            else:
                quiet_run = 0

        wav = _frames_to_wav(frames)
        if not wav:
            return ListenResult(woke=True, wake_word=detection.wake_word, reason="no_audio_captured")

        # --- Phase 3: transcribe locally. Audio is dropped; text survives. ---
        transcript = transcribe_wav(wav, environ)
        if not transcript.ok:
            return ListenResult(woke=True, wake_word=detection.wake_word, reason=f"transcribe_failed:{transcript.error}")
        return ListenResult(
            text=transcript.text,
            woke=True,
            wake_word=detection.wake_word,
            reason="ok" if transcript.text else "no_speech_detected",
        )
    except Exception as exc:
        return ListenResult(reason=f"listen_error:{str(exc)[:100]}")
    finally:
        try:
            close = getattr(stream, "close", None)
            if callable(close):
                close()
        except Exception:
            pass


def _default_stream():
    """A real microphone stream. Only ever constructed when voice input is on."""
    import sounddevice as sd

    raw = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=FRAME_SAMPLES)
    raw.start()

    class _Stream:
        def read(self):
            data, _overflowed = raw.read(FRAME_SAMPLES)
            return data.reshape(-1)

        def close(self):
            raw.stop()
            raw.close()

    return _Stream()


__all__ = ["listen_once", "listen_status", "microphone_available", "ListenResult", "SAMPLE_RATE", "FRAME_SAMPLES"]
