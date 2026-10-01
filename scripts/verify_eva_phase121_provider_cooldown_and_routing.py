"""Standalone verifier for Phase 121 (found by prompting NOVA through its chat UI).

1. "what time is it" took 49s: the primary NIM model (nemotron-3.5-lightning)
   was timing out and every request waited for it before falling back. Measured:
   lightning 32.6s / timeout at 40s, nemotron-3-super-120b 1.5s with tool calls.
   Super is now the default; a model that times out is skipped for a cooldown;
   an unreachable NIM endpoint is not retried with the next model.
2. "open calculator and tell me the result of 9 times 9" answered "Which one do
   you want me to open: Python (programming language) - Wikipedia, ..." -- the
   open-a-search-result shortcut matched substrings ("one" in "done", any
   "result"). Whole words now, and a message with a second request declines.
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
failures = 0


def emit(case: str, ok: bool, **extra: object) -> int:
    payload = {"case": case, "pass": bool(ok)}
    payload.update(extra)
    print(json.dumps(payload, indent=2, default=str))
    return 0 if ok else 1


try:
    import backend.eva.llm.router as router
    from backend.eva.core.web_context import wants_previous_result
    from backend.eva.llm.providers import nvidia_nim
    from backend.eva.llm.rate_limiter import LLMRateLimiter
    from backend.eva.llm.types import LLMResponse, Message

    failures += emit(
        "the default NIM model is the one measured to answer",
        nvidia_nim.DEFAULT_NIM_MODEL == "nvidia/nemotron-3-super-120b-a12b",
        default=nvidia_nim.DEFAULT_NIM_MODEL,
    )

    class Fake:
        name = "nvidia_nim"
        model = "fake/slow"
        request_timeout = 12

        def __init__(self, response):
            self.response = response

        async def complete(self, messages, temperature, max_tokens, tools=None):
            return self.response

    with tempfile.TemporaryDirectory() as tmp:
        limiter = LLMRateLimiter(path=Path(tmp) / "usage.json")
        timeout = LLMResponse(provider="nvidia_nim", model="fake/slow", ok=False, error="ReadTimeout: no response within 12s")
        asyncio.run(router._call_provider(Fake(timeout), limiter, [Message(role="user", content="hi")], purpose="chat", temperature=0.2, max_tokens=20))
        allowed, reason = limiter.can_call("nvidia_nim", "fake/slow")
        failures += emit("a timed-out model is skipped for the cooldown", allowed is False, reason=reason)

    failures += emit(
        "open-a-result needs whole words and a single request",
        wants_previous_result("open the second one")
        and not wants_previous_result("open calculator and tell me the result of 9 times 9")
        and not wants_previous_result("open the phone app"),
    )

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    failures += emit("README records Phase 121", "| 121 |" in readme)
except Exception as exc:  # pragma: no cover
    failures += emit("checks ran", False, error=f"{type(exc).__name__}: {exc}")

print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
raise SystemExit(0 if failures == 0 else 1)
