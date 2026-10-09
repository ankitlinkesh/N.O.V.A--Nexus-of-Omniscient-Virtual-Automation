from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def emit(case: str, passed: bool, **payload: object) -> int:
    print(json.dumps({"case": case, "pass": passed, **payload}, indent=2, ensure_ascii=True))
    return 0 if passed else 1


class DummySettings:
    def __init__(self) -> None:
        from backend.eva.core.config import ModelSettings

        self.models = ModelSettings()


def main() -> int:
    from backend.eva.api.routes import _handle_capability_route
    from backend.eva.core.fast_commands import maybe_handle_fast_command
    from backend.eva.core.intent_router import classify_capability_intent
    from backend.eva.diagnostics.health import explain_workflows, get_eva_health_summary
    from backend.eva.diagnostics.providers import safe_provider_error_summary
    from backend.eva.llm.router import provider_order, set_llm_mode
    from backend.eva.tools.registry import ToolRegistry

    failures = 0
    settings = DummySettings()
    tools = ToolRegistry()

    arch_class = classify_capability_intent("explain your full architecture", {})
    arch_reply = _handle_capability_route("explain your full architecture", arch_class, {}, None, "verify", settings)
    arch_text = arch_reply[0] if arch_reply else ""
    refs = re.findall(r"(?:frontend|backend/eva)/[A-Za-z0-9_./-]+", arch_text)
    required_architecture_refs = (
        "frontend/index.html",
        "frontend/app.js",
        "frontend/styles.css",
        "backend/eva/main.py",
        "backend/eva/api/routes.py",
        "backend/eva/core/intent_router.py",
        "backend/eva/core/capabilities.py",
        "backend/eva/core/operator_commands.py",
        "backend/eva/agent/runner.py",
        "backend/eva/agent/planner.py",
        "backend/eva/agent/executor.py",
        "backend/eva/agent/cognition.py",
        "backend/eva/tools/registry.py",
        "backend/eva/llm/router.py",
        "backend/eva/llm/providers/nvidia_nim.py",
        "backend/eva/desktop/",
        "backend/eva/browser/",
        "backend/eva/research/",
        "backend/eva/code/",
        "backend/eva/workspace/",
        "backend/eva/vision/",
        "backend/eva/memory/",
        "backend/eva/data/research_knowledge.sqlite3",
        "memory SQLite",
        "backend/eva/data/code_index.json",
        "NVIDIA NIM -> Gemini -> OpenRouter -> Groq -> CLoD -> Ollama",
        ".env.local",
        "no arbitrary shell",
        "no camera",
        "screen only on request",
        "power actions require confirmation",
    )
    failures += emit(
        "architecture_file_grounded",
        len(set(refs)) >= 8
        and all(token in arch_text for token in required_architecture_refs)
        and all(
            token in arch_text
            for token in (
                "Agentic v2",
                "Desktop Agent",
                "Browser Agent",
                "Code Intelligence",
                "Research SQLite",
                "NIM",
                "Tool",
                "Voice",
            )
        )
        and not arch_text.startswith("I am Eva"),
        missing=[token for token in required_architecture_refs if token not in arch_text],
        refs=sorted(set(refs))[:20],
        snippet=arch_text[:1000],
    )

    workflows = explain_workflows()
    failures += emit(
        "workflow_explanation_grounded",
        all(
            token in workflows.lower()
            for token in (
                "chat routing",
                "operator workflow",
                "agentic",
                "browser workflow",
                "research workflow",
                "llm routing",
                "code intelligence",
                "voice workflow",
            )
        ),
        snippet=workflows[:1000],
    )

    openrouter_class = classify_capability_intent("test OpenRouter API and tell me if it works", {})
    openrouter_reply = _handle_capability_route("test OpenRouter API and tell me if it works", openrouter_class, {}, None, "verify", settings)
    openrouter_text = openrouter_reply[0] if openrouter_reply else ""
    failures += emit(
        "openrouter_terminal_provider_diagnostics",
        openrouter_class.get("capability") == "provider_diagnostics"
        and "OpenRouter" in openrouter_text
        and "web_search" not in openrouter_text.lower()
        and "tavily" not in openrouter_text.lower(),
        result=openrouter_class,
        snippet=openrouter_text[:800],
    )

    built_in_class = classify_capability_intent("openrouter API is built in within you", {})
    built_in_reply = _handle_capability_route("openrouter API is built in within you", built_in_class, {}, None, "verify", settings)
    failures += emit(
        "openrouter_builtin_routes_internal",
        built_in_class.get("capability") == "provider_diagnostics"
        and built_in_reply is not None
        and "OpenRoute maps" not in built_in_reply[0],
    )

    search_docs = classify_capability_intent("search web for OpenRouter docs", {})
    failures += emit(
        "explicit_web_search_not_captured",
        not (search_docs.get("capability") == "provider_diagnostics"),
        result=search_docs,
    )

    health = get_eva_health_summary(settings.models)
    health_text = health["text"]
    failures += emit(
        "health_has_sections",
        all(section in health_text for section in ("Working:", "Degraded:", "Unavailable:", "Suggested fixes:")),
        snippet=health_text[:1000],
    )

    clean_status = maybe_handle_fast_command("llm status", tools, {}, None, "verify")
    raw_status = maybe_handle_fast_command("llm status raw", tools, {}, None, "verify")
    clean_text = clean_status[0] if clean_status else ""
    raw_text = raw_status[0] if raw_status else ""
    failures += emit(
        "llm_status_clean_not_raw_json",
        clean_status is not None and not clean_text.lstrip().startswith("{") and "provider | configured | model | status" in clean_text.lower(),
        snippet=clean_text[:1000],
    )
    failures += emit(
        "llm_status_raw_json",
        raw_status is not None and raw_text.lstrip().startswith("{") and json.loads(raw_text).get("provider_order") is not None,
    )

    old_mode = os.environ.get("EVA_LLM_MODE")
    old_groq = os.environ.get("GROQ_API_KEY")
    try:
        os.environ.pop("GROQ_API_KEY", None)
        set_llm_mode("groq")
        order = provider_order()
        failures += emit(
            "missing_groq_does_not_trap_provider_order",
            order[:6] == ["nvidia_nim", "gemini", "openrouter", "groq", "clod", "ollama"],
            order=order,
        )
    finally:
        if old_mode is None:
            os.environ.pop("EVA_LLM_MODE", None)
        else:
            os.environ["EVA_LLM_MODE"] = old_mode
        if old_groq is None:
            os.environ.pop("GROQ_API_KEY", None)
        else:
            os.environ["GROQ_API_KEY"] = old_groq

    failures += emit(
        "error_summarizer_maps_known_errors",
        safe_provider_error_summary("HTTP 401 User not found") == "auth failed / key invalid"
        and safe_provider_error_summary("404 page not found") == "model unavailable"
        and safe_provider_error_summary("RESOURCE_EXHAUSTED 429") == "quota/rate limit",
    )

    # Read a fresh limiter state, not the live one: a real NIM timeout minutes earlier
    # left it cooling_down and failed this case for reasons outside the code.
    import tempfile

    from backend.eva.llm import rate_limiter

    old_nim = os.environ.get("NVIDIA_NIM_API_KEY")
    old_defaults = rate_limiter.LLMRateLimiter.__init__.__defaults__
    state_dir = tempfile.mkdtemp(prefix="eva_selfdiag_")
    try:
        rate_limiter.LLMRateLimiter.__init__.__defaults__ = (Path(state_dir) / "llm_usage_state.json",)
        os.environ["NVIDIA_NIM_API_KEY"] = "configured-placeholder"
        nim_health = get_eva_health_summary(settings.models)["providers"].get("nvidia_nim", {})
        failures += emit(
            "nim_configured_can_be_ready",
            nim_health.get("configured") is True and nim_health.get("status") in {"ready", "degraded", "quota_blocked", "model_unavailable"},
            nim_health=nim_health,
        )
    finally:
        rate_limiter.LLMRateLimiter.__init__.__defaults__ = old_defaults
        if old_nim is None:
            os.environ.pop("NVIDIA_NIM_API_KEY", None)
        else:
            os.environ["NVIDIA_NIM_API_KEY"] = old_nim

    secret_patterns = [
        r"AIza[0-9A-Za-z_\-]{20,}",
        r"sk-or-v1-[0-9A-Za-z_\-]+",
        r"nvapi-[0-9A-Za-z_\-]+",
        r"tvly-[0-9A-Za-z_\-]+",
    ]
    combined = "\n".join([arch_text, workflows, openrouter_text, health_text, clean_text])
    leaks = [pattern for pattern in secret_patterns if re.search(pattern, combined)]
    failures += emit("no_keys_in_diagnostics", not leaks, leaked_patterns=leaks)

    print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
