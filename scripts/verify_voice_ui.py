from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def emit(case: str, passed: bool, **payload: object) -> int:
    print(json.dumps({"case": case, "pass": passed, **payload}, indent=2, ensure_ascii=True))
    return 0 if passed else 1


def main() -> int:
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    css = (ROOT / "frontend" / "styles.css").read_text(encoding="utf-8")
    env = (ROOT / ".env.example").read_text(encoding="utf-8-sig")
    combined = "\n".join([html, js, css])
    failures = 0

    failures += emit(
        "voice_controls_present",
        all(
            token in html
            for token in (
                "voiceToggle",
                "voiceSelect",
                "refreshVoicesButton",
                "testVoiceButton",
                "stopVoiceButton",
                "voiceRate",
                "voicePitch",
                "voiceVolume",
            )
        ),
    )
    failures += emit(
        "push_to_talk_controls_present",
        # The label was renamed with the product (Eva -> NOVA); the control is what matters.
        all(token in html for token in ("micButton", "micLabel", "voiceTranscript", 'aria-label="Push to talk"')),
    )
    failures += emit(
        "speech_synthesis_used",
        "speechSynthesis" in js and "SpeechSynthesisUtterance" in js and "onvoiceschanged" in js,
    )
    failures += emit("get_voices_used", "getVoices()" in js)
    failures += emit(
        "speech_recognition_used",
        "SpeechRecognition" in js
        and "webkitSpeechRecognition" in js
        and "recognition.interimResults = true" in js
        and "submitCommand(command)" in js,
    )
    failures += emit(
        "stable_voice_persistence",
        "eva.selectedVoiceName" in js
        and "eva.selectedVoiceLang" in js
        and "saveLockedVoice" in js
        and "lockedVoice" in js,
    )
    failures += emit(
        "soft_defaults",
        "const DEFAULT_VOICE_RATE = 1.08" in js
        and "const DEFAULT_VOICE_PITCH = 1.02" in js
        and "const DEFAULT_VOICE_VOLUME = 0.82" in js
        and "2.35" not in js,
    )
    failures += emit(
        "slider_ranges_soft",
        'id="voiceRate" type="range" min="0.85" max="1.25" step="0.01"' in html
        and 'id="voicePitch" type="range" min="0.9" max="1.15" step="0.01"' in html
        and 'id="voiceVolume" type="range" min="0.4" max="1.0" step="0.01"' in html,
    )
    failures += emit(
        "voice_values_persist",
        "eva.voiceRate" in js and "eva.voicePitch" in js and "eva.voiceVolume" in js,
    )
    failures += emit(
        "rapid_backend_config_clamped",
        "return Math.min(max, Math.max(min, fallbackNumber));" in js,
    )
    failures += emit(
        "browser_voice_default_not_piper",
        'localStorage.getItem("eva-tts-provider") || "browser"' in js
        and 'localStorage.removeItem("eva-tts-provider")' in js,
    )
    failures += emit(
        "speak_eva_helper_exists",
        "function speakEva" in js
        and "window.setTimeout" in js
        and "70" in js
        and "window.speechSynthesis.speak(utterance)" in js,
    )
    failures += emit(
        "voice_reliability_globals",
        "activeUtterance" in js
        and "speechQueue" in js
        and "speechSequence" in js
        and "speechStallTimer" in js,
    )
    failures += emit(
        "should_speak_filter_exists",
        "function shouldSpeakMessage" in js
        and "Planning" in js
        and "Tavily returned" in js
        and "configured_keys" in js,
    )
    failures += emit(
        "speech_cleanup_exists",
        "cleanSpeechText" in js
        and "link available in chat" in js
        and "MAX_SPOKEN_CHARS = 450" in js
        and "I put the full details in chat" in js,
    )
    failures += emit(
        "technical_speech_replacements",
        "normalizeTechnicalSpeech" in js
        and "Operating system" in js
        and "executable" in js
        and "local Windows path" in js
        and "C:\\\\" in js,
    )
    failures += emit(
        "speak_final_response_only",
        "finalDisplayedReply" in js
        and "speakEva(finalDisplayedReply)" in js
        and "reply += event.text" in js
        and "speakEva(reply);" not in js,
    )
    failures += emit(
        "diagnostics_voice_summarized",
        "I put the full architecture in chat" in js
        and "System health is in chat" in js
        and "provider | configured | model | status" in js,
    )
    failures += emit(
        "long_speech_preserves_beginning",
        "slice(0, 2)" in js
        and "substring" not in js
        and "substr(" not in js
        and "speech.slice(MAX_SPOKEN_CHARS" not in js,
    )
    failures += emit(
        "stop_speaking_supported",
        "speechSynthesis.cancel()" in js and "stopVoiceButton" in js and "stopAllSpeech" in js,
    )
    failures += emit(
        "activity_cancel_not_used",
        "speech_skip_activity" in js
        and "stopAllSpeech(false)" not in js
        and "window.speechSynthesis.cancel();\n  window.speechSynthesis.speak(utterance)" not in js,
    )
    failures += emit(
        "speech_retry_once",
        "retryCount" in js and "retryCount < 1" in js and "speech_stall_retry" in js,
    )
    failures += emit(
        "test_voice_phrase",
        "Hey Ankit, this is Eva. I" in js and "soft and quick" in js,
    )
    failures += emit(
        "natural_voice_priority",
        # Phase 102 made the fallback voices male to match the persona and the
        # installed Piper model; this check used to pin the old female list.
        "Microsoft Guy Online" in js
        and "Microsoft David" in js
        and "Google US English Male" in js
        and "Microsoft Zira" not in js.split("preferredVoices: [", 1)[1].split("]", 1)[0],
    )
    failures += emit(
        "final_only_speaking",
        "speakEva(finalDisplayedReply)" in js and "speakEva(label" not in js and "speakEva(event.message" not in js,
    )
    failures += emit(
        "speaking_visual_state",
        "body[data-eva-state=\"speaking\"]" in css,
    )
    # The defaults are not in .env.example (they never were at HEAD); what must
    # hold is that the backend and the UI agree and that a missing browser
    # setting falls back to them instead of clamping to the minimum.
    routes_src = (ROOT / "backend" / "eva" / "api" / "routes.py").read_text(encoding="utf-8")
    failures += emit(
        "voice_defaults_agree_and_apply",
        "DEFAULT_VOICE_RATE = 1.08" in js
        and "DEFAULT_VOICE_PITCH = 1.02" in js
        and "DEFAULT_VOICE_VOLUME = 0.82" in js
        and '"EVA_VOICE_RATE", "1.08"' in routes_src
        and '"EVA_VOICE_PITCH", "1.02"' in routes_src
        and '"EVA_VOICE_VOLUME", "0.82"' in routes_src
        and 'value === null || value === undefined || value === "" ? NaN' in js,
    )
    secret_patterns = [
        r"AIza[0-9A-Za-z_\-]{20,}",
        r"sk-or-v1-[0-9A-Za-z_\-]+",
        r"nvapi-[0-9A-Za-z_\-]+",
        r"tvly-[0-9A-Za-z_\-]+",
    ]
    leaked = [pattern for pattern in secret_patterns if re.search(pattern, combined)]
    failures += emit("no_hardcoded_api_keys", not leaked, leaked_patterns=leaked)

    print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
