"""Playwright DOM automation is opt-in and SSRF-guarded.

Default suite runs with the flag off, so these tests never launch a browser.
The one live navigation test is skipped unless EVA_RUN_LIVE_BROWSER is set, so
CI/verifier runs stay headless-free while a human can still prove it live.
"""
from __future__ import annotations

import os

import pytest

from backend.eva.browser_automation import playwright_driver as d


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("EVA_V2_PLAYWRIGHT_ENABLED", raising=False)
    assert d.playwright_status()["enabled"] is False
    for result in (d.open_url("https://example.com"), d.get_page_snapshot(),
                   d.click_element({"selector": "a"}), d.type_text({"selector": "input"}, "x")):
        assert result["ok"] is False
        assert result["error"] == "playwright_disabled"


def test_private_hosts_blocked_before_launch(monkeypatch):
    monkeypatch.setenv("EVA_V2_PLAYWRIGHT_ENABLED", "true")
    for target in ("http://localhost:8000", "http://127.0.0.1", "http://192.168.1.1", "http://10.0.0.5"):
        result = d.open_url(target)
        assert result["ok"] is False
        assert result["error"] == "private_host_blocked", target


def test_bad_scheme_rejected(monkeypatch):
    monkeypatch.setenv("EVA_V2_PLAYWRIGHT_ENABLED", "true")
    result = d.open_url("file:///etc/passwd")
    assert result["ok"] is False
    assert "http" in result["error"].lower()


@pytest.mark.skipif(not os.environ.get("EVA_RUN_LIVE_BROWSER"), reason="live browser test is opt-in (set EVA_RUN_LIVE_BROWSER=1)")
def test_live_navigation(monkeypatch):
    monkeypatch.setenv("EVA_V2_PLAYWRIGHT_ENABLED", "true")
    try:
        opened = d.open_url("https://example.com")
        assert opened["ok"] is True
        assert "Example Domain" in opened["title"]
        assert d.verify_page(expected_text="example domain")["verified"] is True
    finally:
        d.close_browser()
