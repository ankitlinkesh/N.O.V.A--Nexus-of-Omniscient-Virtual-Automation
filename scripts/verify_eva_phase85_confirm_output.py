"""Standalone verifier for Phase 85 (approved-action output surfaced).

Found during the gate stress-test: after `confirm override <id>`, the tool-gate
handoff executed the tool but answered with a bare "Executed successfully.",
dropping the result the user approved the action to see -- a `$ git status` you
approved showed you nothing. It is the exact "computed, returned, then dropped"
shape the _FAILURE_REASON_KEYS note in confirmation.py already records, on the
success side (the failure path had already learned this in Phase 68).

The fix surfaces the output, with the SAME safety discipline: a deliberate key
allowlist (text/summary/output), never a dict dump, because a tool result can
also carry page text, raw file content, or a decrypted secret.

What this verifies:
  1. An approved READ shows its output (end to end, real ledger approval).
  2. Untrusted output is flagged as data-not-instructions.
  3. An actuation with no output key keeps the plain "successfully" line (no
     over-reach), and its effect really happens.
  4. A sensitive key (secret/content/value) is NEVER echoed -- the allowlist is
     doing its job, not a dict dump.

Offline except one bounded, read-only `git status` the user-equivalent approves.
"""

from __future__ import annotations

import re
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

    from eva.core.fast_commands import maybe_handle_fast_command
    from eva.permissions.confirmation import _SUCCESS_OUTPUT_KEYS, _success_output, handle_confirmation_command
    from eva.tools.registry import ToolRegistry
    from eva.tools.safe_file_tools import SAFE_ROOT

    # ------------------------------------------------------------------ 4 (allowlist)
    check(_success_output({"ok": True, "text": "hello"}) == "hello", "text output was not surfaced")
    check(_success_output({"text": "T", "summary": "S", "output": "O"}) == "T", "output key precedence wrong")
    check(_success_output({"ok": True, "path": "/x", "checkpoint": "c"}) == "", "an actuation with no output key leaked something")
    check(
        _success_output({"ok": True, "secret": "hunter2", "content": "bytes", "value": "s3cr3t"}) == "",
        "a sensitive key was echoed -- the allowlist is not holding",
    )
    for forbidden in ("secret", "content", "value", "stdout", "ciphertext"):
        check(forbidden not in _SUCCESS_OUTPUT_KEYS, f"`{forbidden}` must not be in the success-output allowlist")

    # ------------------------------------------------------------------ 1 + 2 (read shows output, flagged untrusted)
    registry = ToolRegistry()
    issued = maybe_handle_fast_command("$ git status", registry, {})
    check(issued is not None, "the console did not handle `$ git status`")
    pid = re.search(r"act_[0-9a-f]+", issued[0])
    check(pid is not None, "no pending id was issued for the gated command")
    result = maybe_handle_fast_command(f"confirm override {pid.group(0)}", registry, {})[0]
    check("branch" in result.lower() or "commit" in result.lower(), "the approved git status did not surface its output")
    check("executed successfully." not in result.lower() or "branch" in result.lower(), "the bare success line still swallowed the output")
    check("untrusted" in result.lower(), "untrusted command output was not flagged as data-not-instructions")

    # ------------------------------------------------------------------ 3 (actuation keeps plain success + effect happens)
    target = Path(SAFE_ROOT) / "_p85_verify_write.txt"
    if target.exists():
        target.unlink()
    try:
        w = registry.run("file.write_text", path=str(target), content="phase85")
        wpid = w.get("pending_id")
        check(wpid and not target.exists(), "file.write_text executed before approval -- the gate did not hold")
        out = handle_confirmation_command(f"confirm override {wpid}")
        check("successfully" in out.lower(), "an approved write did not report success")
        check(target.exists() and target.read_text() == "phase85", "the approved write did not actually happen")
    finally:
        if target.exists():
            target.unlink()

    # ------------------------------------------------------------------ registration
    import verify_eva_all

    name = "verify_eva_phase85_confirm_output.py"
    check(name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 85 verifier")
    check(name in verify_eva_all.QUICK_VERIFIERS, "quick profile missing the Phase 85 verifier")
    check(name in verify_eva_all.VERIFIER_DESCRIPTORS, "master descriptor missing the Phase 85 verifier")

    print(
        "PASS: Phase 85 approved-action output. After `confirm override <id>` the tool-gate handoff used to answer "
        "'Executed successfully.' and drop the result -- an approved `$ git status` showed nothing, the same "
        "computed-then-dropped shape the failure path had already fixed. Output is now surfaced through a deliberate "
        "key allowlist (text/summary/output), never a dict dump, so a decrypted secret or raw file content is never "
        "echoed just because the action succeeded; untrusted command output is flagged as data-not-instructions; and "
        "an actuation with no output (file.write) keeps the plain success line while its effect really happens, proven "
        "end to end through real ledger approval."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
