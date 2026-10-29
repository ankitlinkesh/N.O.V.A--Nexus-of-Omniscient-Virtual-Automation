from backend.eva.media import whatsapp_desktop as wa
from backend.eva.tools.message_tools import message_send_via_ui


def test_refuses_without_real_input(monkeypatch):
    monkeypatch.setenv("EVA_ENABLE_REAL_INPUT", "0")
    result = wa.send_whatsapp_desktop("kutty", "hi")
    assert result["sent"] is False and result["error"] == "real_input_disabled"


def test_refuses_without_local_vision(monkeypatch):
    monkeypatch.setenv("EVA_ENABLE_REAL_INPUT", "1")
    monkeypatch.setenv("VISION_PROVIDER", "gemini")
    result = wa.send_whatsapp_desktop("kutty", "hi")
    assert result["sent"] is False and result["error"] == "local_vision_not_enabled"


def test_rejects_empty_and_multiline_input():
    assert wa.send_whatsapp_desktop("", "hi")["error"] == "recipient_and_message_required"
    assert wa.send_whatsapp_desktop("kutty", "")["error"] == "recipient_and_message_required"
    assert wa.send_whatsapp_desktop("kutty", "a\nb")["error"] == "message_must_be_one_line_under_1000_chars"


def test_approved_send_reports_the_real_outcome_not_a_stub_success(monkeypatch):
    monkeypatch.setattr(wa, "send_whatsapp_desktop", lambda r, m: {"sent": False, "step": "verify_chat", "error": "chat_header_mismatch", "message": "The open chat was not kutty, so I did not send anything."})
    out = message_send_via_ui("kutty", "hi", confirmed=True)
    assert out["ok"] is False and out["sent"] is False and out["step"] == "verify_chat"
    assert "did not send" in out["message"]


def test_a_successful_send_exposes_its_outcome_for_the_approval_reply(monkeypatch):
    from backend.eva.permissions.confirmation import _render_executed

    monkeypatch.setattr(wa, "send_whatsapp_desktop", lambda r, m: {"sent": True, "verified": False, "message": "I pressed send on \"hi\" to kutty, but could not confirm it appeared in the chat."})
    out = message_send_via_ui("kutty", "hi", confirmed=True)
    reply = _render_executed("act_1", "base", out)
    assert "could not confirm it appeared" in reply
