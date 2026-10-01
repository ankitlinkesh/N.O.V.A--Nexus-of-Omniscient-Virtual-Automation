from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PIPER_EXE = ROOT / "bin" / "piper.exe"
DEFAULT_PIPER_MODEL = ROOT / "models" / "piper" / "en_US-ryan-high.onnx"


def _env_bool(name: str, default: bool = True) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def piper_status() -> dict:
    exe = Path(os.environ.get("EVA_PIPER_EXE", str(DEFAULT_PIPER_EXE))).expanduser()
    model = Path(os.environ.get("EVA_PIPER_MODEL", str(DEFAULT_PIPER_MODEL))).expanduser()
    runtime_files = [
        exe.parent / "onnxruntime.dll",
        exe.parent / "piper_phonemize.dll",
        exe.parent / "espeak-ng.dll",
        exe.parent / "espeak-ng-data",
    ]
    return {
        "enabled": _env_bool("EVA_PIPER_ENABLED", True),
        "exe_exists": exe.exists(),
        "model_exists": model.exists(),
        "runtime_ready": all(path.exists() for path in runtime_files),
        "exe": str(exe),
        "model": str(model),
    }


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return min(maximum, max(minimum, value))


def clean_tts_text(text: str, max_chars: int = 900) -> str:
    cleaned = " ".join(str(text or "").strip().split())
    if not cleaned:
        raise ValueError("No text to speak.")
    if cleaned.startswith("{") or cleaned.startswith("["):
        raise ValueError("Refusing to speak raw structured data.")
    cleaned = cleaned.replace("—", ", ").replace("–", ", ")
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars].rsplit(" ", 1)[0] + ". Details are in chat."
    return cleaned


def synthesize_piper_wav(text: str) -> bytes:
    status = piper_status()
    if not status["enabled"]:
        raise RuntimeError("Piper TTS is disabled.")
    if not status["exe_exists"]:
        raise RuntimeError("piper.exe was not found.")
    if not status["model_exists"]:
        raise RuntimeError("Piper voice model was not found.")
    if not status["runtime_ready"]:
        raise RuntimeError("Piper runtime files are incomplete.")

    cleaned = clean_tts_text(text)
    exe = Path(status["exe"])
    model = Path(status["model"])
    with tempfile.TemporaryDirectory(prefix="eva-piper-") as tmp:
        output = Path(tmp) / "speech.wav"
        command = [
            str(exe),
            "--model",
            str(model),
            "--output_file",
            str(output),
            "--length_scale",
            str(_env_float("EVA_PIPER_LENGTH_SCALE", 0.82, 0.4, 2.0)),
            "--noise_scale",
            str(_env_float("EVA_PIPER_NOISE_SCALE", 0.55, 0.0, 1.5)),
            "--noise_w",
            str(_env_float("EVA_PIPER_NOISE_W", 0.65, 0.0, 1.5)),
        ]
        completed = subprocess.run(
            command,
            input=cleaned,
            capture_output=True,
            text=True,
            # Phase 122: Piper reads UTF-8. Without this Python wrote cp1252, so any
            # reply holding a character outside it -- Hindi, a symbol like "◑" from
            # a window title, an emoji -- raised before Piper ran, and NOVA went
            # silent for that reply (HTTP 500 from /api/tts/piper).
            encoding="utf-8",
            errors="replace",
            timeout=30,
            cwd=str(exe.parent),
        )
        if completed.returncode != 0:
            error = (completed.stderr or completed.stdout or "Piper failed.").strip()
            raise RuntimeError(error[:500])
        if not output.exists() or output.stat().st_size == 0:
            raise RuntimeError("Piper did not create audio.")
        return output.read_bytes()
