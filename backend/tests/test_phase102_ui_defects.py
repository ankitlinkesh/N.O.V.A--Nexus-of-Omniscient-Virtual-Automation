"""Phase 102 -- the defects that were only visible from the page itself.

Every test in this project so far drove `POST /api/chat`. Driving the actual
web UI with a real browser for the first time surfaced six defects in minutes,
none of which any API-level test could see, and four of which were the same
shape: a preference written down in more than one place, the copies disagreeing,
and the copy nobody was looking at being the one that decided the behaviour.

The tests here assert AGREEMENT between the copies rather than checking each
copy in isolation -- a per-location check passes happily while the locations
contradict each other, which is exactly the state that shipped.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
APP_JS = ROOT / "frontend" / "app.js"
INDEX_HTML = ROOT / "frontend" / "index.html"
FAVICON = ROOT / "frontend" / "favicon.svg"
ROUTES_PY = ROOT / "backend" / "eva" / "api" / "routes.py"

# Names a listener hears as female. Deliberately a literal, not a call into the
# code under test, so this cannot pass by sharing a bug with what it checks.
FEMALE = re.compile(r"(zira|aria|jenny|sonia|ava|samantha|female|hazel|susan|linda)", re.I)


def _js_string_array(source: str, name: str) -> list[str]:
    """Pull a JS array-of-strings literal out of app.js.

    The frontend has no test harness, so the alternative to parsing it is not
    checking it -- and the client-side copy of the voice list is precisely the
    one that decided the voice while the two server-side copies were fixed.
    """
    match = re.search(name + r"\s*:\s*\[(.*?)\]", source, re.S)
    if match is None:
        match = re.search(name + r"\s*=\s*\[(.*?)\]", source, re.S)
    assert match is not None, name + " array not found in app.js"
    return re.findall(r'"([^"]*)"', match.group(1))


def _backend_default_voices() -> list[str]:
    source = ROUTES_PY.read_text(encoding="utf-8")
    match = re.search(r'"EVA_PREFERRED_VOICES",\s*(?:#[^\n]*\n\s*)*"([^"]+)"', source)
    assert match is not None, "EVA_PREFERRED_VOICES default not found in routes.py"
    return [item.strip() for item in match.group(1).split(",") if item.strip()]


# --------------------------------------------------------------------------
# The voice: three copies of one preference, and they disagreed
# --------------------------------------------------------------------------


def test_backend_default_voice_list_is_male() -> None:
    voices = _backend_default_voices()
    assert voices, "backend default voice list is empty"
    offenders = [name for name in voices if FEMALE.search(name)]
    assert not offenders, "female voices in the backend default list: " + repr(offenders)


def test_client_default_voice_list_is_male() -> None:
    """The list used BEFORE /api/health resolves.

    `voiceschanged` fires and a voice is locked in before the backend's
    preferences ever arrive, so this list -- not the backend's -- is what a
    fresh browser actually hears.
    """
    voices = _js_string_array(APP_JS.read_text(encoding="utf-8"), "preferredVoices")
    assert voices, "client default voice list is empty"
    offenders = [name for name in voices if FEMALE.search(name)]
    assert not offenders, "female voices in the client default list: " + repr(offenders)


def test_client_and_backend_voice_lists_agree() -> None:
    """The invariant that actually failed.

    Both lists being independently male is not enough: they can drift apart and
    each stay 'correct' while the page picks a voice the server never named.
    Requiring a non-empty overlap keeps the two copies describing one preference.
    """
    client = set(_js_string_array(APP_JS.read_text(encoding="utf-8"), "preferredVoices"))
    backend = set(_backend_default_voices())
    assert client & backend, (
        "the client and backend voice preferences share no voice at all -- "
        "client=" + repr(sorted(client)) + " backend=" + repr(sorted(backend))
    )


def test_voice_gender_default_matches_the_installed_piper_model() -> None:
    """The config contradicted itself: gender defaulted to female while
    EVA_TTS_PROVIDER=piper points at `en_US-ryan-high.onnx`, a male model."""
    source = ROUTES_PY.read_text(encoding="utf-8")
    match = re.search(r'"EVA_VOICE_GENDER",\s*"([a-z]+)"', source)
    assert match is not None, "EVA_VOICE_GENDER default not found"
    assert match.group(1) == "male"


def test_browser_voice_sorter_prefers_male_names() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    assert "voiceLooksFemaleEnglish" not in source, (
        "the sorter that ranks system voices still prefers female ones; with a "
        "male persona and a male Piper model, this was the third disagreeing copy"
    )
    assert "voiceLooksMaleEnglish" in source


def test_voice_profile_version_was_bumped_so_stale_choices_are_cleared() -> None:
    """Fixing the defaults only fixes a browser that has never run NOVA.

    Every existing profile reads localStorage first, so the operator who
    reported hearing a female voice would have kept hearing it forever. The
    version constant is the existing mechanism for invalidating a stored voice
    profile; not bumping it makes the whole fix invisible to the one browser
    that matters.
    """
    source = APP_JS.read_text(encoding="utf-8")
    match = re.search(r'VOICE_PROFILE_VERSION\s*=\s*"([^"]+)"', source)
    assert match is not None, "VOICE_PROFILE_VERSION not found"
    assert match.group(1) != "soft-stable-v2-browser-default", (
        "the voice profile version is unchanged, so browsers that already stored "
        "the female voice and the browser TTS provider keep them"
    )
    reset = source.split("storedVoiceProfileVersion !== VOICE_PROFILE_VERSION", 1)[1][:800]
    for key in ("eva.selectedVoiceName", "eva-tts-provider"):
        assert 'removeItem("' + key + '")' in reset, "the profile reset does not clear " + key


def test_tts_provider_is_persisted_only_on_an_explicit_choice() -> None:
    """`setTtsProvider` wrote localStorage on every call, including the one that
    applied the DEFAULT -- so the first page load ever stored 'browser', and
    that stored value then shadowed the backend's config forever after."""
    source = APP_JS.read_text(encoding="utf-8")
    match = re.search(r"function setTtsProvider\(([^)]*)\)", source)
    assert match is not None, "setTtsProvider not found"
    assert "persist" in match.group(1), "setTtsProvider takes no persist flag"
    body = source.split("function setTtsProvider(", 1)[1][:1200]
    assert re.search(r"if\s*\(\s*persist\s*\)", body), (
        "setTtsProvider still persists unconditionally, so applying the default "
        "writes it and the default outranks the server from then on"
    )


# --------------------------------------------------------------------------
# The cache-buster: a hand-written constant nobody bumps
# --------------------------------------------------------------------------


def _index_html() -> str:
    from fastapi.testclient import TestClient

    from eva.main import create_app

    with TestClient(create_app()) as client:
        response = client.get("/")
        assert response.status_code == 200
        return response.text


def _stamp_of(html: str) -> str:
    match = re.search(r"app\.js\?v=([0-9a-f]+)", html)
    assert match is not None, "app.js carries no derived stamp"
    return match.group(1)


def test_index_is_served_with_a_stamp_derived_from_the_assets() -> None:
    html = _index_html()
    assert "v=orb-v2" not in html, (
        "index.html is still served with the hand-written version string; it was "
        "never bumped, so an edited app.js never reached a returning browser"
    )
    assert _stamp_of(html)


def test_the_stamp_changes_when_an_asset_changes() -> None:
    """The check that bites. 'The stamp is a hex string' passes against a
    constant; only touching a file and seeing the stamp move proves it tracks
    the assets at all."""
    before = _index_html()
    # A throwaway asset, not a touch of app.js: an interrupted run between the
    # touch and the restore would leave app.js with a future mtime, and every
    # stamp after that would be wrong but stable -- the stale-forever mode this
    # phase fixes. Nothing durable to corrupt this way.
    probe = APP_JS.parent / "_phase102_stamp_probe.js"
    try:
        probe.write_text("// transient test asset", encoding="utf-8")
        later = max(APP_JS.stat().st_mtime, probe.stat().st_mtime) + 500
        os.utime(probe, (later, later))
        after = _index_html()
    finally:
        probe.unlink(missing_ok=True)
    assert _stamp_of(before) != _stamp_of(after), (
        "the cache-buster did not move when app.js did -- it is not derived from "
        "the assets, and a returning browser keeps running the cached copy"
    )


# --------------------------------------------------------------------------
# The favicon: a 404 on every single page load
# --------------------------------------------------------------------------


def test_favicon_is_a_served_file_not_an_inline_data_uri() -> None:
    assert FAVICON.exists(), "frontend/favicon.svg is missing"
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert 'href="/favicon.svg"' in html, "index.html does not point at the served favicon"
    assert "data:image/svg" not in html, (
        "the favicon is inline again -- the data URI silently failed because the "
        "unescaped spaces in viewBox='0 0 32 32' make it an invalid URI, which "
        "the browser reports as nothing at all"
    )


def test_favicon_is_reachable() -> None:
    from fastapi.testclient import TestClient

    from eva.main import create_app

    with TestClient(create_app()) as client:
        response = client.get("/favicon.svg")
        assert response.status_code == 200
        assert "svg" in response.text[:200].lower()


# --------------------------------------------------------------------------
# The model readout: health reported configuration, not what serves
# --------------------------------------------------------------------------


def test_health_names_a_provider_that_could_actually_serve() -> None:
    from eva.api import routes

    fields = routes._serving_model_fields()
    assert fields["serving_provider"] not in {"", None}
    assert fields["model"] not in {"", None}


def test_serving_fields_say_unknown_rather_than_guess(monkeypatch) -> None:
    """Failing soft into a confident wrong answer is the bug being fixed, so the
    failure path has to say it does not know."""
    from eva.api import routes
    from eva.llm import router as llm_router

    def boom(*_args, **_kwargs):
        raise RuntimeError("router unavailable")

    monkeypatch.setattr(llm_router, "get_llm_status", boom)
    fields = routes._serving_model_fields()
    assert fields == {"model": "unknown", "serving_provider": "unknown", "fast_model": "unknown"}


def test_serving_provider_is_the_first_configured_one_in_the_order(monkeypatch) -> None:
    """Not 'some provider' -- the one the router would reach first. A provider
    with no key must be skipped rather than named."""
    from eva.api import routes
    from eva.llm import router as llm_router

    monkeypatch.setattr(
        llm_router,
        "get_llm_status",
        lambda *a, **k: {
            "provider_order": ["groq", "nvidia_nim", "ollama"],
            "configured_keys": {"groq": False, "nvidia_nim": True, "ollama": True},
            "models": {"groq": "llama-x", "nvidia_nim": "nemotron-x", "ollama": "qwen-x"},
            "nvidia_nim": {"primary_model": "nemotron-primary"},
        },
    )
    fields = routes._serving_model_fields()
    assert fields["serving_provider"] == "nvidia_nim"
    assert fields["model"] == "nemotron-primary"


def test_serving_fields_report_none_when_nothing_is_configured(monkeypatch) -> None:
    from eva.api import routes
    from eva.llm import router as llm_router

    monkeypatch.setattr(
        llm_router,
        "get_llm_status",
        lambda *a, **k: {
            "provider_order": ["groq", "nvidia_nim"],
            "configured_keys": {"groq": False, "nvidia_nim": False},
            "models": {"groq": "llama-x", "nvidia_nim": "nemotron-x"},
        },
    )
    assert routes._serving_model_fields()["serving_provider"] == "none"


def test_configured_local_model_is_reported_under_an_honest_name() -> None:
    """The old `model` field held `settings.models.ollama_model` -- the local
    fallback, LAST in the provider order, which had served nothing all session,
    while the UI displayed it as the active brain. The value is still true about
    the configuration, so it keeps a name that says so rather than being deleted."""
    source = ROUTES_PY.read_text(encoding="utf-8")
    assert '"configured_local_model": settings.models.ollama_model' in source
    assert '"configured_deep_model": settings.models.deep_model' in source
    assert '"model": settings.models.ollama_model' not in source, (
        "health still reports the local fallback as the serving model"
    )


@pytest.mark.parametrize("field", ["model", "serving_provider", "fast_model"])
def test_serving_fields_are_all_present(field: str) -> None:
    from eva.api import routes

    assert field in routes._serving_model_fields()
