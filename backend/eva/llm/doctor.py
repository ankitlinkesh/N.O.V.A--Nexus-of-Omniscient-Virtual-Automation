"""Provider health diagnostics — stop guessing which LLM actually works (Phase 48).

Eva has six configured providers, a key-rotation pool, and a per-purpose model
map. Any of it can rot silently: a key gets revoked, a model id is retired, a
provider order lists something with no key. When that happens nothing announces
it — calls just fall through the fallback chain and Eva quietly runs on whatever
still answers, or on nothing.

That is not hypothetical. Notes carried for weeks said "only Gemini works, NVIDIA
NIM has no key"; a live probe found the exact opposite — NIM was working and
primary, while two of six Gemini keys had been returning 404 for a retired model.
The beliefs were wrong in both directions because **there was no way to check**.

This module is the way to check.

  * :func:`configuration_report` is offline and CI-safe: it reports what is
    configured — which providers have keys, the provider order, how many
    rotation keys exist, which model each purpose maps to — and makes **no
    network calls whatsoever**. Safe to run anywhere, any time.
  * :func:`live_probe` actually calls each provider once. It is opt-in and never
    runs by default, because it costs real quota and real money.

Secrets never leave: only key *names*, presence, and lengths are ever reported —
never a value. Fail-safe throughout.
"""

from __future__ import annotations

import os
from typing import Any

# Every provider Eva knows, and the env var holding its key.
PROVIDER_KEY_ENV = {
    "nvidia_nim": "NVIDIA_NIM_API_KEY",
    "gemini": "GEMINI_API_KEY",  # plus the GEMINI_API_KEY_N rotation pool
    "openrouter": "OPENROUTER_API_KEY",
    "groq": "GROQ_API_KEY",
    "clod": "CLOD_API_KEY",
    "ollama": "",  # local, no key
}

_MAX_GEMINI_KEYS = 12


def gemini_key_names(environ: dict[str, str] | None = None) -> list[str]:
    """The names of every Gemini rotation key that is actually set."""
    env = environ if environ is not None else os.environ
    names: list[str] = []
    if str(env.get("GEMINI_API_KEY", "") or "").strip():
        names.append("GEMINI_API_KEY")
    for i in range(2, _MAX_GEMINI_KEYS + 1):
        name = f"GEMINI_API_KEY_{i}"
        if str(env.get(name, "") or "").strip():
            names.append(name)
    return names


def _has_key(name: str, environ: dict[str, str] | None = None) -> bool:
    if not name:
        return True  # ollama needs none
    env = environ if environ is not None else os.environ
    return bool(str(env.get(name, "") or "").strip())


def configuration_report(environ: dict[str, str] | None = None) -> dict[str, Any]:
    """What is configured, offline. NEVER makes a network call.

    Reports each provider's key presence, the effective provider order, and —
    the useful part — which providers appear in the order but have no key, i.e.
    every call wastes an attempt on them before reaching one that works.
    """
    env = environ if environ is not None else os.environ
    report: dict[str, Any] = {"providers": {}, "warnings": [], "network_used": False}

    try:
        for provider, key_env in PROVIDER_KEY_ENV.items():
            entry: dict[str, Any] = {"key_env": key_env or "(none needed)", "configured": _has_key(key_env, env)}
            if provider == "gemini":
                pool = gemini_key_names(env)
                entry["rotation_keys"] = pool
                entry["rotation_key_count"] = len(pool)
                entry["configured"] = bool(pool)
                entry["model"] = str(env.get("GEMINI_MODEL", "") or "")
            if provider == "nvidia_nim":
                entry["model"] = str(env.get("NVIDIA_NIM_MODEL", "") or "")
                entry["planner_model"] = str(env.get("NVIDIA_NIM_PLANNER_MODEL", "") or "")
                entry["deep_reasoning_model"] = str(env.get("NVIDIA_NIM_DEEP_REASONING_MODEL", "") or "")
            if provider == "openrouter":
                entry["model"] = str(env.get("OPENROUTER_MODEL", "") or "")
            if provider == "clod":
                entry["model"] = str(env.get("CLOD_MODEL", "") or "")
            report["providers"][provider] = entry

        raw_order = str(env.get("EVA_CLOUD_PROVIDER_ORDER", "") or "")
        order = [p.strip().lower() for p in raw_order.split(",") if p.strip()]
        report["provider_order"] = order

        # The actionable finding: a provider in the order with no key is a
        # guaranteed failed attempt on every single call.
        dead_in_order = [p for p in order if p in PROVIDER_KEY_ENV and not report["providers"][p]["configured"]]
        report["unconfigured_in_order"] = dead_in_order
        for provider in dead_in_order:
            report["warnings"].append(
                f"'{provider}' is in EVA_CLOUD_PROVIDER_ORDER but has no key — every call wastes an attempt on it."
            )
        if not any(report["providers"][p]["configured"] for p in order if p in PROVIDER_KEY_ENV):
            report["warnings"].append("No provider in the order has a key; Eva has no working cloud LLM.")
    except Exception as exc:  # pragma: no cover - defensive
        report["warnings"].append(f"diagnostic error: {str(exc)[:120]}")

    return report


def format_configuration_report(report: dict[str, Any]) -> str:
    """Human-readable configuration report (no secret values, ever)."""
    lines = ["LLM provider configuration (no network calls made):"]
    order = report.get("provider_order") or []
    lines.append(f"  order: {', '.join(order) if order else '(default)'}")
    for provider, entry in (report.get("providers") or {}).items():
        state = "configured" if entry.get("configured") else "NO KEY"
        extra = ""
        if entry.get("rotation_key_count"):
            extra += f", {entry['rotation_key_count']} rotation keys"
        if entry.get("model"):
            extra += f", model={entry['model']}"
        lines.append(f"  - {provider}: {state}{extra}")
    for warning in report.get("warnings") or []:
        lines.append(f"  ! {warning}")
    # Phase 92: this line used to point at a live probe that had no caller, so
    # the advice could not be followed. Name the command now that one exists.
    lines.append("  (Type `llm probe` to see which keys/models actually answer — that costs real quota.)")
    return "\n".join(lines)


def _nim_models_to_probe() -> list[tuple[str, str]]:
    """(role, model) for every NIM model an operator has actually configured.

    Phase 92: probing one model per provider is not enough. NIM maps a DIFFERENT
    model to each purpose, so `openai/gpt-oss-120b` could die as the general,
    planner AND code model while a chat-only probe of some other model reported
    the provider healthy. Rot hides in the map, so the map is what gets probed.
    """
    try:
        from .providers.nvidia_nim import nvidia_nim_role_models
    except Exception:  # pragma: no cover - defensive
        return []
    roles = nvidia_nim_role_models()
    primary = str(os.environ.get("NVIDIA_NIM_MODEL", "") or "").strip()
    pairs: list[tuple[str, str]] = []
    if primary:
        pairs.append(("general", primary))
    # embed/rerank/pii/asr/tts are not chat-completions models; probing them with
    # a chat message would report a false failure, which is worse than no answer.
    for role in ("planner", "code", "deep_reasoning", "vision", "screen_reason", "safety"):
        model = str(roles.get(role) or "").strip()
        if model:
            pairs.append((role, model))
    return pairs


async def live_probe(provider_names: list[str] | None = None, *, settings: Any = None) -> dict[str, Any]:
    """Actually call each provider once and report what answers.

    Opt-in and never run by default or in CI: this spends real quota. Returns
    per-provider ok/model/error. Never raises.

    Phase 92 additions, both earned by a real outage: NIM's per-purpose model map
    is probed rather than one model, and each distinct model id is called at most
    once however many roles share it (`gpt-oss-120b` filled three).
    """
    from ..core.config import ModelSettings
    from .router import PROVIDER_CLASSES, LLMRateLimiter, _call_provider

    # A probe that reports a HEALTHY provider as dead is worse than no probe at
    # all, and passing settings=None did exactly that: GeminiProvider reads
    # settings.smart_model in its constructor, so gemini came back
    # "DID NOT ANSWER - AttributeError: 'NoneType' object has no attribute
    # 'smart_model'" while four working keys sat right there.
    if settings is None:
        settings = ModelSettings()

    results: dict[str, Any] = {"network_used": True, "providers": {}, "models": {}}
    names = provider_names or [p for p in PROVIDER_KEY_ENV if p != "ollama"]
    messages = [{"role": "user", "content": "Reply with exactly: ok"}]
    # Not 16. A reasoning model spends its budget thinking before it emits any
    # content, so a tight cap returns empty text and the probe reports a
    # perfectly healthy provider as `empty_response` -- gemini-2.5-flash did
    # exactly that. The probe's own parameters must not manufacture the failure
    # it is looking for. Still small enough to be cheap.
    probe_max_tokens = 256
    limiter = LLMRateLimiter()

    for name in names:
        try:
            provider_cls = PROVIDER_CLASSES.get(name)
            if provider_cls is None:
                results["providers"][name] = {"ok": False, "error": "unknown provider"}
                continue
            provider = provider_cls(settings)
            response, _ = await _call_provider(provider, limiter, messages, purpose="chat", temperature=0.0, max_tokens=probe_max_tokens)
            results["providers"][name] = {
                "ok": bool(getattr(response, "ok", False)),
                "model": str(getattr(response, "model", "")),
                "error": str(getattr(response, "error", "") or "")[:200],
            }
        except Exception as exc:
            results["providers"][name] = {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:150]}"}

    if "nvidia_nim" in names and PROVIDER_CLASSES.get("nvidia_nim") is not None:
        probed: dict[str, dict[str, Any]] = {}
        for role, model in _nim_models_to_probe():
            if model in probed:
                results["models"][f"nvidia_nim:{role}"] = dict(probed[model], model=model, deduped=True)
                continue
            try:
                provider = PROVIDER_CLASSES["nvidia_nim"](settings, model=model)
                # Probe each model under ITS OWN role, not a generic "chat".
                # Purpose decides the request timeout (Phase 104), so probing the
                # deep_reasoning model as chat gave it 12 seconds to do a job that
                # takes 164 -- and the probe then reported the model as dead. This
                # file already carries that lesson one line up, about max_tokens:
                # "the probe's own parameters must not manufacture the failure it
                # is looking for". It was true of the timeout too.
                response, _ = await _call_provider(
                    provider, limiter, messages, purpose=role, temperature=0.0, max_tokens=probe_max_tokens
                )
                entry = {
                    "ok": bool(getattr(response, "ok", False)),
                    "status_code": getattr(response, "status_code", None),
                    "error": str(getattr(response, "error", "") or "")[:200],
                }
            except Exception as exc:
                entry = {"ok": False, "status_code": None, "error": f"{type(exc).__name__}: {str(exc)[:150]}"}
            probed[model] = entry
            results["models"][f"nvidia_nim:{role}"] = dict(entry, model=model, deduped=False)
    return results


def format_live_probe(report: dict[str, Any]) -> str:
    """Human-readable live-probe report (no secret values, ever)."""
    lines = ["LLM live probe (real network calls were made, real quota was spent):"]
    for provider, entry in (report.get("providers") or {}).items():
        if entry.get("ok"):
            lines.append(f"  - {provider}: ANSWERED as {entry.get('model') or '(model unreported)'}")
        else:
            lines.append(f"  - {provider}: DID NOT ANSWER — {entry.get('error') or 'no reason reported'}")

    models = report.get("models") or {}
    if models:
        lines.append("  NVIDIA NIM per-purpose models:")
        for label, entry in models.items():
            role = label.split(":", 1)[-1]
            model = entry.get("model") or "(unset)"
            if entry.get("ok"):
                suffix = "  (same model, not re-probed)" if entry.get("deduped") else ""
                lines.append(f"    - {role:<14} {model}  ANSWERED{suffix}")
            else:
                status = entry.get("status_code")
                # Only 404/410 are grounds for saying a model is retired. Anything
                # else -- a timeout, a network error, a provider returning nothing
                # -- means "did not answer just now", and saying more than that
                # would be the probe asserting what it does not know.
                reason = str(entry.get("error") or "").strip()
                if status in {404, 410}:
                    lines.append(f"    - {role:<14} {model}  FAILED [{status}] <- THIS MODEL IS GONE {reason[:120]}")
                else:
                    detail = reason[:120] or "no answer and no error reported (usually a timeout); model may be fine"
                    lines.append(f"    - {role:<14} {model}  NO ANSWER — {detail}")

    dead = sorted(
        {
            str(entry.get("model"))
            for entry in models.values()
            if entry.get("status_code") in {404, 410} and entry.get("model")
        }
    )
    if dead:
        lines.append(
            "  ! Retired or unknown model id(s): "
            + ", ".join(dead)
            + ". Point the matching NVIDIA_NIM_*_MODEL setting at a model that exists."
        )
    return "\n".join(lines)


__all__ = [
    "configuration_report",
    "format_configuration_report",
    "live_probe",
    "format_live_probe",
    "gemini_key_names",
    "PROVIDER_KEY_ENV",
]
