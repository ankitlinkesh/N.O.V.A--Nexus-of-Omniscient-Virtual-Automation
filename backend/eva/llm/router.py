from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Iterable

from ..core.config import ModelSettings
from .providers.clod import ClodProvider
from .providers.gemini import GeminiProvider
from .providers.groq import GroqEmergencyProvider, GroqProvider
from .providers.nvidia_nim import DEFAULT_NIM_MODEL, NvidiaNIMProvider, nvidia_nim_models_for_purpose, nvidia_nim_role_models
from .providers.ollama import OllamaProvider
from .providers.openrouter import OpenRouterProvider
from .rate_limiter import LLMRateLimiter, provider_limits, provider_token_limits
from .types import LLMAttempt, LLMProvider, LLMResponse, Message, RoutedLLMResponse

DEFAULT_PROVIDER_ORDER = ["nvidia_nim", "gemini", "openrouter", "groq", "clod", "ollama"]
LLM_MODES = {"auto", "nvidia_nim", "gemini", "openrouter", "groq", "clod", "qwen", "llama", "local"}
PROVIDER_CLASSES = {
    "gemini": GeminiProvider,
    "groq": GroqProvider,
    "openrouter": OpenRouterProvider,
    "nvidia_nim": NvidiaNIMProvider,
    "clod": ClodProvider,
    "ollama": OllamaProvider,
}


def preview_llm_route(request: str):
    """Return Phase 15A metadata only; never invokes the legacy completion path."""
    from .models import LLMDegradedMode, LLMProviderName, LLMRouteDecision, LLMRouteRequestPreview
    from .routing_policy import get_fallback_policy

    preview = LLMRouteRequestPreview(str(request or "").strip() or "No request supplied.")
    fallback = get_fallback_policy()
    return LLMRouteDecision(LLMProviderName.MOCK, fallback.order, False, LLMDegradedMode.MOCK_ONLY, f"Route preview for: {preview.request}. Phase 15A never calls a provider.")


def llm_mode() -> str:
    mode = os.environ.get("EVA_LLM_MODE", "auto").strip().lower()
    return mode if mode in LLM_MODES else "auto"


def set_llm_mode(mode: str) -> str:
    normalized = mode.strip().lower()
    aliases = {
        "automatic": "auto",
        "default": "auto",
        "cloud": "auto",
        "local only": "local",
        "local brain": "local",
        "nvidia": "nvidia_nim",
        "nvidia nim": "nvidia_nim",
        "nim": "nvidia_nim",
        "google": "gemini",
        "gemini api": "gemini",
        "open router": "openrouter",
        "openrouter": "openrouter",
        "groq": "groq",
        "clod": "clod",
        "clōd": "clod",
        "qwen local": "qwen",
        "llama local": "llama",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in LLM_MODES:
        supported = ", ".join(sorted(LLM_MODES))
        raise ValueError(f"Unsupported LLM mode: {mode}. Supported: {supported}.")
    os.environ["EVA_LLM_MODE"] = normalized
    if normalized in {"qwen", "llama", "local"}:
        os.environ["EVA_USE_OLLAMA_FOR_PLANNER"] = "true"
    else:
        os.environ["EVA_USE_OLLAMA_FOR_PLANNER"] = "false"
    return normalized


def ollama_model_for_mode(settings: ModelSettings) -> str:
    mode = llm_mode()
    if mode == "qwen":
        return os.environ.get("EVA_OLLAMA_QWEN_MODEL", "").strip() or settings.fast_model or "qwen2.5:1.5b"
    if mode == "llama":
        return os.environ.get("EVA_OLLAMA_LLAMA_MODEL", "").strip() or "llama3.1:8b"
    return os.environ.get("EVA_OLLAMA_FALLBACK_MODEL", "").strip() or settings.fast_model or settings.ollama_model


def provider_order() -> list[str]:
    mode = llm_mode()
    if mode in {"qwen", "llama", "local"}:
        return ["ollama"]
    auto_order = _auto_provider_order()
    if mode in {"nvidia_nim", "gemini", "openrouter", "groq", "clod"}:
        if _provider_configured(mode) and not _provider_currently_blocked(mode):
            ordered = [mode] + [name for name in auto_order if name != mode]
            return ordered
        return auto_order
    return auto_order


def _auto_provider_order() -> list[str]:
    raw = os.environ.get("EVA_CLOUD_PROVIDER_ORDER", ",".join(DEFAULT_PROVIDER_ORDER))
    allow_cloud = os.environ.get("EVA_ALLOW_CLOUD_FALLBACK", "true").strip().lower() not in {"0", "false", "no", "off"}
    names = [item.strip().lower() for item in raw.split(",") if item.strip()]
    if not names:
        names = list(DEFAULT_PROVIDER_ORDER)
    deduped: list[str] = []
    for name in names:
        if name in PROVIDER_CLASSES and name != "ollama" and name not in deduped:
            deduped.append(name)
    ordered = deduped if allow_cloud else []
    if "ollama" not in ordered:
        ordered.append("ollama")
    return ordered


def _provider_configured(name: str) -> bool:
    if name == "gemini":
        return _gemini_key_count() > 0
    if name == "nvidia_nim":
        return _env_has_key("NVIDIA_NIM_API_KEY")
    if name == "openrouter":
        return _env_has_key("OPENROUTER_API_KEY")
    if name == "groq":
        return _env_has_key("GROQ_API_KEY")
    if name == "clod":
        return _env_has_key("CLOD_API_KEY")
    if name == "ollama":
        return True
    return False


def _provider_current_model(name: str) -> str:
    settings = ModelSettings()
    if name == "gemini":
        return os.environ.get("GEMINI_MODEL", settings.smart_model or "gemini-2.5-flash")
    if name == "nvidia_nim":
        return os.environ.get("NVIDIA_NIM_MODEL", DEFAULT_NIM_MODEL)
    if name == "openrouter":
        return os.environ.get("OPENROUTER_MODEL", "deepseek/deepseek-chat-v3-0324:free")
    if name == "groq":
        return os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    if name == "clod":
        return os.environ.get("CLOD_MODEL", "DeepSeek V3")
    return ollama_model_for_mode(settings)


def _provider_currently_blocked(name: str) -> bool:
    if name == "ollama":
        return False
    model = _provider_current_model(name)
    usage = LLMRateLimiter().status()
    now = int(time.time())
    for key, entry in usage.items():
        if not isinstance(entry, dict) or not str(key).startswith(f"{name}:"):
            continue
        tracked_model = str(key).split(":", 1)[1]
        if name == "gemini":
            if not tracked_model.startswith(model):
                continue
        elif tracked_model != model:
            continue
        if int(entry.get("blocked_until") or 0) > now:
            return True
    return False


def build_provider(name: str, settings: ModelSettings) -> LLMProvider | None:
    cls = PROVIDER_CLASSES.get(name)
    return cls(settings) if cls else None


# A model that is retired or misspelled, as opposed to a provider that is down.
# NVIDIA NIM returns 410 with an "end of life" detail; most OpenAI-compatible
# backends return 404 for an unknown model id. Both mean "this model is gone",
# which is a fact about the MODEL, never about the provider or the key.
_MODEL_UNAVAILABLE_STATUS = {404, 410}


def _is_retryable_failure(response: LLMResponse) -> bool:
    if response.ok and (response.text.strip() or response.tool_calls):
        return False
    if response.rate_limited:
        return True
    if response.status_code is None:
        return True
    if response.status_code >= 500:
        return True
    if response.error in {"empty_response", "missing_api_key", "invalid_planner_json"}:
        return True
    return False


def _json_is_valid(text: str) -> bool:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").removeprefix("json").strip()
    try:
        json.loads(cleaned)
        return True
    except json.JSONDecodeError:
        return False


def _normalized_attempt_error(response: LLMResponse) -> str | None:
    if response.ok:
        return response.error
    if response.rate_limited or response.status_code == 429:
        return "rate_limited_429"
    if response.error in {"missing_api_key", "empty_response", "invalid_planner_json", "skipped_for_planner"}:
        return response.error
    if response.error and response.error.startswith("soft_limit_exhausted"):
        return "soft_limit_exhausted"
    if response.error and response.error.startswith("blocked_until:"):
        return response.error
    if response.status_code is None and response.error:
        return "network_error"
    if response.status_code is not None and response.status_code >= 500:
        return "provider_error"
    return response.error or "provider_error"


def _attempt_from_response(response: LLMResponse, purpose: str, *, selected_provider: str | None = None, fallback_used: bool = False) -> LLMAttempt:
    return LLMAttempt(
        provider=response.provider,
        model=response.model,
        purpose=purpose,
        ok=response.ok,
        error=_normalized_attempt_error(response),
        status_code=response.status_code,
        rate_limited=response.rate_limited,
        fallback_used=fallback_used,
        selected_provider=selected_provider,
    )


def _estimated_tokens(messages: list[Message], max_tokens: int) -> int:
    chars = sum(len(str(item.get("content", ""))) for item in messages)
    return max(1, chars // 4 + max_tokens)


async def _call_provider(
    provider: LLMProvider,
    limiter: LLMRateLimiter,
    messages: list[Message],
    *,
    purpose: str,
    temperature: float,
    max_tokens: int,
    tools: list[dict[str, Any]] | None = None,
) -> tuple[LLMResponse, bool]:
    estimate = _estimated_tokens(messages, max_tokens)
    response = await provider.complete(messages, temperature=temperature, max_tokens=max_tokens, tools=tools)
    # The planner-JSON guard only applies to the JSON-prompt path -- which is
    # exactly the path that passes no `tools`. That is what the condition now
    # says; before Phase 93 it only exempted a response CARRYING tool_calls, and
    # a native planner has TWO valid replies. The agent-step prompt explicitly
    # asks for the second one ("If the results you can already see answer the
    # goal, do NOT call a tool -- reply in plain text with the final answer for
    # the user"), and plain text is not JSON, so the model's correct final answer
    # was rewritten into `invalid_planner_json` and thrown away on the last step
    # of every errand. Proven with one request, same model, only purpose changed:
    # purpose="chat" returned "Task complete."; purpose="planner" returned
    # ok=False with the text discarded.
    asked_for_json = tools is None
    if (
        response.ok
        and purpose == "planner"
        and asked_for_json
        and not response.tool_calls
        and not _json_is_valid(response.text)
    ):
        response = LLMResponse(
            provider=response.provider,
            model=response.model,
            text=response.text,
            ok=False,
            error="invalid_planner_json",
            status_code=response.status_code,
            rate_limited=False,
            raw_headers=response.raw_headers,
        )
    if getattr(provider, "uses_internal_rate_limits", False):
        return response, _is_retryable_failure(response)
    if response.ok:
        limiter.record_success(provider.name, provider.model, estimated_tokens=estimate)
    else:
        limiter.record_failure(
            provider.name,
            response.error or "unknown_error",
            model=provider.model,
            rate_limited=response.rate_limited,
            retry_after_seconds=response.retry_after_seconds,
            count_attempt=True,
            estimated_tokens=estimate,
        )
    return response, _is_retryable_failure(response)


async def _try_nvidia_nim_models(
    settings: ModelSettings,
    limiter: LLMRateLimiter,
    attempts: list[LLMAttempt],
    messages: list[Message],
    *,
    purpose: str,
    temperature: float,
    max_tokens: int,
    estimated_tokens: int,
    tools: list[dict[str, Any]] | None = None,
) -> RoutedLLMResponse | None:
    models = nvidia_nim_models_for_purpose(purpose)
    if not models:
        return None

    first_provider = NvidiaNIMProvider(settings, model=models[0])
    if not first_provider.available():
        response = LLMResponse(provider="nvidia_nim", model=models[0], ok=False, error="missing_api_key")
        attempts.append(_attempt_from_response(response, purpose, fallback_used=bool(attempts)))
        return None

    for model in models:
        provider = NvidiaNIMProvider(settings, model=model)
        allowed, reason = limiter.can_call("nvidia_nim", model, estimated_tokens=estimated_tokens)
        if not allowed:
            response = LLMResponse(provider="nvidia_nim", model=model, ok=False, error=reason)
            attempts.append(_attempt_from_response(response, purpose, fallback_used=bool(attempts)))
            continue

        response, retryable = await _call_provider(provider, limiter, messages, purpose=purpose, temperature=temperature, max_tokens=max_tokens, tools=tools)
        if response.ok and (response.text.strip() or response.tool_calls):
            attempts.append(_attempt_from_response(response, purpose, selected_provider="nvidia_nim", fallback_used=bool(attempts)))
            return RoutedLLMResponse(response=response, attempts=attempts, fallback_occurred=len(attempts) > 1)

        attempts.append(_attempt_from_response(response, purpose, fallback_used=bool(attempts)))
        if response.status_code in {401, 403}:
            break
        # A model that is GONE is the strongest possible reason to try the NEXT
        # model in this list -- and until Phase 92 it was treated as a reason to
        # abandon the provider entirely, so the configured fallback model was
        # never once reached. `retryable` answers "should I retry this same
        # model?", for which 404/410 is correctly False. This loop is asking a
        # different question -- "should I try a DIFFERENT model?" -- and had
        # inherited the wrong answer to it. Handled here rather than inside
        # _is_retryable_failure, which is shared with the cross-provider loop
        # below and must keep meaning what it says.
        if response.status_code in _MODEL_UNAVAILABLE_STATUS:
            continue
        if not retryable:
            break
    return None


async def complete_with_fallback(
    messages: list[Message],
    settings: ModelSettings,
    *,
    purpose: str = "planner",
    temperature: float = 0.2,
    max_tokens: int = 800,
    tools: list[dict[str, Any]] | None = None,
) -> RoutedLLMResponse:
    limiter = LLMRateLimiter()
    attempts: list[LLMAttempt] = []
    estimate = _estimated_tokens(messages, max_tokens)

    for name in provider_order():
        if name == "nvidia_nim":
            routed = await _try_nvidia_nim_models(
                settings,
                limiter,
                attempts,
                messages,
                purpose=purpose,
                temperature=temperature,
                max_tokens=max_tokens,
                estimated_tokens=estimate,
                tools=tools,
            )
            if routed is not None:
                return routed
            continue

        provider = build_provider(name, settings)
        if provider is None:
            continue

        if purpose == "planner" and name == "ollama" and llm_mode() not in {"qwen", "llama"} and os.environ.get("EVA_USE_OLLAMA_FOR_PLANNER", "false").strip().lower() not in {"1", "true", "yes", "on"}:
            response = LLMResponse(provider=name, model=getattr(provider, "model", ""), ok=False, error="skipped_for_planner")
            attempts.append(_attempt_from_response(response, purpose, fallback_used=bool(attempts)))
            continue

        if not provider.available():
            response = LLMResponse(provider=name, model=getattr(provider, "model", ""), ok=False, error="missing_api_key")
            attempts.append(_attempt_from_response(response, purpose, fallback_used=bool(attempts)))
            continue

        if not getattr(provider, "uses_internal_rate_limits", False):
            allowed, reason = limiter.can_call(name, getattr(provider, "model", None), estimated_tokens=estimate)
            if not allowed:
                response = LLMResponse(provider=name, model=getattr(provider, "model", ""), ok=False, error=reason)
                attempts.append(_attempt_from_response(response, purpose, fallback_used=bool(attempts)))
                if name == "groq":
                    emergency = GroqEmergencyProvider(settings)
                    if emergency.available() and emergency.model != provider.model:
                        allowed_emergency, emergency_reason = limiter.can_call("groq", emergency.model, estimated_tokens=estimate)
                        if allowed_emergency:
                            emergency_response, _ = await _call_provider(emergency, limiter, messages, purpose=purpose, temperature=temperature, max_tokens=max_tokens, tools=tools)
                            if emergency_response.ok and (emergency_response.text.strip() or emergency_response.tool_calls):
                                attempts.append(_attempt_from_response(emergency_response, purpose, selected_provider="groq", fallback_used=True))
                                return RoutedLLMResponse(response=emergency_response, attempts=attempts, fallback_occurred=True)
                            attempts.append(_attempt_from_response(emergency_response, purpose, fallback_used=True))
                        else:
                            attempts.append(LLMAttempt(provider="groq", model=emergency.model, purpose=purpose, ok=False, error=emergency_reason, fallback_used=True))
                continue

        response, retryable = await _call_provider(provider, limiter, messages, purpose=purpose, temperature=temperature, max_tokens=max_tokens, tools=tools)
        if response.ok and (response.text.strip() or response.tool_calls):
            selected = response.provider
            attempts.append(_attempt_from_response(response, purpose, selected_provider=selected, fallback_used=bool(attempts)))
            return RoutedLLMResponse(response=response, attempts=attempts, fallback_occurred=len(attempts) > 1)

        attempts.append(_attempt_from_response(response, purpose, fallback_used=bool(attempts)))

        if name == "groq" and provider.model == os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile") and retryable:
            emergency = GroqEmergencyProvider(settings)
            if emergency.available() and emergency.model != provider.model:
                allowed, reason = limiter.can_call("groq", emergency.model, estimated_tokens=estimate)
                if allowed:
                    emergency_response, _ = await _call_provider(emergency, limiter, messages, purpose=purpose, temperature=temperature, max_tokens=max_tokens, tools=tools)
                    if emergency_response.ok and (emergency_response.text.strip() or emergency_response.tool_calls):
                        attempts.append(_attempt_from_response(emergency_response, purpose, selected_provider="groq", fallback_used=True))
                        return RoutedLLMResponse(response=emergency_response, attempts=attempts, fallback_occurred=True)
                    attempts.append(_attempt_from_response(emergency_response, purpose, fallback_used=True))
                else:
                    attempts.append(LLMAttempt(provider="groq", model=emergency.model, purpose=purpose, ok=False, error=reason, fallback_used=True))

    final_error = "; ".join(f"{attempt.provider}:{attempt.error or attempt.status_code}" for attempt in attempts[-4:]) or "no_provider_available"
    return RoutedLLMResponse(
        response=LLMResponse(provider="none", model="none", ok=False, error=final_error),
        attempts=attempts,
        fallback_occurred=bool(attempts),
    )


def _env_has_key(name: str) -> bool:
    return bool(os.environ.get(name, "").strip())


def _gemini_key_count() -> int:
    keys: list[str] = []
    for raw in (os.environ.get("GEMINI_API_KEY", ""), os.environ.get("GEMINI_API_KEY_2", ""), os.environ.get("GEMINI_API_KEYS", "")):
        for token in re.findall(r"AIza[0-9A-Za-z_-]{35}", raw or ""):
            if token not in keys:
                keys.append(token)
    return len(keys)



def _sanitize_status_error(error: object) -> str:
    text = str(error or "")[:500]
    try:
        data = json.loads(text)
        err = data.get("error") if isinstance(data, dict) else None
        if isinstance(err, dict):
            safe = {key: err.get(key) for key in ("message", "type", "code", "status", "param") if err.get(key) is not None}
            return json.dumps({"error": safe}, ensure_ascii=False)[:500]
    except Exception:
        pass
    return re.sub(r'[,\s]*"user_id"\s*:\s*"[^"]*"', "", text)

def _sanitize_usage_state(usage: dict) -> dict:
    sanitized = {}
    for key, entry in usage.items():
        if not isinstance(entry, dict):
            continue
        clean = entry.copy()
        if clean.get("last_error"):
            clean["last_error"] = _sanitize_status_error(clean.get("last_error"))
        sanitized[key] = clean
    return sanitized


def _gemini_key_status(usage: dict, model: str) -> dict:
    key_count = _gemini_key_count()
    rpm, rpd = provider_limits("gemini", model)
    tpm, _ = provider_token_limits("gemini", model)
    now = int(time.time())
    slots = []
    exhausted_count = 0
    for index in range(1, key_count + 1):
        slot_model = f"{model}[key{index}]"
        entry = usage.get(f"gemini:{slot_model}", {})
        if not isinstance(entry, dict):
            entry = {}
        blocked_until = int(entry.get("blocked_until") or 0)
        reasons = []
        if blocked_until > now:
            reasons.append(f"blocked_until:{blocked_until}")
        if rpm is not None and int(entry.get("requests_this_minute") or 0) >= rpm:
            reasons.append("soft_limit_exhausted:rpm")
        if rpd is not None and int(entry.get("requests_today") or 0) >= rpd:
            reasons.append("soft_limit_exhausted:rpd")
        if tpm is not None and int(entry.get("estimated_tokens_this_minute") or 0) >= tpm:
            reasons.append("soft_limit_exhausted:tpm")
        exhausted = bool(reasons)
        exhausted_count += 1 if exhausted else 0
        slots.append(
            {
                "slot": index,
                "model": slot_model,
                "available": not exhausted,
                "reasons": reasons,
                "blocked_until": blocked_until if blocked_until > now else None,
            }
        )
    return {
        "key_slots": key_count,
        "all_exhausted_or_blocked": bool(key_count and exhausted_count == key_count),
        "slots": slots,
    }


def get_llm_status(settings: ModelSettings | None = None) -> dict:
    settings = settings or ModelSettings()
    limiter = LLMRateLimiter()
    usage = _sanitize_usage_state(limiter.status())
    models = {
        "gemini": os.environ.get("GEMINI_MODEL", settings.smart_model or "gemini-2.5-flash"),
        "groq": os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
        "groq_fallback": os.environ.get("GROQ_FALLBACK_MODEL", "llama-3.1-8b-instant"),
        "openrouter": os.environ.get("OPENROUTER_MODEL", "deepseek/deepseek-chat-v3-0324:free"),
        "nvidia_nim": os.environ.get("NVIDIA_NIM_MODEL", DEFAULT_NIM_MODEL),
        "clod": os.environ.get("CLOD_MODEL", "DeepSeek V3"),
        "ollama": ollama_model_for_mode(settings),
    }
    keys = {
        "gemini": _gemini_key_count() > 0,
        "groq": _env_has_key("GROQ_API_KEY"),
        "openrouter": _env_has_key("OPENROUTER_API_KEY"),
        "nvidia_nim": _env_has_key("NVIDIA_NIM_API_KEY"),
        "clod": _env_has_key("CLOD_API_KEY"),
        "ollama": True,
    }
    now = int(time.time())
    blocked = {
        key: int(entry.get("blocked_until") or 0)
        for key, entry in usage.items()
        if isinstance(entry, dict) and int(entry.get("blocked_until") or 0) > now
    }
    last_errors = {key: _sanitize_status_error(entry.get("last_error")) for key, entry in usage.items() if isinstance(entry, dict) and entry.get("last_error")}
    limits = {}
    for provider, model in {
        "gemini": models["gemini"],
        "groq": models["groq"],
        "groq_fallback": models["groq_fallback"],
        "openrouter": models["openrouter"],
        "nvidia_nim": models["nvidia_nim"],
        "clod": models["clod"],
    }.items():
        base_provider = "groq" if provider == "groq_fallback" else provider
        rpm, rpd = provider_limits(base_provider, model)
        tpm, tpd = provider_token_limits(base_provider, model)
        limits[provider] = {"soft_rpm": rpm, "soft_rpd": rpd, "soft_tpm": tpm, "soft_tpd": tpd}
    warnings = []
    if models["openrouter"] and not str(models["openrouter"]).endswith(":free"):
        warnings.append("OpenRouter model does not end with :free and may use paid credits.")
    gemini_status = _gemini_key_status(usage, models["gemini"])
    if gemini_status["all_exhausted_or_blocked"]:
        warnings.append("All configured Gemini key slots are locally exhausted or blocked right now; Eva will use fallback mode/provider.")
    return {
        "active_mode": llm_mode(),
        "provider_order": provider_order(),
        "configured_keys": keys,
        "configured_key_slots": {"gemini": _gemini_key_count()},
        "models": models,
        "nvidia_nim": {
            "configured": keys["nvidia_nim"],
            "base_url": os.environ.get("NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1"),
            "primary_model": models["nvidia_nim"],
            "fallback_models": nvidia_nim_models_for_purpose("planner")[1:],
            "role_models": nvidia_nim_role_models(),
            "soft_rpm": limits["nvidia_nim"]["soft_rpm"],
            "soft_rpd": limits["nvidia_nim"]["soft_rpd"],
            "usage": {key: value for key, value in usage.items() if key.startswith("nvidia_nim:")},
        },
        "gemini_key_status": gemini_status,
        "usage": usage,
        "blocked_providers": blocked,
        "last_errors": last_errors,
        "limits": limits,
        "warnings": warnings,
        "allow_cloud_fallback": os.environ.get("EVA_ALLOW_CLOUD_FALLBACK", "true").strip().lower() not in {"0", "false", "no", "off"},
    }


def attempts_as_dicts(attempts: Iterable[LLMAttempt]) -> list[dict]:
    return [attempt.__dict__.copy() for attempt in attempts]




