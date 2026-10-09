from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.eva.core.config import ModelSettings, load_local_env
from backend.eva.llm import router as llm_router
from backend.eva.llm.rate_limiter import LLMRateLimiter, _day_bucket, _minute_bucket, provider_limits, provider_token_limits
from backend.eva.llm.types import LLMResponse


class FakeProvider:
    name = "fake"
    model = "fake-model"
    available_value = True
    response = LLMResponse(provider="fake", model="fake-model", text='{"type":"answer","final_response":"ok","tool_calls":[],"reason":"ok"}', ok=True)
    calls: list[str] = []

    def __init__(self, settings: ModelSettings) -> None:
        self.settings = settings

    def available(self) -> bool:
        return self.available_value

    async def complete(self, messages, temperature=0.2, max_tokens=800, tools=None):
        type(self).calls.append(f"{self.name}:{self.model}")
        response = self.response
        return LLMResponse(
            provider=self.name,
            model=self.model,
            text=response.text,
            ok=response.ok,
            error=response.error,
            status_code=response.status_code,
            rate_limited=response.rate_limited,
            retry_after_seconds=response.retry_after_seconds,
            raw_headers=response.raw_headers,
        )


class FakeGemini(FakeProvider):
    name = "gemini"
    model = "gemini-2.5-flash"
    calls: list[str] = []


class FakeGroq(FakeProvider):
    name = "groq"
    model = "llama-3.3-70b-versatile"
    calls: list[str] = []


class FakeGroqFallback(FakeProvider):
    name = "groq"
    model = "llama-3.1-8b-instant"
    calls: list[str] = []


class FakeOpenRouter(FakeProvider):
    name = "openrouter"
    model = "deepseek/deepseek-chat-v3-0324:free"
    calls: list[str] = []


class FakeClod(FakeProvider):
    name = "clod"
    model = "DeepSeek V3"
    calls: list[str] = []


class FakeOllama(FakeProvider):
    name = "ollama"
    model = "qwen2.5:1.5b"
    calls: list[str] = []


FAKES = [FakeGemini, FakeGroq, FakeGroqFallback, FakeOpenRouter, FakeClod, FakeOllama]


@contextmanager
def temporary_env(updates: dict[str, str | None]):
    previous = {key: os.environ.get(key) for key in updates}
    try:
        for key, value in updates.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def reset_fakes() -> None:
    for cls in FAKES:
        cls.calls = []
        cls.available_value = True
        cls.response = LLMResponse(
            provider=cls.name,
            model=cls.model,
            text='{"type":"answer","final_response":"ok","tool_calls":[],"reason":"ok"}',
            ok=True,
        )


def state_entry(provider: str, model: str, **updates: Any) -> dict[str, Any]:
    entry = {
        "provider": provider,
        "model": model,
        "requests_this_minute": 0,
        "requests_today": 0,
        "estimated_tokens_this_minute": 0,
        "estimated_tokens_today": 0,
        "last_reset_minute": _minute_bucket(),
        "last_reset_day": _day_bucket(),
        "blocked_until": 0,
        "last_error": None,
    }
    entry.update(updates)
    return entry


def compact_attempts(attempts) -> list[dict[str, Any]]:
    return [
        {
            "provider": item.provider,
            "model": item.model,
            "ok": item.ok,
            "error": item.error,
            "status_code": item.status_code,
            "rate_limited": item.rate_limited,
            "selected_provider": item.selected_provider,
        }
        for item in attempts
    ]


async def with_fake_router(state: dict[str, Any], order: str = "gemini,groq,openrouter,clod"):
    temp_dir = tempfile.TemporaryDirectory()
    limiter = LLMRateLimiter(Path(temp_dir.name) / "llm_usage_state.json")
    limiter.save(state)

    original_limiter = llm_router.LLMRateLimiter
    original_classes = llm_router.PROVIDER_CLASSES.copy()
    original_groq_emergency = llm_router.GroqEmergencyProvider
    old_order = os.environ.get("EVA_CLOUD_PROVIDER_ORDER")
    old_allow = os.environ.get("EVA_ALLOW_CLOUD_FALLBACK")
    os.environ["EVA_CLOUD_PROVIDER_ORDER"] = order
    os.environ["EVA_ALLOW_CLOUD_FALLBACK"] = "true"
    llm_router.LLMRateLimiter = lambda: limiter
    llm_router.PROVIDER_CLASSES = {
        "gemini": FakeGemini,
        "groq": FakeGroq,
        "openrouter": FakeOpenRouter,
        "clod": FakeClod,
        "ollama": FakeOllama,
    }
    llm_router.GroqEmergencyProvider = FakeGroqFallback
    try:
        routed = await llm_router.complete_with_fallback(
            [{"role": "user", "content": "open chrome"}],
            ModelSettings(),
            purpose="planner",
            temperature=0.1,
            max_tokens=100,
        )
        return routed, limiter.status()
    finally:
        llm_router.LLMRateLimiter = original_limiter
        llm_router.PROVIDER_CLASSES = original_classes
        llm_router.GroqEmergencyProvider = original_groq_emergency
        if old_order is None:
            os.environ.pop("EVA_CLOUD_PROVIDER_ORDER", None)
        else:
            os.environ["EVA_CLOUD_PROVIDER_ORDER"] = old_order
        if old_allow is None:
            os.environ.pop("EVA_ALLOW_CLOUD_FALLBACK", None)
        else:
            os.environ["EVA_ALLOW_CLOUD_FALLBACK"] = old_allow
        temp_dir.cleanup()


def print_case(name: str, passed: bool, payload: dict[str, Any]) -> None:
    payload = {"case": name, "pass": passed, **payload}
    print(json.dumps(payload, indent=2))


async def main() -> int:
    load_local_env(ROOT / ".env")
    failures = 0
    gemini_env_keys = {
        "GEMINI_SOFT_RPM": None,
        "GEMINI_SOFT_TPM": None,
        "GEMINI_SOFT_RPD": None,
    }

    with temporary_env(gemini_env_keys):
        gemini_rpm, gemini_rpd = provider_limits("gemini", FakeGemini.model)
        gemini_tpm, gemini_tpd = provider_token_limits("gemini", FakeGemini.model)
    # b1af2c2 replaced the flat 4 RPM / 18 per day cap with Google's real per-model
    # free tier (gemini-2.5-flash: 10 RPM, 250 per day).
    passed = gemini_rpm == 10 and gemini_tpm == 200000 and gemini_rpd == 250 and gemini_tpd is None
    failures += 0 if passed else 1
    print_case(
        "gemini_default_caps_match_dashboard",
        passed,
        {"rpm": gemini_rpm, "tpm": gemini_tpm, "rpd": gemini_rpd, "tpd": gemini_tpd},
    )

    with temporary_env({"GEMINI_SOFT_RPM": "3", "GEMINI_SOFT_TPM": "12345", "GEMINI_SOFT_RPD": "7"}):
        override_rpm, override_rpd = provider_limits("gemini", FakeGemini.model)
        override_tpm, override_tpd = provider_token_limits("gemini", FakeGemini.model)
    passed = override_rpm == 3 and override_tpm == 12345 and override_rpd == 7 and override_tpd is None
    failures += 0 if passed else 1
    print_case(
        "gemini_env_override_wins",
        passed,
        {"rpm": override_rpm, "tpm": override_tpm, "rpd": override_rpd, "tpd": override_tpd},
    )

    reset_fakes()
    future = int(time.time()) + 600
    routed, state = await with_fake_router({"gemini:gemini-2.5-flash": state_entry("gemini", "gemini-2.5-flash", blocked_until=future)})
    attempts = compact_attempts(routed.attempts)
    passed = attempts[0]["provider"] == "gemini" and str(attempts[0]["error"]).startswith("blocked_until:") and not FakeGemini.calls and routed.response.provider != "gemini"
    failures += 0 if passed else 1
    print_case("gemini_blocked_until_skipped", passed, {"attempts": attempts, "calls": {"gemini": FakeGemini.calls}, "selected_provider": routed.response.provider})

    reset_fakes()
    with temporary_env(gemini_env_keys):
        gemini_rpm, _ = provider_limits("gemini", FakeGemini.model)
        routed, state = await with_fake_router(
            {"gemini:gemini-2.5-flash": state_entry("gemini", "gemini-2.5-flash", requests_this_minute=gemini_rpm)},
            order="gemini,groq",
        )
    attempts = compact_attempts(routed.attempts)
    passed = attempts[0]["provider"] == "gemini" and attempts[0]["error"] == "soft_limit_exhausted" and not FakeGemini.calls and routed.response.provider != "gemini"
    failures += 0 if passed else 1
    print_case("gemini_rpm_cap_skipped_before_call", passed, {"attempts": attempts, "calls": {"gemini": FakeGemini.calls}, "selected_provider": routed.response.provider})

    reset_fakes()
    _, openrouter_rpd = provider_limits("openrouter", FakeOpenRouter.model)
    routed, state = await with_fake_router({"openrouter:deepseek/deepseek-chat-v3-0324:free": state_entry("openrouter", FakeOpenRouter.model, requests_today=openrouter_rpd)}, order="openrouter,clod")
    attempts = compact_attempts(routed.attempts)
    passed = attempts[0]["provider"] == "openrouter" and attempts[0]["error"] == "soft_limit_exhausted" and not FakeOpenRouter.calls
    failures += 0 if passed else 1
    print_case("openrouter_daily_cap_skipped", passed, {"attempts": attempts, "calls": {"openrouter": FakeOpenRouter.calls}, "selected_provider": routed.response.provider})

    reset_fakes()
    _, clod_rpd = provider_limits("clod", FakeClod.model)
    routed, state = await with_fake_router({"clod:DeepSeek V3": state_entry("clod", FakeClod.model, requests_today=clod_rpd)}, order="clod,ollama")
    attempts = compact_attempts(routed.attempts)
    passed = attempts[0]["provider"] == "clod" and attempts[0]["error"] == "soft_limit_exhausted" and not FakeClod.calls
    failures += 0 if passed else 1
    print_case("clod_daily_cap_skipped", passed, {"attempts": attempts, "calls": {"clod": FakeClod.calls}, "selected_provider": routed.response.provider})

    reset_fakes()
    FakeGroq.response = LLMResponse(provider="groq", model=FakeGroq.model, ok=False, error="rate limit", status_code=429, rate_limited=True, retry_after_seconds=77)
    routed, state = await with_fake_router({}, order="groq,openrouter")
    attempts = compact_attempts(routed.attempts)
    groq_state = state.get("groq:llama-3.3-70b-versatile", {})
    passed = attempts[0]["error"] == "rate_limited_429" and int(groq_state.get("blocked_until") or 0) > int(time.time()) and routed.response.provider in {"groq", "openrouter"}
    failures += 0 if passed else 1
    print_case("groq_429_blocks_and_falls_back", passed, {"attempts": attempts, "groq_blocked_until": groq_state.get("blocked_until"), "selected_provider": routed.response.provider})

    reset_fakes()
    state_seed = {
        "groq:llama-3.3-70b-versatile": state_entry("groq", "llama-3.3-70b-versatile", requests_today=5),
        "groq:llama-3.1-8b-instant": state_entry("groq", "llama-3.1-8b-instant", requests_today=9),
    }
    limiter = LLMRateLimiter(Path(tempfile.mkdtemp()) / "llm_usage_state.json")
    limiter.save(state_seed)
    status = limiter.status()
    passed = status["groq:llama-3.3-70b-versatile"]["requests_today"] == 5 and status["groq:llama-3.1-8b-instant"]["requests_today"] == 9
    failures += 0 if passed else 1
    print_case("provider_model_counters_separate", passed, {"groq_primary": status.get("groq:llama-3.3-70b-versatile"), "groq_fallback": status.get("groq:llama-3.1-8b-instant")})

    reset_fakes()
    for cls in [FakeGemini, FakeGroq, FakeOpenRouter, FakeClod]:
        cls.available_value = False
    routed, state = await with_fake_router({}, order="gemini,groq,openrouter,clod")
    attempts = compact_attempts(routed.attempts)
    passed = (
        (routed.response.provider == "ollama" and routed.response.ok and all(item["error"] == "missing_api_key" for item in attempts[:-1]))
        or (
            routed.response.provider == "none"
            and attempts[-1]["provider"] == "ollama"
            and attempts[-1]["error"] == "skipped_for_planner"
            and all(item["error"] == "missing_api_key" for item in attempts[:-1])
        )
    )
    failures += 0 if passed else 1
    print_case("missing_keys_fall_through", passed, {"attempts": attempts, "selected_provider": routed.response.provider})

    from backend.eva.agent.planner import ToolCallPlanner
    from backend.eva.tools.registry import ToolRegistry

    old_allow = os.environ.get("EVA_ALLOW_CLOUD_FALLBACK")
    os.environ["EVA_ALLOW_CLOUD_FALLBACK"] = "false"
    decision = await ToolCallPlanner(ModelSettings(), ToolRegistry()).plan("open chrome", [])
    if old_allow is None:
        os.environ.pop("EVA_ALLOW_CLOUD_FALLBACK", None)
    else:
        os.environ["EVA_ALLOW_CLOUD_FALLBACK"] = old_allow
    passed = decision.type == "tool_calls" and decision.tool_calls and decision.tool_calls[0].tool == "open_app"
    failures += 0 if passed else 1
    print_case("safe_local_planner_open_chrome", passed, {"decision": {"type": decision.type, "tool_calls": [{"tool": call.tool, "args": call.args} for call in decision.tool_calls]}})

    print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
