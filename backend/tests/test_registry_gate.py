"""Executable spec for the central permission gate in ToolRegistry.run().

Target design (see task description / hardening-tool-gate spec):
  * ToolRegistry.run(name, **kwargs) enforces permissions for EVERY call.
    A `confirmed` kwarg is stripped/ignored -- it must not grant anything.
  * A gated (non-allowed) call returns
        {"ok": False, "requires_confirmation": True, "pending_id": "act_...", "message": ...}
    and creates a matching EvaPendingAction in the ledger, plus registers the
    exact call in backend.eva.security.tool_gate's in-memory store.
  * ToolRegistry.run_approved(pending_id) executes the call for real, but
    only if the ledger action is confirmed AND the pending call is still in
    the in-memory store.

None of this exists on the current branch: ToolRegistry.run() just calls the
handler directly, several handlers (file.copy, screen.*) have no gate at
all, and ToolRegistry.run_approved does not exist. Most tests below are
therefore expected to FAIL until the fix lands.

Note on tool names: the actual registry uses dotted names (file.delete,
file.write_text, file.copy, screen.type_text, screen.hotkey), not the
underscore names sketched in the original task description. Tests use the
real names so they reflect the real registry.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.tests.conftest import import_tool_gate


def test_file_delete_requires_confirmation_and_creates_pending_override(sandbox_dir):
    from backend.eva.permissions.ledger import get_pending_action
    from backend.eva.tools.registry import ToolRegistry

    target = sandbox_dir / "victim.txt"
    target.write_text("keep me", encoding="utf-8")
    registry = ToolRegistry()

    result = registry.run("file.delete", path=str(target), confirmed=True)

    assert result.get("ok") is False, (
        f"file.delete with confirmed=True kwarg must not bypass the gate: {result}"
    )
    assert result.get("requires_confirmation") is True, f"unexpected result: {result}"
    pending_id = result.get("pending_id")
    assert isinstance(pending_id, str) and pending_id.startswith("act_"), (
        f"missing/invalid pending_id in gated result: {result}"
    )
    assert target.exists(), "file was deleted despite missing ledger confirmation"

    pending = get_pending_action(pending_id)
    assert pending is not None, "gated call did not create a ledger entry"
    assert pending.status == "pending_override", f"unexpected ledger status: {pending.status}"
    assert pending.requires_override is True, "file.delete is a DESTRUCTIVE_FILE_ACTION/dangerous tool and must require override"


def test_file_write_text_requires_confirmation(sandbox_dir):
    from backend.eva.tools.registry import ToolRegistry

    target = sandbox_dir / "should_not_exist.txt"
    registry = ToolRegistry()

    result = registry.run("file.write_text", path=str(target), content="malicious content", confirmed=True)

    assert result.get("ok") is False
    assert result.get("requires_confirmation") is True, f"unexpected result: {result}"
    assert not target.exists(), "file.write_text executed despite missing ledger confirmation"


def test_file_copy_refused_without_confirmation(sandbox_dir):
    """file.copy currently has NO gate at all (safety_level='safe',
    action_type='SAFE_LOCAL_READ') -- it copies immediately. The target
    design requires every non-safe-read call to go through the gate; a tool
    that duplicates arbitrary local file contents to an arbitrary
    destination should not be exempt just because its current spec labels
    it 'safe'. This test intentionally fails today.
    """
    from backend.eva.tools.registry import ToolRegistry

    src = sandbox_dir / "src.txt"
    src.write_text("some contents", encoding="utf-8")
    dst = sandbox_dir / "dst.txt"
    registry = ToolRegistry()

    result = registry.run("file.copy", src=str(src), dst=str(dst))

    assert result.get("requires_confirmation") is True, f"file.copy ran without gating: {result}"
    assert not dst.exists(), "file.copy executed despite missing confirmation"


def test_screen_type_text_refused_before_handler_runs(monkeypatch):
    """screen.type_text is currently safety_level='safe' / SAFE_LOCAL_UI and
    runs immediately. Confirm refusal happens BEFORE pyautogui-backed code is
    ever invoked, by making the underlying handler blow up if called.
    """
    import backend.eva.tools.registry as registry_module

    def _boom(*_args, **_kwargs):
        raise AssertionError("screen_type_text handler must not run before confirmation")

    monkeypatch.setattr(registry_module, "screen_type_text", _boom)
    registry = registry_module.ToolRegistry()

    result = registry.run("screen.type_text", text="hello", reason="test")

    assert result.get("requires_confirmation") is True, f"unexpected result: {result}"


def test_screen_hotkey_refused_before_handler_runs(monkeypatch):
    import backend.eva.tools.registry as registry_module

    def _boom(*_args, **_kwargs):
        raise AssertionError("screen_hotkey handler must not run before confirmation")

    monkeypatch.setattr(registry_module, "screen_hotkey", _boom)
    registry = registry_module.ToolRegistry()

    result = registry.run("screen.hotkey", keys=["ctrl", "c"], reason="test")

    assert result.get("requires_confirmation") is True, f"unexpected result: {result}"


def test_safe_read_tool_still_works():
    """Lock-in: safe read-only tools must keep working with no confirmation."""
    from backend.eva.tools.registry import ToolRegistry

    registry = ToolRegistry()
    result = registry.run("workspace_status")

    assert result.get("ok") is True
    assert result.get("requires_confirmation") is not True


def test_gate_registers_pending_call_in_memory(sandbox_dir):
    from backend.eva.tools.registry import ToolRegistry

    tool_gate = import_tool_gate()

    target = sandbox_dir / "victim2.txt"
    target.write_text("keep me", encoding="utf-8")
    registry = ToolRegistry()

    result = registry.run("file.delete", path=str(target), confirmed=True)
    pending_id = result.get("pending_id")
    assert pending_id, f"gate result missing pending_id: {result}"

    stored = tool_gate.get_pending_call(pending_id)
    assert stored is not None, "register_pending_call did not persist the call for its pending_id"


def test_full_approved_flow_executes_for_real(sandbox_dir):
    from backend.eva.permissions.ledger import confirm_pending_action, get_pending_action
    from backend.eva.tools.registry import ToolRegistry

    target = sandbox_dir / "approved_write.txt"
    registry = ToolRegistry()

    gated = registry.run("file.write_text", path=str(target), content="hello world", confirmed=True)
    assert gated.get("requires_confirmation") is True, f"unexpected gate result: {gated}"
    pending_id = gated.get("pending_id")
    assert pending_id, f"gate result did not include a pending_id: {gated}"

    pending = get_pending_action(pending_id)
    assert pending is not None, "gated call did not create a ledger entry"
    confirm_result = confirm_pending_action(pending_id, override=bool(pending.requires_override))
    assert confirm_result.success, confirm_result.message

    if not hasattr(registry, "run_approved"):
        pytest.fail("ToolRegistry.run_approved is not implemented yet.", pytrace=False)
    executed = registry.run_approved(pending_id)

    assert executed.get("ok") is True, f"approved execution failed: {executed}"
    assert target.exists(), "run_approved did not actually perform the approved write"
    assert target.read_text(encoding="utf-8") == "hello world"


def test_run_approved_refuses_unknown_pending_id():
    from backend.eva.tools.registry import ToolRegistry

    registry = ToolRegistry()
    if not hasattr(registry, "run_approved"):
        pytest.fail("ToolRegistry.run_approved is not implemented yet.", pytrace=False)

    result = registry.run_approved("act_does_not_exist_000000000000")

    assert result.get("ok") is False, f"unknown pending_id must be refused: {result}"


def test_run_approved_refuses_unconfirmed_pending_action(sandbox_dir):
    from backend.eva.tools.registry import ToolRegistry

    target = sandbox_dir / "unconfirmed.txt"
    registry = ToolRegistry()

    gated = registry.run("file.write_text", path=str(target), content="nope", confirmed=True)
    pending_id = gated.get("pending_id")
    assert pending_id, f"gate result did not include a pending_id: {gated}"

    if not hasattr(registry, "run_approved"):
        pytest.fail("ToolRegistry.run_approved is not implemented yet.", pytrace=False)

    result = registry.run_approved(pending_id)  # never confirmed via the ledger

    assert result.get("ok") is False, f"unconfirmed pending action must be refused: {result}"
    assert not target.exists()


def test_run_approved_refuses_expired_pending_action(sandbox_dir):
    from backend.eva.permissions import ledger as ledger_module
    from backend.eva.tools.registry import ToolRegistry

    target = sandbox_dir / "expired.txt"
    target.write_text("keep me too", encoding="utf-8")
    registry = ToolRegistry()

    gated = registry.run("file.delete", path=str(target), confirmed=True)
    pending_id = gated.get("pending_id")
    assert pending_id, f"gate result did not include a pending_id: {gated}"

    pending = ledger_module.get_pending_action(pending_id)
    assert pending is not None
    pending.expires_at = "2000-01-01T00:00:00+00:00"
    ledger_module._append(pending, note="test_forced_expiry")

    if not hasattr(registry, "run_approved"):
        pytest.fail("ToolRegistry.run_approved is not implemented yet.", pytrace=False)

    result = registry.run_approved(pending_id)

    assert result.get("ok") is False, f"expired pending action must be refused: {result}"
