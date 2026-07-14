from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from .local_trace_store import LocalTraceStore


def _store(root: Path | None = None) -> LocalTraceStore:
    return LocalTraceStore(root=root)


def start_trace(request_id: str, user_request: str, root: Path | None = None) -> str:
    trace_id = f"trace_{request_id or uuid4().hex}"
    _store(root).append(trace_id, "trace_started", {"request_id": request_id, "user_request": user_request})
    return trace_id


def log_agent_selection(trace_id: str, agent_name: str, reason: str, root: Path | None = None) -> None:
    _store(root).append(trace_id, "agent_selected", {"agent_name": agent_name, "reason": reason})


def log_llm_call(trace_id: str, provider: str, model: str, prompt_summary: str, result_summary: str, root: Path | None = None) -> None:
    _store(root).append(trace_id, "llm_call", {"provider": provider, "model": model, "prompt_summary": prompt_summary, "result_summary": result_summary})


def log_tool_call(trace_id: str, tool_name: str, args_redacted: dict[str, Any], result_summary: str, root: Path | None = None) -> None:
    _store(root).append(trace_id, "tool_call", {"tool_name": tool_name, "args": args_redacted, "result_summary": result_summary})


def log_permission(trace_id: str, decision: dict[str, Any], root: Path | None = None) -> None:
    _store(root).append(trace_id, "permission", decision)


def log_verification(trace_id: str, verification: dict[str, Any], root: Path | None = None) -> None:
    _store(root).append(trace_id, "verification", verification)


def log_threat(trace_id: str, threat: dict[str, Any], root: Path | None = None) -> None:
    _store(root).append(trace_id, "threat", threat)


def log_critic(trace_id: str, verdict: dict[str, Any], root: Path | None = None) -> None:
    _store(root).append(trace_id, "critic", verdict)


def log_dry_run_preview(trace_id: str, payload: dict[str, Any], root: Path | None = None) -> None:
    _store(root).append(trace_id, "dry_run_preview", payload)


def log_execution_bridge(trace_id: str, payload: dict[str, Any], root: Path | None = None) -> None:
    _store(root).append(trace_id, "v2_execute", payload)


def log_pending_action_event(trace_id: str, event_type: str, payload: dict[str, Any], root: Path | None = None) -> None:
    allowed = {
        "pending_action_created",
        "pending_action_confirmed",
        "pending_action_cancelled",
        "pending_action_expired",
        "pending_action_executor_unavailable",
    }
    safe_type = event_type if event_type in allowed else "pending_action_created"
    summary = {
        "action_id": payload.get("action_id") or payload.get("id"),
        "risk_category": payload.get("risk_category"),
        "status": payload.get("status"),
        "summary": payload.get("summary"),
        "source": payload.get("source"),
        "selected_agent": payload.get("selected_agent"),
    }
    _store(root).append(trace_id, safe_type, summary)


def end_trace(trace_id: str, final_summary: str, root: Path | None = None) -> None:
    _store(root).append(trace_id, "trace_ended", {"final_summary": final_summary})


def traces_status() -> dict[str, Any]:
    status = _store().status()
    status["message"] = "Traces status: local JSONL trace store is active; remote tracing is disabled unless explicitly configured."
    return status


def list_traces(limit: int = 20, root: Path | None = None) -> list[dict]:
    store = _store(root)
    summaries: list[dict] = []
    for trace_id in store.list_trace_ids(limit):
        events = store.read(trace_id)
        request = ""
        final_summary = ""
        for event in events:
            if event.get("type") == "trace_started":
                request = (event.get("payload") or {}).get("user_request", "")
            elif event.get("type") == "trace_ended":
                final_summary = (event.get("payload") or {}).get("final_summary", "")
        summaries.append(
            {
                "trace_id": trace_id,
                "path": str(store.path_for(trace_id)),
                "event_count": len(events),
                "request": request,
                "final_summary": final_summary,
            }
        )
    return summaries


def read_trace(trace_id: str, root: Path | None = None) -> dict:
    events = _store(root).read(trace_id)
    return {"trace_id": trace_id, "found": bool(events), "events": events}
