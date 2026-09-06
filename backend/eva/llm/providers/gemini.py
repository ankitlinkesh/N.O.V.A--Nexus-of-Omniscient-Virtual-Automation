from __future__ import annotations

import copy
import json
import os
import re
from typing import Any

import httpx

from ...core.config import ModelSettings
from ..rate_limiter import LLMRateLimiter
from ._openai_compatible import CONNECT_TIMEOUT, DEFAULT_REQUEST_TIMEOUT, describe_transport_error
from ..types import LLMResponse, Message, headers_to_dict, retry_after_from_headers


class GeminiProvider:
    name = "gemini"
    uses_internal_rate_limits = True

    def __init__(self, settings: ModelSettings) -> None:
        self.settings = settings
        self.api_keys = self._load_api_keys()
        self.model = os.environ.get("GEMINI_MODEL", settings.smart_model or "gemini-2.5-flash").strip() or "gemini-2.5-flash"

    def available(self) -> bool:
        return bool(self.api_keys)

    async def complete(
        self,
        messages: list[Message],
        temperature: float = 0.2,
        max_tokens: int = 800,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        if not self.available():
            return LLMResponse(provider=self.name, model=self.model, ok=False, error="missing_api_key")

        system_text, contents = self._gemini_contents(messages)
        payload = {
            "systemInstruction": {"parts": [{"text": system_text}]},
            "contents": contents,
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens, "topP": 0.9},
        }
        if tools:
            gemini_tools = self._to_gemini_tools(tools)
            if gemini_tools:
                payload["tools"] = gemini_tools
                payload["toolConfig"] = {"functionCallingConfig": {"mode": "AUTO"}}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        limiter = LLMRateLimiter()
        estimated_tokens = self._estimated_tokens(messages, max_tokens)
        last_response: LLMResponse | None = None

        # Phase 104: the same flat 12s the OpenAI-compatible providers had.
        # Gemini is the FALLBACK for nvidia_nim, so a deep_reasoning request
        # that failed over to it would have been cut off here regardless of the
        # budget the purpose was granted -- the fix has to reach every provider
        # a purpose can land on, not just the one it starts at.
        timeout = float(getattr(self, "request_timeout", DEFAULT_REQUEST_TIMEOUT) or DEFAULT_REQUEST_TIMEOUT)
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=CONNECT_TIMEOUT)) as client:
            for index, api_key in enumerate(self.api_keys, start=1):
                slot_model = self._slot_model(index)
                allowed, reason = limiter.can_call(self.name, slot_model, estimated_tokens=estimated_tokens)
                if not allowed:
                    last_response = LLMResponse(provider=self.name, model=slot_model, ok=False, error=reason)
                    continue

                headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
                try:
                    response = await client.post(url, headers=headers, json=payload)
                except httpx.HTTPError as exc:
                    # `str(httpx.ReadTimeout(...))` is the EMPTY STRING, so this
                    # reported a failure with no reason AND wrote that blank into
                    # the rate limiter's persisted failure record.
                    reason = describe_transport_error(exc, timeout)
                    last_response = LLMResponse(provider=self.name, model=slot_model, ok=False, error=reason)
                    limiter.record_failure(self.name, reason, model=slot_model, estimated_tokens=estimated_tokens)
                    continue

                raw_headers = headers_to_dict(response.headers)
                if response.status_code >= 400:
                    retry_after = retry_after_from_headers(raw_headers)
                    last_response = LLMResponse(
                        provider=self.name,
                        model=slot_model,
                        ok=False,
                        error=response.text[:500],
                        status_code=response.status_code,
                        rate_limited=response.status_code == 429,
                        retry_after_seconds=retry_after,
                        raw_headers=self._safe_headers(raw_headers),
                    )
                    limiter.record_failure(
                        self.name,
                        response.text[:500],
                        model=slot_model,
                        rate_limited=response.status_code == 429,
                        retry_after_seconds=retry_after,
                        estimated_tokens=estimated_tokens,
                    )
                    if response.status_code in {401, 403, 429} or response.status_code >= 500:
                        continue
                    return last_response

                data = response.json()
                text = self._extract_text(data)
                tool_calls = self._extract_tool_calls(data) if tools else None
                if text or tool_calls:
                    limiter.record_success(self.name, slot_model, estimated_tokens=estimated_tokens)
                    return LLMResponse(
                        provider=self.name,
                        model=slot_model,
                        text=text,
                        ok=True,
                        status_code=response.status_code,
                        raw_headers=self._safe_headers(raw_headers),
                        tool_calls=tool_calls,
                    )

                last_response = LLMResponse(
                    provider=self.name,
                    model=slot_model,
                    ok=False,
                    error="empty_response",
                    status_code=response.status_code,
                    raw_headers=self._safe_headers(raw_headers),
                )
                limiter.record_failure(self.name, "empty_response", model=slot_model, estimated_tokens=estimated_tokens)

        return last_response or LLMResponse(provider=self.name, model=self.model, ok=False, error="no_gemini_key_available")

    def _load_api_keys(self) -> list[str]:
        raw_values = [os.environ.get("GEMINI_API_KEY", "")]
        numbered_keys: list[tuple[int, str]] = []
        for name, value in os.environ.items():
            match = re.fullmatch(r"GEMINI_API_KEY_(\d+)", name)
            if match:
                numbered_keys.append((int(match.group(1)), value))
        raw_values.extend(value for _, value in sorted(numbered_keys))
        raw_values.append(os.environ.get("GEMINI_API_KEYS", ""))
        keys: list[str] = []
        for raw in raw_values:
            for token in re.findall(r"AIza[0-9A-Za-z_-]{35}", raw or ""):
                if token not in keys:
                    keys.append(token)
        return keys

    def _slot_model(self, index: int) -> str:
        return f"{self.model}[key{index}]"

    def _estimated_tokens(self, messages: list[Message], max_tokens: int) -> int:
        chars = sum(len(str(item.get("content", ""))) for item in messages)
        return max(1, chars // 4 + max_tokens)

    def _gemini_contents(self, messages: list[Message]) -> tuple[str, list[dict]]:
        system_parts = [m.get("content", "") for m in messages if m.get("role") == "system" and m.get("content")]
        system_text = "\n".join(system_parts) or "You are Eva."
        contents = []
        for item in messages:
            role = item.get("role", "user")
            if role == "system":
                continue
            text = str(item.get("content", "")).strip()
            if text:
                contents.append({"role": "model" if role == "assistant" else "user", "parts": [{"text": text}]})
        if not contents:
            contents.append({"role": "user", "parts": [{"text": "Hello"}]})
        return system_text, contents

    def _extract_text(self, data: dict) -> str:
        parts = []
        for candidate in data.get("candidates", []) or []:
            content = candidate.get("content", {}) or {}
            for part in content.get("parts", []) or []:
                if part.get("text"):
                    parts.append(part["text"])
        return "".join(parts).strip()

    def _to_gemini_tools(self, openai_tools: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
        decls: list[dict[str, Any]] = []
        for tool in openai_tools or []:
            fn = tool.get("function", {}) or {}
            name = fn.get("name")
            if not name:
                continue
            decl: dict[str, Any] = {"name": name, "description": fn.get("description", "")}
            params = self._sanitize_gemini_schema(fn.get("parameters") or {})
            if params and params.get("properties"):
                decl["parameters"] = params
            decls.append(decl)
        if not decls:
            return None
        return [{"function_declarations": decls}]

    def _sanitize_gemini_schema(self, schema: Any) -> Any:
        if not isinstance(schema, dict):
            return schema
        unsupported = {"additionalProperties", "$schema", "title", "default", "examples"}
        result = copy.deepcopy(schema)
        for key in unsupported:
            result.pop(key, None)
        if "required" in result and not result["required"]:
            result.pop("required", None)
        if "properties" in result and isinstance(result["properties"], dict):
            result["properties"] = {
                key: self._sanitize_gemini_schema(value) for key, value in result["properties"].items()
            }
        if "items" in result:
            result["items"] = self._sanitize_gemini_schema(result["items"])
        return result

    def _extract_tool_calls(self, data: dict) -> list[dict[str, Any]] | None:
        calls: list[dict[str, Any]] = []
        for candidate in data.get("candidates", []) or []:
            content = candidate.get("content", {}) or {}
            for part in content.get("parts", []) or []:
                fc = part.get("functionCall")
                if not fc:
                    continue
                calls.append(
                    {
                        "id": f"call_{len(calls)}",
                        "type": "function",
                        "function": {
                            "name": fc.get("name", ""),
                            "arguments": json.dumps(fc.get("args") or {}),
                        },
                    }
                )
        return calls or None

    def _safe_headers(self, headers: dict[str, str]) -> dict[str, str]:
        keep = {"retry-after", "x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset", "x-ratelimit-reset-after"}
        return {k: v for k, v in headers.items() if k in keep}
