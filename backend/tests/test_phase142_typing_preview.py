"""Phase 142: an approval to type shows what it will type, unless it looks secret.

The live PC scorecard's multi-step task (read a number from a file, type "14*3=" into
Calculator) stopped at a prompt reading `screen.type_text(text='[HIDDEN]', ...)`: the
ledger masks typed text (it may be a password) and the prompt used the same masked
args, so the user was asked to approve typing without seeing what. The prompt now
shows short, non-secret text; the ledger stays masked either way.
"""
from __future__ import annotations

from eva.permissions.ledger import ledger_path
from eva.tools.registry import ToolRegistry, _typing_preview


def test_prompt_shows_plain_text_and_ledger_stays_masked(eva_pending_action_ledger_path):
    result = ToolRegistry().run("screen.type_text", text="14*3=", reason="probe")
    assert result.get("requires_confirmation") is True
    assert "It will type exactly: `14*3=`" in result["message"]
    raw = ledger_path().read_text(encoding="utf-8")
    assert "14*3=" not in raw and "[HIDDEN]" in raw


def test_secret_shaped_text_is_not_shown(eva_pending_action_ledger_path):
    result = ToolRegistry().run("screen.type_text", text="Hunter2!xQ", reason="probe")
    assert "Hunter2!xQ" not in result["message"]
    assert "hidden here because it looks like a secret" in result["message"]
    assert "Hunter2!xQ" not in ledger_path().read_text(encoding="utf-8")


def test_preview_rules():
    window = {"title": "Calculator"}
    assert _typing_preview("screen.type_text", {"text": "hello world"}, window) == "\nIt will type exactly: `hello world` into Calculator."
    for hidden in ("123456", "x" * 81, "a`b", "two\nlines", "sk-abcdefghijklmnopqrstu"):
        assert "hidden here" in _typing_preview("screen.type_text", {"text": hidden}, None), hidden
    assert _typing_preview("file.copy", {"text": "anything"}, None) == ""
