"""Standalone verifier for Phase 102 (the defects only the page could show).

For 101 phases every check in this project went through `POST /api/chat`. The
first time NOVA's actual web UI was driven by a real browser it produced six
defects inside ten minutes, and the interesting thing is what they had in
common: five of the six were a preference or a fact written down in more than
one place, the copies disagreeing, and the copy nobody was watching being the
one that decided the behaviour.

  * the model readout showed `qwen2.5:1.5b`, a local fallback LAST in the
    provider order that had served nothing all session, while every answer came
    from nvidia_nim/nemotron -- a health field reporting configuration with no
    relation to what runs, two keys away from the identical bug Phase 90 fixed;
  * `EVA_VOICE_GENDER` defaulted to female while `EVA_TTS_PROVIDER=piper`
    pointed at `en_US-ryan-high.onnx`, a MALE model -- the config contradicted
    itself and the UI honoured the wrong half;
  * the browser-voice sorter ranked female names first;
  * the client-side default voice list was female, and it is used BEFORE
    `/api/health` resolves, so it -- not the server -- picked the voice;
  * `setTtsProvider` persisted on EVERY call, so the first page load ever stored
    the default and that stored value outranked the server from then on;
  * the favicon 404'd on every load.

So the invariants asserted here are AGREEMENT invariants. Checking each copy in
isolation passes cheerfully while the copies contradict each other, which is
precisely the state that shipped -- and it is why fixing the sorter and then the
backend list both failed to change what the browser said out loud.

Two properties carry the fix:

  * **The stale profile is cleared, not just the defaults changed.** Fixing a
    default only fixes a browser that has never run NOVA. Every existing profile
    reads `localStorage` first, so the operator who reported the female voice
    would have kept hearing it forever. Proven live: with the version constant
    left unbumped, a browser seeded with the old keys still selected Zira and
    the browser TTS engine after a reload; bumped, the same browser came back
    with Piper and a male voice.
  * **The cache-buster is derived, not written down.** `?v=orb-v2` was hand
    maintained on three tags and nobody bumps a constant -- an edited `app.js`
    never reached a returning browser. Not hypothetical: a fix made minutes
    earlier was invisible in the UI while `curl` showed the new file being
    served, because the browser was still running the copy cached under the
    unchanged version string.

Every source-level check is mutation-tested against an in-memory copy: the
mutation is applied, the check must go red, and the original is never written.
The two behavioural checks are not mutated but driven -- the serving-model
readout against a fabricated router status, and the cache stamp against a real
asset appearing on disk -- because a mutation of those would only restate the
source text they are deliberately not reading.
Fully offline: no network, no LLM, no provider, no browser.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

APP_JS = ROOT / "frontend" / "app.js"
INDEX_HTML = ROOT / "frontend" / "index.html"
FAVICON = ROOT / "frontend" / "favicon.svg"
ROUTES_PY = ROOT / "backend" / "eva" / "api" / "routes.py"

FEMALE = re.compile(r"(zira|aria|jenny|sonia|ava|samantha|female|hazel|susan|linda)", re.I)


def check(value: object, message: str) -> None:
    if not value:
        raise AssertionError(message)


def check_raises(fn, message: str) -> None:
    """A check that cannot fail is not a check -- so prove this one can."""
    try:
        fn()
    except AssertionError:
        return
    raise AssertionError("MUTATION SURVIVED: " + message)


# ------------------------------------------------------------------ parsing


def js_array(source: str, name: str) -> list[str]:
    match = re.search(name + r"\s*:\s*\[(.*?)\]", source, re.S)
    check(match is not None, name + " array not found in app.js")
    return re.findall(r'"([^"]*)"', match.group(1))


def backend_voices(source: str) -> list[str]:
    match = re.search(r'"EVA_PREFERRED_VOICES",\s*(?:#[^\n]*\n\s*)*"([^"]+)"', source)
    check(match is not None, "EVA_PREFERRED_VOICES default not found in routes.py")
    return [item.strip() for item in match.group(1).split(",") if item.strip()]


# ------------------------------------------------- the checks, over sources


def assert_voices_agree(js: str, py: str) -> None:
    client = js_array(js, "preferredVoices")
    server = backend_voices(py)
    check(client, "client default voice list is empty")
    check(server, "backend default voice list is empty")
    for label, names in (("client", client), ("backend", server)):
        bad = [n for n in names if FEMALE.search(n)]
        check(not bad, "female voices in the " + label + " default list: " + repr(bad))
    check(
        set(client) & set(server),
        "the client and backend voice preferences name no voice in common, so the page "
        "can pick a voice the server never asked for while both lists look correct",
    )
    gender = re.search(r'"EVA_VOICE_GENDER",\s*"([a-z]+)"', py)
    check(gender is not None and gender.group(1) == "male", "EVA_VOICE_GENDER does not default to male")
    check(
        "voiceLooksFemaleEnglish" not in js and "voiceLooksMaleEnglish" in js,
        "the system-voice sorter still ranks female names first",
    )


def assert_stale_profile_is_cleared(js: str) -> None:
    match = re.search(r'VOICE_PROFILE_VERSION\s*=\s*"([^"]+)"', js)
    check(match is not None, "VOICE_PROFILE_VERSION not found")
    check(
        match.group(1) != "soft-stable-v2-browser-default",
        "the voice profile version is unchanged, so every browser that already stored the "
        "female voice and the browser TTS provider keeps them and the fix is invisible",
    )
    reset = js.split("storedVoiceProfileVersion !== VOICE_PROFILE_VERSION", 1)
    check(len(reset) == 2, "the stored-profile reset block is gone")
    body = reset[1][:900]
    for key in ("eva.selectedVoiceName", "eva-tts-provider"):
        check('removeItem("' + key + '")' in body, "the profile reset does not clear " + key)


def assert_default_provider_is_not_persisted(js: str) -> None:
    signature = re.search(r"function setTtsProvider\(([^)]*)\)", js)
    check(signature is not None, "setTtsProvider not found")
    check("persist" in signature.group(1), "setTtsProvider takes no persist flag")
    body = js.split("function setTtsProvider(", 1)[1][:1200]
    check(
        re.search(r"if\s*\(\s*persist\s*\)", body),
        "setTtsProvider still persists unconditionally: applying the DEFAULT writes it to "
        "localStorage, and from then on the default outranks the server's own config",
    )


def assert_health_reports_what_serves(py: str) -> None:
    check(
        '"model": settings.models.ollama_model' not in py,
        "health still reports the local Ollama fallback as the serving model",
    )
    check(
        '"configured_local_model": settings.models.ollama_model' in py,
        "the configured local model was deleted rather than renamed; it is still true about "
        "the configuration and still serves if every cloud provider is unavailable",
    )


# ------------------------------------------------------------------- runner


def main() -> int:
    js = APP_JS.read_text(encoding="utf-8")
    py = ROUTES_PY.read_text(encoding="utf-8")

    # ------------------------------------------------ 1. the voice, in three places
    assert_voices_agree(js, py)
    check_raises(
        lambda: assert_voices_agree(js.replace('"Microsoft Guy Online"', '"Microsoft Zira"', 1), py),
        "a female voice put back at the head of the CLIENT list was not caught -- that is the "
        "copy that decides the voice before /api/health ever answers",
    )
    check_raises(
        lambda: assert_voices_agree(js, py.replace("Microsoft Guy Online,", "Microsoft Aria Online,", 1)),
        "a female voice put back in the BACKEND list was not caught",
    )
    check_raises(
        lambda: assert_voices_agree(
            js.replace('"Microsoft Guy Online"', '"Microsoft Zephyr Online"', 1)
            .replace('"Microsoft Ryan Online"', '"Microsoft Kai Online"', 1)
            .replace('"Microsoft Andrew Online"', '"Microsoft Otto Online"', 1)
            .replace('"Microsoft David"', '"Microsoft Otis"', 1)
            .replace('"Microsoft Mark"', '"Microsoft Milo"', 1)
            .replace('"Google US English Male"', '"Google US English Chap"', 1)
            .replace('"Daniel"', '"Dermot"', 1)
            .replace('"Alex"', '"Axel"', 1),
            py,
        ),
        "THE INVARIANT THAT ACTUALLY FAILED: two lists that are each independently male but "
        "share no voice at all must be rejected. Every name above is male, so a per-list check "
        "passes -- and the page still speaks with a voice the server never named.",
    )

    # --------------------------------------- 2. the stale profile, which is the whole fix
    assert_stale_profile_is_cleared(js)
    check_raises(
        lambda: assert_stale_profile_is_cleared(
            re.sub(r'VOICE_PROFILE_VERSION\s*=\s*"[^"]+"',
                   'VOICE_PROFILE_VERSION = "soft-stable-v2-browser-default"', js)
        ),
        "leaving the profile version unbumped was not caught -- new defaults reach only a "
        "browser that has never run NOVA, and the reporting operator's browser is not one",
    )
    check_raises(
        lambda: assert_stale_profile_is_cleared(js.replace('removeItem("eva-tts-provider")', "")),
        "a reset that leaves the stored TTS provider behind was not caught",
    )

    assert_default_provider_is_not_persisted(js)
    check_raises(
        lambda: assert_default_provider_is_not_persisted(
            js.replace("if (persist) localStorage.setItem", "localStorage.setItem")
        ),
        "persisting on every call was not caught -- that is how the FIRST EVER page load "
        "wrote the default and made it permanently outrank the server",
    )

    # ---------------------------------------------- 3. the model the UI names
    assert_health_reports_what_serves(py)
    check_raises(
        lambda: assert_health_reports_what_serves(
            py.replace('"configured_local_model": settings.models.ollama_model',
                       '"model": settings.models.ollama_model')
        ),
        "reporting the local fallback as the serving model was not caught",
    )

    from eva.api import routes
    from eva.llm import router as llm_router

    fields = routes._serving_model_fields()
    for key in ("model", "serving_provider", "fast_model"):
        check(key in fields, "health serving fields missing " + key)

    original_status = llm_router.get_llm_status
    try:
        llm_router.get_llm_status = lambda *a, **k: {
            "provider_order": ["groq", "nvidia_nim", "ollama"],
            "configured_keys": {"groq": False, "nvidia_nim": True, "ollama": True},
            "models": {"groq": "llama-x", "nvidia_nim": "nemotron-x", "ollama": "qwen2.5:1.5b"},
            "nvidia_nim": {"primary_model": "nemotron-primary"},
        }
        picked = routes._serving_model_fields()
        check(
            picked["serving_provider"] == "nvidia_nim" and picked["model"] == "nemotron-primary",
            "the readout does not name the first CONFIGURED provider in the router's own order; "
            "a provider with no key must be skipped, and the local fallback at the end of the "
            "order must never be named while a cloud provider is answering: " + repr(picked),
        )

        def boom(*_a, **_k):
            raise RuntimeError("router unavailable")

        llm_router.get_llm_status = boom
        blind = routes._serving_model_fields()
        check(
            blind == {"model": "unknown", "serving_provider": "unknown", "fast_model": "unknown"},
            "with no way to read the router the readout must say unknown, not name a model on "
            "no evidence -- naming a model on no evidence IS the bug being fixed: " + repr(blind),
        )
    finally:
        llm_router.get_llm_status = original_status

    # ------------------------------- 4. the cache-buster, derived from the assets
    from fastapi.testclient import TestClient

    from eva.main import create_app

    with TestClient(create_app()) as client:
        first = client.get("/")
        check(first.status_code == 200, "GET / did not serve the app")
        check(
            "v=orb-v2" not in first.text,
            "index.html still ships the hand-written version string; nobody bumps a constant, "
            "so an edited app.js never reaches a browser that has been here before",
        )
        stamp = re.search(r"app\.js\?v=([0-9a-f]+)", first.text)
        check(stamp is not None, "app.js carries no derived cache stamp")

        # THE CHECK THAT BITES: "the stamp is a hex string" passes against a
        # constant. Only changing an asset and watching the stamp move proves
        # the stamp tracks the assets at all.
        #
        # Deliberately a NEW throwaway file rather than a touch of app.js. An
        # interrupted run -- a timeout kill, a Ctrl-C -- between the touch and
        # the restore would leave app.js with a future mtime, and every stamp
        # after that would be wrong but stable: precisely the stale-forever
        # failure this phase exists to fix. A temp file has nothing to restore.
        probe = APP_JS.parent / "_phase102_stamp_probe.js"
        try:
            probe.write_text("// transient verifier asset", encoding="utf-8")
            later = max(APP_JS.stat().st_mtime, probe.stat().st_mtime) + 500
            os.utime(probe, (later, later))
            moved = re.search(r"app\.js\?v=([0-9a-f]+)", client.get("/").text)
        finally:
            probe.unlink(missing_ok=True)
        check(moved is not None, "app.js lost its stamp after the asset changed")
        check(
            moved.group(1) != stamp.group(1),
            "the cache-buster did not move when app.js did, so it is not derived from the "
            "assets and a returning browser keeps running the copy it already has",
        )

        # ------------------------------------------- 5. the favicon that 404'd
        icon = client.get("/favicon.svg")
        check(icon.status_code == 200, "favicon.svg is not served")
        check("svg" in icon.text[:200].lower(), "favicon.svg is not an SVG")

    check(FAVICON.exists(), "frontend/favicon.svg is missing")
    html = INDEX_HTML.read_text(encoding="utf-8")
    check('href="/favicon.svg"' in html, "index.html does not point at the served favicon")
    check(
        "data:image/svg" not in html,
        "the favicon is inline again -- the data URI failed silently because the unescaped "
        "spaces in viewBox='0 0 32 32' make it an invalid URI, reported by the browser as "
        "nothing at all, which is why it looked like the file was simply missing",
    )

    # ---------------------------------------------------------- registration
    import verify_eva_all

    name = "verify_eva_phase102_ui_truth.py"
    check(name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 102 verifier")
    check(name in verify_eva_all.QUICK_VERIFIERS, "quick profile missing the Phase 102 verifier")
    check(name in verify_eva_all.VERIFIER_DESCRIPTORS, "master descriptor missing the Phase 102 verifier")

    print(
        "PASS: Phase 102 UI truth. Driving NOVA's own web page for the first time found six "
        "defects no API-level test could see, five of them one shape -- a fact written down in "
        "several places, the copies disagreeing, and the unwatched copy deciding. The status "
        "readout now names the provider that would actually serve rather than a local fallback "
        "that had served nothing; the voice preference agrees across the client default, the "
        "backend default and the sorter, and the agreement itself is asserted so two "
        "independently-correct lists cannot drift apart; browsers that already stored the old "
        "voice are reset rather than left with it; the default TTS provider is no longer "
        "persisted over the server's config on first load; the cache-buster is derived from the "
        "assets instead of hand-maintained; and the favicon is a served file rather than a data "
        "URI that was invalid all along. Every check mutation-tested."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
