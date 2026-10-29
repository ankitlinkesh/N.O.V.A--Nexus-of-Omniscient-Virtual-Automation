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


def _stub_draft(monkeypatch):
    monkeypatch.setattr("backend.eva.browser.controller.open_url_in_chrome", lambda url: {"ok": True})
    email_tools.email_draft_gmail("a@b.com", "Hello", "Body")


def test_send_phrase_only_counts_after_a_draft(monkeypatch):
    email_tools._LAST_DRAFT.clear()
    assert not email_tools.is_send_draft_request("send")
    _stub_draft(monkeypatch)
    for phrase in ("send", "Send it", "send the email", "hit send", "send now."):
        assert email_tools.is_send_draft_request(phrase), phrase
    assert not email_tools.is_send_draft_request("send hi to kutty on whatsapp")


def test_send_requires_confirmation_and_presses_nothing(monkeypatch):
    _stub_draft(monkeypatch)
    pressed = []
    monkeypatch.setattr("backend.eva.screen.screen_controller.hotkey", lambda *a, **k: pressed.append(a))
    result = email_tools.email_send_drafted(confirmed=False)
    assert result["ok"] is False and result.get("requires_confirmation") and not pressed
    assert email_tools.pending_draft() is not None


def test_confirmed_send_presses_ctrl_enter_once(monkeypatch):
    _stub_draft(monkeypatch)
    titles = iter(["Compose Mail - me - Gmail", "Compose Mail - me - Gmail", "Inbox - me - Gmail"])
    monkeypatch.setattr(email_tools, "_gmail_title", lambda: next(titles, "Inbox - me - Gmail"))
    monkeypatch.setattr("backend.eva.desktop.focus_window_safe", lambda name: {"ok": True})
    monkeypatch.setattr("backend.eva.screen.screen_controller.real_input_enabled", lambda: True)
    pressed = []

    class Obs:
        success = True

    monkeypatch.setattr("backend.eva.screen.screen_controller.hotkey", lambda keys, reason, *a, **k: pressed.append(keys) or Obs())
    result = email_tools.email_send_drafted(confirmed=True, sleep=lambda s: None)
    assert result["ok"] and result["sent"] and result["verified"] and pressed == [["ctrl", "enter"]]
    assert email_tools.pending_draft() is None


def test_confirmed_send_refuses_when_gmail_not_in_front(monkeypatch):
    _stub_draft(monkeypatch)
    monkeypatch.setattr(email_tools, "_gmail_title", lambda: "Some Game")
    monkeypatch.setattr("backend.eva.desktop.focus_window_safe", lambda name: {"ok": True})
    monkeypatch.setattr("backend.eva.screen.screen_controller.real_input_enabled", lambda: True)
    monkeypatch.setattr("backend.eva.screen.screen_controller.hotkey", lambda *a, **k: (_ for _ in ()).throw(AssertionError("pressed")))
    assert email_tools.email_send_drafted(confirmed=True, sleep=lambda s: None)["error"] == "gmail_not_in_front"
