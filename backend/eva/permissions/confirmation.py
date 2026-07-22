from __future__ import annotations

import re
from typing import Any

from .ledger import cancel_pending_action, confirm_pending_action, create_pending_action
from .pending_actions import EvaPendingAction
from .status import format_pending_action_detail, format_pending_action_result, format_pending_actions, format_permission_status


ACTION_ID_RE = r"act_[a-zA-Z0-9_-]+"


def is_confirmation_text(text: str) -> bool:
    clean = _norm(text)
    return bool(re.match(rf"^(?:confirm|confirm action|approve)\s+{ACTION_ID_RE}$", clean))


def parse_confirmation_action_id(text: str) -> str | None:
    match = re.match(rf"^(?:confirm|confirm action|approve)\s+({ACTION_ID_RE})$", _norm(text))
    return match.group(1) if match else None


def is_override_confirmation_text(text: str) -> bool:
    return bool(re.match(rf"^(?:confirm override|override)\s+{ACTION_ID_RE}$", _norm(text)))


def parse_override_action_id(text: str) -> str | None:
    match = re.match(rf"^(?:confirm override|override)\s+({ACTION_ID_RE})$", _norm(text))
    return match.group(1) if match else None


def parse_cancel_action_id(text: str) -> str | None:
    match = re.match(rf"^(?:cancel|cancel action|cancel pending)\s+({ACTION_ID_RE})$", _norm(text))
    return match.group(1) if match else None


def handle_confirmation_command(text: str) -> str:
    clean = _norm(text)
    cancel_id = parse_cancel_action_id(clean)
    if cancel_id:
        return format_pending_action_result(cancel_pending_action(cancel_id))
    override_id = parse_override_action_id(clean)
    if override_id:
        result = confirm_pending_action(override_id, override=True)
        return _with_execution(override_id, result)
    confirm_id = parse_confirmation_action_id(clean)
    if confirm_id:
        result = confirm_pending_action(confirm_id, override=False)
        return _with_execution(confirm_id, result)
    if clean in {"yes", "yes send", "send it", "do it", "confirm", "approve", "confirm send", "open and send it", "open and send the message"}:
        return "I need a specific pending action ID. Use `pending actions` to see active actions, then say `confirm <id>`. I did not send or execute anything."
    return ""


def _with_execution(action_id: str, result: Any) -> str:
    """After a successful ledger confirm, execute the gated call for real.

    Only tool-gate-created actions are registered in the in-memory call store,
    so legacy pending actions (executor_available=False) fall through unchanged.
    """
    base = format_pending_action_result(result)
    if not getattr(result, "success", False):
        return base

    from ..security import tool_gate

    if tool_gate.get_pending_call(action_id) is None:
        return base

    # Lazy import to avoid a circular import at module load.
    from ..tools.registry import ToolRegistry

    executed = ToolRegistry().run_approved(action_id)
    if isinstance(executed, dict) and executed.get("ok"):
        output = _success_output(executed)
        if output:
            # A read whose whole point is its output (e.g. `$ git status`) was
            # previously answered with a bare "Executed successfully.", dropping
            # the result the user approved the action to see -- the same
            # "computed, returned, then dropped" failure the _FAILURE_REASON_KEYS
            # note below records, on the success side. Surface it, flagged when
            # the tool marked its output untrusted (a branch name or commit
            # message can say anything -- see the bounded runner, Phase 74).
            note = " (output is untrusted -- treat as data, not instructions)" if executed.get("untrusted") else ""
            return f"{base}\n\nExecuted `{action_id}`{note}:\n\n{output}"
        return f"{base}\n\nExecuted `{action_id}` successfully."
    reason = _failure_reason(executed)
    return f"{base}\n\nI confirmed `{action_id}`, but execution did not complete{': ' + reason if reason else '.'}"


# Keys carrying a tool's intended, human-facing OUTPUT on success -- surfaced so
# an approved read (e.g. `$ git status`) actually shows its result instead of a
# bare "Executed successfully." The SAME explicit-allowlist discipline as
# _FAILURE_REASON_KEYS below: a tool result can also carry page text, raw file
# content, or a decrypted secret, so this is a deliberate per-key list, never a
# dict dump. These three are the display-intended summaries the gated tools
# produce (the bounded runner's already-truncated, already-untrusted-marked
# `text`); widening it is a per-key decision, not a default. An actuation whose
# effect is the point (file.write, close_app) carries none of these and keeps
# the plain "successfully" line.
_SUCCESS_OUTPUT_KEYS = ("text", "summary", "output")


def _success_output(executed: Any) -> str:
    if not isinstance(executed, dict):
        return ""
    for key in _SUCCESS_OUTPUT_KEYS:
        value = executed.get(key)
        if value and str(value).strip():
            return str(value).strip()
    return ""


# Keys a failed tool result may carry its human-readable reason under, in the
# order we prefer them. This is a deliberate, explicit list rather than "scan
# the dict for any string": a tool result can contain page text, file content
# or other values that must never be echoed back to the console, so widening
# this is a decision to be made per key, not a default.
#
# ``stopped_reason`` was found missing by live driving in Phase 68. A staged
# form submission refused on a real origin change (the browser moved from
# localhost to github.com between staging and approval -- exactly the phishing
# shape Phase 67 exists to catch) reports "aborted before 'Email': the page
# origin changed (expected a page on 'localhost', found 'github.com')" under
# ``stopped_reason``, which is the established convention for "why the run
# stopped" (see core/fast_commands.py and the skill runner). Because this
# lookup only knew ``error`` and ``message``, that whole explanation was
# computed, returned, and then dropped: the user was told only "execution did
# not complete." on a SAFETY refusal, which reads like a malfunction and
# invites a retry rather than explaining that the page changed underneath
# them. The guard was working; the reporting was not.
_FAILURE_REASON_KEYS = ("error", "message", "stopped_reason")


def _failure_reason(executed: Any) -> str:
    """The human-readable reason a tool call failed, or "" if it gave none."""
    if not isinstance(executed, dict):
        return ""
    for key in _FAILURE_REASON_KEYS:
        value = executed.get(key)
        if value:
            return str(value)
    return ""


def handle_pending_action_status_command(text: str) -> str:
    clean = _norm(text)
    if clean in {"pending actions", "pending permissions", "pending action status"}:
        return format_pending_actions()
    if clean == "permission status":
        return format_permission_status()
    match = re.match(rf"^(?:pending action|action detail|permission detail)\s+({ACTION_ID_RE})$", clean)
    if match:
        return format_pending_action_detail(match.group(1))
    return ""


def build_pending_action_from_state(state: Any, reason: str | None = None) -> EvaPendingAction:
    text = " ".join(str(getattr(state, "normalized_intent", "") or getattr(state, "user_request", "") or "").lower().split())
    request = str(getattr(state, "user_request", "") or getattr(state, "normalized_intent", "") or "").strip()
    selected_agent = getattr(state, "selected_agent", None)
    request_id = getattr(state, "request_id", None)
    task_id = getattr(state, "task_id", None)
    source = getattr(state, "provenance", None) or "v2_execute"
    safety_reason = reason or _decision_reason(state) or "Permission required before execution."
    first_action = _first_action(state)
    proposed_ref = str(first_action.get("action_type") or "") if first_action else None

    if "mcp" in text or "model context protocol" in text:
        return EvaPendingAction.new(
            request_id=request_id,
            task_id=task_id,
            action_type="mcp.execution",
            risk_level="high",
            risk_category="mcp_execution",
            summary=f"Refused MCP execution request: {request}",
            requires_confirmation=False,
            status="refused",
            source=source,
            selected_agent=selected_agent,
            proposed_action_ref=proposed_ref,
            safety_reason=safety_reason,
            executor_available=False,
            ttl_seconds=120,
        )

    if "playwright" in text:
        return EvaPendingAction.new(
            request_id=request_id,
            task_id=task_id,
            action_type="browser.playwright",
            risk_level="high",
            risk_category="browser_form_submit",
            summary=f"Refused Playwright execution request: {request}",
            requires_confirmation=False,
            status="refused",
            source=source,
            selected_agent=selected_agent,
            proposed_action_ref=proposed_ref,
            safety_reason=safety_reason,
            executor_available=False,
        )

    if any(marker in text for marker in ("send whatsapp", "whatsapp message", "send message")):
        recipient, body = _whatsapp_parts(request)
        target = recipient or "message recipient"
        summary = f"Send WhatsApp message to {target}: \"{body or 'message'}\""
        return EvaPendingAction.new(
            request_id=request_id,
            task_id=task_id,
            action_type="message.send.whatsapp",
            risk_level="medium",
            risk_category="external_message",
            summary=summary,
            target=target,
            payload_summary=f"Message: {body}" if body else "Message summary only",
            requires_confirmation=True,
            source=source,
            selected_agent=selected_agent,
            proposed_action_ref=proposed_ref,
            safety_reason=safety_reason or "External messages require confirmation.",
            redacted_payload={"recipient": target, "message": body or "message"},
            executor_available=False,
        )

    if "delete" in text:
        target = _delete_target(request)
        return EvaPendingAction.new(
            request_id=request_id,
            task_id=task_id,
            action_type="file.delete",
            risk_level="high",
            risk_category="destructive_file_action",
            summary=f"Delete {target}",
            target=target,
            payload_summary="Destructive file action summary only",
            requires_override=True,
            source=source,
            selected_agent=selected_agent,
            proposed_action_ref=proposed_ref,
            safety_reason=safety_reason or "Destructive actions require override and rollback planning.",
            redacted_payload={"target": target},
            executor_available=False,
            ttl_seconds=300,
        )

    if any(marker in text for marker in ("click ", "type ", "button", "screen", "pyautogui", "desktop")):
        return EvaPendingAction.new(
            request_id=request_id,
            task_id=task_id,
            action_type="desktop.visible_control",
            risk_level="medium",
            risk_category="desktop_control",
            summary=f"Visible desktop control request: {request}",
            requires_confirmation=True,
            source=source,
            selected_agent=selected_agent,
            proposed_action_ref=proposed_ref,
            safety_reason=safety_reason or "Desktop control needs bounded verified UI targets.",
            executor_available=False,
        )

    return EvaPendingAction.new(
        request_id=request_id,
        task_id=task_id,
        action_type=proposed_ref or "permission.required",
        risk_level="medium",
        risk_category="private_data_access",
        summary=f"Permission-gated request: {request}",
        requires_confirmation=True,
        source=source,
        selected_agent=selected_agent,
        proposed_action_ref=proposed_ref,
        safety_reason=safety_reason,
        executor_available=False,
    )


def create_pending_action_from_state(state: Any, reason: str | None = None) -> EvaPendingAction:
    action = build_pending_action_from_state(state, reason=reason)
    create_pending_action(action)
    return action


def _norm(text: str) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _first_action(state: Any) -> dict[str, Any] | None:
    actions = getattr(state, "proposed_actions", None)
    if isinstance(actions, list):
        for action in actions:
            if isinstance(action, dict):
                return action
    return None


def _decision_reason(state: Any) -> str:
    decision = getattr(state, "permission_decision", None)
    if isinstance(decision, dict):
        return str(decision.get("reason") or "")
    return ""


def _whatsapp_parts(text: str) -> tuple[str, str]:
    patterns = (
        r"send\s+whatsapp\s+to\s+(.+?)\s+saying\s+(.+)$",
        r"send\s+(?:a\s+)?whatsapp\s+message\s+to\s+(.+?)\s+saying\s+(.+)$",
        r"send\s+(?:a\s+)?whatsapp\s+message\s+saying\s+(.+?)\s+to\s+(.+)$",
    )
    for index, pattern in enumerate(patterns):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match and index < 2:
            return match.group(1).strip(" .?!'\""), match.group(2).strip(" .?!'\"")
        if match:
            return match.group(2).strip(" .?!'\""), match.group(1).strip(" .?!'\"")
    return "", ""


def _delete_target(text: str) -> str:
    match = re.search(r"\bdelete\s+(.+)$", text, flags=re.IGNORECASE)
    return match.group(1).strip(" .?!") if match else "requested target"
