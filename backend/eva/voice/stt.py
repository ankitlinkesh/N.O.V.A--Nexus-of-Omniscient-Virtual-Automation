"""Speech-to-text — the input half of the voice loop (Phase 49).

N.O.V.A could already *speak* (Piper TTS is real and local). This is the other
half: turning your voice into text. It is the highest-privacy surface in the
whole project, so the shape of it matters more than the features.

Everything else N.O.V.A does is safe partly because **a human is present** — the
gate holds a privileged action and someone answers. A microphone inverts that:
it is the one component that can capture something you never chose to give. So:

  * **Default off.** Gated behind ``EVA_VOICE_INPUT_ENABLED``, empty == off. No
    activation profile may ever enable it — like real input and the browser, the
    microphone is opt-in one flag at a time, deliberately.
  * **Fully local.** Transcription runs on-device via faster-whisper
    (CTranslate2 — no torch, matching this project's CPU-only constraint). No
    audio and no transcript is ever sent to a speech service.
  * **Nothing is retained.** This module transcribes a buffer it is handed and
    returns text. It does not record to disk, and it does not keep audio.
  * **Speech earns no privilege.** A transcript is just text: it goes to the same
    planner and the same permission gate as something you typed. Saying "delete
    my files" is exactly as gated as typing it.
  * **Lazily imported.** The engine is imported inside the call, never at module
    top, so the verifier suite stays fast and this file is importable on a
    machine with no speech stack installed at all.

Fail-safe throughout: a missing model, a missing engine, or a decode error
degrades to "no transcript", never an exception into the caller.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_ABSENT = {"", "0", "false", "no", "off"}

# Models live off the system drive by default (this project already keeps heavy
# binaries on D: — C: is tight). Override with EVA_STT_MODEL_DIR.
_DEFAULT_MODEL_DIR = Path(os.environ.get("EVA_STT_MODEL_DIR", r"D:\eva-agent-tools\voice"))
_DEFAULT_MODEL = "base"


def voice_input_enabled(environ: dict[str, str] | None = None) -> bool:
    """Whether microphone input is active (default OFF, empty == off).

    The single switch for the whole voice-input path. Nothing in this package
    captures audio unless this is explicitly on.
    """
    env = environ if environ is not None else os.environ
    return env.get("EVA_VOICE_INPUT_ENABLED", "").strip().lower() not in _ABSENT


def stt_model_name(environ: dict[str, str] | None = None) -> str:
    env = environ if environ is not None else os.environ
    return str(env.get("EVA_STT_MODEL", "") or _DEFAULT_MODEL).strip() or _DEFAULT_MODEL


def stt_model_dir(environ: dict[str, str] | None = None) -> Path:
    env = environ if environ is not None else os.environ
    raw = str(env.get("EVA_STT_MODEL_DIR", "") or "").strip()
    return Path(raw) if raw else _DEFAULT_MODEL_DIR


@dataclass(frozen=True)
class Transcript:
    """What was heard. ``text`` is empty when nothing usable was captured."""

    text: str
    language: str = ""
    duration_seconds: float = 0.0
    ok: bool = True
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def stt_status(environ: dict[str, str] | None = None) -> dict[str, Any]:
    """Report the speech-to-text stack without importing or loading anything heavy."""
    status: dict[str, Any] = {
        "enabled": voice_input_enabled(environ),
        "engine": "faster-whisper",
        "model": stt_model_name(environ),
        "model_dir": str(stt_model_dir(environ)),
        "local_only": True,
        "note": "Audio never leaves this machine; a transcript is treated exactly like typed text.",
    }
    try:
        import importlib.util

        status["engine_installed"] = importlib.util.find_spec("faster_whisper") is not None
    except Exception:
        status["engine_installed"] = False
    return status


_MODEL_CACHE: dict[str, Any] = {}


def _load_model(environ: dict[str, str] | None = None):
    """Load (and cache) the faster-whisper model. Returns None if unavailable."""
    name = stt_model_name(environ)
    cached = _MODEL_CACHE.get(name)
    if cached is not None:
        return cached
    try:
        from faster_whisper import WhisperModel  # lazy: never at module top
    except Exception:
        return None
    try:
        directory = stt_model_dir(environ)
        directory.mkdir(parents=True, exist_ok=True)
        model = WhisperModel(name, device="cpu", compute_type="int8", download_root=str(directory))
        _MODEL_CACHE[name] = model
        return model
    except Exception:
        return None


def transcribe_wav(wav_bytes: bytes, environ: dict[str, str] | None = None) -> Transcript:
    """Transcribe a WAV buffer locally. Refuses unless voice input is enabled.

    Takes bytes rather than a path so no audio has to touch the disk. Never
    raises: any failure returns a Transcript with ok=False.
    """
    if not voice_input_enabled(environ):
        return Transcript(text="", ok=False, error="voice_input_disabled")
    if not wav_bytes:
        return Transcript(text="", ok=False, error="empty_audio")

    model = _load_model(environ)
    if model is None:
        return Transcript(text="", ok=False, error="stt_engine_unavailable")

    try:
        import io

        segments, info = model.transcribe(io.BytesIO(wav_bytes), beam_size=1, vad_filter=True)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return Transcript(
            text=text,
            language=str(getattr(info, "language", "") or ""),
            duration_seconds=float(getattr(info, "duration", 0.0) or 0.0),
            ok=True,
        )
    except Exception as exc:
        return Transcript(text="", ok=False, error=f"transcribe_failed:{str(exc)[:120]}")


__all__ = [
    "Transcript",
    "transcribe_wav",
    "stt_status",
    "voice_input_enabled",
    "stt_model_name",
    "stt_model_dir",
]
