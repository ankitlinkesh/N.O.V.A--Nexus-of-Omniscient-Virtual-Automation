"""First-party MCP servers (Phase 160): the gate must survive the move into a server process."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from backend.eva.mcp import domain_server, first_party
from backend.eva.mcp.domain_server import APPROVAL_ARG, execute, mint_approval, verify_approval
from backend.eva.mcp.domains import DOMAIN_TOOLS
from backend.eva.tools.registry import ToolRegistry


@pytest.fixture(autouse=True)
def isolated_draft_state(monkeypatch, tmp_path):
    """Enabling the gmail domain points the draft at a shared file; keep that off the live data dir."""
    from backend.eva.tools import email_tools

    monkeypatch.setenv("EVA_DRAFT_STATE_PATH", str(tmp_path / "draft.json"))
    monkeypatch.setattr(email_tools, "_shared_path", None)
    monkeypatch.setattr(email_tools, "_LAST_DRAFT", {})


def _spec(name="message.send_via_ui", gated=True, accepts_confirmed=True, calls=None):
    calls = calls if calls is not None else []

    if accepts_confirmed:
        def handler(recipient, message, confirmed=False):
            calls.append({"recipient": recipient, "message": message, "confirmed": confirmed})
            return {"ok": True, "sent": bool(confirmed)}
    else:
        def handler(query):
            calls.append({"query": query})
            return {"ok": True}

    return SimpleNamespace(
        name=name,
        handler=handler,
        requires_confirmation=gated,
        safety_level="sensitive" if gated else "safe",
        action_type="EXTERNAL_MESSAGE_SEND" if gated else "SAFE_LOCAL_UI",
    )


def test_approval_token_binds_tool_and_exact_arguments():
    args = {"recipient": "kutty", "message": "hi"}
    token = mint_approval("message.send_via_ui", args, "s3cret")
    assert verify_approval("message.send_via_ui", args, token, "s3cret")
    assert not verify_approval("message.send_via_ui", {**args, "message": "hello"}, token, "s3cret")
    assert not verify_approval("email.send_drafted", args, token, "s3cret")
    assert not verify_approval("message.send_via_ui", args, token, "other")
    # An unset secret can never verify, even against an empty token.
    assert mint_approval("t", args, "") == ""
    assert not verify_approval("t", args, "", "")


def test_gated_tool_does_not_run_without_a_valid_token(monkeypatch):
    monkeypatch.setenv(domain_server.SECRET_ENV, "s3cret")
    calls = []
    spec = _spec(calls=calls)
    base = {"recipient": "kutty", "message": "hi"}
    for extra in ({}, {APPROVAL_ARG: "deadbeef"}, {"confirmed": True}):
        out = execute(spec, {**base, **extra})
        assert out["needs_confirmation"] is True
    assert calls == []


def test_gated_tool_runs_with_token_and_sets_confirmed_itself(monkeypatch):
    monkeypatch.setenv(domain_server.SECRET_ENV, "s3cret")
    calls = []
    spec = _spec(calls=calls)
    args = {"recipient": "kutty", "message": "hi"}
    out = execute(spec, {**args, APPROVAL_ARG: mint_approval(spec.name, args)})
    assert out == {"ok": True, "sent": True}
    assert calls == [{"recipient": "kutty", "message": "hi", "confirmed": True}]


def test_safe_tool_runs_without_a_token():
    calls = []
    spec = _spec(name="spotify_search", gated=False, accepts_confirmed=False, calls=calls)
    assert execute(spec, {"query": "tokyo drift"}) == {"ok": True}
    assert calls == [{"query": "tokyo drift"}]


def test_advertised_schema_hides_confirmed_and_adds_token_only_when_gated():
    registry = ToolRegistry()
    send = domain_server._advertised_schema(registry.get("message.send_via_ui"))
    assert "confirmed" not in send["properties"] and APPROVAL_ARG in send["properties"]
    pause = domain_server._advertised_schema(registry.get("spotify_pause"))
    assert APPROVAL_ARG not in pause["properties"]


def test_every_domain_tool_exists_and_sends_are_gated():
    registry = ToolRegistry()
    for domain, names in DOMAIN_TOOLS.items():
        for name in names:
            assert registry.get(name) is not None, f"{domain}: {name} missing from the registry"
    assert domain_server.is_gated(registry.get("message.send_via_ui"))
    assert domain_server.is_gated(registry.get("email.send_drafted"))
    assert not domain_server.is_gated(registry.get("spotify_pause"))


def test_enabled_domains_parsing(monkeypatch):
    monkeypatch.delenv("EVA_FIRST_PARTY_MCP", raising=False)
    assert first_party.enabled_domains() == []
    monkeypatch.setenv("EVA_FIRST_PARTY_MCP", "spotify, youtube nonsense")
    assert first_party.enabled_domains() == ["spotify", "youtube"]
    monkeypatch.setenv("EVA_FIRST_PARTY_MCP", "all")
    assert first_party.enabled_domains() == list(DOMAIN_TOOLS)
    monkeypatch.setenv("EVA_FIRST_PARTY_MCP", "0")
    assert first_party.enabled_domains() == []


def test_off_by_default_leaves_handlers_alone(monkeypatch):
    monkeypatch.delenv("EVA_FIRST_PARTY_MCP", raising=False)
    assert first_party.apply_first_party(ToolRegistry()._tools) == []


def test_enabled_domain_keeps_spec_and_swaps_only_the_handler(monkeypatch):
    plain = ToolRegistry().get("spotify_pause")
    monkeypatch.setenv("EVA_FIRST_PARTY_MCP", "spotify")
    routed = ToolRegistry().get("spotify_pause")
    assert routed.handler is not plain.handler
    for field in ("name", "description", "args_schema", "safety_level", "requires_confirmation", "action_type", "risk"):
        assert getattr(routed, field) == getattr(plain, field)


class _FakeClient:
    def __init__(self, reply):
        self.reply = reply
        self.sent = []

    def call_tool(self, server, name, payload):
        self.sent.append((server.name, name, dict(payload)))
        return self.reply


def _routed(monkeypatch, tool, reply):
    fake = _FakeClient(reply)
    monkeypatch.setattr(first_party, "client", fake)
    monkeypatch.setenv("EVA_FIRST_PARTY_MCP", "all")
    return ToolRegistry().get(tool).handler, fake


def test_send_without_post_approval_flag_carries_no_token(monkeypatch):
    handler, fake = _routed(monkeypatch, "message.send_via_ui", {"ok": True, "content": json.dumps({"ok": False, "needs_confirmation": True})})
    out = handler(recipient="kutty", message="hi")
    assert out["needs_confirmation"] is True
    (server, name, payload), = fake.sent
    assert (server, name) == ("eva-whatsapp", "message.send_via_ui")
    assert APPROVAL_ARG not in payload and "confirmed" not in payload


def test_send_after_approval_carries_a_token_that_verifies(monkeypatch):
    handler, fake = _routed(monkeypatch, "message.send_via_ui", {"ok": True, "content": json.dumps({"ok": True, "sent": True})})
    out = handler(recipient="kutty", message="hi", confirmed=True)
    assert out == {"ok": True, "sent": True}
    payload = fake.sent[0][2]
    assert verify_approval("message.send_via_ui", {"recipient": "kutty", "message": "hi"}, payload[APPROVAL_ARG], first_party._SECRET)
    assert "confirmed" not in payload


def test_failed_server_falls_back_for_safe_tools_but_never_for_sends(monkeypatch):
    down = {"ok": False, "error": "server did not start"}
    pause, _ = _routed(monkeypatch, "spotify_status", down)
    assert "mcp_transport_failed" not in pause()  # the in-process handler answered

    send, fake = _routed(monkeypatch, "message.send_via_ui", down)
    out = send(recipient="kutty", message="hi", confirmed=True)
    assert out["ok"] is False and out["mcp_transport_failed"] is True


def test_gmail_draft_is_shared_through_the_state_file(monkeypatch, tmp_path):
    from backend.eva.tools import email_tools

    state = tmp_path / "draft.json"
    monkeypatch.setenv("EVA_DRAFT_STATE_PATH", str(state))
    email_tools._LAST_DRAFT.clear()
    email_tools._remember_draft({"to": ["a@b.co"], "subject": "hi", "at": __import__("time").time()})
    email_tools._LAST_DRAFT.clear()  # a different process has no in-memory copy
    assert email_tools.pending_draft()["to"] == ["a@b.co"]
    email_tools._LAST_DRAFT.clear()


def test_a_draft_sent_by_the_other_process_cannot_be_sent_again(monkeypatch, tmp_path):
    # Regression: NOVA drafted (memory + file), the Gmail server sent it and cleared only its own memory,
    # so NOVA still had the draft in memory and a second "send" pressed Send again.
    from backend.eva.tools import email_tools

    state = tmp_path / "draft.json"
    monkeypatch.setenv("EVA_DRAFT_STATE_PATH", str(state))
    email_tools._remember_draft({"to": ["a@b.co"], "subject": "hi", "at": __import__("time").time()})
    state.unlink()  # what the server process does after pressing Send
    assert email_tools.pending_draft() is None
    email_tools._LAST_DRAFT.clear()


def test_pressing_send_removes_the_shared_draft(monkeypatch, tmp_path):
    from backend.eva.screen import screen_controller
    from backend.eva.tools import email_tools

    state = tmp_path / "draft.json"
    monkeypatch.setenv("EVA_DRAFT_STATE_PATH", str(state))
    email_tools._remember_draft({"to": ["a@b.co"], "subject": "hi", "at": __import__("time").time()})
    titles = iter(["Draft - Gmail", "Inbox - Gmail"])
    monkeypatch.setattr(email_tools, "_gmail_title", lambda: next(titles, "Inbox - Gmail"))
    monkeypatch.setattr(screen_controller, "real_input_enabled", lambda: True)
    monkeypatch.setattr(screen_controller, "hotkey", lambda keys, reason: __import__("types").SimpleNamespace(success=True))
    monkeypatch.setattr("backend.eva.desktop.focus_window_safe", lambda query: {"ok": True})
    out = email_tools.email_send_drafted(confirmed=True, sleep=lambda seconds: None)
    assert out["sent"] is True and not state.exists() and email_tools.pending_draft() is None


def test_the_draft_file_path_does_not_depend_on_the_working_folder(monkeypatch):
    from backend.eva.mcp.first_party import draft_state_path

    monkeypatch.delenv("EVA_DRAFT_STATE_PATH", raising=False)
    assert draft_state_path().is_absolute()


@pytest.mark.parametrize("domain", sorted(DOMAIN_TOOLS))
def test_server_builds_for_every_domain(domain):
    server = domain_server.build_server(domain)
    assert server.name == f"eva-{domain}"


def test_server_process_never_routes_back_through_mcp(monkeypatch):
    # Regression: a server that inherited the routing flag spawned itself without end.
    monkeypatch.setenv("EVA_FIRST_PARTY_MCP", "all")
    env = first_party.server_config("spotify").env
    assert env["EVA_FIRST_PARTY_MCP"] == "0"
    domain_server.build_server("spotify")
    assert ToolRegistry().get("spotify_pause").handler.__module__ != first_party.__name__
