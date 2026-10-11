from __future__ import annotations

import heapq
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..privacy.redaction import redact_secrets
from ..core.data_paths import data_path


DEFAULT_TRACE_ROOT = Path(__file__).resolve().parents[1] / "data" / "traces"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize(value: Any) -> Any:
    text = json.dumps(value, ensure_ascii=False, default=str)
    redacted, _events = redact_secrets(text)
    try:
        return json.loads(redacted)
    except Exception:
        return redacted


# Retention. Traces only ever grew: 34k files / 165 MB, and "learn from traces"
# reads just the newest 25. Keep the newest MAX_TRACE_FILES and anything younger
# than MAX_TRACE_AGE_DAYS; the rest is pruned once per process per folder.
MAX_TRACE_FILES = 2000
MAX_TRACE_AGE_DAYS = 60
_PRUNED_ROOTS: set[str] = set()


def _trace_entries(root: Path) -> list[os.DirEntry]:
    # os.scandir carries the stat data on Windows, so this is one call per folder,
    # not one per file (list_trace_ids took 1.3s over 34k files with Path.stat()).
    try:
        with os.scandir(root) as entries:
            return [entry for entry in entries if entry.name.endswith(".jsonl") and entry.is_file()]
    except OSError:
        return []


def _mtime(entry: os.DirEntry) -> float:
    try:
        return entry.stat().st_mtime
    except OSError:
        return 0.0


def prune_traces(root: Path, *, max_files: int = MAX_TRACE_FILES, max_age_days: int = MAX_TRACE_AGE_DAYS, now: float | None = None) -> int:
    """Delete trace files that are both beyond the newest ``max_files`` and older
    than ``max_age_days``. Returns how many were removed. Never raises."""
    entries = sorted(_trace_entries(root), key=_mtime, reverse=True)
    cutoff = (now if now is not None else time.time()) - max_age_days * 86400
    removed = 0
    for entry in entries[max_files:]:
        if _mtime(entry) >= cutoff:
            continue
        try:
            os.remove(entry.path)
            removed += 1
        except OSError:
            continue
    return removed


class LocalTraceStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or data_path(DEFAULT_TRACE_ROOT)
        self.root.mkdir(parents=True, exist_ok=True)
        key = str(self.root)
        if key not in _PRUNED_ROOTS:
            _PRUNED_ROOTS.add(key)
            prune_traces(self.root)

    def path_for(self, trace_id: str) -> Path:
        safe = "".join(ch for ch in trace_id if ch.isalnum() or ch in {"-", "_"})[:80] or "trace"
        return self.root / f"{safe}.jsonl"

    def append(self, trace_id: str, event_type: str, payload: dict[str, Any]) -> None:
        event = {"created_at": _now(), "type": event_type, "payload": _sanitize(payload)}
        with self.path_for(trace_id).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def status(self) -> dict[str, Any]:
        count = len(_trace_entries(self.root)) if self.root.exists() else 0
        return {"ok": True, "backend": "local", "path": str(self.root), "trace_files": count}

    def list_trace_ids(self, limit: int = 20) -> list[str]:
        """Trace ids for recent trace files, newest first, capped at ``limit``.

        Fail-safe: any filesystem error (missing root, permission issues) is
        swallowed and yields an empty list rather than raising into a caller.
        """
        try:
            if not self.root.exists():
                return []
            newest = heapq.nlargest(max(0, limit), _trace_entries(self.root), key=_mtime)
            return [entry.name[: -len(".jsonl")] for entry in newest]
        except Exception:
            return []

    def read(self, trace_id: str) -> list[dict]:
        """Parsed JSONL events for ``trace_id``, or ``[]`` if unreadable.

        Uses the same filename rule as :meth:`path_for`. Malformed lines are
        skipped rather than raising, matching the fail-safe convention.
        """
        try:
            path = self.path_for(trace_id)
            if not path.exists():
                return []
            events: list[dict] = []
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except Exception:
                    continue
                if isinstance(event, dict):
                    events.append(event)
            return events
        except Exception:
            return []
