from __future__ import annotations

from typing import Any

from ..agent.action_model import AgentAction
from ..security.action_types import ActionType
from ..security.permission_gate import PermissionContext, evaluate_action


_DRAFTS: dict[str, dict[str, str]] = {}


def message_prepare(recipient: str, message: str) -> dict[str, Any]:
    key = recipient.strip().lower() or "current"
    _DRAFTS[key] = {"recipient": recipient, "message": message}
    # Phase 65: this used to also return a hardcoded
    # "verification": {"verified": True, "confidence": 0.8} for merely
    # stashing a dict in memory -- nothing was verified, the third instance
    # of the laundering pattern Phase 64 cleaned up elsewhere. draft_prepared
    # is the accurate, sufficient claim: the draft really is stored.
    return {"ok": True, "recipient": recipient, "message": message, "draft_prepared": True}


def message_confirm_send(recipient: str, message: str) -> dict[str, Any]:
    return {"ok": False, "requires_confirmation": True, "message": f"Send this message to {recipient}: {message}"}


def message_send_via_ui(recipient: str, message: str, confirmed: bool = False) -> dict[str, Any]:
    action = AgentAction(
        "message.send_via_ui",
        ActionType.EXTERNAL_MESSAGE_SEND.value,
        "Send visible external message",
        {"recipient": recipient, "message": message},
        [ActionType.EXTERNAL_MESSAGE_SEND.value],
        external_visible=True,
        verification={"method": "message_sent_likely"},
    )
    decision = evaluate_action(action, PermissionContext(user_confirmed=bool(confirmed)))
    if decision.decision != "allow":
        return {"ok": False, "requires_confirmation": True, "decision": decision.as_dict(), "message": f"Confirm before sending this message to {recipient}: {message}"}
    # This used to return ok=True / "completed through visible UI" and do nothing at
    # all. It now really drives WhatsApp Desktop, and says exactly what happened.
    from ..media.whatsapp_desktop import send_whatsapp_desktop

    result = send_whatsapp_desktop(recipient, message)
    if result.get("sent"):
        return {
            "ok": True,
            "recipient": recipient,
            "sent": True,
            "verified": bool(result.get("verified")),
            "message": str(result.get("message") or "Sent."),
            # The approval reply shows `summary`; without it the user saw a bare
            # "Executed successfully." and could not tell if delivery was verified.
            "summary": str(result.get("message") or "Sent."),
        }
    return {
        "ok": False,
        "recipient": recipient,
        "sent": False,
        "step": result.get("step"),
        "error": result.get("error"),
        "message": str(result.get("message") or f"I did not send the message to {recipient} ({result.get('error')})."),
    }
