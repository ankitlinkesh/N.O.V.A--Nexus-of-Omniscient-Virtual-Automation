from __future__ import annotations

from typing import Any

from ..core.config import ModelSettings
from .providers import format_provider_health, get_provider_health, provider_from_alias
from .subsystems import get_subsystem_health


def explain_workflows() -> str:
    return "\n".join(
        [
            "Eva's real workflows:",
            "",
            "1. Chat routing workflow: `frontend/app.js` sends chat to `backend/eva/api/routes.py`; the route checks deterministic safety/control commands, fast casual replies, contextual/operator commands, capability routing, agent/planner execution, then final response synthesis.",
            "2. Operator workflow: user command -> `backend/eva/core/operator_commands.py` parser -> `backend/eva/tools/registry.py` safe whitelist -> `backend/eva/agent/executor.py` -> desktop observation/verifier -> short result.",
            "3. Agentic workflow: goal -> `backend/eva/agent/planner.py` -> safe tool call via executor -> observation stored in `backend/eva/agent/state.py` -> reflection/cognition -> continue or stop under policy budgets.",
            "4. Browser workflow: browser command -> safe browser controller/search/open tools -> current page/title/URL/link extraction -> optional page summary -> optional research save.",
            "5. Research workflow: topic/query -> local SQLite recall first -> Tavily fresh search if needed -> save sources/notes/sessions -> summarize -> recall later from `backend/eva/research/`.",
            "6. LLM routing workflow: NVIDIA NIM -> Gemini -> OpenRouter -> Groq -> CLoD -> Ollama/local fallback. `backend/eva/llm/router.py` skips missing keys, local soft-cap exhaustion, and blocked providers before wasting calls.",
            "7. Code intelligence workflow: safe workspace/code index -> symbol search/project map -> traceback debugging -> patch planning. It reads only allowed files and does not edit in v1.",
            "8. Voice workflow: final assistant message -> speech cleanup in `frontend/app.js` -> stable selected voice from localStorage -> speak final answer only, not tool/activity/status spam.",
            "",
            "Safety limits: no arbitrary shell, no camera, no always-on screen watching, no secrets, and power actions require confirmation.",
        ]
    )


def _bucket_provider(item: dict[str, Any]) -> str:
    status = item.get("status")
    if status == "ready":
        return "working"
    if status in {"degraded", "quota_blocked", "cooling_down", "model_unavailable", "auth_failed"}:
        return "degraded"
    return "unavailable"


def get_eva_health_summary(settings: ModelSettings | None = None) -> dict[str, Any]:
    providers = get_provider_health(settings)
    subsystems = get_subsystem_health()
    working: list[str] = []
    degraded: list[str] = []
    unavailable: list[str] = []

    for item in providers.values():
        label = str(item.get("label") or item.get("provider"))
        status = str(item.get("status") or "unknown")
        safe_error = str(item.get("safe_error") or "none")
        text = f"{label}: {status}" + (f" ({safe_error})" if safe_error not in {"", "none"} else "")
        bucket = _bucket_provider(item)
        if bucket == "working":
            working.append(text)
        elif bucket == "degraded":
            degraded.append(text)
        else:
            unavailable.append(text)

    for name, item in subsystems.items():
        status = str(item.get("status") or "unknown")
        text = f"{name}: {status}"
        if status == "ready":
            working.append(text)
        elif status in {"degraded", "quota_blocked", "cooling_down", "model_unavailable", "auth_failed"}:
            degraded.append(text)
        else:
            unavailable.append(text)

    fixes = _suggest_fixes(providers, subsystems)
    text = "\n".join(
        [
            "Eva system health:",
            "",
            "Working:",
            *(f"- {item}" for item in working[:16]),
            "",
            "Degraded:",
            *(f"- {item}" for item in (degraded[:12] or ["none detected"])),
            "",
            "Unavailable:",
            *(f"- {item}" for item in (unavailable[:12] or ["none detected"])),
            "",
            "Suggested fixes:",
            *(f"{index}. {fix}" for index, fix in enumerate(fixes, start=1)),
        ]
    )
    return {"providers": providers, "subsystems": subsystems, "text": text}


def _suggest_fixes(providers: dict[str, dict[str, Any]], subsystems: dict[str, dict[str, Any]]) -> list[str]:
    fixes: list[str] = []
    for item in providers.values():
        status = item.get("status")
        if status != "ready":
            fix = str(item.get("suggested_fix") or "").strip()
            if fix and fix not in fixes:
                fixes.append(fix)
    if subsystems.get("Tavily/web search", {}).get("status") == "missing_key":
        fixes.append("Add a Tavily key if you want real web search instead of browser fallback.")
    if subsystems.get("screen vision", {}).get("status") in {"missing_key", "unavailable"}:
        fixes.append("Configure Gemini Vision only if you want screen understanding; capture remains explicit only.")
    if not fixes:
        fixes.append("No urgent fix. Keep auto brain enabled for fastest fallback.")
    return fixes[:6]


def explain_broken_parts(settings: ModelSettings | None = None) -> str:
    return get_eva_health_summary(settings)["text"]


def diagnose_capability(capability_or_provider_name: str, settings: ModelSettings | None = None) -> str:
    provider = provider_from_alias(capability_or_provider_name)
    if provider:
        return format_provider_health(provider, settings)
    health = get_eva_health_summary(settings)
    needle = capability_or_provider_name.strip().lower()
    for name, item in health["subsystems"].items():
        if needle in name.lower():
            return f"{name}: {item.get('status')}\n{item.get('notes')}"
    return health["text"]
