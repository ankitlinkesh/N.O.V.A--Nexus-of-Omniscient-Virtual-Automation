"""Standalone verifier for Phase 123 (second round of prompting the chat UI).

1. "latest news about NVIDIA" returned NIM provider diagnostics ("test" in "latest").
2. "open github.com/anthropics and tell me ..." opened a URL that ran on through the
   rest of the sentence.
3. "open github.com/anthropics" answered "no previous search results".
4. A timeout cooldown was reported as "quota_blocked".
5. Free disk space was refused; system_status now reports it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
failures = 0


def emit(case: str, ok: bool, **extra: object) -> int:
    payload = {"case": case, "pass": bool(ok)}
    payload.update(extra)
    print(json.dumps(payload, indent=2, default=str))
    return 0 if ok else 1


class Tools:
    def __init__(self):
        self.calls = []

    def run(self, name, **kwargs):
        self.calls.append((name, kwargs))
        return {"ok": True}


try:
    from backend.eva.core.fast_commands import maybe_handle_fast_command
    from backend.eva.core.intent_router import classify_capability_intent
    from backend.eva.diagnostics.providers import _provider_status

    news = classify_capability_intent("what's the latest news about NVIDIA today?").get("capability")
    failures += emit("news about NVIDIA is not a provider diagnostic", news != "provider_diagnostics", capability=news)

    tools = Tools()
    swallowed = maybe_handle_fast_command("open github.com/anthropics and tell me what repos are pinned", tools, {})
    failures += emit("an errand after a link reaches the agent", swallowed is None and not tools.calls)

    tools = Tools()
    maybe_handle_fast_command("open github.com/anthropics", tools, {})
    failures += emit("an explicit github address opens", ("open_url", {"url": "github.com/anthropics"}) in tools.calls)

    status = _provider_status(True, "ReadTimeout: no response within 12s", 9999999999, "nvidia_nim")
    failures += emit("a timeout cooldown is not called a quota", status == "cooling_down", status=status)

    if sys.platform == "win32":
        from backend.eva.tools.power_info import disk_space

        failures += emit("system_status can report free disk space", bool(disk_space()))

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    failures += emit("README records Phase 123", "| 123 |" in readme)
except Exception as exc:  # pragma: no cover
    failures += emit("checks ran", False, error=f"{type(exc).__name__}: {exc}")

print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
raise SystemExit(0 if failures == 0 else 1)
