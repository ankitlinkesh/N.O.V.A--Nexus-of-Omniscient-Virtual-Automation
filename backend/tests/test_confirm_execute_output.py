"""Executable spec for surfacing approved-action output (Phase 85).

Found during the gate stress-test: after `confirm override <id>`, the handoff
executed the tool but returned a bare "Executed successfully." -- dropping the
result the user approved the action to see. A `$ git status` you approved showed
you nothing. It is the exact "computed, returned, then dropped" shape the
_FAILURE_REASON_KEYS note already records, on the success side.

The fix surfaces the tool's output, but with the SAME safety discipline: a
deliberate key allowlist, never a dict dump, because a tool result can also
carry page text, raw file content, or a decrypted secret.

Pinned:
  1. An output-carrying success (text/summary/output) is shown, not swallowed.
  2. Untrusted output is flagged.
  3. An actuation with no output key keeps the plain "successfully" line.
  4. A non-allowlisted key (a secret, file content) is NEVER echoed.
"""

from __future__ import annotations

import re

from eva.permissions.confirmation import _SUCCESS_OUTPUT_KEYS, _success_output


class TestSuccessOutputAllowlist:
    def test_picks_the_first_present_allowlisted_key(self) -> None:
        assert _success_output({"ok": True, "text": "hello"}) == "hello"
        assert _success_output({"ok": True, "summary": "did the thing"}) == "did the thing"
        assert _success_output({"ok": True, "output": "result"}) == "result"

    def test_prefers_text_over_summary_over_output(self) -> None:
        assert _success_output({"text": "T", "summary": "S", "output": "O"}) == "T"

    def test_no_output_key_yields_empty(self) -> None:
        """An actuation (file.write returns ok/path/checkpoint) carries none of
        these, so the caller keeps the plain success line."""
        assert _success_output({"ok": True, "path": "/tmp/x", "checkpoint": "c"}) == ""

    def test_a_sensitive_key_is_never_echoed(self) -> None:
        """The whole reason this is an allowlist: a decrypted secret or raw file
        content must not be surfaced just because the action succeeded."""
        assert _success_output({"ok": True, "secret": "hunter2", "content": "file bytes", "value": "s3cr3t"}) == ""
        assert "secret" not in _SUCCESS_OUTPUT_KEYS
        assert "content" not in _SUCCESS_OUTPUT_KEYS
        assert "value" not in _SUCCESS_OUTPUT_KEYS


class TestEndToEndThroughTheApprovalFlow:
    def _run(self, msg, registry):
        from eva.core.fast_commands import maybe_handle_fast_command

        return maybe_handle_fast_command(msg, registry, {})

    def test_approved_read_shows_its_output(self) -> None:
        from eva.tools.registry import ToolRegistry

        r = ToolRegistry()
        issued = self._run("$ git status", r)
        pid = re.search(r"act_[0-9a-f]+", issued[0]).group(0)
        result = self._run(f"confirm override {pid}", r)[0]
        # The actual git output is now present, not just "Executed successfully".
        assert "On branch" in result or "branch" in result.lower()
        assert "untrusted" in result.lower()

    def test_approved_write_keeps_plain_success(self) -> None:
        from pathlib import Path

        from eva.tools.registry import ToolRegistry
        from eva.tools.safe_file_tools import SAFE_ROOT

        r = ToolRegistry()
        target = Path(SAFE_ROOT) / "_p85_write_test.txt"
        if target.exists():
            target.unlink()
        try:
            issued = r.run("file.write_text", path=str(target), content="hi")
            pid = issued.get("pending_id")
            from eva.permissions.confirmation import handle_confirmation_command

            out = handle_confirmation_command(f"confirm override {pid}")
            assert "successfully" in out.lower()
            assert target.read_text() == "hi"  # effect really happened
        finally:
            if target.exists():
                target.unlink()
