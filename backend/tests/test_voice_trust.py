"""Trusted-voice mode: reversible actions run on your own spoken request; sending and undoable ones still ask."""

import asyncio
from types import SimpleNamespace

import pytest

from backend.eva.security import voice_trust as vt
from backend.eva.tools.registry import ToolRegistry

NEVER = [
    ("message.send_via_ui", {"recipient": "x", "message": "hi"}), ("message.confirm_send", {"recipient": "x", "message": "hi"}),
    ("email.send_drafted", {}), ("screen.submit_form", {"reason": "r", "spec_id": "s"}), ("file.delete", {"path": "Documents/a.txt"}),
    ("file.write_text", {"path": "Documents/a.txt", "content": "x"}), ("file.copy", {"src": "a", "dst": "b"}), ("file.move", {"src": "a", "dst": "b"}),
    ("close_app", {"app": "notepad"}), ("system_power", {"action": "shutdown"}), ("guarded_power_action", {"action": "restart"}),
    ("shell.run_bounded", {}), ("share.to_box", {"path": "Documents/a.txt"}), ("share.from_box", {"name": "a"}), ("mcp.srv.tool", {}),
    ("web.click", {}),
]
# `window_close_safe` is allow-class by design (it is not part of this feature), so it is not listed here.
ELIGIBLE = [
    ("screen.type_text", {"text": "12+7=", "reason": "r"}), ("screen.press", {"key": "escape", "reason": "r"}),
    ("screen.hotkey", {"keys": ["ctrl", "c"], "reason": "r"}), ("screen.click", {"label": "Seven", "reason": "r"}),
    ("screen.scroll", {"amount": 3, "reason": "r"}), ("capture_screen", {}), ("clipboard.read", {}), ("radio_set", {"kind": "bluetooth", "state": "off"}),
]


@pytest.fixture(autouse=True)
def on(monkeypatch):
    monkeypatch.setenv("EVA_VOICE_TRUST", "1")
    # No test here may run a real tool handler: a handler that was NOT gated would act on this machine (an earlier
    # draft of these tests closed a real Chrome window that way). The gate decides; `_invoke` only records.
    monkeypatch.setattr(ToolRegistry, "_invoke", lambda self, spec, args: {"ok": True, "invoked": spec.name})


def ok(name, args, front="Notepad notepad.exe"):
    with vt.voice_turn():
        return vt.allow_reason(name, None, args, foreground=front)


@pytest.mark.parametrize("name,args", ELIGIBLE)
def test_reversible_tools_are_allowed_on_a_voice_turn(name, args):
    assert ok(name, args) == "voice_trust"


@pytest.mark.parametrize("name,args", NEVER)
def test_sending_and_undoable_tools_are_never_allowed(name, args):
    assert ok(name, args) == ""


def test_off_by_default_and_outside_a_voice_turn(monkeypatch):
    assert vt.allow_reason("screen.type_text", None, {"text": "x"}, foreground="Notepad") == ""  # typed request
    monkeypatch.delenv("EVA_VOICE_TRUST")
    assert ok("screen.type_text", {"text": "x"}) == ""  # flag off


def test_enter_and_newlines_are_refused_in_messaging_and_mail_windows_only():
    for front in ("WhatsApp WhatsApp.exe", "Compose Mail - Gmail - Google Chrome", "Slack", "Discord"):
        assert ok("screen.press", {"key": "enter"}, front) == "", front
        assert ok("screen.hotkey", {"keys": ["ctrl", "enter"]}, front) == "", front
        assert ok("screen.type_text", {"text": "hi\nthere"}, front) == "", front
        assert ok("screen.type_text", {"text": "hi there"}, front) == "voice_trust", front  # typing alone sends nothing
    assert ok("screen.press", {"key": "enter"}, "Notepad notepad.exe") == "voice_trust"


def test_clicks_on_send_like_labels_are_refused():
    for label in ("Send", "send message", "Post", "Submit", "Pay now", "Buy", "Delete", "Confirm order", "Sign out"):
        assert ok("screen.click", {"label": label}) == "", label
    for label in ("Seven", "Plus", "File", "Next", "Search"):
        assert ok("screen.click", {"label": label}) == "voice_trust", label


def test_wifi_off_and_cloud_vision_keep_their_prompts(monkeypatch):
    assert ok("radio_set", {"kind": "wifi", "state": "off"}) == ""
    assert ok("radio_set", {"kind": "wifi", "state": "on"}) == "voice_trust"
    import backend.eva.vision.screen_vision as sv

    monkeypatch.setattr(sv, "local_vision_enabled", lambda: False)
    assert ok("analyze_screen", {}) == ""
    monkeypatch.setattr(sv, "local_vision_enabled", lambda: True)
    assert ok("analyze_screen", {}) == "voice_trust"


# --- through the real gate ---------------------------------------------------------------------

def test_the_gate_skips_the_prompt_only_inside_a_voice_turn(monkeypatch):
    reg = ToolRegistry()
    monkeypatch.setattr(vt, "_foreground_text", lambda: "Notepad notepad.exe")
    args = {"text": "hello", "reason": "r"}
    typed = reg.run("screen.type_text", **args)
    assert typed.get("pending_id") and not typed.get("invoked")  # a typed request still asks
    with vt.voice_turn():
        result = reg.run("screen.type_text", **args)
    assert result.get("invoked") == "screen.type_text" and not result.get("pending_id")


@pytest.mark.parametrize("name,args", [n for n in NEVER if not n[0].startswith("mcp.")])
def test_the_gate_still_asks_for_sending_and_undoable_actions_in_a_voice_turn(name, args, monkeypatch):
    reg = ToolRegistry()
    monkeypatch.setattr(vt, "_foreground_text", lambda: "Notepad notepad.exe")
    with vt.voice_turn():
        result = reg.run(name, **args)
    assert not result.get("invoked"), f"{name} ran without a prompt"
    assert result.get("pending_id") or result.get("requires_confirmation") or result.get("hard_blocked") or result.get("ok") is False, name


def test_the_voice_endpoint_opens_the_scope_and_a_typed_chat_does_not(monkeypatch):
    from backend.eva.api import routes

    seen = {}

    async def fake_chat(payload, request):
        seen["voice"] = vt.in_voice_turn()
        return SimpleNamespace(session_id="s", reply="ok", source="x", requires_confirmation=False, action=None)

    monkeypatch.setattr(routes, "chat", fake_chat)
    monkeypatch.setattr(routes, "listen_once", lambda: SimpleNamespace(text="type hello", woke=True, wake_word="hey", reason=""))
    asyncio.run(routes.chat_voice(routes.VoiceListenRequest(), SimpleNamespace()))
    assert seen["voice"] is True and vt.in_voice_turn() is False  # scope closed again afterwards
