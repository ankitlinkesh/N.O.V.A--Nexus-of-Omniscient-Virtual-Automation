from __future__ import annotations

import hashlib

from .models import VoiceSessionPreview
from .transcript_safety import classify_transcript


def _session_id(transcript: str) -> str:
    digest = hashlib.sha256(str(transcript or "").encode("utf-8")).hexdigest()[:12]
    return f"voice-preview-{digest}"


def build_voice_route_preview(transcript: str = "show voice assistant status") -> VoiceSessionPreview:
    safety = classify_transcript(transcript)
    if safety.classification == "safe":
        state = "routed_to_agent_preview"
        intent = "local status, policy, or planning request"
        route = "PlannerAgent local preview"
        confirmation = "not required for this read-only preview"
        gate = "Execution gate preview: read-only route; no action path."
        blocked_reason = ""
        readiness = "ready for local text-preview routing"
    elif safety.classification == "confirmation_required":
        state = "confirmation_required"
        intent = "high-risk future action"
        route = "Controlled Execution Gates confirmation preview"
        confirmation = "required as preview only"
        gate = "Execution gate preview: confirmation does not authorize an action."
        blocked_reason = safety.blocked_reason
        readiness = "stopped before execution pending a future implemented gate"
    else:
        state = "transcript_blocked"
        intent = "unsafe or unsupported voice request"
        route = "SafetyAgent refusal preview"
        confirmation = "cannot override this block"
        gate = "Execution gate preview: blocked; no action path."
        blocked_reason = safety.blocked_reason
        readiness = "stopped safely"

    return VoiceSessionPreview(
        voice_session_id=_session_id(transcript),
        current_state=state,
        mock_input_transcript=safety.safe_transcript,
        transcript_safety_classification=safety.classification,
        redaction_status="redacted" if safety.redacted else "not required",
        detected_intent_summary=intent,
        selected_route_preview=route,
        confirmation_requirement=confirmation,
        execution_gate_decision_summary=gate,
        response_mode="text preview only",
        blocked_reason=blocked_reason,
        final_readiness_status=readiness,
        no_microphone_access_statement="No microphone access happened.",
        no_audio_playback_statement="No audio playback happened.",
        no_live_asr_tts_statement="No live ASR/TTS happened.",
        no_live_llm_call_statement="No live LLM call was made.",
        no_tool_execution_statement="Voice commands cannot execute tools.",
        no_new_write_path_statement="Phase 12L remains a gated write path.",
    )
