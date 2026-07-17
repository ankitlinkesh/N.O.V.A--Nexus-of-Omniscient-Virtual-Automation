"""Wake-word detection — the thing that decides when NOVA is listening (Phase 49b).

This is the most privacy-critical component in the project, and it is worth
being precise about why. Speech-to-text (Phase 49a) only ever transcribed a
buffer someone handed it. A wake word implies something far stronger: a
microphone that is *open*, continuously, sampling the room.

The design that makes that tolerable:

  * **Nothing is transcribed before the wake word.** Audio flows through a small
    ring buffer that is overwritten continuously and never written to disk,
    never sent anywhere, and never handed to the STT engine. Only after a
    detection does anything downstream see audio. If the wake word never fires,
    nothing you said ever existed as data.
  * **Detection is local and tiny.** openWakeWord runs an ONNX model
    (~1MB) on CPU. No audio leaves the machine to decide whether you said the
    wake word — that would defeat the entire point.
  * **Default off, and no profile may enable it.** Gated behind
    ``EVA_VOICE_INPUT_ENABLED`` like the rest of voice input. A microphone is
    opt-in one flag at a time, forever.
  * **Lazily imported.** The engine and model load inside the call, so this file
    imports fine on a machine with no audio stack and the verifier suite never
    touches a sound device.

The wake word itself is configurable (``EVA_WAKE_WORD``). It defaults to
``hey_jarvis`` for an honest reason: openWakeWord ships pretrained models for a
handful of phrases, and "hey nova" is not one of them — a custom phrase requires
training a model, which is real work, not a config line. Better a wake word that
actually works than a branded one that does not.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_ABSENT = {"", "0", "false", "no", "off"}

# openWakeWord's pretrained phrases. "hey nova" would need a trained model.
AVAILABLE_WAKE_WORDS = ("hey_jarvis", "alexa", "hey_mycroft", "hey_rhasspy")
_DEFAULT_WAKE_WORD = "hey_jarvis"

# Detection confidence required to say "that was the wake word". openWakeWord
# scores 0..1; 0.5 is its own suggested threshold. Higher = fewer false wakes,
# and a false wake is a privacy event, not just an annoyance.
_DEFAULT_THRESHOLD = 0.5

# Wake models live off the system drive, beside the STT models.
_DEFAULT_MODEL_DIR = Path(r"D:\eva-agent-tools\voice\openwakeword")


def wake_word_name(environ: dict[str, str] | None = None) -> str:
    env = environ if environ is not None else os.environ
    name = str(env.get("EVA_WAKE_WORD", "") or "").strip() or _DEFAULT_WAKE_WORD
    return name if name in AVAILABLE_WAKE_WORDS else _DEFAULT_WAKE_WORD


def wake_model_dir(environ: dict[str, str] | None = None) -> Path:
    env = environ if environ is not None else os.environ
    raw = str(env.get("EVA_WAKE_MODEL_DIR", "") or "").strip()
    return Path(raw) if raw else _DEFAULT_MODEL_DIR


def wake_threshold(environ: dict[str, str] | None = None) -> float:
    env = environ if environ is not None else os.environ
    try:
        value = float(str(env.get("EVA_WAKE_THRESHOLD", "") or _DEFAULT_THRESHOLD))
    except (TypeError, ValueError):
        return _DEFAULT_THRESHOLD
    return min(max(value, 0.0), 1.0)


@dataclass(frozen=True)
class WakeDetection:
    detected: bool
    score: float = 0.0
    wake_word: str = ""


def wake_status(environ: dict[str, str] | None = None) -> dict[str, Any]:
    """Report the wake stack without loading a model or opening a microphone."""
    from .stt import voice_input_enabled

    name = wake_word_name(environ)
    directory = wake_model_dir(environ)
    status: dict[str, Any] = {
        "enabled": voice_input_enabled(environ),
        "wake_word": name,
        "available_wake_words": list(AVAILABLE_WAKE_WORDS),
        "model_dir": str(directory),
        "threshold": wake_threshold(environ),
        "local_only": True,
        "note": (
            "Nothing is transcribed before the wake word fires; pre-wake audio is overwritten in memory "
            "and never stored or sent anywhere."
        ),
    }
    try:
        import importlib.util

        status["engine_installed"] = importlib.util.find_spec("openwakeword") is not None
    except Exception:
        status["engine_installed"] = False
    try:
        status["model_present"] = (directory / f"{name}_v0.1.onnx").exists()
    except Exception:
        status["model_present"] = False
    return status


_MODEL_CACHE: dict[str, Any] = {}


def _load_model(environ: dict[str, str] | None = None):
    """Load (and cache) the wake model. Returns None when unavailable."""
    name = wake_word_name(environ)
    cached = _MODEL_CACHE.get(name)
    if cached is not None:
        return cached
    try:
        from openwakeword.model import Model  # lazy: never at module import
    except Exception:
        return None
    try:
        path = wake_model_dir(environ) / f"{name}_v0.1.onnx"
        if not path.exists():
            return None
        model = Model(wakeword_models=[str(path)], inference_framework="onnx")
        _MODEL_CACHE[name] = model
        return model
    except Exception:
        return None


def detect_wake_word(audio_frame: Any, environ: dict[str, str] | None = None) -> WakeDetection:
    """Score one frame of 16kHz mono int16 audio for the wake word.

    Refuses unless voice input is enabled — a disabled microphone must not even
    load a detection model. Never raises: any failure means "no wake".
    """
    from .stt import voice_input_enabled

    if not voice_input_enabled(environ):
        return WakeDetection(detected=False)
    model = _load_model(environ)
    if model is None:
        return WakeDetection(detected=False)
    try:
        scores = model.predict(audio_frame)
        if not scores:
            return WakeDetection(detected=False)
        name, score = max(scores.items(), key=lambda kv: kv[1])
        threshold = wake_threshold(environ)
        return WakeDetection(detected=float(score) >= threshold, score=float(score), wake_word=str(name))
    except Exception:
        return WakeDetection(detected=False)


def reset_wake_state() -> None:
    """Clear cached model state (used between tests/sessions)."""
    for model in _MODEL_CACHE.values():
        try:
            model.reset()
        except Exception:
            pass
    _MODEL_CACHE.clear()


__all__ = [
    "WakeDetection",
    "detect_wake_word",
    "wake_status",
    "wake_word_name",
    "wake_model_dir",
    "wake_threshold",
    "reset_wake_state",
    "AVAILABLE_WAKE_WORDS",
]
