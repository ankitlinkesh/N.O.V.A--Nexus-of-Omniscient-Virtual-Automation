from urllib.parse import parse_qs, urlparse

from backend.eva.tools import email_tools
from backend.eva.tools.registry import ToolRegistry


def test_compose_url_round_trips_fields():
    url = email_tools.gmail_compose_url("a@b.com", "Hi & bye", "Line one\nLine two")
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.netloc == "mail.google.com"
    assert query["to"] == ["a@b.com"] and query["su"] == ["Hi & bye"] and query["body"] == ["Line one\nLine two"]


def test_draft_opens_chrome_and_never_sends(monkeypatch):
    opened = []
    monkeypatch.setattr("backend.eva.browser.controller.open_url_in_chrome", lambda url: opened.append(url) or {"ok": True})
    result = email_tools.email_draft_gmail("a@b.com, c@d.org", "Subject", "Body")
    assert result["ok"] and result["drafted"] and result["sent"] is False
    assert len(opened) == 1 and "to=a%40b.com%2C%20c%40d.org" in opened[0]


def test_bad_recipient_or_empty_email_opens_nothing(monkeypatch):
    monkeypatch.setattr("backend.eva.browser.controller.open_url_in_chrome", lambda url: (_ for _ in ()).throw(AssertionError("opened")))
    assert email_tools.email_draft_gmail("kutty", "s", "b")["error"] == "invalid_recipient"
    assert email_tools.email_draft_gmail("a@b.com", "", "")["error"] == "empty_email"


def test_tool_is_registered():
    assert "email.draft_gmail" in {tool["name"] for tool in ToolRegistry().list_tools()}
