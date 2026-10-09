from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def emit(case: str, passed: bool, **payload: Any) -> int:
    ok = bool(passed)
    print(json.dumps({"case": case, "pass": ok, **payload}, indent=2, ensure_ascii=False))
    return 0 if ok else 1


def _fast(command: str) -> str:
    from backend.eva.core.fast_commands import maybe_handle_fast_command
    from backend.eva.tools.registry import ToolRegistry

    handled = maybe_handle_fast_command(command, ToolRegistry(), {})
    return handled[0] if handled else ""


def _capability_reply(message: str, session: dict[str, Any] | None = None) -> tuple[dict[str, Any], str, str]:
    from backend.eva.api import routes
    from backend.eva.core.intent_router import classify_capability_intent

    context = session if session is not None else {}
    classification = classify_capability_intent(message, context)
    handled = routes._handle_capability_route(message, classification, context, None, "verify")
    reply, source = handled if handled else ("", "")
    return classification, reply, source


def _clean(text: str) -> bool:
    return "{'" not in text and "EvaPendingAction(" not in text and "EvaRuntimeState(" not in text and "Traceback" not in text


def _source(paths: list[Path]) -> str:
    chunks: list[str] = []
    for root in paths:
        if root.exists():
            files = [root] if root.is_file() else list(root.rglob("*.py"))
            chunks.extend(path.read_text(encoding="utf-8", errors="replace").lower() for path in files)
    return "\n".join(chunks)


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory(prefix="eva_permission_ledger_") as temp:
        os.environ["EVA_PENDING_ACTION_LEDGER_PATH"] = str(Path(temp) / "pending_actions.jsonl")

        try:
            from backend.eva.permissions.confirmation import (
                handle_confirmation_command,
                handle_pending_action_status_command,
                is_confirmation_text,
                parse_cancel_action_id,
                parse_confirmation_action_id,
            )
            from backend.eva.permissions.ledger import (
                cancel_pending_action,
                confirm_pending_action,
                create_pending_action,
                get_pending_action,
                list_pending_actions,
                update_pending_action_status,
            )
            from backend.eva.permissions.pending_actions import EvaPendingAction
        except Exception as exc:
            failures += emit("permissions_package_imports", False, error=str(exc))
            print(json.dumps({"overall_pass": False, "failures": failures}, indent=2))
            return 1

        failures += emit(
            "permissions_package_imports",
            callable(handle_confirmation_command)
            and callable(create_pending_action)
            and callable(list_pending_actions)
            and callable(confirm_pending_action)
            and callable(EvaPendingAction),
        )

        action = EvaPendingAction.new(
            action_type="message.send.whatsapp",
            risk_level="medium",
            risk_category="external_message",
            summary='Send WhatsApp message to kutty: "hi"',
            target="kutty",
            payload_summary="Message: hi",
            requires_confirmation=True,
            source="normal_chat",
            safety_reason="External messages require confirmation.",
            redacted_payload={"recipient": "kutty", "message": "hi"},
        )
        payload = action.as_dict()
        restored = EvaPendingAction.from_dict(payload)
        failures += emit(
            "pending_action_model_serializes",
            restored.id == action.id
            and restored.status == "pending_confirmation"
            and restored.redacted_payload == {"recipient": "kutty", "message": "hi"},
            payload=payload,
        )

        created = create_pending_action(action)
        listed = list_pending_actions()
        fetched = get_pending_action(action.id)
        failures += emit("create_pending_action_stores_locally", created.success and fetched is not None, result=created.as_dict())
        failures += emit("list_pending_actions_returns_active", any(item.id == action.id for item in listed), actions=[item.as_dict() for item in listed])
        failures += emit("get_pending_action_works", bool(fetched and fetched.summary == action.summary), action=fetched.as_dict() if fetched else None)

        cancelled = cancel_pending_action(action.id)
        cancelled_confirm = confirm_pending_action(action.id)
        failures += emit("cancel_pending_action_works", cancelled.success and get_pending_action(action.id).status == "cancelled", result=cancelled.as_dict())
        failures += emit("cancelled_action_cannot_be_confirmed", not cancelled_confirm.success and "cancelled" in cancelled_confirm.message.lower(), result=cancelled_confirm.as_dict())

        expired_action = EvaPendingAction.new(
            action_type="message.send.whatsapp",
            risk_level="medium",
            risk_category="external_message",
            summary="Expired send",
            requires_confirmation=True,
            source="v2_execute",
            safety_reason="External message.",
            ttl_seconds=-1,
        )
        create_pending_action(expired_action)
        expired_confirm = confirm_pending_action(expired_action.id)
        failures += emit("expired_action_cannot_be_confirmed", not expired_confirm.success and "expired" in expired_confirm.message.lower(), result=expired_confirm.as_dict())

        override_action = EvaPendingAction.new(
            action_type="file.delete",
            risk_level="high",
            risk_category="destructive_file_action",
            summary="Delete Downloads folder",
            target="Downloads",
            requires_override=True,
            source="v2_execute",
            safety_reason="Destructive file action.",
            executor_available=False,
        )
        create_pending_action(override_action)
        normal_confirm = confirm_pending_action(override_action.id)
        override_confirm = confirm_pending_action(override_action.id, override=True)
        failures += emit("override_action_rejects_normal_confirm", not normal_confirm.success and "override" in normal_confirm.message.lower(), result=normal_confirm.as_dict())
        failures += emit(
            "override_confirm_marks_executor_unavailable",
            override_confirm.success
            and override_confirm.status == "confirmed_but_executor_unavailable"
            and get_pending_action(override_action.id).status == "confirmed_but_executor_unavailable",
            result=override_confirm.as_dict(),
        )

        vague = handle_confirmation_command("yes send")
        no_id = handle_confirmation_command("confirm")
        failures += emit("vague_yes_rejected", "specific pending action id" in vague.lower(), response=vague)
        failures += emit("confirm_without_id_rejected", "specific pending action id" in no_id.lower(), response=no_id)
        failures += emit(
            "confirmation_parsers_require_ids",
            is_confirmation_text("confirm act_abc123")
            and parse_confirmation_action_id("approve act_abc123") == "act_abc123"
            and parse_cancel_action_id("cancel pending act_abc123") == "act_abc123"
            and parse_confirmation_action_id("confirm") is None,
        )

        new_send = EvaPendingAction.new(
            action_type="message.send.whatsapp",
            risk_level="medium",
            risk_category="external_message",
            summary='Send WhatsApp message to kutty: "hi"',
            requires_confirmation=True,
            source="normal_chat",
            safety_reason="External message.",
            executor_available=False,
        )
        create_pending_action(new_send)
        handled_confirm = handle_confirmation_command(f"confirm {new_send.id}")
        failures += emit(
            "confirmed_risky_action_executor_unavailable",
            "confirmed" in handled_confirm.lower() and "did not" in handled_confirm.lower() and "executor" in handled_confirm.lower(),
            response=handled_confirm,
        )

        update_pending_action_status(new_send.id, "pending_confirmation", note="reset for detail test")
        status_text = handle_pending_action_status_command("pending actions")
        detail_text = handle_pending_action_status_command(f"pending action {new_send.id}")
        failures += emit("pending_actions_status_human_readable", "Pending actions" in status_text and new_send.id in status_text and _clean(status_text), response=status_text)
        failures += emit("pending_action_detail_human_readable", "Pending action" in detail_text and "Risk:" in detail_text and _clean(detail_text), response=detail_text)

        normal_session: dict[str, Any] = {}
        whatsapp_classification, whatsapp_reply, _ = _capability_reply("send WhatsApp to kutty saying hi", normal_session)
        failures += emit(
            "whatsapp_normal_chat_creates_pending_action",
            whatsapp_classification.get("capability") == "message_workflow"
            and "Pending action:" in whatsapp_reply
            and "did not send" in whatsapp_reply
            and "confirm " in whatsapp_reply
            and _clean(whatsapp_reply),
            classification=whatsapp_classification,
            reply=whatsapp_reply,
        )
        send_it_reply = _capability_reply("send it", {})[1]
        failures += emit(
            "send_it_without_action_id_does_not_send",
            "specific pending action id" in send_it_reply.lower() and "did not send" in send_it_reply.lower(),
            reply=send_it_reply,
        )

        v2_send = _fast("eva v2 execute send WhatsApp to kutty saying hi")
        v2_delete = _fast("eva v2 execute delete Downloads folder")
        v2_click = _fast("eva v2 execute click this button")
        v2_mcp = _fast("eva v2 execute inspect my repo with GitHub MCP")
        v2_playwright = _fast("eva v2 execute use playwright to open gmail")
        v2_pyautogui = _fast("eva v2 execute pyautogui click 10 10")
        v2_file = _fast("eva v2 execute write file notes.txt")
        v2_shell = _fast("eva v2 execute run powershell dir")
        failures += emit("v2_whatsapp_creates_pending_confirmation", "requires confirmation" in v2_send.lower() and "Pending action:" in v2_send and "No real action was executed." in v2_send, response=v2_send)
        failures += emit("v2_delete_creates_pending_override", "requires override" in v2_delete.lower() and "Pending action:" in v2_delete and "confirm override" in v2_delete, response=v2_delete)
        failures += emit("v2_click_does_not_execute_desktop_action", ("requires confirmation" in v2_click.lower() or "execution refused" in v2_click.lower()) and "No real action was executed." in v2_click, response=v2_click)
        failures += emit("mcp_execution_remains_disabled", "mcp execution is disabled" in v2_mcp.lower() and "No real action was executed." in v2_mcp, response=v2_mcp)
        failures += emit("playwright_execution_remains_disabled", "playwright execution is disabled" in v2_playwright.lower(), response=v2_playwright)
        failures += emit("pyautogui_execution_remains_disabled", "desktop execution is disabled" in v2_pyautogui.lower(), response=v2_pyautogui)
        failures += emit("file_write_delete_remains_disabled", "file modification" in v2_file.lower() or "not allowed" in v2_file.lower(), response=v2_file)
        failures += emit("shell_script_execution_remains_disabled", "arbitrary shell is blocked" in v2_shell.lower(), response=v2_shell)

        fast_status = _fast("pending actions")
        fast_detail = _fast(f"pending action {new_send.id}")
        fast_cancel = _fast(f"cancel {new_send.id}")
        failures += emit("fast_pending_actions_command", "Pending actions" in fast_status and _clean(fast_status), response=fast_status)
        failures += emit("fast_pending_action_detail_command", "Pending action" in fast_detail and _clean(fast_detail), response=fast_detail)
        failures += emit("fast_cancel_command", "cancelled" in fast_cancel.lower() and _clean(fast_cancel), response=fast_cancel)

        source_paths = [
            ROOT / "backend" / "eva" / "permissions",
            ROOT / "backend" / "eva" / "runtime" / "execution_bridge.py",
            ROOT / "backend" / "eva" / "runtime" / "execution_policy.py",
            ROOT / "backend" / "eva" / "core" / "fast_commands.py",
            ROOT / "backend" / "eva" / "api" / "routes.py",
        ]
        source_text = _source(source_paths)
        failures += emit("no_raw_dict_repr_outputs", all("{'" not in text for text in (v2_send, v2_delete, whatsapp_reply, fast_status)))
        failures += emit("no_dataclass_repr_outputs", "EvaPendingAction(" not in v2_send + v2_delete + whatsapp_reply + fast_status)
        failures += emit("no_env_local_read", "open('.env.local" not in source_text and 'open(".env.local' not in source_text)
        from _source_guard import no_package_install, no_shell

        # Real imports/calls only; "`pip install uiautomation`" in a help string is not an install.
        install = no_package_install(source_paths)[0]
        failures += emit("no_package_install", not install, found=[str(f) for f in install])
        shell = no_shell(source_paths)[0]
        failures += emit("no_arbitrary_shell_subprocess", not shell, found=[str(f) for f in shell])

    print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
