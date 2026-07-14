"""Ambient trace context for the flight recorder.

The observability subsystem (``traces`` + ``LocalTraceStore``) already knows how
to write redacted JSONL events. What was missing is a way to make those events
happen automatically along the *real* execution paths — the central tool gate
and the agent loop — without threading a ``trace_id`` argument through every
signature (the gate's ``run(name, /, **kwargs)`` cannot grow a trace param
without breaking every call site).

This module supplies that glue:

  * a :class:`contextvars.ContextVar` holding the trace id of the task currently
    executing, so any code deep in a call stack can find "which trace am I in"
    without being handed one;
  * a :func:`task_trace` context manager the agent runner wraps its body in;
  * thin ``trace_*`` emit helpers the gate calls.

Every public helper is **fail-safe** (never raises into the caller) and **inert
by default**: tracing only does work when ``EVA_TRACING_ENABLED`` is truthy AND
there is an active trace on the context var. With the flag off, each helper
returns immediately, so the hot path is byte-identical to before this module
existed. Phase 37 ("turn on & exercise") is where the flag flips on by default.
"""

from __future__ import annotations

import contextlib
import os
from contextvars import ContextVar, Token
from typing import Any, Iterator

_current_trace_id: ContextVar[str | None] = ContextVar("eva_current_trace_id", default=None)


def tracing_enabled() -> bool:
    """Whether the flight recorder should capture events.

    Default-off and fail-safe: an unset or empty ``EVA_TRACING_ENABLED`` means
    off, matching the ``real_input_enabled`` / ``mcp_enabled`` convention, so the
    verifier and test suites never write trace files unless a run opts in.
    """
    raw = os.environ.get("EVA_TRACING_ENABLED", "")
    return raw.strip().lower() not in {"", "0", "false", "no", "off"}


def get_current_trace_id() -> str | None:
    """The trace id of the task currently executing, or ``None`` if untraced."""
    return _current_trace_id.get()


def set_current_trace_id(trace_id: str | None) -> Token:
    """Bind ``trace_id`` as the active trace; returns a token for :func:`reset`."""
    return _current_trace_id.set(trace_id)


def reset_current_trace_id(token: Token) -> None:
    """Restore the trace id to what it was before the matching ``set`` call."""
    try:
        _current_trace_id.reset(token)
    except Exception:
        return


@contextlib.contextmanager
def task_trace(request_id: str, user_request: str) -> Iterator[str | None]:
    """Scope a flight-recorder trace around a unit of agent work.

    Yields the new trace id (or ``None`` when tracing is disabled). Starting and
    ending the trace, plus binding/clearing the context var, all happen here so
    the caller only has to wrap its body. Wholly fail-safe: any tracing error is
    swallowed and the wrapped work still runs and still yields (``None``).
    """
    if not tracing_enabled():
        yield None
        return

    trace_id: str | None = None
    token: Token | None = None
    try:
        from . import traces

        trace_id = traces.start_trace(request_id, user_request)
        token = _current_trace_id.set(trace_id)
    except Exception:
        # If we could not even start the trace, run untraced rather than break
        # the task. Clear any half-set state first.
        if token is not None:
            reset_current_trace_id(token)
        yield None
        return

    try:
        yield trace_id
    finally:
        if token is not None:
            reset_current_trace_id(token)
        with contextlib.suppress(Exception):
            from . import traces

            traces.end_trace(trace_id or "", "task complete")


def _active_trace_id() -> str | None:
    """Return the active trace id only when tracing is on, else ``None``."""
    if not tracing_enabled():
        return None
    return _current_trace_id.get()


def trace_gate_decision(tool_name: str, decision: str, spec: Any = None) -> None:
    """Record how the central tool gate classified a call (allow/confirm/…)."""
    trace_id = _active_trace_id()
    if not trace_id:
        return
    try:
        from . import traces

        payload = {
            "tool_name": tool_name,
            "decision": decision,
            "action_type": getattr(spec, "action_type", None),
            "safety_level": getattr(spec, "safety_level", None),
        }
        traces.log_permission(trace_id, payload)
    except Exception:
        return


def trace_tool_call(tool_name: str, args: dict[str, Any] | None, result_summary: str) -> None:
    """Record an actual tool invocation and a compact summary of its result."""
    trace_id = _active_trace_id()
    if not trace_id:
        return
    try:
        from . import traces

        traces.log_tool_call(trace_id, tool_name, dict(args or {}), result_summary)
    except Exception:
        return


def trace_verification(tool_name: str, verification: dict[str, Any]) -> None:
    """Record an independent post-condition verification for a tool effect."""
    trace_id = _active_trace_id()
    if not trace_id:
        return
    try:
        from . import traces

        payload = {"tool_name": tool_name, **(verification or {})}
        traces.log_verification(trace_id, payload)
    except Exception:
        return


def trace_threat(threat: dict[str, Any]) -> None:
    """Record a detected prompt-injection / taint threat for the active task."""
    trace_id = _active_trace_id()
    if not trace_id:
        return
    try:
        from . import traces

        traces.log_threat(trace_id, threat or {})
    except Exception:
        return


def trace_critic(verdict: dict[str, Any]) -> None:
    """Record the critic's completion verdict for the active task."""
    trace_id = _active_trace_id()
    if not trace_id:
        return
    try:
        from . import traces

        traces.log_critic(trace_id, verdict or {})
    except Exception:
        return


def summarize_result(result: Any, limit: int = 240) -> str:
    """Best-effort compact string for a tool result, safe for any input.

    Prefers the ``ok`` flag and top-level keys of a dict result (the common
    shape) so a trace stays readable; falls back to a truncated repr. Secret
    redaction is applied downstream by the trace store, so this only shapes
    length, not sensitivity.
    """
    try:
        if isinstance(result, dict):
            ok = result.get("ok")
            keys = sorted(k for k in result.keys() if isinstance(k, str))[:8]
            head = f"ok={ok} " if "ok" in result else ""
            text = f"{head}keys={keys}"
        else:
            text = repr(result)
    except Exception:
        return "<unsummarizable result>"
    if len(text) > limit:
        return text[:limit] + "…"
    return text
