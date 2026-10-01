from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from ..core.config import ModelSettings
from ..llm.rate_limiter import provider_limits, provider_token_limits
from ..llm.router import DEFAULT_PROVIDER_ORDER, get_llm_status, llm_mode, provider_order


PROVIDER_LABELS = {
    "nvidia_nim": "NVIDIA NIM",
    "gemini": "Gemini",
    "openrouter": "OpenRouter",
    "groq": "Groq",
    "clod": "CLoD",
    "ollama": "Ollama",
}

PROVIDER_ALIASES = {
    "openrouter": {"openrouter", "open router"},
    "nvidia_nim": {"nvidia_nim", "nvidia nim", "nim", "nvidia"},
    "gemini": {"gemini", "google ai"},
    "groq": {"groq"},
    "clod": {"clod", "clōd", "clod ai"},
    "ollama": {"ollama", "qwen", "llama", "mistral", "local"},
}


def provider_from_alias(value: str | None) -> str | None:
    text = str(value or "").strip().lower().replace("-", "_")
    for provider, aliases in PROVIDER_ALIASES.items():
        if text in aliases or any(alias in text for alias in aliases):
            return provider
    return None


def safe_provider_error_summary(error: object) -> str:
    text = str(error or "").strip()
    if not text:
        return "none"
    lowered = text.lower()
    if "missing_api_key" in lowered or "missing key" in lowered:
        return "missing key"
    if "resource_exhausted" in lowered or "429" in lowered or "quota" in lowered or "rate limit" in lowered:
        return "quota/rate limit"
    if "503" in lowered or "high demand" in lowered or "temporarily unavailable" in lowered:
        return "temporarily unavailable"
    if ("401" in lowered or "user not found" in lowered or "invalid api key" in lowered or "unauthorized" in lowered) and "openrouter" in lowered:
        return "auth failed / key invalid"
    if "401" in lowered or "user not found" in lowered or "invalid api key" in lowered or "unauthorized" in lowered:
        return "auth failed / key invalid"
    if "team quota exceeded" in lowered or ("403" in lowered and "quota" in lowered):
        return "quota exceeded"
    if "no endpoints" in lowered or "model unavailable" in lowered or "404 page not found" in lowered or "page not found" in lowered:
        return "model unavailable"
    if "connection" in lowered and ("refused" in lowered or "failed" in lowered or "unreachable" in lowered):
        return "local server unreachable"
    if "blocked_until:" in lowered:
        return "temporarily blocked by local rate limiter"
    if "soft_limit_exhausted" in lowered:
        return "local soft limit exhausted"
    # Keep normal status readable and avoid dumping provider JSON into chat.
    scrubbed = re.sub(r"\{.*\}", "", text, flags=re.DOTALL).strip()
    scrubbed = re.sub(r"\s+", " ", scrubbed)
    return (scrubbed[:120] + "...") if len(scrubbed) > 120 else (scrubbed or "provider error")


def _usage_for_provider(status: dict[str, Any], provider: str, model: str | None) -> tuple[int, str, int | None]:
    usage = status.get("usage") if isinstance(status.get("usage"), dict) else {}
    errors = status.get("last_errors") if isinstance(status.get("last_errors"), dict) else {}
    blocked = status.get("blocked_providers") if isinstance(status.get("blocked_providers"), dict) else {}
    now = int(time.time())
    total_today = 0
    last_error = ""
    blocked_until: int | None = None

    allowed_models: set[str] | None = {model} if model else None
    if provider == "nvidia_nim":
        nim = status.get("nvidia_nim") if isinstance(status.get("nvidia_nim"), dict) else {}
        configured = [nim.get("primary_model"), *(nim.get("fallback_models") or [])]
        allowed_models = {str(item) for item in configured if item}

    for key, entry in usage.items():
        if not isinstance(entry, dict) or not str(key).startswith(f"{provider}:"):
            continue
        tracked_model = str(key).split(":", 1)[1]
        if allowed_models and provider != "gemini" and tracked_model not in allowed_models:
            continue
        if allowed_models and provider == "gemini" and not any(tracked_model.startswith(item) for item in allowed_models):
            continue
        total_today += int(entry.get("requests_today") or 0)
        raw_error = errors.get(key) or entry.get("last_error")
        if raw_error:
            last_error = safe_provider_error_summary(raw_error)
        raw_blocked = int(blocked.get(key) or entry.get("blocked_until") or 0)
        if raw_blocked > now:
            blocked_until = max(blocked_until or 0, raw_blocked)

    return total_today, last_error, blocked_until


def _provider_status(configured: bool, safe_error: str, blocked_until: int | None, provider: str) -> str:
    if provider == "ollama" and safe_error == "local server unreachable":
        return "local_server_unreachable"
    if not configured:
        return "missing_key" if provider != "ollama" else "unknown"
    if blocked_until and "timeout" in safe_error.lower():
        # Phase 123: Phase 121 skips a model that timed out for a few minutes.
        # That is not a quota, and "wait for quota/reset" sent people the wrong way.
        return "cooling_down"
    if blocked_until:
        return "quota_blocked"
    if safe_error in {"none", ""}:
        return "ready"
    if safe_error == "missing key":
        return "missing_key"
    if safe_error == "auth failed / key invalid":
        return "auth_failed"
    if safe_error in {"quota/rate limit", "quota exceeded", "local soft limit exhausted"}:
        return "quota_blocked"
    if safe_error == "model unavailable":
        return "model_unavailable"
    if safe_error == "local server unreachable":
        return "local_server_unreachable"
    return "degraded"


def get_provider_health(settings: ModelSettings | None = None) -> dict[str, dict[str, Any]]:
    status = get_llm_status(settings)
    models = status.get("models") if isinstance(status.get("models"), dict) else {}
    keys = status.get("configured_keys") if isinstance(status.get("configured_keys"), dict) else {}
    health: dict[str, dict[str, Any]] = {}

    for provider in DEFAULT_PROVIDER_ORDER:
        model = str(models.get(provider) or "")
        configured = provider == "ollama" or bool(keys.get(provider))
        requests_today, safe_error, blocked_until = _usage_for_provider(status, provider, model)
        safe_error = safe_error or "none"
        current_status = _provider_status(configured, safe_error, blocked_until, provider)
        rpm, rpd = (None, None) if provider == "ollama" else provider_limits(provider, model)
        tpm, tpd = (None, None) if provider == "ollama" else provider_token_limits(provider, model)
        if provider == "nvidia_nim":
            nim = status.get("nvidia_nim") if isinstance(status.get("nvidia_nim"), dict) else {}
            model = str(nim.get("primary_model") or model)
        health[provider] = {
            "provider": provider,
            "label": PROVIDER_LABELS.get(provider, provider),
            "configured": configured,
            "model": model,
            "status": current_status,
            "requests_today": requests_today,
            "safe_error": safe_error,
            "blocked_until": blocked_until,
            "can_use": configured and current_status in {"ready", "degraded"} and not blocked_until,
            "soft_rpm": rpm,
            "soft_rpd": rpd,
            "soft_tpm": tpm,
            "soft_tpd": tpd,
            "suggested_fix": _suggest_provider_fix(provider, configured, current_status, safe_error),
        }
    return health


def _suggest_provider_fix(provider: str, configured: bool, status: str, safe_error: str) -> str:
    label = PROVIDER_LABELS.get(provider, provider)
    if provider == "ollama" and status == "local_server_unreachable":
        return "Start Ollama locally or switch to a configured cloud provider."
    if not configured and provider != "ollama":
        return f"Add {label} key in local env or leave Eva on auto fallback."
    if status == "cooling_down":
        return f"Nothing to do: {label} stopped answering, so NOVA is skipping it for a few minutes and using the next provider, then will try it again."
    if status == "quota_blocked":
        return f"Wait for {label} quota/reset or use the next fallback provider."
    if status == "auth_failed":
        return f"Replace the {label} key; it looks invalid or unauthorized."
    if status == "model_unavailable":
        return f"Switch {label} to an available model."
    if safe_error not in {"", "none"}:
        return f"Keep auto fallback on; {label} is degraded right now."
    return "No action needed."


def format_provider_health(provider: str | None, settings: ModelSettings | None = None) -> str:
    provider_key = provider_from_alias(provider) or "openrouter"
    health = get_provider_health(settings)
    item = health.get(provider_key)
    if not item:
        return "I do not recognize that provider yet."
    lines = [
        f"{item['label']} provider diagnostics:",
    ]
    if provider_key == "openrouter":
        lines.append("- Note: OpenRouter here means Eva's LLM provider, not a maps/navigation service.")
    lines.extend(
        [
            f"- Configured: {'yes' if item['configured'] else 'no'}",
            f"- Model: {item['model'] or 'not configured'}",
            f"- Status: {item['status']}",
            f"- Requests today: {item['requests_today']}",
            f"- Safe error: {item['safe_error']}",
            f"- Can use now: {'yes' if item['can_use'] else 'no'}",
        ]
    )
    if item.get("blocked_until"):
        lines.append(f"- Blocked until: {item['blocked_until']}")
    lines.append(f"- Suggested fix: {item['suggested_fix']}")
    return "\n".join(lines)


def _manual_mode_warning(health: dict[str, dict[str, Any]]) -> str | None:
    mode = llm_mode()
    if mode in {"auto", "qwen", "llama", "local"}:
        return None
    item = health.get(mode)
    if item and not item.get("configured"):
        return f"{item['label']} is selected but not configured, so Eva will use auto fallback."
    if item and item.get("blocked_until"):
        return f"{item['label']} is selected but locally blocked, so Eva will use auto fallback."
    return None


def format_llm_status(settings: ModelSettings | None = None, *, raw: bool = False) -> str:
    status = get_llm_status(settings)
    if raw:
        return json.dumps(status, indent=2, ensure_ascii=False)
    health = get_provider_health(settings)
    warning = _manual_mode_warning(health)
    rows = []
    for provider in DEFAULT_PROVIDER_ORDER:
        item = health.get(provider, {})
        rows.append(
            " | ".join(
                [
                    str(item.get("label") or provider),
                    "yes" if item.get("configured") else "no",
                    str(item.get("model") or "-"),
                    str(item.get("status") or "unknown"),
                    str(item.get("requests_today") or 0),
                    str(item.get("safe_error") or "none"),
                ]
            )
        )
    ready = [item["label"] for item in health.values() if item.get("status") == "ready"]
    degraded = [item["label"] for item in health.values() if item.get("status") in {"degraded", "quota_blocked", "cooling_down", "model_unavailable", "auth_failed"}]
    unavailable = [item["label"] for item in health.values() if item.get("status") in {"missing_key", "local_server_unreachable", "unavailable"}]
    lines = [
        "LLM status:",
        f"Active mode: {status.get('active_mode')}",
        f"Effective provider order: {', '.join(provider_order())}",
    ]
    if warning:
        lines.append(f"Warning: {warning}")
    lines.extend(
        [
            "",
            "provider | configured | model | status | requests today | safe error",
            *rows,
            "",
            "Ready providers: " + (", ".join(ready) if ready else "none"),
            "Degraded providers: " + (", ".join(degraded) if degraded else "none"),
            "Unavailable providers: " + (", ".join(unavailable) if unavailable else "none"),
            "Suggested next action: keep auto brain on unless you are testing one provider intentionally.",
            "Say `llm status raw` if you want the debug JSON.",
        ]
    )
    return "\n".join(lines)
