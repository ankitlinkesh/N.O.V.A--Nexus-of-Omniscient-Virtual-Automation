"""Speech-to-text gating and safety (Phase 49).

These tests never load a model or open a microphone: they pin the *contract* —
voice input is off by default, refuses to transcribe when off, and fails safe.
"""

from __future__ import annotations

import pytest

from eva.voice import stt


def test_voice_input_is_off_by_default(monkeypatch):
    monkeypatch.delenv("EVA_VOICE_INPUT_ENABLED", raising=False)
    assert stt.voice_input_enabled() is False
    monkeypatch.setenv("EVA_VOICE_INPUT_ENABLED", "0")
    assert stt.voice_input_enabled() is False
    monkeypatch.setenv("EVA_VOICE_INPUT_ENABLED", "1")
    assert stt.voice_input_enabled() is True


def test_transcribe_refuses_when_disabled(monkeypatch):
    """The microphone switch is load-bearing: with it off, nothing transcribes
    even if audio is handed straight to the function."""
    monkeypatch.delenv("EVA_VOICE_INPUT_ENABLED", raising=False)
    result = stt.transcribe_wav(b"RIFF....fake wav bytes")
    assert result.ok is False
    assert result.error == "voice_input_disabled"
    assert result.text == ""


def test_transcribe_refuses_when_disabled_even_with_real_audio(monkeypatch, tmp_path):
    monkeypatch.delenv("EVA_VOICE_INPUT_ENABLED", raising=False)
    # Must not even attempt to load a model.
    monkeypatch.setattr(stt, "_load_model", lambda *a, **k: pytest.fail("must not load a model when disabled"))
    assert stt.transcribe_wav(b"x" * 1000).ok is False


def test_empty_audio_fails_safe(monkeypatch):
    monkeypatch.setenv("EVA_VOICE_INPUT_ENABLED", "1")
    result = stt.transcribe_wav(b"")
    assert result.ok is False
    assert result.error == "empty_audio"


def test_missing_engine_fails_safe(monkeypatch):
    monkeypatch.setenv("EVA_VOICE_INPUT_ENABLED", "1")
    monkeypatch.setattr(stt, "_load_model", lambda *a, **k: None)
    result = stt.transcribe_wav(b"some audio")
    assert result.ok is False
    assert result.error == "stt_engine_unavailable"
    assert result.text == ""


def test_decode_error_fails_safe(monkeypatch):
    monkeypatch.setenv("EVA_VOICE_INPUT_ENABLED", "1")

    class _Boom:
        def transcribe(self, *args, **kwargs):
            raise RuntimeError("kaboom")

    monkeypatch.setattr(stt, "_load_model", lambda *a, **k: _Boom())
    result = stt.transcribe_wav(b"audio")
    assert result.ok is False
    assert "transcribe_failed" in result.error


def test_transcript_joins_segments(monkeypatch):
    monkeypatch.setenv("EVA_VOICE_INPUT_ENABLED", "1")

    class _Seg:
        def __init__(self, text):
            self.text = text

    class _Info:
        language = "en"
        duration = 2.5

    class _Model:
        def transcribe(self, *args, **kwargs):
            return [_Seg(" hello "), _Seg(" world ")], _Info()

    monkeypatch.setattr(stt, "_load_model", lambda *a, **k: _Model())
    result = stt.transcribe_wav(b"audio")
    assert result.ok is True
    assert result.text == "hello world"
    assert result.language == "en"


def test_status_reports_without_loading_a_model(monkeypatch):
    monkeypatch.delenv("EVA_VOICE_INPUT_ENABLED", raising=False)
    monkeypatch.setattr(stt, "_load_model", lambda *a, **k: pytest.fail("status must not load a model"))
    status = stt.stt_status()
    assert status["enabled"] is False
    assert status["local_only"] is True
    assert status["engine"] == "faster-whisper"


def test_model_dir_defaults_off_the_system_drive(monkeypatch):
    monkeypatch.delenv("EVA_STT_MODEL_DIR", raising=False)
    assert "eva-agent-tools" in str(stt.stt_model_dir())


def test_model_dir_and_name_are_overridable(monkeypatch):
    monkeypatch.setenv("EVA_STT_MODEL_DIR", r"X:\voices")
    monkeypatch.setenv("EVA_STT_MODEL", "small")
    assert str(stt.stt_model_dir()) == r"X:\voices"
    assert stt.stt_model_name() == "small"
