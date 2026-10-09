"""Standalone verifier for Phase 139 (tests and verifiers never write NOVA's live data).

1. data_path() maps the repo layout under EVA_DATA_DIR and leaves outside paths alone.
2. Every store under backend/eva builds its path through data_path() (AST check).
3. With EVA_DATA_DIR set, the chat memory, usage counters, traces and ledger all land
   in the temp root and nothing under the live data folders changes.
4. verify_eva_all and the pytest conftest set a temp data root and report live changes.
5. README records the phase.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
failures = 0


def emit(case: str, ok: bool, **extra: object) -> int:
    payload = {"case": case, "pass": bool(ok)}
    payload.update(extra)
    print(json.dumps(payload, indent=2, default=str))
    return 0 if ok else 1


try:
    from backend.eva.core import data_paths
    from backend.tests.test_data_paths_isolation import unrouted_data_paths

    with tempfile.TemporaryDirectory() as tmp:
        saved = os.environ.get("EVA_DATA_DIR")
        os.environ["EVA_DATA_DIR"] = tmp
        try:
            ledger_default = ROOT / "backend" / "eva" / "data" / "permissions" / "pending_actions.jsonl"
            mapped = data_paths.data_path(ledger_default)
            failures += emit(
                "data_path maps the repo layout under EVA_DATA_DIR",
                mapped == Path(tmp) / "backend" / "eva" / "data" / "permissions" / "pending_actions.jsonl"
                and data_paths.data_path(Path(tmp) / "x.db") == Path(tmp) / "x.db",
                mapped=mapped,
            )

            problems = []
            for path in sorted((ROOT / "backend" / "eva").rglob("*.py")):
                if path.name != "data_paths.py":
                    problems += unrouted_data_paths(path)
            failures += emit("every store path goes through data_path()", not problems, problems=problems)

            before = data_paths.live_data_snapshot()
            ledger_saved = os.environ.pop("EVA_PENDING_ACTION_LEDGER_PATH", None)
            try:
                from backend.eva.llm.rate_limiter import LLMRateLimiter
                from backend.eva.main import create_app
                from backend.eva.observability.local_trace_store import LocalTraceStore
                from backend.eva.permissions.ledger import ledger_path

                app = create_app()
                landed = {
                    "memory": str(app.state.memory.path),
                    "usage": str(LLMRateLimiter().path),
                    "traces": str(LocalTraceStore().root),
                    "ledger": str(ledger_path()),
                }
            finally:
                if ledger_saved is not None:
                    os.environ["EVA_PENDING_ACTION_LEDGER_PATH"] = ledger_saved
            changed = data_paths.live_data_changes(before)
            failures += emit(
                "stores land in the temp root and live data is untouched",
                all(value.startswith(tmp) for value in landed.values()) and not changed,
                landed=landed,
                live_changed=changed[:8],
            )
        finally:
            if saved is None:
                os.environ.pop("EVA_DATA_DIR", None)
            else:
                os.environ["EVA_DATA_DIR"] = saved

    suite = (ROOT / "scripts" / "verify_eva_all.py").read_text(encoding="utf-8")
    conftest = (ROOT / "backend" / "tests" / "conftest.py").read_text(encoding="utf-8")
    failures += emit(
        "both suites run on a temp data root and report live changes",
        'child_env.setdefault("EVA_DATA_DIR"' in suite and "_live_changes(live_before)" in suite
        and 'os.environ["EVA_DATA_DIR"] = tempfile.mkdtemp(' in conftest and "LIVE DATA CHANGED" in conftest,
    )

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    failures += emit("README records Phase 139", "| 139 |" in readme)
except Exception as exc:  # a crash is a failure, never a pass
    failures += emit("verifier crashed", False, error=f"{type(exc).__name__}: {exc}")

print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
sys.exit(0 if failures == 0 else 1)
