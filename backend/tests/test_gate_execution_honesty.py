"""Executable spec for Phase 86 (gate execution honesty).

Found by driving gated tools through real ledger approval:

Bug A -- a successful screen capture was reported as a failure. `_capture_screen`
returned a dict with no `ok` key, but `_with_execution` in confirmation.py decides
success via `executed.get("ok")`. So approving `capture_screen` fell into the
failure branch and answered "I confirmed `act_...`, but execution did not
complete." even though the screenshot was taken and saved.

Bug B -- a gated call missing a required arg crashed on approval. `screen.observe`
requires `reason` in its args_schema, but `ToolRegistry.run` never validates
args_schema before creating the gated pending. On approval, `run_approved` reached
`self._invoke(spec, dict(stored["args"]))` and `spec.handler(**args)` raised
`TypeError: missing 1 required positional argument: 'reason'` -- an unhandled
crash after the user already approved the action.

Pinned:
  1. Approving `capture_screen` reports success end to end (real ledger flow).
  2. `_capture_screen()` itself returns `ok: True`.
  3. `run_approved` on a malformed stored call (missing required arg) returns a
     clean `ok: False` + error, and does not raise.
"""

from __future__ import annotations

import eva.tools.registry as registry_mod
from eva.permissions.ledger import confirm_pending_action
from eva.screen.capture import CaptureRegion
from eva.tools.registry import ToolRegistry, _capture_screen

# A tiny fake JPEG. The capture is stubbed so these tests are DETERMINISTIC:
# `_capture_screen` calls the real `capture_screen_jpeg`, which raises when the
# display cannot be grabbed (screen locked, under load) -- and Fix B then
# correctly turns that raise into ok:False, which is exactly the "did not
# complete" the flaky first version of this test tripped over during a long full
# suite run. The behaviour under test is "a SUCCESSFUL capture reports success",
# so we make the capture deterministically succeed rather than depend on live
# hardware. (Capture actually failing -> honest failure is a separate, correct path.)
#
# Phase 108 renamed the function and made it return (bytes, region) rather than
# aliasing the old name. `monkeypatch.setattr` with `raising=True` is what keeps
# that honest: a stub patching a name that no longer exists would silently
# exercise the real capture instead, which is the failure this whole file is about.
_FAKE_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF fake"
_FAKE_REGION = CaptureRegion(left=0, top=0, width=1920, height=1080)


def _stub_capture(monkeypatch) -> None:
    monkeypatch.setattr(
        registry_mod,
        "capture_screen_jpeg",
        lambda quality=74, region=None: (_FAKE_JPEG, region or _FAKE_REGION),
        raising=True,
    )


class TestCaptureScreenApprovalReportsSuccess:
    def test_approved_capture_screen_is_not_reported_as_failed(self, monkeypatch) -> None:
        from eva.permissions.confirmation import handle_confirmation_command

        _stub_capture(monkeypatch)
        r = ToolRegistry()
        res = r.run("capture_screen")
        pid = res.get("pending_id")
        assert pid, "capture_screen did not create a gated pending as expected"

        # A single `confirm override <id>` both confirms in the ledger AND
        # triggers the tool-gate execution handoff (handle_confirmation_command
        # -> confirm_pending_action -> _with_execution -> run_approved).
        out = handle_confirmation_command(f"confirm override {pid}")

        assert "did not complete" not in out.lower()
        assert "successfully" in out.lower() or "executed" in out.lower()

    def test_capture_screen_returns_ok_true(self, monkeypatch) -> None:
        _stub_capture(monkeypatch)
        result = _capture_screen()
        assert isinstance(result, dict)
        assert result.get("ok") is True


class TestRunApprovedFailsGracefullyOnMalformedCall:
    def test_missing_required_arg_does_not_crash_run_approved(self) -> None:
        r = ToolRegistry()
        # screen.observe requires `reason`; calling it without one still gets
        # gated (args_schema is not checked before the pending is created).
        res = r.run("screen.observe")
        pid = res.get("pending_id")
        assert pid, "screen.observe (no reason) did not create a gated pending as expected"

        confirm_pending_action(pid, override=True)

        # This must not raise -- the crash this test pins was a TypeError from
        # spec.handler(**args) escaping run_approved after approval.
        out = r.run_approved(pid)

        assert isinstance(out, dict)
        assert out.get("ok") is False
        assert "execution failed" in str(out.get("error", "")).lower()
