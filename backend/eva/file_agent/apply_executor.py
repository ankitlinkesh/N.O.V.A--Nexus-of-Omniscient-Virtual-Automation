from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .approval_ledger import FileApprovalRequest, get_file_approval_request, record_file_approval_event
from .authority import evaluate_file_authority_for_sandbox_apply, file_authority_to_global_decision
from ..authority.formatter import format_authority_decision
from ..core.data_paths import data_path


SANDBOX_LINE = "Sandbox only. No real project file was created, modified, backed up, restored, or applied."
SUPPORTED_OPERATIONS = {"create_preview", "append_preview", "replace_preview", "rewrite_preview"}


@dataclass(frozen=True)
class FileApplyRequest:
    approval_id: str
    approval_status: str
    operation: str
    display_path: str
    sandbox_target: str
    proposed_content: str
    sandbox_only: bool = True
    allowed: bool = False
    reason: str = ""
    warnings: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def __str__(self) -> str:
        return format_apply_request(self)


@dataclass(frozen=True)
class FileBackupRecord:
    approval_id: str
    backup_id: str
    sandbox_target: str
    backup_path: str
    existed_before: bool
    content_hash_before: str
    created_at: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class FileApplyResult:
    approval_id: str
    ok: bool
    sandbox_only: bool
    sandbox_target: str
    operation: str
    backup: FileBackupRecord | None
    content_hash_after: str
    message: str
    error: str | None = None
    created_at: str = ""

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["backup"] = self.backup.as_dict() if self.backup else None
        return payload

    def __str__(self) -> str:
        return format_apply_result(self)


@dataclass(frozen=True)
class FileVerificationResult:
    approval_id: str
    verified: bool
    confidence: float
    sandbox_target: str
    evidence: str
    failure_reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def __str__(self) -> str:
        return format_verification_result(self)


@dataclass(frozen=True)
class FileRollbackResult:
    approval_id: str
    attempted: bool
    success: bool
    sandbox_only: bool
    restored_path: str | None
    summary: str
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def __str__(self) -> str:
        return format_rollback_result(self)


def build_apply_request_from_approval(approval_id: str, sandbox_only: bool = True) -> FileApplyRequest:
    approval = get_file_approval_request(approval_id)
    if approval is None:
        return _blocked_request(approval_id, "unknown", "unknown", "unknown", "Approval request was not found.")
    if not sandbox_only:
        return _blocked_request(approval.approval_id, approval.status, approval.operation, approval.display_path, "Real apply is unavailable; sandbox_only must stay true.")
    if approval.status != "approved_for_future_apply":
        return _blocked_request(
            approval.approval_id,
            approval.status,
            approval.operation,
            approval.display_path,
            f"Approval must be approved_for_future_apply before sandbox apply; current status is {approval.status}.",
        )
    decision = evaluate_file_authority_for_sandbox_apply(approval)
    if not decision.sandbox_apply_allowed:
        return _blocked_request(approval.approval_id, approval.status, approval.operation, approval.display_path, decision.reason, blockers=tuple(decision.blockers))
    proposed = _content_from_diff(approval.diff_preview_redacted)
    if not proposed.strip():
        return _blocked_request(approval.approval_id, approval.status, approval.operation, approval.display_path, "Approval has no safe diff preview content to apply in the sandbox.")
    target = map_approval_to_sandbox_target(approval)
    return FileApplyRequest(
        approval_id=approval.approval_id,
        approval_status=approval.status,
        operation=approval.operation,
        display_path=approval.display_path,
        sandbox_target=str(target),
        proposed_content=proposed,
        sandbox_only=True,
        allowed=True,
        reason="Approved metadata can be applied inside the FileAgent sandbox only.",
        warnings=tuple(decision.warnings),
        blockers=(),
    )


def evaluate_apply_request(request: FileApplyRequest) -> Any:
    approval = get_file_approval_request(request.approval_id)
    return evaluate_file_authority_for_sandbox_apply(approval)


def create_sandbox_apply_workspace() -> Path:
    root = _sandbox_root()
    root.mkdir(parents=True, exist_ok=True)
    (root / "targets").mkdir(parents=True, exist_ok=True)
    (root / "backups").mkdir(parents=True, exist_ok=True)
    return root


def create_sandbox_backup(target_path: str | Path) -> FileBackupRecord:
    target = Path(target_path)
    if not is_sandbox_path(target):
        raise ValueError("Sandbox backup target must stay inside FileAgent sandbox.")
    create_sandbox_apply_workspace()
    existed = target.exists()
    before = target.read_text(encoding="utf-8", errors="replace") if existed else ""
    backup_id = f"bak_{uuid.uuid4().hex[:12]}"
    backup_path = _sandbox_root() / "backups" / f"{backup_id}.json"
    record = FileBackupRecord(
        approval_id=target.stem.split("_", 1)[0] if "_" in target.stem else "unknown",
        backup_id=backup_id,
        sandbox_target=str(target),
        backup_path=str(backup_path),
        existed_before=existed,
        content_hash_before=_hash_text(before),
        created_at=_now(),
    )
    backup_path.write_text(
        json.dumps({"record": record.as_dict(), "content": before}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return record


def apply_draft_to_sandbox(request: FileApplyRequest) -> FileApplyResult:
    if not request.allowed or not request.sandbox_only:
        _record_event_safe(request.approval_id, "sandbox_apply_refused", request.reason or "Sandbox apply request was refused.")
        return FileApplyResult(request.approval_id, False, True, request.sandbox_target, request.operation, None, "", request.reason, error=request.reason, created_at=_now())
    target = Path(request.sandbox_target)
    if not is_sandbox_path(target):
        _record_event_safe(request.approval_id, "sandbox_apply_refused", "Sandbox target was outside the FileAgent sandbox.")
        return FileApplyResult(request.approval_id, False, True, str(target), request.operation, None, "", "Refused outside-sandbox target.", error="outside_sandbox", created_at=_now())
    if request.operation not in SUPPORTED_OPERATIONS:
        _record_event_safe(request.approval_id, "sandbox_apply_refused", "Unsupported sandbox apply operation.")
        return FileApplyResult(request.approval_id, False, True, str(target), request.operation, None, "", "Unsupported operation.", error="unsupported_operation", created_at=_now())
    _record_event_safe(request.approval_id, "sandbox_apply_requested", "Sandbox apply requested; broad real apply remains blocked.")
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = create_sandbox_backup(target)
    _record_event_safe(request.approval_id, "sandbox_backup_created", "Sandbox-only backup/checkpoint created.")
    target.write_text(request.proposed_content, encoding="utf-8")
    content_hash = _hash_text(request.proposed_content)
    result = FileApplyResult(
        approval_id=request.approval_id,
        ok=True,
        sandbox_only=True,
        sandbox_target=str(target),
        operation=request.operation,
        backup=backup,
        content_hash_after=content_hash,
        message="Sandbox apply completed. Real project files were not touched.",
        created_at=_now(),
    )
    _save_latest_result(result)
    _record_event_safe(request.approval_id, "sandbox_apply_completed", "Sandbox apply completed without touching real project files.")
    return result


def verify_sandbox_apply(request: FileApplyRequest, result: FileApplyResult | None = None) -> FileVerificationResult:
    result = result or _load_latest_result(request.approval_id)
    if result is None or not result.ok:
        verification = FileVerificationResult(request.approval_id, False, 0.0, request.sandbox_target, "No successful sandbox apply result exists.", "missing_result")
        _record_event_safe(request.approval_id, "sandbox_verify_failed", verification.evidence)
        return verification
    target = Path(result.sandbox_target)
    if not is_sandbox_path(target) or not target.exists():
        verification = FileVerificationResult(request.approval_id, False, 0.1, str(target), "Sandbox target was unavailable.", "missing_sandbox_target")
        _record_event_safe(request.approval_id, "sandbox_verify_failed", verification.evidence)
        return verification
    actual = target.read_text(encoding="utf-8", errors="replace")
    expected_hash = result.content_hash_after
    verified = _hash_text(actual) == expected_hash
    verification = FileVerificationResult(
        request.approval_id,
        verified,
        0.95 if verified else 0.25,
        str(target),
        "Sandbox file content matches the approved sandbox result." if verified else "Sandbox file content did not match the expected hash.",
        None if verified else "hash_mismatch",
    )
    _record_event_safe(request.approval_id, "sandbox_verify_passed" if verified else "sandbox_verify_failed", verification.evidence)
    return verification


def rollback_sandbox_apply(result: FileApplyResult) -> FileRollbackResult:
    if result.backup is None:
        rollback = FileRollbackResult(result.approval_id, False, False, True, result.sandbox_target, "No sandbox backup was available.", "missing_backup")
        _record_event_safe(result.approval_id, "sandbox_rollback_failed", rollback.summary)
        return rollback
    target = Path(result.sandbox_target)
    backup_path = Path(result.backup.backup_path)
    if not is_sandbox_path(target) or not is_sandbox_path(backup_path):
        rollback = FileRollbackResult(result.approval_id, True, False, True, str(target), "Rollback refused because target or backup was outside the sandbox.", "outside_sandbox")
        _record_event_safe(result.approval_id, "sandbox_rollback_failed", rollback.summary)
        return rollback
    try:
        payload = json.loads(backup_path.read_text(encoding="utf-8"))
        content = str(payload.get("content") or "")
        existed = bool(payload.get("record", {}).get("existed_before"))
        if existed:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        elif target.exists():
            target.unlink()
        rollback = FileRollbackResult(result.approval_id, True, True, True, str(target), "Sandbox rollback restored the sandbox checkpoint only.")
        _record_event_safe(result.approval_id, "sandbox_rollback_completed", "Sandbox rollback completed; no real project file was restored.")
        return rollback
    except (OSError, json.JSONDecodeError) as exc:
        rollback = FileRollbackResult(result.approval_id, True, False, True, str(target), "Sandbox rollback failed safely.", type(exc).__name__)
        _record_event_safe(result.approval_id, "sandbox_rollback_failed", rollback.summary)
        return rollback


def format_apply_executor_status() -> str:
    return "\n".join(
        [
            "FileAgent apply executor status",
            "",
            "Mode: sandbox harness only.",
            "Real apply enabled: no.",
            "Sandbox writes: allowed only under ignored FileAgent runtime sandbox.",
            "Backup/checkpoint: sandbox-only.",
            "Verification: sandbox-only readback and hash comparison.",
            "Rollback: sandbox-only checkpoint restoration.",
            "",
            SANDBOX_LINE,
        ]
    )


def format_apply_request(request: FileApplyRequest) -> str:
    decision = file_authority_to_global_decision(
        evaluate_apply_request(request),
        action_type="file.sandbox_apply_request",
        capability_id="file.sandbox_apply_approved",
        approval_id=request.approval_id,
    )
    lines = [
        "FileAgent sandbox apply request",
        "",
        f"Approval ID: {request.approval_id}",
        f"Approval status: {request.approval_status}",
        f"Operation: {request.operation}",
        f"Target: {request.display_path}",
        f"Sandbox target: {_sandbox_label(request.sandbox_target)}",
        f"Allowed: {'yes' if request.allowed else 'no'}",
        f"Reason: {request.reason}",
    ]
    if request.blockers:
        lines.append("Blockers:")
        lines.extend(f"- {item}" for item in request.blockers)
    if request.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {item}" for item in request.warnings)
    lines.extend(["", format_authority_decision(decision), "", SANDBOX_LINE])
    return "\n".join(lines)


def format_apply_result(result: FileApplyResult) -> str:
    decision = allow_decision_for_apply_result(result)
    lines = [
        "FileAgent sandbox apply result",
        "",
        f"Approval ID: {result.approval_id}",
        f"Status: {'applied in sandbox' if result.ok else 'refused'}",
        f"Operation: {result.operation}",
        f"Sandbox target: {_sandbox_label(result.sandbox_target)}",
        f"Message: {result.message}",
    ]
    if result.backup:
        lines.extend(
            [
                "Backup/checkpoint:",
                f"- ID: {result.backup.backup_id}",
                f"- Location: {_sandbox_label(result.backup.backup_path)}",
                f"- Existing sandbox file: {'yes' if result.backup.existed_before else 'no'}",
            ]
        )
    if result.error:
        lines.append(f"Error: {result.error}")
    lines.extend(["", format_authority_decision(decision), "", SANDBOX_LINE])
    return "\n".join(lines)


def format_verification_result(result: FileVerificationResult) -> str:
    from ..authority.decision import allow_sandbox_decision

    decision = allow_sandbox_decision(
        action_type="file.sandbox_verify_apply",
        action_category="verify",
        capability_id="file.sandbox_verify_apply",
        agent_name="FileAgent",
        approval_id=result.approval_id,
        reason="Verification reads sandbox state only.",
        rollback_available=False,
    )
    return "\n".join(
        [
            "FileAgent sandbox verification",
            "",
            f"Approval ID: {result.approval_id}",
            f"Verified: {'yes' if result.verified else 'no'}",
            f"Confidence: {result.confidence:.2f}",
            f"Sandbox target: {_sandbox_label(result.sandbox_target)}",
            f"Evidence: {result.evidence}",
            *([f"Failure: {result.failure_reason}"] if result.failure_reason else []),
            "",
            format_authority_decision(decision),
            "",
            SANDBOX_LINE,
        ]
    )


def format_rollback_result(result: FileRollbackResult) -> str:
    from ..authority.decision import allow_sandbox_decision

    decision = allow_sandbox_decision(
        action_type="file.sandbox_rollback_apply",
        action_category="rollback",
        capability_id="file.sandbox_rollback_apply",
        agent_name="FileAgent",
        approval_id=result.approval_id,
        reason="Rollback restores sandbox checkpoint state only.",
        verification_required=False,
    )
    return "\n".join(
        [
            "FileAgent sandbox rollback",
            "",
            f"Approval ID: {result.approval_id}",
            f"Attempted: {'yes' if result.attempted else 'no'}",
            f"Success: {'yes' if result.success else 'no'}",
            f"Sandbox target: {_sandbox_label(result.restored_path or '')}",
            f"Summary: {result.summary}",
            *([f"Error: {result.error}"] if result.error else []),
            "",
            format_authority_decision(decision),
            "",
            SANDBOX_LINE,
        ]
    )


def allow_decision_for_apply_result(result: FileApplyResult) -> AuthorityDecision:
    from ..authority.decision import allow_sandbox_decision, block_real_execution_decision
    from ..authority.models import AuthorityDecision

    if result.ok:
        return allow_sandbox_decision(
            action_type="file.sandbox_apply_approved",
            action_category="sandbox_apply",
            capability_id="file.sandbox_apply_approved",
            agent_name="FileAgent",
            approval_id=result.approval_id,
            reason="Approved metadata was applied inside the sandbox harness only.",
        )
    return block_real_execution_decision(
        action_type="file.sandbox_apply_approved",
        action_category="sandbox_apply",
        capability_id="file.sandbox_apply_approved",
        agent_name="FileAgent",
        approval_id=result.approval_id,
        reason=result.message,
        blocked_reason=result.error or result.message,
    )


def is_sandbox_path(path: str | Path) -> bool:
    try:
        Path(path).resolve().relative_to(_sandbox_root().resolve())
        return True
    except (OSError, ValueError):
        return False


def map_approval_to_sandbox_target(approval: FileApprovalRequest) -> Path:
    safe_name = _safe_name(approval.display_path)
    digest = hashlib.sha256(f"{approval.approval_id}|{approval.display_path}".encode("utf-8")).hexdigest()[:12]
    suffix = Path(approval.display_path).suffix or ".txt"
    return _sandbox_root() / "targets" / f"{approval.approval_id}_{digest}_{safe_name}{suffix}"


def _blocked_request(
    approval_id: str,
    status: str,
    operation: str,
    display_path: str,
    reason: str,
    *,
    blockers: tuple[str, ...] = (),
) -> FileApplyRequest:
    return FileApplyRequest(
        approval_id=str(approval_id or "unknown"),
        approval_status=str(status or "unknown"),
        operation=str(operation or "unknown"),
        display_path=str(display_path or "unknown"),
        sandbox_target=str(_sandbox_root() / "targets" / "refused.txt"),
        proposed_content="",
        sandbox_only=True,
        allowed=False,
        reason=str(reason or "Sandbox apply refused."),
        blockers=blockers,
    )


def _content_from_diff(diff_text: str) -> str:
    output: list[str] = []
    for line in str(diff_text or "").splitlines():
        if line.startswith(("+++", "---", "@@")):
            continue
        if line.startswith("+") and not line.startswith("+++"):
            output.append(line[1:])
        elif line.startswith(" ") and not line.startswith("  "):
            output.append(line[1:])
        elif line and not line.startswith("-") and not line.startswith("\\"):
            output.append(line)
    return "\n".join(output).rstrip("\n") + ("\n" if output else "")


def _save_latest_result(result: FileApplyResult) -> None:
    state = _load_state()
    state[result.approval_id] = result.as_dict()
    _state_path().write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_latest_result(approval_id: str) -> FileApplyResult | None:
    item = _load_state().get(str(approval_id or ""))
    if not isinstance(item, dict):
        return None
    backup_data = item.get("backup")
    backup = FileBackupRecord(**backup_data) if isinstance(backup_data, dict) else None
    return FileApplyResult(
        approval_id=str(item.get("approval_id") or approval_id),
        ok=bool(item.get("ok")),
        sandbox_only=bool(item.get("sandbox_only", True)),
        sandbox_target=str(item.get("sandbox_target") or ""),
        operation=str(item.get("operation") or "unknown"),
        backup=backup,
        content_hash_after=str(item.get("content_hash_after") or ""),
        message=str(item.get("message") or ""),
        error=item.get("error") if isinstance(item.get("error"), str) else None,
        created_at=str(item.get("created_at") or ""),
    )


def _load_state() -> dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _state_path() -> Path:
    root = create_sandbox_apply_workspace()
    return root / "apply_state.json"


def _record_event_safe(approval_id: str, event_type: str, message: str) -> None:
    try:
        record_file_approval_event(approval_id, event_type, message)
    except Exception:
        return


def _sandbox_root() -> Path:
    override = os.environ.get("EVA_FILE_AGENT_APPLY_SANDBOX_ROOT")
    if override:
        return Path(override)
    return data_path(Path(__file__).resolve().parents[1] / "data" / "file_agent" / "apply_sandbox")


def _sandbox_label(path: str | Path) -> str:
    if not path:
        return "sandbox"
    try:
        rel = Path(path).resolve().relative_to(_sandbox_root().resolve())
        return f"sandbox/{rel.as_posix()}"
    except (OSError, ValueError):
        return "sandbox/refused"


def _safe_name(display_path: str) -> str:
    stem = Path(str(display_path or "target")).stem or "target"
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in stem)
    return cleaned.strip("_")[:40] or "target"


def _hash_text(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()[:16]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
