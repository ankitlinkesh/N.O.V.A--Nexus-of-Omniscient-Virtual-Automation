"""A refused execution must tell the user WHY (Phase 68).

Found by live driving, not by the suite: a staged form submission correctly
refused because the browser origin changed between staging and approval
(localhost -> github.com, the exact phishing shape Phase 67 guards), and the
console reported only "I confirmed act_..., but execution did not complete."
The guard's explanation was computed and returned under ``stopped_reason``,
then discarded because the reason lookup only knew ``error`` and ``message``.

Every test here is about the CONSOLE STRING a human reads, which is precisely
what the pre-existing tests did not assert on -- they checked the tool's
return dict, where the reason was present all along.
"""
from __future__ import annotations

from eva.permissions.confirmation import _failure_reason


ORIGIN_REFUSAL = (
    "aborted before 'Email': the page origin changed "
    "(expected a page on 'localhost', found 'github.com')"
)


def test_stopped_reason_is_surfaced() -> None:
    """The live-found case: the only reason present is ``stopped_reason``."""
    executed = {"ok": False, "steps": [], "filled": 0, "stopped_reason": ORIGIN_REFUSAL}
    assert _failure_reason(executed) == ORIGIN_REFUSAL


def test_origin_refusal_names_both_domains() -> None:
    """Regression pin on the *content*: a user has to be able to tell that the
    page moved, and where to. A reason that surfaced but said only "aborted"
    would pass the test above while leaving the user just as stuck."""
    executed = {"ok": False, "stopped_reason": ORIGIN_REFUSAL}
    reason = _failure_reason(executed)
    assert "localhost" in reason
    assert "github.com" in reason


def test_error_still_wins_over_stopped_reason() -> None:
    """``error`` stays the preferred key -- this must not reorder existing
    reporting for every tool that already sets it."""
    executed = {"ok": False, "error": "the real error", "stopped_reason": "secondary"}
    assert _failure_reason(executed) == "the real error"


def test_message_still_surfaced() -> None:
    executed = {"ok": False, "message": "a message-style reason"}
    assert _failure_reason(executed) == "a message-style reason"


def test_no_reason_available_returns_empty() -> None:
    """No reason must stay "" so the caller renders a clean full stop rather
    than "did not complete: None"."""
    assert _failure_reason({"ok": False}) == ""
    assert _failure_reason({"ok": False, "error": "", "stopped_reason": None}) == ""


def test_non_dict_results_never_raise() -> None:
    """run_approved can return anything; this is on a failure path already."""
    for value in (None, "a string", 42, [], object()):
        assert _failure_reason(value) == ""


def test_only_declared_keys_are_read() -> None:
    """The lookup must NOT scan the dict for any string it can find: a tool
    result can carry page text, file content or a decrypted value, and none of
    that may be echoed to the console just because the call failed."""
    executed = {
        "ok": False,
        "content": "sensitive file content that must never be surfaced",
        "value": "hunter2",
        "page_text": "whatever was on screen",
    }
    assert _failure_reason(executed) == ""
