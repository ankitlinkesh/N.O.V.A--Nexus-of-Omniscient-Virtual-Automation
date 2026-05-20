from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

Message = dict[str, str]


@dataclass(frozen=True)
class LLMResponse:
    provider: str
    model: str
    text: str = ""
    ok: bool = False
    error: str | None = None
    status_code: int | None = None
    rate_limited: bool = False
    retry_after_seconds: int | None = None
    raw_headers: dict[str, str] | None = None


@dataclass(frozen=True)
class LLMAttempt:
    provider: str
    model: str
    purpose: str
    ok: bool
    error: str | None = None
    status_code: int | None = None
    rate_limited: bool = False
    fallback_used: bool = False
    selected_provider: str | None = None


@dataclass(frozen=True)
class RoutedLLMResponse:
    response: LLMResponse
    attempts: list[LLMAttempt] = field(default_factory=list)
    fallback_occurred: bool = False


class LLMProvider(Protocol):
    name: str
    model: str

    def available(self) -> bool:
        ...

    async def complete(self, messages: list[Message], temperature: float = 0.2, max_tokens: int = 800) -> LLMResponse:
        ...


def headers_to_dict(headers: Any) -> dict[str, str]:
    try:
        return {str(k).lower(): str(v) for k, v in dict(headers).items()}
    except Exception:
        return {}


def retry_after_from_headers(headers: dict[str, str]) -> int | None:
    value = headers.get("retry-after") or headers.get("x-ratelimit-reset-after")
    if not value:
        return None
    try:
        seconds = float(value)
        return max(1, min(3600, int(seconds)))
    except ValueError:
        pass
    try:
        from email.utils import parsedate_to_datetime
        import time

        parsed = parsedate_to_datetime(value)
        seconds = int(parsed.timestamp() - time.time())
        return max(1, min(3600, seconds))
    except Exception:
        return None

