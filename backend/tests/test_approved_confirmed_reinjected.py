"""Executable spec for Phase 88 (approved gated actions actually execute).

Found by sweeping the last gated tools -- the power pair and the message pair --
through real ledger approval:

`registry.run` STRIPS the `confirmed`/`_approved` flags at the untrusted entry so
a planner LLM or HTTP client cannot self-approve (see registry.py ~line 1554).
But a few handlers self-guard on `confirmed` as a SECOND check beyond the gate:
  * system_power / _guarded_power_action -> returns "say 'confirm shutdown'..."
  * message.send_via_ui -> re-evaluates the gate with user_confirmed=confirmed
Because the flag was stripped, `run_approved` replayed the stored args WITHOUT
it, so an override/confirm-approved shutdown/restart/sleep/message never ran --
it just re-asked for confirmation forever. The user approved and nothing happened.

Fix: `run_approved` -- the ONE trusted replay path, unreachable unless
action.status is already `confirmed` -- re-injects `confirmed=True` for handlers
that actually accept a `confirmed` parameter. Handlers whose lambda drops it
(file.write_text/copy/move/delete, where the gate is the sole enforcement) are
untouched, so they cannot start receiving an unexpected kwarg.

NO REAL POWER ACTION IS EXECUTED here: system_power is monkeypatched to a spy,
and the confirmed=False guidance path (the safe branch) is used to prove the
handler's own guard is intact.
"""

from __future__ import annotations

import eva.tools.registry as registry_mod
from eva.permissions.ledger import confirm_pending_action
from eva.tools.registry import (
    ToolRegistry,
    _guarded_power_action,
    _handler_accepts_confirmed,
)


class TestHandlerAcceptsConfirmed:
    def test_true_for_named_confirmed_param(self) -> None:
        assert _handler_accepts_confirmed(lambda action, confirmed=False: None) is True

    def test_true_for_the_real_power_handlers(self) -> None:
        from eva.tools.desktop import system_power

        assert _handler_accepts_confirmed(system_power) is True
        assert _handler_accepts_confirmed(_guarded_power_action) is True

    def test_true_for_var_keyword(self) -> None:
        assert _handler_accepts_confirmed(lambda **kw: None) is True

    def test_false_for_handler_without_confirmed(self) -> None:
        # The file-tool shape: the lambda deliberately drops `confirmed`.
        assert _handler_accepts_confirmed(lambda path, content: None) is False

    def test_false_for_the_real_file_handler(self) -> None:
        r = ToolRegistry()
        spec = r._tools["file.write_text"]
        assert _handler_accepts_confirmed(spec.handler) is False


class TestPowerGuardIsUnchanged:
    """The fix must not weaken the handler's own guard: without confirmed it
    still refuses to execute (returns guidance, spawns no process)."""

    def test_guarded_power_action_without_confirmed_returns_guidance(self) -> None:
        out = _guarded_power_action("shutdown")
        assert "confirm" in out.lower()
        # crucial: it did not run -- the reply is the guidance, not "Shutting down".
        assert "shutting down" not in out.lower()


class TestApprovedPowerReinjectsConfirmed:
    def test_run_approved_calls_power_handler_with_confirmed_true(self, monkeypatch) -> None:
        calls: list[dict] = []

        def spy(action, confirmed=False):
            calls.append({"action": action, "confirmed": confirmed})
            return f"[spy] {action} confirmed={confirmed}"

        # _guarded_power_action resolves `system_power` from the registry module
        # global; patch it so NO real shutdown/sleep is ever attempted.
        monkeypatch.setattr(registry_mod, "system_power", spy)

        r = ToolRegistry()
        res = r.run("guarded_power_action", action="sleep")
        pid = res.get("pending_id")
        assert pid, "guarded_power_action did not create a gated pending"

        confirm_pending_action(pid, override=True)
        out = r.run_approved(pid)

        assert calls, "the power handler was never invoked after approval"
        assert calls[-1]["confirmed"] is True, "run_approved did not re-inject confirmed=True"
        assert "confirmed=True" in str(out)


class TestApprovedMessageActuallySends:
    """Real end-to-end: message.send_via_ui is a harmless stub (returns a dict,
    no external IO). Before the fix, approval replayed it without confirmed, the
    handler re-gated with user_confirmed=False, and it answered
    requires_confirmation forever."""

    def test_approved_message_reports_sent_not_reconfirm(self) -> None:
        r = ToolRegistry()
        res = r.run("message.send_via_ui", recipient="Alex", message="on my way")
        pid = res.get("pending_id")
        assert pid, "message.send_via_ui did not create a gated pending"

        # EXTERNAL_MESSAGE_SEND is confirm-class (not override-class like power),
        # so a plain `confirm` is the right approval here.
        confirm_pending_action(pid)
        out = r.run_approved(pid)

        assert isinstance(out, dict)
        assert out.get("ok") is True, f"approved message did not send: {out!r}"
        assert out.get("requires_confirmation") is not True
