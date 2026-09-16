from __future__ import annotations

import os

from ...core.config import ModelSettings
from ._openai_compatible import OpenAICompatibleProvider


# Phase 92: openai/gpt-oss-120b reached end of life on 2026-09-03T08:00:00Z and
# now returns HTTP 410 Gone. It was the default here for the general, planner AND
# code roles, so an operator with no override got a dead model for three of them.
# nemotron-3.5-lightning was already the configured fallback and was verified on
# 2026-09-03 to answer, to return clean text in `content` (its reasoning goes to
# `reasoning_content`, which _openai_compatible.py ignores), and -- the check that
# actually matters for the planner -- to emit real `tool_calls`.
DEFAULT_NIM_MODEL = "nvidia/nemotron-3.5-lightning-30b-a3b"
DEFAULT_NIM_FALLBACKS = "nvidia/nemotron-3.5-lightning-30b-a3b"


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def nvidia_nim_role_models() -> dict[str, str]:
    return {
        "planner": os.environ.get("NVIDIA_NIM_PLANNER_MODEL", DEFAULT_NIM_MODEL).strip() or DEFAULT_NIM_MODEL,
        # Phase 110: deepseek-v4-pro-0813 was retired (HTTP 410); a fresh checkout pointed at a dead model.
        "deep_reasoning": os.environ.get("NVIDIA_NIM_DEEP_REASONING_MODEL", "nvidia/nemotron-3-super-120b-a12b").strip(),
        "code": os.environ.get("NVIDIA_NIM_CODE_MODEL", DEFAULT_NIM_MODEL).strip(),
        "vision": os.environ.get("NVIDIA_NIM_VISION_MODEL", "meta/llama-3.2-11b-vision-instruct").strip(),
        "screen_reason": os.environ.get("NVIDIA_NIM_SCREEN_REASON_MODEL", "meta/llama-3.2-11b-vision-instruct").strip(),
        "embed": os.environ.get("NVIDIA_NIM_EMBED_MODEL", "nvidia/nemotron-3-embed-1b").strip(),
        # No rerank NIM is available on this account (checked 2026-09-01); "" means
        # "unconfigured" rather than naming a model that 404s. No caller reads this today.
        "rerank": os.environ.get("NVIDIA_NIM_RERANK_MODEL", "").strip(),
        "safety": os.environ.get("NVIDIA_NIM_SAFETY_MODEL", "nvidia/nemotron-3.5-content-safety").strip(),
        # No pii NIM is available on this account (checked 2026-09-01); "" means
        # "unconfigured" rather than naming a model that 404s. No caller reads this today.
        "pii": os.environ.get("NVIDIA_NIM_PII_MODEL", "").strip(),
        "asr": os.environ.get("NVIDIA_NIM_ASR_MODEL", "nvidia/parakeet-tdt-0.6b-v2").strip(),
        "tts": os.environ.get("NVIDIA_NIM_TTS_MODEL", "nvidia/magpie-tts-zeroshot").strip(),
    }


def nvidia_nim_models_for_purpose(purpose: str = "planner") -> list[str]:
    roles = nvidia_nim_role_models()
    primary = os.environ.get("NVIDIA_NIM_MODEL", DEFAULT_NIM_MODEL).strip() or DEFAULT_NIM_MODEL
    purpose_key = purpose.strip().lower()
    role_model = ""
    if purpose_key == "planner":
        role_model = roles["planner"]
    elif purpose_key in {"code", "workspace", "workspace_summary"}:
        role_model = roles["code"]
    elif purpose_key in {"vision", "screen", "screen_reason"}:
        role_model = roles["vision"]
    elif purpose_key in {"deep_reasoning", "debug"}:
        role_model = roles["deep_reasoning"]
    models = [role_model, primary, *_csv(os.environ.get("NVIDIA_NIM_FALLBACK_MODELS", DEFAULT_NIM_FALLBACKS))]
    deduped: list[str] = []
    for model in models:
        if model and model not in deduped:
            deduped.append(model)
    return deduped


class NvidiaNIMProvider(OpenAICompatibleProvider):
    name = "nvidia_nim"
    api_key_env = "NVIDIA_NIM_API_KEY"
    model_env = "NVIDIA_NIM_MODEL"
    default_model = DEFAULT_NIM_MODEL
    base_url_env = "NVIDIA_NIM_BASE_URL"
    default_base_url = "https://integrate.api.nvidia.com/v1"

    def __init__(self, settings: ModelSettings, model: str | None = None) -> None:
        super().__init__(settings)
        if model:
            self.model = model

    def extra_payload(self, tools: list[dict[str, object]] | None) -> dict[str, object]:
        """Turn nemotron's visible thinking off -- but ONLY when it has no tools.

        nemotron-3.5-lightning is a reasoning model. Asked to write one sentence
        from tool results it spends its budget thinking, and a user saw the
        result: NOVA answered "Here's a thinking process: 1. **Analyze User
        Input:** ..." instead of the time. The same call shape sometimes returns
        EMPTY content instead, which reads as a provider failure and falls
        through to gemini -- two faces of one cause.

        `chat_template_kwargs={"thinking": False}` removes it cleanly: measured,
        reasoning drops from 612 characters to 0 while content stays
        "It's 9:14 AM on Friday."

        **Gated on `tools`, because turning thinking off BREAKS TOOL CALLING --
        and breaks it in the worst possible way.** Measured on the identical
        request: with thinking on the model calls `system_time`; with it off it
        emits no tool call and answers "The current time is 12:34 PM", a time it
        invented. A planner that fabricates rather than reading the clock is far
        worse than a chatty one, so the planner keeps its reasoning and only the
        tool-free synthesis calls lose it.

        Harmless where unsupported: llama-3.2-vision and the content-safety model
        both answer normally with the field present.
        """
        if tools:
            return {}
        return {"chat_template_kwargs": {"thinking": False}}
