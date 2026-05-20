from __future__ import annotations

import json
import os

import httpx

from ...core.config import ModelSettings
from ..types import LLMResponse, Message, headers_to_dict, retry_after_from_headers


class OpenAICompatibleProvider:
    name = "openai-compatible"
    api_key_env = ""
    model_env = ""
    default_model = ""
    base_url_env = ""
    default_base_url = ""
    auth_scheme = "Bearer"
    extra_headers: dict[str, str] = {}

    def __init__(self, settings: ModelSettings) -> None:
        self.settings = settings
        self.api_key = os.environ.get(self.api_key_env, "").strip()
        self.model = os.environ.get(self.model_env, self.default_model).strip() or self.default_model
        self.base_url = os.environ.get(self.base_url_env, self.default_base_url).strip().rstrip("/") or self.default_base_url.rstrip("/")

    def available(self) -> bool:
        return bool(self.api_key)

    async def complete(self, messages: list[Message], temperature: float = 0.2, max_tokens: int = 800) -> LLMResponse:
        if not self.available():
            return LLMResponse(provider=self.name, model=self.model, ok=False, error="missing_api_key")
        headers = {
            "Authorization": f"{self.auth_scheme} {self.api_key}",
            "Content-Type": "application/json",
            **self.extra_headers,
        }
        payload = {"model": self.model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(35.0, connect=5.0)) as client:
                response = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
        except httpx.HTTPError as exc:
            return LLMResponse(provider=self.name, model=self.model, ok=False, error=str(exc))
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
            text = str(data.get("choices", [{}])[0].get("message", {}).get("content", "")).strip()
        except Exception as exc:
            return LLMResponse(provider=self.name, model=self.model, ok=False, error=f"invalid_response:{exc}", status_code=response.status_code, raw_headers=self._safe_headers(raw_headers))
        return LLMResponse(provider=self.name, model=self.model, text=text, ok=bool(text), error=None if text else "empty_response", status_code=response.status_code, raw_headers=self._safe_headers(raw_headers))


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

