from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

STATE_PATH = Path(__file__).resolve().parents[1] / "data" / "llm_usage_state.json"
DEFAULT_RPM = {
    # Fallback when a gemini model is not in GEMINI_MODEL_LIMITS below; the
    # per-model table is what actually governs gemini (see provider_limits).
    "gemini": 10,
    "groq": 30,
    "openrouter": 20,
    "nvidia_nim": 20,
    "clod": 10,
}
DEFAULT_RPD = {
    "gemini": 250,
    "groq": 1000,
    "openrouter": 50,
    "nvidia_nim": 300,
    "clod": 100,
}
DEFAULT_TPM = {
    "gemini": 200000,
}
GROQ_MODEL_LIMITS = {
    "llama-3.3-70b-versatile": {"rpm": 30, "rpd": 1000, "tpm": 12000, "tpd": 100000},
    "llama-3.1-8b-instant": {"rpm": 30, "rpd": 14400, "tpm": 6000, "tpd": 500000},
    "qwen/qwen3-32b": {"rpm": 60, "rpd": 1000, "tpm": 6000, "tpd": 500000},
}
# Google AI Studio FREE tier, PER API KEY. The router rate-limits each key's
# slot ("model[keyN]") independently, so N configured keys give roughly N x
# these. Phase 84: this replaced a flat 18-requests-per-DAY cap that throttled
# Gemini ~80x below its real free tier. Verify current numbers at
# https://ai.google.dev/gemini-api/docs/rate-limits -- Google adjusts them, and
# every value is env-overridable via GEMINI_SOFT_RPM / GEMINI_SOFT_RPD. Soft
# limits sit at/below the API's real ceiling: exceeding one only means the API
# returns 429 and the router rotates to the next key, so being slightly
# conservative is safe.
GEMINI_MODEL_LIMITS = {
    "gemini-2.5-pro": {"rpm": 5, "rpd": 100},
    "gemini-2.5-flash": {"rpm": 10, "rpd": 250},
    "gemini-2.5-flash-lite": {"rpm": 15, "rpd": 1000},
    "gemini-2.0-flash": {"rpm": 15, "rpd": 1500},
    "gemini-2.0-flash-lite": {"rpm": 30, "rpd": 1500},
    "gemini-1.5-flash": {"rpm": 15, "rpd": 1500},
}
_GEMINI_DEFAULT_LIMIT = {"rpm": 10, "rpd": 250}


def _now() -> int:
    return int(time.time())


def _minute_bucket() -> int:
    return _now() // 60


def _day_bucket() -> str:
    return time.strftime("%Y-%m-%d", time.localtime(_now()))


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _state_key(provider: str, model: str | None = None) -> str:
    clean_model = (model or "").strip()
    return f"{provider}:{clean_model}" if clean_model else provider


def _default_rpd(provider: str) -> int:
    if provider == "openrouter" and _env_bool("OPENROUTER_PAID_CREDITS"):
        return 1000
    if provider == "clod" and _env_bool("CLOD_HAS_CREDITS"):
        return 1000
    return DEFAULT_RPD.get(provider, 500)


def _groq_defaults(model: str | None) -> dict[str, int]:
    clean = (model or os.environ.get("GROQ_MODEL") or "llama-3.3-70b-versatile").strip()
    return GROQ_MODEL_LIMITS.get(clean, GROQ_MODEL_LIMITS["llama-3.3-70b-versatile"])


def _gemini_base_model(model: str | None) -> str:
    """The base Gemini model name, with the router's per-key ``[keyN]`` slot
    suffix stripped, so the per-model free-tier limit is looked up correctly for
    every key slot."""
    base = re.sub(r"\[key\d+\]$", "", str(model or "").strip())
    return base or (os.environ.get("GEMINI_MODEL", "").strip() or "gemini-2.5-flash")


def _gemini_defaults(model: str | None) -> dict[str, int]:
    return GEMINI_MODEL_LIMITS.get(_gemini_base_model(model), _GEMINI_DEFAULT_LIMIT)


def provider_limits(provider: str, model: str | None = None) -> tuple[int | None, int | None]:
    if provider == "ollama":
        return None, None
    if provider == "groq":
        defaults = _groq_defaults(model)
        return _env_int("GROQ_SOFT_RPM", defaults["rpm"]), _env_int("GROQ_SOFT_RPD", defaults["rpd"])
    if provider == "gemini":
        defaults = _gemini_defaults(model)
        return _env_int("GEMINI_SOFT_RPM", defaults["rpm"]), _env_int("GEMINI_SOFT_RPD", defaults["rpd"])
    prefix = provider.upper()
    return _env_int(f"{prefix}_SOFT_RPM", DEFAULT_RPM.get(provider, 20)), _env_int(f"{prefix}_SOFT_RPD", _default_rpd(provider))


def provider_token_limits(provider: str, model: str | None = None) -> tuple[int | None, int | None]:
    if provider == "gemini":
        return _env_int("GEMINI_SOFT_TPM", DEFAULT_TPM["gemini"]), None
    if provider != "groq":
        return None, None
    defaults = _groq_defaults(model)
    return _env_int("GROQ_SOFT_TPM", defaults["tpm"]), _env_int("GROQ_SOFT_TPD", defaults["tpd"])


class LLMRateLimiter:
    def __init__(self, path: Path = STATE_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            return {}

    def save(self, state: dict[str, Any]) -> None:
        tmp = self.path.with_name(f"{self.path.name}.{os.getpid()}.{uuid4().hex}.tmp")
        tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        for attempt in range(5):
            try:
                tmp.replace(self.path)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.05 * (attempt + 1))
        tmp.replace(self.path)

    def _entry(self, state: dict[str, Any], provider: str, model: str | None = None) -> dict[str, Any]:
        key = _state_key(provider, model)
        entry = state.setdefault(key, {})
        if not isinstance(entry, dict):
            entry = {}
            state[key] = entry
        entry["provider"] = provider
        if model:
            entry["model"] = model
        minute = _minute_bucket()
        day = _day_bucket()
        if entry.get("last_reset_minute") != minute:
            entry["last_reset_minute"] = minute
            entry["requests_this_minute"] = 0
            entry["estimated_tokens_this_minute"] = 0
        if entry.get("last_reset_day") != day:
            entry["last_reset_day"] = day
            entry["requests_today"] = 0
            entry["estimated_tokens_today"] = 0
        entry.setdefault("requests_this_minute", 0)
        entry.setdefault("requests_today", 0)
        entry.setdefault("estimated_tokens_this_minute", 0)
        entry.setdefault("estimated_tokens_today", 0)
        entry.setdefault("blocked_until", 0)
        entry.setdefault("last_error", None)
        return entry

    def can_call(self, provider: str, model: str | None = None, *, estimated_tokens: int = 0) -> tuple[bool, str | None]:
        if provider == "ollama":
            return True, None
        state = self.load()
        entry = self._entry(state, provider, model)
        rpm, rpd = provider_limits(provider, model)
        tpm, tpd = provider_token_limits(provider, model)
        now = _now()
        if int(entry.get("blocked_until") or 0) > now:
            self.save(state)
            return False, f"blocked_until:{entry['blocked_until']}"
        if rpm is not None and int(entry.get("requests_this_minute") or 0) >= rpm:
            self.save(state)
            return False, "soft_limit_exhausted:rpm"
        if rpd is not None and int(entry.get("requests_today") or 0) >= rpd:
            self.save(state)
            return False, "soft_limit_exhausted:rpd"
        if estimated_tokens > 0 and tpm is not None and int(entry.get("estimated_tokens_this_minute") or 0) + estimated_tokens > tpm:
            self.save(state)
            return False, "soft_limit_exhausted:tpm"
        if estimated_tokens > 0 and tpd is not None and int(entry.get("estimated_tokens_today") or 0) + estimated_tokens > tpd:
            self.save(state)
            return False, "soft_limit_exhausted:tpd"
        self.save(state)
        return True, None

    def _record_sent(self, entry: dict[str, Any], estimated_tokens: int = 0) -> None:
        entry["requests_this_minute"] = int(entry.get("requests_this_minute") or 0) + 1
        entry["requests_today"] = int(entry.get("requests_today") or 0) + 1
        if estimated_tokens > 0:
            entry["estimated_tokens_this_minute"] = int(entry.get("estimated_tokens_this_minute") or 0) + estimated_tokens
            entry["estimated_tokens_today"] = int(entry.get("estimated_tokens_today") or 0) + estimated_tokens

    def record_success(self, provider: str, model: str | None = None, *, estimated_tokens: int = 0) -> None:
        if provider == "ollama":
            return
        state = self.load()
        entry = self._entry(state, provider, model)
        self._record_sent(entry, estimated_tokens)
        entry["last_error"] = None
        self.save(state)

    def record_failure(
        self,
        provider: str,
        error: str,
        *,
        model: str | None = None,
        rate_limited: bool = False,
        retry_after_seconds: int | None = None,
        count_attempt: bool = True,
        estimated_tokens: int = 0,
        cooldown_seconds: int | None = None,
    ) -> None:
        if provider == "ollama":
            return
        state = self.load()
        entry = self._entry(state, provider, model)
        if count_attempt:
            self._record_sent(entry, estimated_tokens)
        entry["last_error"] = error[:500]
        if rate_limited:
            entry["blocked_until"] = _now() + int(retry_after_seconds or 60)
        elif cooldown_seconds:
            # Phase 121: a model that timed out is skipped for a while instead of
            # being waited on again by the very next request.
            entry["blocked_until"] = max(int(entry.get("blocked_until") or 0), _now() + int(cooldown_seconds))
        self.save(state)

    def status(self) -> dict[str, Any]:
        state = self.load()
        for key, entry in list(state.items()):
            if not isinstance(entry, dict):
                continue
            provider = str(entry.get("provider") or key.split(":", 1)[0])
            model = str(entry.get("model") or (key.split(":", 1)[1] if ":" in key else ""))
            self._entry(state, provider, model or None)
        self.save(state)
        return state
