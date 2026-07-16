from __future__ import annotations

import logging

from ._openai_compatible import OpenAICompatibleProvider

logger = logging.getLogger(__name__)


class OpenRouterProvider(OpenAICompatibleProvider):
    name = "openrouter"
    api_key_env = "OPENROUTER_API_KEY"
    model_env = "OPENROUTER_MODEL"
    default_model = "deepseek/deepseek-chat-v3-0324:free"
    base_url_env = "OPENROUTER_BASE_URL"
    default_base_url = "https://openrouter.ai/api/v1"
    extra_headers = {"HTTP-Referer": "http://127.0.0.1:8765", "X-Title": "N.O.V.A"}

    def __init__(self, settings):
        super().__init__(settings)
        if not self.model.endswith(":free"):
            logger.warning("OpenRouter model does not end with :free: %s", self.model)
