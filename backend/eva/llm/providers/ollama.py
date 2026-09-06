from __future__ import annotations

import os
from typing import Any

from ...core.config import ModelSettings
from ...models.ollama import OllamaClient
from ._openai_compatible import describe_transport_error
from ..types import LLMResponse, Message


class OllamaProvider:
    name = "ollama"

    def __init__(self, settings: ModelSettings) -> None:
        self.settings = settings
        mode = os.environ.get("EVA_LLM_MODE", "auto").strip().lower()
        if mode == "qwen":
            self.model = os.environ.get("EVA_OLLAMA_QWEN_MODEL", "").strip() or settings.fast_model or "qwen2.5:1.5b"
        elif mode == "llama":
            self.model = os.environ.get("EVA_OLLAMA_LLAMA_MODEL", "").strip() or "llama3.1:8b"
        else:
            self.model = os.environ.get("EVA_OLLAMA_FALLBACK_MODEL", "").strip() or settings.fast_model or settings.ollama_model

    def available(self) -> bool:
        return True

    async def complete(
        self,
        messages: list[Message],
        temperature: float = 0.2,
        max_tokens: int = 800,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        # tools: native function-calling not yet wired for this provider
        user = "\n".join(item.get("content", "") for item in messages if item.get("role") == "user").strip() or "Hello"
        history = [item for item in messages if item.get("role") in {"user", "assistant"}][:-1]
        try:
            text = await OllamaClient(self.settings).chat(user, history=history, model=self.model)
        except RuntimeError as exc:
            # `str(RuntimeError())` is empty too, and a failure with no reason is
            # not a diagnosis -- the class name is worth more than nothing.
            return LLMResponse(
                provider=self.name, model=self.model, ok=False, error=describe_transport_error(exc, 0.0)
            )
        return LLMResponse(provider=self.name, model=self.model, text=text, ok=bool(text), error=None if text else "empty_response")
