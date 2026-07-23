"""Standalone verifier for Phase 88 (approved gated actions actually execute).

Sweeping the last gated tools -- the power pair and the message pair -- through
real ledger approval surfaced this: `registry.run` STRIPS `confirmed`/`_approved`
at the untrusted entry so a caller cannot self-approve. But a few handlers
self-guard on `confirmed` as a SECOND check beyond the gate (system_power /
_guarded_power_action return guidance; message.send_via_ui re-evaluates the gate
with user_confirmed). Because the flag was stripped, `run_approved` replayed
those handlers WITHOUT it, so an override/confirm-approved shutdown/restart/
sleep/message never ran -- it re-asked for confirmation forever.

Fix: `run_approved` -- the ONE trusted path, unreachable unless action.status is
already `confirmed` -- re-injects `confirmed=True` for handlers that accept a
`confirmed` parameter. File handlers whose lambda drops it (gate is sole
enforcement) are untouched.

Fully offline. NO real power action executes: system_power is swapped for a spy,
and the confirmed=False guidance branch (the safe branch) proves the handler's
own guard is intact. message.send_via_ui is a harmless stub (returns a dict, no
external IO), so it can be driven end-to-end for real.
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
    import eva.tools.registry as registry_mod
    from eva.permissions.ledger import confirm_pending_action
    from eva.tools.desktop import system_power
    from eva.tools.registry import ToolRegistry, _guarded_power_action, _handler_accepts_confirmed

    # ------------------------------------------------------------------ helper
    check(_handler_accepts_confirmed(system_power) is True, "handler detector missed system_power's confirmed param")
    check(_handler_accepts_confirmed(_guarded_power_action) is True, "handler detector missed _guarded_power_action")
    check(_handler_accepts_confirmed(lambda **kw: None) is True, "handler detector missed **kwargs")
    check(_handler_accepts_confirmed(lambda path, content: None) is False, "handler detector wrongly flagged a file-shaped lambda")
    r0 = ToolRegistry()
    check(_handler_accepts_confirmed(r0._tools["file.write_text"].handler) is False, "file.write_text must NOT be treated as confirmed-accepting")

    # ------------------------------------------------------------------ guard intact
    guidance = _guarded_power_action("shutdown")  # confirmed defaults False -> must NOT run
    check("confirm" in guidance.lower(), "power handler lost its own confirmed guard")
    check("shutting down" not in guidance.lower(), "power handler executed without confirmation (guard broken)")

    # ------------------------------------------------------------------ approved power re-injects confirmed (spy, no real action)
    calls: list[dict] = []

    def spy(action, confirmed=False):
        calls.append({"action": action, "confirmed": confirmed})
        return f"[spy] {action} confirmed={confirmed}"

    original = registry_mod.system_power
    registry_mod.system_power = spy
    try:
        r = ToolRegistry()
        res = r.run("guarded_power_action", action="sleep")
        pid = res.get("pending_id")
        check(bool(pid), "guarded_power_action did not create a gated pending")
        confirm_pending_action(pid, override=True)
        out = r.run_approved(pid)
    finally:
        registry_mod.system_power = original

    check(bool(calls), "approved power handler was never invoked")
    check(calls[-1]["confirmed"] is True, "run_approved did not re-inject confirmed=True for the power handler")
    check("confirmed=True" in str(out), "approved power run did not reflect the executed (confirmed) reply")

    # ------------------------------------------------------------------ approved message actually sends (real, harmless stub)
    r2 = ToolRegistry()
    mres = r2.run("message.send_via_ui", recipient="Alex", message="on my way")
    mpid = mres.get("pending_id")
    check(bool(mpid), "message.send_via_ui did not create a gated pending")
    confirm_pending_action(mpid)  # confirm-class, not override
    mout = r2.run_approved(mpid)
    check(isinstance(mout, dict) and mout.get("ok") is True, f"approved message did not send: {mout!r}")
    check(mout.get("requires_confirmation") is not True, "approved message still asked to re-confirm")

    # ------------------------------------------------------------------ registration
    import verify_eva_all

    name = "verify_eva_phase88_approved_confirmed_reinjected.py"
    check(name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 88 verifier")
    check(name in verify_eva_all.QUICK_VERIFIERS, "quick profile missing the Phase 88 verifier")
    check(name in verify_eva_all.VERIFIER_DESCRIPTORS, "master descriptor missing the Phase 88 verifier")

    print(
        "PASS: Phase 88 approved gated actions execute. registry.run strips confirmed/_approved at the untrusted "
        "entry, but system_power/guarded_power_action and message.send_via_ui self-guard on confirmed as a second "
        "check -- so run_approved replayed them without it and an approved shutdown/message re-asked for confirmation "
        "forever. run_approved (the trusted, confirmed-only replay path) now re-injects confirmed=True for handlers "
        "that accept it; file handlers that drop it are untouched. Proven with a system_power spy (no real power "
        "action) and a real end-to-end message send."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
