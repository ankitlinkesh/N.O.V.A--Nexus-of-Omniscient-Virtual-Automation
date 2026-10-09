from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import MISSING, asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .authority import evaluate_file_authority_for_approval
from .draft_preview import DraftPreview
from .write_safety import WriteSafetyPlan, build_write_safety_plan
from ..core.data_paths import data_path


APPROVAL_STATUSES = {
    "pending",
    "approved_for_future_apply",
    "denied",
    "cancelled",
    "expired",
    "blocked",
    "consumed_future_apply",
    "consumed_by_real_create",
}
NO_APPLY_LINE = "No file was created, modified, backed up, restored, or applied."
APPROVED_ONLY_LINE = "Approval recorded for future apply only. No file was created or modified."


@dataclass(frozen=True)
class FileApprovalEvent:
    event_id: str
    approval_id: str
    event_type: str
    message: str
    created_at: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class FileApprovalRequest:
    approval_id: str
    created_at: str
    expires_at: str
    status: str
    operation: str
    display_path: str
    path_hash: str
    required_confirmation_phrase: str
    safety_summary: str
    diff_preview_redacted: str = ""
    warnings: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    future_apply_enabled: bool = False
    future_required_steps: list[str] = field(default_factory=list)
    real_apply_status: str = ""
    real_apply_mode: str = ""
    real_apply_created_path: str = ""
    real_apply_created_hash: str = ""
    real_apply_verified_at: str = ""
    real_apply_rollback_status: str = ""
    real_apply_rollback_at: str = ""
    events: list[FileApprovalEvent] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["events"] = [event.as_dict() for event in self.events]
        return payload

    def __str__(self) -> str:
        return format_file_approval_request(self)


@dataclass(frozen=True)
class FileApprovalLedgerStatus:
    total: int
    pending: int
    approved_for_future_apply: int
    denied: int
    cancelled: int
    expired: int
    blocked: int
    consumed_future_apply: int
    consumed_by_real_create: int
    future_apply_enabled: bool = False

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def __str__(self) -> str:
        return format_file_approval_ledger_status()


def create_file_approval_request(
    draft_preview: DraftPreview,
    safety_plan: WriteSafetyPlan | None = None,
    repo_root: str | Path | None = None,
) -> FileApprovalRequest:
    plan = safety_plan or build_write_safety_plan(draft_preview, repo_root=repo_root)
    authority = evaluate_file_authority_for_approval(draft_preview)
    now = _now()
    approval_id = _new_approval_id(draft_preview.display_path, now)
    status = "pending" if authority.approval_request_allowed else "blocked"
    blockers = _dedupe(list(plan.eligibility.blockers) + list(authority.blockers))
    warnings = _dedupe(list(plan.eligibility.warnings) + list(authority.warnings))
    request = FileApprovalRequest(
        approval_id=approval_id,
        created_at=now,
        expires_at=(datetime.fromisoformat(now) + timedelta(minutes=60)).isoformat(),
        status=status,
        operation=draft_preview.operation,
        display_path=draft_preview.display_path,
        path_hash=_hash_text(draft_preview.display_path),
        required_confirmation_phrase=plan.confirmation_phrase,
        safety_summary=authority.reason,
        diff_preview_redacted=_safe_diff_preview(draft_preview, allowed=status == "pending"),
        warnings=warnings,
        blockers=blockers,
        future_apply_enabled=False,
        future_required_steps=authority.required_future_steps,
        events=[
            _event(
                approval_id,
                "created" if status == "pending" else "blocked",
                "Approval request recorded for future apply metadata." if status == "pending" else "Approval request blocked by FileAgent safety policy.",
            )
        ],
    )
    _upsert_request(request)
    return request


def get_file_approval_request(approval_id: str) -> FileApprovalRequest | None:
    wanted = str(approval_id or "").strip()
    return next((request for request in _load_requests() if request.approval_id == wanted), None)


def list_file_approval_requests(status: str | None = None, limit: int = 20) -> list[FileApprovalRequest]:
    requests = _load_requests()
    wanted = str(status or "").strip()
    if wanted:
        requests = [request for request in requests if request.status == wanted]
    return sorted(requests, key=lambda request: request.created_at, reverse=True)[: max(1, int(limit or 20))]


def approve_file_approval_request(approval_id: str, confirmation_phrase: str) -> FileApprovalRequest:
    request = _require_request(approval_id)
    if request.status != "pending":
        updated = _with_event(request, "approve_refused", f"Approval cannot be approved from status {request.status}.")
        _upsert_request(updated)
        return updated
    if str(confirmation_phrase or "").strip() != request.required_confirmation_phrase:
        updated = _with_event(request, "approve_refused", "Wrong confirmation phrase. Approval remains pending.")
        _upsert_request(updated)
        return updated
    updated = _replace_request(
        request,
        status="approved_for_future_apply",
        event_type="approved_for_future_apply",
        message="Exact confirmation phrase accepted for future apply metadata only.",
    )
    _upsert_request(updated)
    return updated


def deny_file_approval_request(approval_id: str, reason: str | None = None) -> FileApprovalRequest:
    request = _require_request(approval_id)
    updated = _replace_request(request, status="denied", event_type="denied", message=f"Approval denied. {_clean_reason(reason)}")
    _upsert_request(updated)
    return updated


def cancel_file_approval_request(approval_id: str, reason: str | None = None) -> FileApprovalRequest:
    request = _require_request(approval_id)
    updated = _replace_request(request, status="cancelled", event_type="cancelled", message=f"Approval cancelled. {_clean_reason(reason)}")
    _upsert_request(updated)
    return updated


def expire_old_file_approvals(max_age_minutes: int = 60) -> int:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=max(0, int(max_age_minutes or 0)))
    changed = 0
    updated: list[FileApprovalRequest] = []
    for request in _load_requests():
        created = _parse_dt(request.created_at)
        expires = _parse_dt(request.expires_at)
        should_expire = request.status == "pending" and (created <= cutoff or expires <= now)
        if should_expire:
            request = _replace_request(request, status="expired", event_type="expired", message="Approval expired without deleting the audit record.")
            changed += 1
        updated.append(request)
    _save_requests(updated)
    return changed


def record_file_approval_event(approval_id: str, event_type: str, message: str) -> FileApprovalEvent:
    request = _require_request(approval_id)
    event = _event(request.approval_id, event_type, message)
    updated = FileApprovalRequest(**{**request.as_dict(), "events": [*request.events, event]})
    _upsert_request(updated)
    return event


def update_file_approval_real_apply(
    approval_id: str,
    *,
    status: str | None = None,
    event_type: str,
    message: str,
    real_apply_status: str | None = None,
    real_apply_mode: str | None = None,
    real_apply_created_path: str | None = None,
    real_apply_created_hash: str | None = None,
    real_apply_verified_at: str | None = None,
    real_apply_rollback_status: str | None = None,
    real_apply_rollback_at: str | None = None,
) -> FileApprovalRequest:
    request = _require_request(approval_id)
    payload = request.as_dict()
    if status is not None:
        payload["status"] = status
    for key, value in {
        "real_apply_status": real_apply_status,
        "real_apply_mode": real_apply_mode,
        "real_apply_created_path": real_apply_created_path,
        "real_apply_created_hash": real_apply_created_hash,
        "real_apply_verified_at": real_apply_verified_at,
        "real_apply_rollback_status": real_apply_rollback_status,
        "real_apply_rollback_at": real_apply_rollback_at,
    }.items():
        if value is not None:
            payload[key] = value
    payload["events"] = [*request.events, _event(request.approval_id, event_type, message)]
    updated = FileApprovalRequest(**payload)
    _upsert_request(updated)
    return updated


def format_file_approval_request(request: FileApprovalRequest | None) -> str:
    if request is None:
        return "\n".join(["File approval request", "", "Status: not found.", NO_APPLY_LINE])
    lines = [
        "File approval request",
        "",
        f"Approval ID: {request.approval_id}",
        f"Status: {request.status}",
        f"Operation: {request.operation}",
        f"Path: {request.display_path}",
        f"Expires: {_short_time(request.expires_at)}",
        f"Future apply enabled: {'yes' if request.future_apply_enabled else 'no'}",
        f"Required confirmation phrase: {request.required_confirmation_phrase}",
        "",
        "Safety:",
        request.safety_summary,
    ]
    if request.status == "approved_for_future_apply":
        lines.extend(["", APPROVED_ONLY_LINE])
    if request.blockers:
        lines.append("Blockers:")
        lines.extend(f"- {item}" for item in request.blockers)
    if request.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {item}" for item in request.warnings)
    if request.diff_preview_redacted:
        lines.extend(["", "Diff preview summary:", _fence(request.diff_preview_redacted, "diff")])
    if request.future_required_steps:
        lines.append("Future required steps:")
        lines.extend(f"- {item}" for item in request.future_required_steps)
    lines.extend(["", NO_APPLY_LINE])
    return "\n".join(lines)


def format_file_approval_list(requests: list[FileApprovalRequest]) -> str:
    lines = ["File approval requests", "", f"Count: {len(requests)}"]
    if not requests:
        lines.append("No matching approval requests.")
    for request in requests[:20]:
        lines.append(f"- {request.approval_id}: {request.status}; {request.operation}; {request.display_path}; expires {_short_time(request.expires_at)}")
    lines.extend(["", NO_APPLY_LINE])
    return "\n".join(lines)


def format_file_approval_events(approval_id: str) -> str:
    request = get_file_approval_request(approval_id)
    if request is None:
        return "\n".join(["Approval events", "", "Status: approval not found.", NO_APPLY_LINE])
    lines = ["Approval events", "", f"Approval ID: {request.approval_id}", f"Status: {request.status}"]
    if not request.events:
        lines.append("No events recorded.")
    for event in request.events[-20:]:
        lines.append(f"- {_short_time(event.created_at)}: {event.event_type}; {event.message}")
    lines.extend(["", NO_APPLY_LINE])
    return "\n".join(lines)


def format_file_approval_ledger_status() -> str:
    status = _ledger_status()
    return "\n".join(
        [
            "File approval ledger status",
            "",
            f"Total records: {status.total}",
            f"Pending: {status.pending}",
            f"Approved for future apply: {status.approved_for_future_apply}",
            f"Denied: {status.denied}",
            f"Cancelled: {status.cancelled}",
            f"Expired: {status.expired}",
            f"Blocked: {status.blocked}",
            f"Consumed future apply: {status.consumed_future_apply}",
            f"Consumed by real create: {status.consumed_by_real_create}",
            "Future apply enabled: no",
            "",
            "Storage: local ignored runtime metadata.",
            NO_APPLY_LINE,
        ]
    )


def _ledger_status() -> FileApprovalLedgerStatus:
    requests = _load_requests()
    counts = {status: 0 for status in APPROVAL_STATUSES}
    for request in requests:
        counts[request.status] = counts.get(request.status, 0) + 1
    return FileApprovalLedgerStatus(total=len(requests), **{key: counts.get(key, 0) for key in APPROVAL_STATUSES})


def _load_requests() -> list[FileApprovalRequest]:
    path = _ledger_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = payload.get("requests") if isinstance(payload, dict) else []
    requests: list[FileApprovalRequest] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        events = [_event_from_dict(event) for event in item.get("events", []) if isinstance(event, dict)]
        data = {}
        for key, field_def in FileApprovalRequest.__dataclass_fields__.items():
            if key == "events":
                continue
            if key in item:
                data[key] = item.get(key)
            elif field_def.default is not MISSING:
                data[key] = field_def.default
            else:
                data[key] = None
        requests.append(FileApprovalRequest(**data, events=events))
    return requests


def _save_requests(requests: list[FileApprovalRequest]) -> None:
    path = _ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "future_apply_enabled": False, "requests": [request.as_dict() for request in requests]}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _upsert_request(request: FileApprovalRequest) -> None:
    requests = [item for item in _load_requests() if item.approval_id != request.approval_id]
    requests.append(request)
    _save_requests(requests)


def _ledger_path() -> Path:
    override = os.environ.get("EVA_FILE_AGENT_APPROVAL_LEDGER_PATH")
    if override:
        return Path(override)
    return data_path(Path(__file__).resolve().parents[1] / "data" / "file_agent" / "approval_ledger.json")


def _new_approval_id(display_path: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{display_path}|{created_at}|{uuid.uuid4().hex}".encode("utf-8")).hexdigest()[:12]
    return f"fap_{digest}"


def _hash_text(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()[:16]


def _safe_diff_preview(draft_preview: DraftPreview, *, allowed: bool) -> str:
    if not allowed:
        return ""
    text = str(draft_preview.diff_preview or "")
    if not text:
        return "No diff preview was available."
    if len(text) > 1800:
        return text[:1800] + "\n... diff preview truncated ..."
    return text


def _event(approval_id: str, event_type: str, message: str) -> FileApprovalEvent:
    return FileApprovalEvent(event_id=f"evt_{uuid.uuid4().hex[:12]}", approval_id=approval_id, event_type=str(event_type or "event"), message=_clean_reason(message), created_at=_now())


def _event_from_dict(data: dict[str, object]) -> FileApprovalEvent:
    return FileApprovalEvent(
        event_id=str(data.get("event_id") or f"evt_{uuid.uuid4().hex[:12]}"),
        approval_id=str(data.get("approval_id") or ""),
        event_type=str(data.get("event_type") or "event"),
        message=str(data.get("message") or ""),
        created_at=str(data.get("created_at") or _now()),
    )


def _with_event(request: FileApprovalRequest, event_type: str, message: str) -> FileApprovalRequest:
    return FileApprovalRequest(**{**request.as_dict(), "events": [*request.events, _event(request.approval_id, event_type, message)]})


def _replace_request(request: FileApprovalRequest, *, status: str, event_type: str, message: str) -> FileApprovalRequest:
    return FileApprovalRequest(**{**request.as_dict(), "status": status, "events": [*request.events, _event(request.approval_id, event_type, message)]})


def _require_request(approval_id: str) -> FileApprovalRequest:
    request = get_file_approval_request(approval_id)
    if request is None:
        now = _now()
        return FileApprovalRequest(
            approval_id=str(approval_id or "unknown").strip() or "unknown",
            created_at=now,
            expires_at=now,
            status="blocked",
            operation="unknown",
            display_path="unknown",
            path_hash="unknown",
            required_confirmation_phrase="unavailable",
            safety_summary="Approval request was not found.",
            blockers=["Approval request was not found."],
            events=[_event(str(approval_id or "unknown"), "not_found", "Approval request was not found.")],
        )
    return request


def _parse_dt(value: str) -> datetime:
    try:
        return datetime.fromisoformat(str(value or ""))
    except ValueError:
        return datetime.now(timezone.utc)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_time(value: str) -> str:
    try:
        dt = datetime.fromisoformat(value)
        return dt.replace(microsecond=0).isoformat()
    except ValueError:
        return "unknown"


def _clean_reason(value: str | None) -> str:
    text = str(value or "No reason provided.").strip()
    return text.replace("\n", " ")[:240]


def _fence(text: str, language: str = "text") -> str:
    safe = str(text or "").replace("```", "` ` `")
    return f"```{language}\n{safe}\n```"


def _dedupe(items: list[str]) -> list[str]:
    output: list[str] = []
    for item in items:
        if item and item not in output:
            output.append(item)
    return output
