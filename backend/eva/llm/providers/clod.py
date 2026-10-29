from __future__ import annotations

from ._openai_compatible import OpenAICompatibleProvider


class ClodProvider(OpenAICompatibleProvider):
    name = "clod"
    api_key_env = "CLOD_API_KEY"
    model_env = "CLOD_MODEL"
    # KNOWN BROKEN (verified live 2026-07-16): "DeepSeek V3" is a display name,
    # not an API model id — Clod answers every call with 400 "Model not found:
    # Model not found: DeepSeek V3", so this provider has never once worked.
    # The correct id could NOT be discovered: /v1/models 403s for this key and
    # raw probes are Cloudflare-blocked (error 1010). Left as-is deliberately
    # rather than replaced with an unverified guess — set CLOD_MODEL to a real
    # id from the Clod dashboard to fix it. `llm doctor` will keep reporting it.
    default_model = "DeepSeek V3"
    base_url_env = "CLOD_BASE_URL"
    default_base_url = "https://api.clod.io/v1"

    @property
    def supports_response_format(self) -> bool:  # type: ignore[override]
        # llama.cpp's server enforces json_schema; only trust that for a local endpoint.
        from ...agent.planner_schema import local_endpoint

        return local_endpoint()

