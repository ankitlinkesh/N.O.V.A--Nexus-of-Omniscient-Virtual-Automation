"""Honest answers about the last action, and a minimal "do it again".

Two things the local 4B model used to invent:

  * "is that action complete" / "did it send": answered from the pending-action ledger
    (what was really asked, confirmed, cancelled) plus the result of the last approved
    execution, never from the model. With no record it says so.
  * "do it again": the previous request is re-run through the normal routing, which means
    a send builds a NEW pending action that needs a fresh confirmation. This module only
    remembers text; it never confirms, executes or sends anything.

Everything here is in memory and small. No new database.
"""

from __future__ import annotations

import re
from typing import Any

_SUBJECT = r"(?:that|it|this|the (?:last |previous )?(?:action|message|send|task|whatsapp message))(?: (?:action|message|send|task))?"
_STATUS_QUESTION = re.compile(
    rf"^(?:(?:is|was|has) {_SUBJECT} (?:been )?(?:complete|completed|done|finished|sent|executed|successful)"
    rf"|did {_SUBJECT} (?:actually )?(?:send|go through|work|run|execute|finish|complete)"
    rf"|did you (?:actually )?send (?:it|that|the message)"
    rf"|(?:what(?:'s| is) )?(?:the )?(?:status of (?:the )?)?last action(?: status)?"
    rf"|what happened (?:to|with) {_SUBJECT})$"
)
_REPEAT = re.compile(
    r"^(?:do (?:it|that|this) again|again|repeat(?: (?:it|that|this|the last (?:one|request|action)))?|same again|do the same again"
    r"|(?:run|try) (?:it|that) again|one more time|once more|do (?:it|that) one more time)$"
)

_LAST_REQUEST: str = ""
_LAST_RESULTS: dict[str, tuple[bool, str]] = {}
_MAX_RESULTS = 20


def _clean(text: str) -> str:
    return " ".join(str(text or "").strip().strip("`'\"*_ .!?").lower().split())


def is_status_question(text: str) -> bool:
    return bool(_STATUS_QUESTION.match(_clean(text)))


def is_repeat_request(text: str) -> bool:
    return bool(_REPEAT.match(_clean(text)))


def note_execution(action_id: str, ok: bool, text: str) -> None:
    """Remember what an approved action really returned (called after a real, confirmed run)."""
    _LAST_RESULTS[str(action_id)] = (bool(ok), " ".join(str(text or "").split())[:300])
    while len(_LAST_RESULTS) > _MAX_RESULTS:
        _LAST_RESULTS.pop(next(iter(_LAST_RESULTS)))


def _is_control_message(text: str) -> bool:
    """Confirmations, cancels, status and repeat phrases are not a request worth repeating."""
    from ..permissions.confirmation import is_bare_confirm

    clean = _clean(text)
    if is_bare_confirm(clean) or is_status_question(clean) or is_repeat_request(clean):
        return True
    return clean.startswith(("confirm", "approve", "cancel", "deny", "reject", "override", "pending ", "yes ", "no ")) or clean in {"yes", "no", "y", "n"}


def remember_request(message: str) -> None:
    """Keep the last request a deterministic action route handled, so "do it again" can re-run it."""
    global _LAST_REQUEST
    text = " ".join(str(message or "").split())
    if text and not _is_control_message(text):
        _LAST_REQUEST = text[:1000]


def last_request() -> str:
    return _LAST_REQUEST


def reset() -> None:
    global _LAST_REQUEST
    _LAST_REQUEST = ""
    _LAST_RESULTS.clear()


NO_PREVIOUS_REQUEST = "I have no earlier request to repeat. Nothing was run."


def last_action_status() -> str:
    """The true state of the most recent action, from the ledger and the recorded result."""
    from ..permissions.ledger import list_pending_actions

    actions = list_pending_actions(include_expired=True, limit=1)
    if not actions:
        return "Nothing is pending and I have no record of a send or any other action, so I can't say one completed."
    action: Any = actions[0]
    label = f"`{action.id}` ({action.summary})"
    status = str(action.status)
    if status in {"pending_confirmation", "pending_override"}:
        phrase = f"confirm override {action.id}" if status == "pending_override" else f"confirm {action.id}"
        return f"Not yet. {label} is still waiting for your confirmation, and nothing has been sent or run. Say `{phrase}` to approve it."
    if status == "confirmed":
        recorded = _LAST_RESULTS.get(action.id)
        if recorded is None:
            return f"{label} was confirmed, but I have no record of its result, so I can't say it completed."
        ok, text = recorded
        if ok:
            return f"{label} was confirmed and ran. Result: {text or 'it reported success with no details.'}"
        return f"{label} was confirmed but did not complete{': ' + text if text else '.'}"
    if status == "confirmed_but_executor_unavailable":
        return f"{label} was confirmed, but there is no executor for it, so nothing was run."
    if status == "cancelled":
        return f"No. {label} was cancelled, and nothing was run."
    if status == "expired":
        return f"No. {label} expired before it was confirmed, and nothing was run."
    return f"{label} is {status}. Nothing was run."
