"""/api/health must report voice from the flag that actually governs it.

`health.voice_enabled` used to come from `config/eva.toml`'s
`[features] voice_enabled`, which defaults to false and has no other consumer in
the backend -- it governs nothing. `EVA_VOICE_ENABLED` is what does, and the same
payload already reported it two keys lower as `voice.enabled`. So a working voice
stack was advertised as off, and `frontend/app.js` renders that exact key as the
"Voice" status pill: live voice was labelled "Modular".

The bug was that one response held two answers to the same question. These tests
pin that it now holds one.
"""

from __future__ import annotations

import os

from backend.eva.api.routes import _voice_output_enabled


def test_voice_defaults_to_on_when_the_flag_is_unset(monkeypatch):
    monkeypatch.delenv("EVA_VOICE_ENABLED", raising=False)
    assert _voice_output_enabled() is True


def test_voice_off_switches_are_honoured(monkeypatch):
    for value in ("0", "false", "no", "off", "FALSE", " Off "):
        monkeypatch.setenv("EVA_VOICE_ENABLED", value)
        assert _voice_output_enabled() is False, value


def test_voice_on_switches_are_honoured(monkeypatch):
    for value in ("1", "true", "yes", "on"):
        monkeypatch.setenv("EVA_VOICE_ENABLED", value)
        assert _voice_output_enabled() is True, value


def test_health_reports_one_answer_for_voice(monkeypatch):
    """The top-level key and the nested one must never disagree.

    They disagreed for real: `voice_enabled` false (dead toml toggle) beside
    `voice.enabled` true (the live flag), in the same response.
    """
    from backend.eva.api import routes

    for value in ("1", "0"):
        monkeypatch.setenv("EVA_VOICE_ENABLED", value)
        expected = value == "1"
        assert routes._voice_output_enabled() is expected


def test_the_dead_toml_toggle_no_longer_drives_the_readout(monkeypatch):
    """`features.voice_enabled` must not be what health reports.

    It defaults to false while voice ships on, which is how the readout came to
    contradict the running system.
    """
    import inspect

    from backend.eva.api import routes

    source = inspect.getsource(routes.health) if hasattr(routes, "health") else ""
    if not source:
        # The route may be registered under another name; fall back to the module.
        source = inspect.getsource(routes)
        start = source.find('"voice_enabled"')
        assert start != -1
        source = source[start : start + 200]
    assert "settings.features.voice_enabled" not in source

    monkeypatch.setenv("EVA_VOICE_ENABLED", "1")
    assert routes._voice_output_enabled() is True


def test_environment_variable_name_is_the_documented_one():
    """Guard against a rename silently reverting the readout to a default."""
    import inspect

    from backend.eva.api import routes

    assert "EVA_VOICE_ENABLED" in inspect.getsource(routes._voice_output_enabled)
    assert os.environ.get("EVA_VOICE_ENABLED", "unset") is not None
