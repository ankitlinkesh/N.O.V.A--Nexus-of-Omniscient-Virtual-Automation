"""Draft an email in Gmail (Chrome). NOVA never sends it.

Opens Gmail's compose window with To / Subject / Body already filled in, using the
documented compose URL. The user reads the draft and presses Send themselves, so
no password, token or send permission is involved and a wrong draft costs nothing.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Any

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
    summary = f"Opened a Gmail draft to {', '.join(addresses)} in Chrome. I have not sent it; review it and press Send."
    return {"ok": True, "drafted": True, "sent": False, "to": addresses, "subject": subject, "message": summary, "summary": summary}
