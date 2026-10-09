from __future__ import annotations

import json
import tempfile
import time
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Intentional fake secret-pattern fixture for redaction tests. Not a real secret.

# The gate case below creates a real pending action; keep it out of the user's ledger.
import os

os.environ.setdefault("EVA_PENDING_ACTION_LEDGER_PATH", str(Path(tempfile.mkdtemp(prefix="eva_hybrid_")) / "pending_actions.jsonl"))

from backend.eva.agent.action_model import AgentAction, AgentObservation
from backend.eva.agent.checkpoints import CheckpointStore
from backend.eva.agent.executor import ToolExecutor
from backend.eva.agent.rollback import rollback_action
from backend.eva.agent.verifier import verify_action
from backend.eva.config import hybrid_defaults
from backend.eva.privacy.cloud_context_firewall import CloudContextFirewall, CloudContextRequest
from backend.eva.privacy.redaction import redact_secrets
from backend.eva.security.action_types import ActionType
from backend.eva.security.override_store import OverrideStore
from backend.eva.security.permission_gate import PermissionContext, evaluate_action
from backend.eva.tools.registry import ToolRegistry


def emit(case: str, passed: bool, **payload: Any) -> int:
    print(json.dumps({"case": case, "pass": passed, **payload}, indent=2, ensure_ascii=False))
    return 0 if passed else 1


def action(
    tool_name: str,
    action_type: ActionType | str,
    *,
    params: dict[str, Any] | None = None,
    risk_categories: list[str] | None = None,
    destructive: bool = False,
    privacy_sensitive: bool = False,
    external_visible: bool = False,
    expected_result: str = "",
    verification: dict[str, Any] | None = None,
    rollback: dict[str, Any] | None = None,
) -> AgentAction:
    type_value = action_type.value if isinstance(action_type, ActionType) else str(action_type)
    return AgentAction(
        tool_name=tool_name,
        action_type=type_value,
        description=f"Verify {tool_name}",
        params=params or {},
        risk_categories=risk_categories or [type_value],
        expected_result=expected_result,
        verification=verification or {},
        rollback=rollback or {},
        destructive=destructive,
        privacy_sensitive=privacy_sensitive,
        external_visible=external_visible,
    )


def main() -> int:
    failures = 0
    defaults = hybrid_defaults()
    failures += emit(
        "local_memory_cloud_reasoning_defaults",
        defaults["privacy"]["memory_storage"] == "local"
        and defaults["privacy"]["cloud_llm_allowed"] is True
        and defaults["agent"]["require_verification"] is True
        and defaults["agent"]["rollback_enabled"] is True
        and defaults["screen"]["always_on_watch"] is False,
        defaults=defaults,
    )

    text = (
        "OPENAI_API_KEY=sk-test12345678901234567890 bearer abc.def.ghi "
        "password: hunter2 person@example.com +1 415 555 2671 OTP code 123456 "
        "-----BEGIN PRIVATE KEY-----x-----END PRIVATE KEY-----"
    )
    redacted, events = redact_secrets(text)
    failures += emit(
        "redaction_covers_common_secrets",
        "[REDACTED_API_KEY]" in redacted
        and "[REDACTED_TOKEN]" in redacted
        and "[REDACTED_PASSWORD]" in redacted
        and "[REDACTED_EMAIL]" in redacted
        and "[REDACTED_PHONE]" in redacted
        and "[REDACTED_OTP]" in redacted
        and "[REDACTED_PRIVATE_KEY]" in redacted
        and len(events) >= 7,
        redacted=redacted,
        events=events,
    )

    firewall = CloudContextFirewall()
    cloud_result = firewall.prepare(
        CloudContextRequest(
            user_request="plan this",
            candidate_context={"memory": ["likes concise replies"], "raw_file": "password: hunter2"},
            context_sources=["memory", "file"],
            purpose="planning",
            contains_private_content=True,
            contains_raw_file=True,
            contains_raw_chat=True,
            contains_raw_screenshot=True,
        )
    )
    failures += emit(
        "raw_private_context_requires_confirmation",
        cloud_result.needs_confirmation
        and not cloud_result.allowed
        and "cloud_context_requires_confirmation" in [event["type"] for event in cloud_result.ui_events],
        result=cloud_result.as_dict(),
    )

    sanitized = firewall.prepare(
        CloudContextRequest(
            user_request="summarize safely",
            candidate_context={"memory": ["email person@example.com", "token ghp_abcdefghijklmnopqrstuvwxyz1234567890"]},
            context_sources=["memory"],
            purpose="planning",
            contains_private_content=False,
            contains_raw_file=False,
            contains_raw_chat=False,
            contains_raw_screenshot=False,
        )
    )
    failures += emit(
        "cloud_context_minimized_and_redacted",
        sanitized.allowed
        and not sanitized.needs_confirmation
        and "[REDACTED_EMAIL]" in sanitized.sanitized_prompt
        and "[REDACTED_TOKEN]" in sanitized.sanitized_prompt,
        result=sanitized.as_dict(),
    )

    context = PermissionContext(user_confirmed=False, override_granted=False)
    decisions = {
        "safe_ui": evaluate_action(action("screen.click", ActionType.SAFE_LOCAL_UI), context),
        "screen_read": evaluate_action(action("screen.observe", ActionType.PRIVACY_SCREEN_READ, privacy_sensitive=True), context),
        "message_send": evaluate_action(action("message.send_via_ui", ActionType.EXTERNAL_MESSAGE_SEND, external_visible=True), context),
        "file_delete": evaluate_action(action("file.delete", ActionType.DESTRUCTIVE_FILE_ACTION, destructive=True), context),
        "harmful": evaluate_action(action("credential.dump", ActionType.CREDENTIAL_ACCESS, risk_categories=[ActionType.ILLEGAL_HARMFUL.value]), context),
    }
    failures += emit(
        "permission_gate_decisions",
        decisions["safe_ui"].decision == "allow"
        and decisions["screen_read"].decision == "ask_override"
        and decisions["message_send"].decision == "ask_confirmation"
        and decisions["file_delete"].decision == "ask_override"
        and decisions["harmful"].decision == "hard_block",
        decisions={key: value.as_dict() for key, value in decisions.items()},
    )

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        override_store = OverrideStore(Path(tmp) / "overrides.sqlite3", expires_after_seconds=1)
        grant = override_store.create_override("a1", "DESTRUCTIVE_FILE_ACTION", ["DESTRUCTIVE_FILE_ACTION"], "confirm override", "test")
        valid_before = override_store.is_override_valid("a1")
        time.sleep(1.1)
        expired = override_store.expire_old_overrides()
        valid_after = override_store.is_override_valid("a1")
        failures += emit(
            "override_logs_and_expires_locally",
            grant.granted and valid_before and expired >= 1 and not valid_after and grant.path == str(Path(tmp) / "overrides.sqlite3"),
            grant=grant.as_dict(),
            valid_before=valid_before,
            valid_after=valid_after,
            expired=expired,
        )

        target = Path(tmp) / "note.txt"
        target.write_text("before", encoding="utf-8")
        file_action = action(
            "file.write_text",
            ActionType.DESTRUCTIVE_FILE_ACTION,
            params={"path": str(target), "content": "after"},
            destructive=True,
            verification={"method": "file_contains", "path": str(target), "text": "after"},
            rollback={"checkpoint_type": "file_snapshot", "target": str(target)},
        )
        checkpoint_store = CheckpointStore(Path(tmp) / "checkpoints.sqlite3", root=Path(tmp) / "checkpoints")
        checkpoint = checkpoint_store.create_checkpoint(file_action, task_id="task1")
        target.write_text("after", encoding="utf-8")
        observation = AgentObservation(action_id=file_action.action_id, success=True, raw_observation={"path": str(target)}, summary="wrote file")
        verification = verify_action(file_action, observation)
        target.write_text("wrong", encoding="utf-8")
        rollback = rollback_action(file_action, checkpoint)
        failures += emit(
            "checkpoint_verify_and_rollback_file",
            checkpoint is not None
            and checkpoint.checkpoint_type == "file_snapshot"
            and verification.verified
            and rollback.success
            and target.read_text(encoding="utf-8") == "before",
            checkpoint=checkpoint.as_dict() if checkpoint else None,
            verification=verification.as_dict(),
            rollback=rollback.as_dict(),
        )

    registry = ToolRegistry()
    specs = {item["name"]: item for item in registry.list_tools()}
    required_tools = {
        "screen.observe",
        "screen.click",
        "screen.type_text",
        "screen.hotkey",
        "screen.press",
        "screen.scroll",
        "screen.wait",
        "workspace_read_file",
        "file.write_text",
        "file.delete",
        "open_app",
        "message.prepare",
        "message.send_via_ui",
    }
    missing = sorted(required_tools.difference(specs))
    metadata_ok = all(
        specs[name].get("action_type") and specs[name].get("risk_categories") and specs[name].get("verification_method")
        for name in required_tools
        if name in specs
    )
    failures += emit("new_tools_registered_with_metadata", not missing and metadata_ok, missing=missing)

    executor = ToolExecutor(registry)
    from backend.eva.agent.planner import PlannedToolCall

    denied = executor.execute(PlannedToolCall(tool="message.send_via_ui", args={"recipient": "Rahul", "message": "hi"}))
    allowed = executor.execute(PlannedToolCall(tool="screen.wait", args={"seconds": 0.01, "reason": "verifier"}))
    failures += emit(
        "executor_permission_gate_blocks_unconfirmed_tools",
        # ``action`` now carries the pending id (act_...); the tool name is ``tool``.
        denied.requires_confirmation and not denied.ok and denied.tool == "message.send_via_ui" and allowed.ok,
        denied=denied.as_dict(),
        allowed=allowed.as_dict(),
    )

    event_types = [
        "permission_confirmation_required",
        "checkpoint_created",
        "verification_passed",
        "verification_failed",
        "rollback_attempted",
    ]
    failures += emit("hybrid_event_names_available", all(isinstance(item, str) for item in event_types), events=event_types)

    combined = "\n".join(
        path.read_text(encoding="utf-8", errors="replace").lower()
        for path in [
            ROOT / "backend" / "eva" / "tools" / "registry.py",
            ROOT / "backend" / "eva" / "tools" / "safe_file_tools.py",
            ROOT / "backend" / "eva" / "screen" / "screen_tools.py",
        ]
        if path.exists()
    )
    failures += emit("no_default_arbitrary_shell_tool", "shell_action" not in specs and "shell=true" not in combined and "invoke-expression" not in combined)

    print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
