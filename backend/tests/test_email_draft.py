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


def test_whatsapp_text_phrasings_are_understood_and_stay_deterministic():
    from backend.eva.core.intent_router import _whatsapp_message_parts
    from backend.eva.core.routing_mode import must_stay_deterministic

    for phrase in ("text hi to kutty on whatsapp", "texr kutty hi in whatsapp", "send hi to kutty via whatsapp"):
        assert _whatsapp_message_parts(phrase) == ("kutty", "hi"), phrase
        assert must_stay_deterministic(phrase), phrase
    assert _whatsapp_message_parts("text me later") is None


def test_open_app_falls_back_to_the_installed_app_index(monkeypatch):
    from backend.eva.tools import app_index, desktop

    monkeypatch.setattr(desktop.shutil, "which", lambda _alias: None)
    monkeypatch.setattr(desktop, "_find_shortcut", lambda _key: None)
    monkeypatch.setattr(app_index, "open_installed_app", lambda name: f"Opening {name} (store app).")
    assert desktop.open_app("whatsapp") == "Opening whatsapp (store app)."


def test_a_bare_confirm_approves_the_one_pending_send_and_never_on_voice(monkeypatch, tmp_path):
    from backend.eva.media import whatsapp_desktop
    from backend.eva.permissions.confirmation import handle_confirmation_command
    from backend.eva.security import tool_gate
    from backend.eva.security.voice_trust import voice_turn
    from backend.eva.tools.registry import ToolRegistry

    monkeypatch.setenv("EVA_PENDING_ACTION_LEDGER_PATH", str(tmp_path / "pending.jsonl"))
    tool_gate._PENDING_CALLS.clear()
    sent = []
    monkeypatch.setattr(whatsapp_desktop, "send_whatsapp_desktop", lambda recipient, message, **_: sent.append((recipient, message)) or {"ok": True, "sent": True})

    ToolRegistry().run("message.send_via_ui", recipient="kutty", message="hi")
    with voice_turn():
        assert "specific pending action" in handle_confirmation_command("confirm")
    assert not sent  # a spoken "confirm" approves nothing

    handle_confirmation_command("yes send")
    assert sent == [("kutty", "hi")]

    sent.clear()
    ToolRegistry().run("message.send_via_ui", recipient="a", message="1")
    ToolRegistry().run("message.send_via_ui", recipient="b", message="2")
    assert "specific pending action" in handle_confirmation_command("confirm")  # two waiting: no guessing
    assert not sent


def test_confirm_survives_pasted_markdown_and_chat_cannot_claim_a_send():
    from backend.eva.agent.claim_check import unbacked_send_claim
    from backend.eva.core.routing_mode import must_stay_deterministic
    from backend.eva.permissions.confirmation import parse_confirmation_action_id

    for pasted in ("`confirm act_88b4622a45b2", "confirm act_88b4622a45b2`", '"confirm act_88b4622a45b2".'):
        assert parse_confirmation_action_id(pasted) == "act_88b4622a45b2"
        assert must_stay_deterministic(pasted)
    assert unbacked_send_claim("The message 'hi' has been sent to your family on WhatsApp.")
    assert unbacked_send_claim("I sent it.")
    assert not unbacked_send_claim("I can send that once you confirm.")
    assert not unbacked_send_claim("The file was sent from the other PC.")
