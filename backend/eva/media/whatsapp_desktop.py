"""Send a WhatsApp message through the WhatsApp Desktop window.

This drives the real app with the real mouse and keyboard, so every step is
checked before the next one, and the message is typed only after NOVA has read
the open chat's header and confirmed it is the requested contact. Any check that
fails stops the run BEFORE anything is typed: a wrong recipient is the one
mistake here that cannot be undone.

Needs real input on (`EVA_ENABLE_REAL_INPUT`) and the LOCAL vision model
(`VISION_PROVIDER=local`): the chat list and conversations are read from
screenshots of the WhatsApp window, and none of that may be uploaded anywhere.
The caller (`tools/message_tools.py`) only reaches this after the tool gate has
approved the exact recipient and text.
"""

from __future__ import annotations

import os
import re
import time
from typing import Any, Callable

from .spotify import _title_matches

MAX_MESSAGE_CHARS = 1000
OPEN_WAIT_SECONDS = 2.5
STEP_WAIT_SECONDS = 1.2
LOCATE_CONFIDENCE = 0.6


def _fail(step: str, reason: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "sent": False, "step": step, "error": reason, **extra}


def _read_screen(question: str) -> dict[str, Any]:
    """Ask the local vision model about the WhatsApp window (foreground only)."""
    from ..tools.registry import _analyze_screen

    return _analyze_screen(question=question)


def _whatsapp_in_front() -> bool:
    from ..desktop.windows import get_active_window

    active = get_active_window()
    haystack = f"{getattr(active, 'title', '')} {getattr(active, 'process_name', '')}".lower()
    return "whatsapp" in haystack


def send_whatsapp_desktop(
    recipient: str,
    message: str,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    recipient = " ".join(str(recipient or "").split())
    message = str(message or "").strip()
    if not recipient or not message:
        return _fail("input", "recipient_and_message_required")
    if len(message) > MAX_MESSAGE_CHARS or "\n" in message:
        return _fail("input", "message_must_be_one_line_under_1000_chars")

    from ..desktop import focus_window_safe
    from ..screen import screen_controller
    from ..screen.vision_click import locate_by_vision
    from ..vision.screen_vision import local_vision_enabled

    if not screen_controller.real_input_enabled():
        return _fail("preflight", "real_input_disabled", message="Real mouse/keyboard input is off (EVA_ENABLE_REAL_INPUT), so I did not send anything.")
    if not local_vision_enabled():
        return _fail("preflight", "local_vision_not_enabled", message="Local vision is off, and I will not read your chats with a cloud model, so I did not send anything.")

    reason = f"send a WhatsApp message to {recipient}"

    # 1. WhatsApp in front.
    # The Microsoft Store build has no WhatsApp.exe for open_app to find; it is
    # registered under the `whatsapp:` protocol. Focus a running window first, and
    # only launch when there is none.
    if not focus_window_safe("whatsapp").get("ok"):
        try:
            os.startfile("whatsapp:")  # type: ignore[attr-defined]
        except Exception as exc:
            return _fail("open", f"open_failed:{exc.__class__.__name__}")
        sleep(OPEN_WAIT_SECONDS)
        focus_window_safe("whatsapp")
    sleep(STEP_WAIT_SECONDS)
    if not _whatsapp_in_front():
        return _fail("focus", "whatsapp_not_in_front", message="I could not bring WhatsApp to the front, so I did not send anything.")

    # 2. Search for the contact.
    box, box_res = locate_by_vision(
        "the search box at the top of the chat list (placeholder like 'Search or start a new chat')",
        min_confidence=LOCATE_CONFIDENCE,
    )
    if box is None:
        return _fail("search_box", box_res.reason or "not_found")
    if not screen_controller.click(box.x, box.y, reason).success:
        return _fail("search_box", "click_failed")
    screen_controller.hotkey(["ctrl", "a"], reason)
    if not screen_controller.type_text(recipient, reason).success:
        return _fail("search_text", "typing_failed")
    sleep(STEP_WAIT_SECONDS + 0.5)

    # 3. Open the matching chat. The model must NAME the row it picked, and that
    #    name has to match the contact.
    row, row_res = locate_by_vision(
        f"the first chat or contact in the search results whose name is '{recipient}' "
        "(a person's chat row; not a message, group or channel result)",
        min_confidence=LOCATE_CONFIDENCE,
    )
    if row is None:
        return _fail("pick_chat", row_res.reason or "not_found", message=f"I could not find a chat for {recipient}, so I did not send anything.")
    if not _title_matches(recipient, row_res.description):
        return _fail("pick_chat", "result_name_mismatch", saw=row_res.description[:120], message=f"The search result did not look like {recipient}, so I did not send anything.")
    if not screen_controller.click(row.x, row.y, reason).success:
        return _fail("pick_chat", "click_failed")
    sleep(STEP_WAIT_SECONDS)

    # 4. Verify the OPEN chat is the right person BEFORE typing anything.
    header = _read_screen(
        "This is WhatsApp. Read the name shown in the header at the top of the open conversation "
        "(the right-hand pane). Put exactly that name in detected_text."
    )
    header_text = str((header or {}).get("detected_text") or "")
    if not (header or {}).get("ok") or not _title_matches(recipient, header_text):
        return _fail("verify_chat", "chat_header_mismatch", saw=header_text[:120], message=f"The open chat was not {recipient}, so I did not send anything.")

    # 5. Type into the message box.
    field, field_res = locate_by_vision(
        "the message input box at the bottom of the open conversation (placeholder like 'Type a message')",
        min_confidence=LOCATE_CONFIDENCE,
    )
    if field is None:
        return _fail("message_box", field_res.reason or "not_found", message="I could not find the message box, so I did not send anything.")
    if not screen_controller.click(field.x, field.y, reason).success:
        return _fail("message_box", "click_failed")
    if not screen_controller.type_text(message, reason).success:
        return _fail("type_message", "typing_failed", message="Typing the message failed, so I did not press Enter.")
    sleep(0.4)

    # 6. Send, then read the conversation back.
    if not screen_controller.press("enter", reason).success:
        return _fail("send", "enter_failed")
    sleep(STEP_WAIT_SECONDS + 0.5)
    seen = _read_screen(
        "This is a WhatsApp conversation. Read the most recent message at the very bottom of the chat that "
        "I sent (an outgoing bubble on the right). Put exactly its text in detected_text."
    )
    last = str((seen or {}).get("detected_text") or "")
    delivered = bool((seen or {}).get("ok")) and bool(re.sub(r"\W+", "", message)) and re.sub(r"\W+", "", message).lower() in re.sub(r"\W+", "", last).lower()
    return {
        "ok": True,
        "sent": True,
        "verified": delivered,
        "recipient": recipient,
        "step": "done",
        "last_message_seen": last[:200],
        "message": (
            f"Sent \"{message}\" to {recipient} on WhatsApp Desktop and saw it in the chat."
            if delivered
            else f"I pressed send on \"{message}\" to {recipient}, but could not confirm it appeared in the chat."
        ),
    }
