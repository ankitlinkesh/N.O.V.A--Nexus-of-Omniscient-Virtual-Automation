"""Standalone verifier for Phase 86 (gate execution honesty).

Found during the gate stress-test, driving gated tools through real ledger
approval:

Bug A -- a successful screen capture was reported as a failure. `_with_execution`
in confirmation.py decides success via `executed.get("ok")`, but `_capture_screen`
in registry.py returned a dict with NO `ok` key. So approving `capture_screen`
fell into the failure branch and answered "I confirmed `act_...`, but execution
did not complete." even though the screenshot was taken and saved to disk. Fixed
by adding `"ok": True` to `_capture_screen`'s returned dict, matching the
convention every other tool follows.

Bug B -- a gated call missing a required arg crashed on approval. `screen.observe`
requires `reason` in its args_schema, but `ToolRegistry.run` never validates
args_schema before creating the gated pending -- so issuing it without `reason`
still creates a pending. On approval, `run_approved` reached
`self._invoke(spec, dict(stored["args"]))`, which calls `spec.handler(**args)`
and raised `TypeError: missing 1 required positional argument: 'reason'` -- an
unhandled crash AFTER the user already approved the action. Fixed by wrapping
only that final call inside `run_approved` in try/except, converting the crash
into a clean `{"ok": False, "error": ...}` the confirm handoff reports as "did
not complete" -- the normal (ungated) run path still calls `_invoke` directly
and is unaffected.

What this verifies:
  1. An approved `capture_screen` reports success end to end (real ledger flow).
  2. `_capture_screen()` itself returns `ok: True`.
  3. `run_approved` on a malformed stored call (missing required arg) returns a
     clean `ok: False` + error instead of raising.

Fully offline and DETERMINISTIC: the screen capture is stubbed, because
`_capture_screen` raises when the display cannot be grabbed (screen locked, or
under load during a long suite run) and Fix B then correctly turns that into
ok:False -- which is exactly the intended honest-failure path, not the behaviour
under test here ("a SUCCESSFUL capture reports success"). A first version of this
check drove a real screenshot and passed in isolation but flaked inside the full
4-minute sweep for exactly that reason; stubbing removes the live-hardware
dependency.
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def check(value: object, message: str) -> None:
    if not value:
        raise AssertionError(message)


def main() -> int:
    from eva.core.config import load_project_env

    load_project_env(ROOT)

    import eva.tools.registry as registry_mod
    from eva.permissions.confirmation import handle_confirmation_command
    from eva.tools.registry import ToolRegistry, _capture_screen

    # Stub the capture so a successful capture is deterministic (see the module
    # docstring): the behaviour under test is "success reports success", not
    # whether the display can be grabbed at this instant.
    #
    # Phase 108 renamed this function and changed it to return (bytes, region).
    # A bare attribute assignment does NOT raise on a name that no longer exists
    # -- it creates a dead one and lets the REAL capture run, so the stub quietly
    # stops stubbing and the verifier keeps passing. Assert the target is there
    # before replacing it.
    from eva.screen.capture import CaptureRegion

    if not hasattr(registry_mod, "capture_screen_jpeg"):
        raise SystemExit("verify_eva_phase86: capture_screen_jpeg is gone; this stub would patch nothing")
    registry_mod.capture_screen_jpeg = lambda quality=74, region=None: (
        b"\xff\xd8\xff\xe0\x00\x10JFIF fake",
        region or CaptureRegion(0, 0, 1920, 1080),
    )

    # ------------------------------------------------------------------ 2 (ok key present)
    capture = _capture_screen()
    check(isinstance(capture, dict), "_capture_screen did not return a dict")
    check(capture.get("ok") is True, "_capture_screen does not report ok: True on a successful capture")

    # ------------------------------------------------------------------ 1 (approved capture_screen reports success)
    registry = ToolRegistry()
    issued = registry.run("capture_screen")
    pid = issued.get("pending_id")
    check(pid, "capture_screen did not create a gated pending as expected")

    # A single `confirm override <id>` both confirms in the ledger AND triggers
    # the tool-gate execution handoff (real approval path, not a double confirm).
    out = handle_confirmation_command(f"confirm override {pid}")
    check("did not complete" not in out.lower(), "an approved capture_screen was still reported as not completing")
    check(
        "successfully" in out.lower() or "executed" in out.lower(),
        "an approved capture_screen did not report success",
    )

    # ------------------------------------------------------------------ 3 (graceful failure, not a crash)
    from eva.permissions.ledger import confirm_pending_action

    bad = registry.run("screen.observe")  # missing required `reason`
    bad_pid = bad.get("pending_id")
    check(bad_pid, "screen.observe (no reason) did not create a gated pending as expected")
    confirm_pending_action(bad_pid, override=True)

    result = registry.run_approved(bad_pid)  # must not raise
    check(isinstance(result, dict), "run_approved did not return a dict on a malformed stored call")
    check(result.get("ok") is False, "run_approved did not report ok: False on a malformed stored call")
    check(
        "execution failed" in str(result.get("error", "")).lower(),
        "run_approved's graceful failure did not surface an 'execution failed' error",
    )

    # ------------------------------------------------------------------ registration
    import verify_eva_all

    name = "verify_eva_phase86_gate_execution.py"
    check(name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 86 verifier")
    check(name in verify_eva_all.QUICK_VERIFIERS, "quick profile missing the Phase 86 verifier")
    check(name in verify_eva_all.VERIFIER_DESCRIPTORS, "master descriptor missing the Phase 86 verifier")

    print(
        "PASS: Phase 86 gate execution honesty. `_capture_screen` now returns `ok: True` on a successful capture, so "
        "approving `capture_screen` reports success instead of the false 'execution did not complete' -- the same "
        "`ok`-key convention every other tool already follows. And `run_approved` no longer lets a malformed stored "
        "call (a gated pending missing a required arg, e.g. `screen.observe` without `reason`) escape as an unhandled "
        "TypeError after the user already approved it -- it now returns a clean ok:False + error, verified end to end "
        "through real ledger approval."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
