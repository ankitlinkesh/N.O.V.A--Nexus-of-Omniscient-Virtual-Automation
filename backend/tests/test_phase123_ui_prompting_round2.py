"""Phase 123: second round of prompting the chat UI.

1. "what's the latest news about NVIDIA today?" returned NOVA's NIM provider
   diagnostics: "test" matched inside "latest" (and "nim" inside "animal").
2. "open github.com/anthropics and tell me what repos are pinned" opened the URL
   "github.com/anthropics and tell me what repos are pinned".
3. "open github.com/anthropics" -- even with https:// -- answered "I don't have
   previous search results", because "github" is a search-result word.
4. A model skipped after a timeout (Phase 121) was reported as "quota_blocked"
   with "wait for quota/reset".
5. "how much free space is on my C drive?" was refused.
"""
from __future__ import annotations

from backend.eva.core.fast_commands import maybe_handle_fast_command
from backend.eva.core.intent_router import classify_capability_intent
from backend.eva.core.web_context import wants_previous_result


class _Tools:
    def __init__(self):
        self.calls = []

    def run(self, name, **kwargs):
        self.calls.append((name, kwargs))
        return {"ok": True}


def test_news_about_nvidia_is_not_a_provider_diagnostic():
    assert classify_capability_intent("what's the latest news about NVIDIA today?").get("capability") != "provider_diagnostics"
    assert classify_capability_intent("is the nvidia nim provider working?").get("capability") == "provider_diagnostics"
    assert classify_capability_intent("check the animal shelter status").get("capability") != "provider_diagnostics"


def test_an_errand_after_a_link_is_not_swallowed_into_the_url():
    tools = _Tools()
    assert maybe_handle_fast_command("open github.com/anthropics and tell me what repos are pinned", tools, {}) is None
    assert maybe_handle_fast_command("visit example.com and summarize it", tools, {}) is None
    assert not any(name == "open_url" for name, _ in tools.calls)


def test_an_explicit_address_opens_even_when_it_names_github():
    assert not wants_previous_result("open github.com/anthropics")
    assert not wants_previous_result("open https://github.com/anthropics")
    assert wants_previous_result("open my github")
    tools = _Tools()
    maybe_handle_fast_command("open github.com/anthropics", tools, {})
    assert ("open_url", {"url": "github.com/anthropics"}) in tools.calls


def test_a_timeout_cooldown_is_not_reported_as_a_quota():
    from backend.eva.diagnostics.providers import _provider_status

    assert _provider_status(True, "ReadTimeout: no response within 12s", 9999999999, "nvidia_nim") == "cooling_down"
    assert _provider_status(True, "quota/rate limit", 9999999999, "nvidia_nim") == "quota_blocked"


def test_status_reports_free_disk_space():
    import sys

    from backend.eva.tools.power_info import disk_space

    if sys.platform == "win32":
        drives = disk_space()
        assert drives and all({"drive", "free_gb", "total_gb"} <= set(d) for d in drives)
