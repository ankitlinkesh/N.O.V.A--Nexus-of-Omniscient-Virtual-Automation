from __future__ import annotations

import json
import os
from typing import Any

import httpx

from ...core.config import ModelSettings
from ..types import LLMResponse, Message, headers_to_dict, retry_after_from_headers


# Phase 104. Every provider call used a hardcoded 12-second read timeout, for
# every model and every purpose. `deepseek-v4-pro`, configured as the
# deep_reasoning model, answers correctly in **164 seconds** -- measured, HTTP
# 200, content "ok" -- so it could never once have been used. Not flaky, not
# rate-limited: impossible by a factor of fourteen. A reasoning model spends
# minutes thinking by design, which is what it is FOR, so a chat-shaped timeout
# is not a safety margin for it, it is a guarantee of failure.
#
# The default stays 12s: an interactive request must not hang for three minutes
# because a provider is slow. Only the purposes that exist to think get the long
# one, and the caller says which.
DEFAULT_REQUEST_TIMEOUT = float(os.environ.get("EVA_LLM_TIMEOUT_SECONDS", "12") or 12)
DEEP_REQUEST_TIMEOUT = float(os.environ.get("EVA_LLM_DEEP_TIMEOUT_SECONDS", "240") or 240)
CONNECT_TIMEOUT = 4.0

# The purposes whose whole point is to take a long time. Matches the role map in
# providers/nvidia_nim.py::nvidia_nim_models_for_purpose so a purpose that
# selects the deep model also gets the deep timeout -- the two must not drift,
# or a request would be routed to a model it is not allowed to wait for.
DEEP_PURPOSES = frozenset({"deep_reasoning", "debug"})


def timeout_for_purpose(purpose: str | None) -> float:
    return DEEP_REQUEST_TIMEOUT if str(purpose or "").strip().lower() in DEEP_PURPOSES else DEFAULT_REQUEST_TIMEOUT


def describe_transport_error(exc: Exception, timeout: float) -> str:
    """A failure with no reason is not a diagnosis.

    `str(httpx.ReadTimeout(...))` is the EMPTY STRING, and the handler passed it
    straight through -- so a timeout surfaced as `ok=False, status_code=None,
    error=""`, indistinguishable from a retired model, a network blip, a missing
    key or anything else. `llm probe` reported `nemotron-3.5-content-safety` as
    dead on exactly that evidence while the same code path answered in 0.6s, so
    the tool built to make provider rot visible was itself producing false
    negatives it could not explain.
    """
    detail = str(exc).strip()
    label = type(exc).__name__
    if isinstance(exc, httpx.TimeoutException):
        return f"{label}: no response within {timeout:g}s" + (f" ({detail})" if detail else "")
    return f"{label}: {detail}" if detail else label


class OpenAICompatibleProvider:
    name = "openai-compatible"
    api_key_env = ""
    model_env = ""
    default_model = ""
    base_url_env = ""
    default_base_url = ""
    auth_scheme = "Bearer"
    extra_headers: dict[str, str] = {}
    # Set per call by the router, which is the only place that knows the purpose.
    # An instance attribute rather than a `complete()` argument so every provider
    # inherits it without changing a signature five subclasses implement.
    request_timeout: float = DEFAULT_REQUEST_TIMEOUT

    def __init__(self, settings: ModelSettings) -> None:
        self.settings = settings
        self.api_key = os.environ.get(self.api_key_env, "").strip()
        self.model = os.environ.get(self.model_env, self.default_model).strip() or self.default_model
        self.base_url = os.environ.get(self.base_url_env, self.default_base_url).strip().rstrip("/") or self.default_base_url.rstrip("/")

    def available(self) -> bool:
        return bool(self.api_key)

    def extra_payload(self, tools: list[dict[str, Any]] | None) -> dict[str, Any]:
        """Provider-specific request fields. Empty for a generic backend.

        Takes `tools` because whether a request carries them can change what the
        model should be asked to do -- see NvidiaNIMProvider, where a reasoning
        model must keep thinking to plan a tool call but must not think when it
        is only writing a sentence.
        """
        return {}

    async def complete(
        self,
        messages: list[Message],
        temperature: float = 0.2,
        max_tokens: int = 800,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        if not self.available():
            return LLMResponse(provider=self.name, model=self.model, ok=False, error="missing_api_key")
        headers = {
            "Authorization": f"{self.auth_scheme} {self.api_key}",
            "Content-Type": "application/json",
            **self.extra_headers,
        }
        payload = {"model": self.model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        payload.update(self.extra_payload(tools))
        timeout = float(getattr(self, "request_timeout", DEFAULT_REQUEST_TIMEOUT) or DEFAULT_REQUEST_TIMEOUT)
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=CONNECT_TIMEOUT)) as client:
                response = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
        except httpx.HTTPError as exc:
            return LLMResponse(
                provider=self.name,
                model=self.model,
                ok=False,
                error=describe_transport_error(exc, timeout),
            )
        raw_headers = headers_to_dict(response.headers)
        if response.status_code >= 400:
            return LLMResponse(
                provider=self.name,
                model=self.model,
                ok=False,
                error=self._error_text(response),
                status_code=response.status_code,
                rate_limited=response.status_code == 429,
                retry_after_seconds=retry_after_from_headers(raw_headers),
                raw_headers=self._safe_headers(raw_headers),
            )
        try:
            data = response.json()
            message = data.get("choices", [{}])[0].get("message", {})
            text = str(message.get("content", "")).strip()
            raw_tool_calls = message.get("tool_calls")
        except Exception as exc:
            return LLMResponse(provider=self.name, model=self.model, ok=False, error=f"invalid_response:{exc}", status_code=response.status_code, raw_headers=self._safe_headers(raw_headers))
        normalized_tool_calls = list(raw_tool_calls) if raw_tool_calls else None
        ok = bool(text) or bool(normalized_tool_calls)
        return LLMResponse(
            provider=self.name,
            model=self.model,
            text=text,
            ok=ok,
            error=None if ok else "empty_response",
            status_code=response.status_code,
            raw_headers=self._safe_headers(raw_headers),
            tool_calls=normalized_tool_calls,
        )


    def _error_text(self, response: httpx.Response) -> str:
        try:
            data = response.json()
            error = data.get("error") if isinstance(data, dict) else None
            if isinstance(error, dict):
                safe = {key: error.get(key) for key in ("message", "type", "code", "status", "param") if error.get(key) is not None}
                return json.dumps({"error": safe}, ensure_ascii=False)[:500]
        except Exception:
            pass
        return response.text[:500]
    def _safe_headers(self, headers: dict[str, str]) -> dict[str, str]:
        keep = {
            "retry-after",
            "x-ratelimit-limit",
            "x-ratelimit-remaining",
            "x-ratelimit-reset",
            "x-ratelimit-reset-after",
            "x-ratelimit-limit-requests",
            "x-ratelimit-remaining-requests",
            "x-ratelimit-reset-requests",
            "x-ratelimit-limit-tokens",
            "x-ratelimit-remaining-tokens",
            "x-ratelimit-reset-tokens",
        }
        return {k: v for k, v in headers.items() if k in keep}

