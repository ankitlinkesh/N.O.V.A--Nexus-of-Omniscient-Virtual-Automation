"""Draft an email in Gmail (Chrome), and send it only on the user's confirmed say-so.

Drafting opens Gmail's compose window with To / Subject / Body already filled in, using
the documented compose URL: no password, token or send permission, and a wrong draft
costs nothing. Sending is a separate, confirm-gated tool that presses Gmail's own Send
shortcut in that window.
"""

from __future__ import annotations

import re
import time
import urllib.parse
from typing import Any, Callable

from ..agent.action_model import AgentAction
from ..security.action_types import ActionType
from ..security.permission_gate import PermissionContext, evaluate_action

_ADDRESS = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[A-Za-z]{2,}$")
MAX_BODY_CHARS = 4000


def gmail_compose_url(to: str, subject: str, body: str) -> str:
    query = urllib.parse.urlencode(
        {"view": "cm", "fs": "1", "to": to, "su": subject, "body": body}, quote_via=urllib.parse.quote
    )
    return f"https://mail.google.com/mail/?{query}"


def email_draft_gmail(to: str, subject: str = "", body: str = "") -> dict[str, Any]:
    addresses = [part.strip() for part in re.split(r"[;,]", str(to or "")) if part.strip()]
    if not addresses or not all(_ADDRESS.match(address) for address in addresses):
        return {"ok": False, "drafted": False, "sent": False, "error": "invalid_recipient", "message": f"I need a full email address (name@domain.com) to draft this, got '{to}'."}
    subject = " ".join(str(subject or "").split())[:200]
    body = str(body or "").strip()[:MAX_BODY_CHARS]
    if not subject and not body:
        return {"ok": False, "drafted": False, "sent": False, "error": "empty_email", "message": "There is no subject or body to put in the draft."}

    from ..browser.controller import open_url_in_chrome

    result = open_url_in_chrome(gmail_compose_url(", ".join(addresses), subject, body))
    if not result.get("ok"):
        return {"ok": False, "drafted": False, "sent": False, "error": "open_failed", "message": "I could not open Gmail in Chrome."}
    _LAST_DRAFT.clear()
    _LAST_DRAFT.update({"to": addresses, "subject": subject, "at": time.time()})
    summary = f"Opened a Gmail draft to {', '.join(addresses)} in Chrome. I have not sent it; review it, then say `send` and I will press Send after you confirm."
    return {"ok": True, "drafted": True, "sent": False, "to": addresses, "subject": subject, "message": summary, "summary": summary}


# --- sending the draft -------------------------------------------------------
#
# "send" after a draft presses Send in the Gmail window NOVA opened. It is an
# external send, so it goes through the same confirm gate as a WhatsApp message:
# the user types `confirm act_...` for this exact draft first.

DRAFT_TTL_SECONDS = 30 * 60
SEND_WAIT_SECONDS = 2.5
SEND_DRAFT_PHRASE = re.compile(
    r"^(?:(?:hit|press|click)\s+)?send(?:\s+(?:it|that|the\s+(?:email|mail|draft)|(?:the\s+)?(?:email|mail|draft)))?(?:\s+now)?$",
    re.IGNORECASE,
)
_LAST_DRAFT: dict[str, Any] = {}


def pending_draft() -> dict[str, Any] | None:
    """The draft NOVA opened in Gmail, while it is still recent; else None."""
    if _LAST_DRAFT and time.time() - float(_LAST_DRAFT.get("at", 0)) <= DRAFT_TTL_SECONDS:
        return dict(_LAST_DRAFT)
    return None


def is_send_draft_request(message: str) -> bool:
    return bool(SEND_DRAFT_PHRASE.match(" ".join(str(message or "").split()).rstrip(" .!?"))) and pending_draft() is not None


def _gmail_title() -> str:
    from ..desktop.windows import get_active_window

    active = get_active_window()
    return str(getattr(active, "title", "") or "")


def email_send_drafted(confirmed: bool = False, *, sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    draft = pending_draft()
    if draft is None:
        return {"ok": False, "sent": False, "error": "no_draft", "message": "There is no Gmail draft from me to send. Ask me to write one first."}
    to = ", ".join(draft["to"])
    action = AgentAction(
        "email.send_drafted",
        ActionType.EXTERNAL_MESSAGE_SEND.value,
        "Send the drafted Gmail message",
        {"recipient": to, "subject": draft.get("subject", "")},
        [ActionType.EXTERNAL_MESSAGE_SEND.value],
        external_visible=True,
        verification={"method": "message_sent_likely"},
    )
    decision = evaluate_action(action, PermissionContext(user_confirmed=bool(confirmed)))
    if decision.decision != "allow":
        return {"ok": False, "requires_confirmation": True, "decision": decision.as_dict(), "message": f"Confirm before sending the Gmail draft to {to} (subject: {draft.get('subject') or 'none'})."}

    from ..desktop import focus_window_safe
    from ..screen import screen_controller

    if not screen_controller.real_input_enabled():
        return {"ok": False, "sent": False, "error": "real_input_disabled", "message": "Real keyboard input is off (EVA_ENABLE_REAL_INPUT), so I did not press Send. The draft is still open in Chrome."}
    if not focus_window_safe("gmail").get("ok") or "gmail" not in _gmail_title().lower():
        return {"ok": False, "sent": False, "error": "gmail_not_in_front", "message": "I could not bring the Gmail draft to the front, so I did not press Send."}
    before = _gmail_title()
    # Ctrl+Enter is Gmail's Send shortcut; it works wherever the cursor is in the compose window.
    if not screen_controller.hotkey(["ctrl", "enter"], f"send the Gmail draft to {to}").success:
        return {"ok": False, "sent": False, "error": "hotkey_failed", "message": "Pressing Send failed. The draft is still open in Chrome."}
    sleep(SEND_WAIT_SECONDS)
    after = _gmail_title()
    verified = bool(before) and after != before and "gmail" in after.lower()
    _LAST_DRAFT.clear()
    summary = (
        f"Pressed Send on the Gmail draft to {to}; the Gmail window changed afterwards, so it very likely went."
        if verified
        else f"Pressed Send on the Gmail draft to {to}, but I could not confirm it left. Check your Sent folder."
    )
    return {"ok": True, "sent": True, "verified": verified, "to": draft["to"], "message": summary, "summary": summary}
