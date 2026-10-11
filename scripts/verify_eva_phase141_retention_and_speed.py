"""Standalone verifier for Phase 141 (retention, faster listing/search, temp cleanup).

1. Trace retention keeps the newest and the recent, prunes the rest.
2. Trace listing over many files is newest-first and fast.
3. Workspace search finds a file by name in under 3s on this repo; escapes still refused.
4. Both suites keep their temp files in one folder they remove, and sweep stale ones.
5. README records the phase.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
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
    from backend.eva.observability import local_trace_store as lts

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        now = time.time()
        for i in range(400):
            path = root / f"t{i:03d}.jsonl"
            path.write_text("{}\n", encoding="utf-8")
            age = ((400 - i) * 0.5 + 0.25) * 86400  # 0.75 .. 200.25 days, never exactly 60
            os.utime(path, (now - age, now - age))
        removed = lts.prune_traces(root, max_files=100, max_age_days=60, now=now)
        left = len(list(root.glob("*.jsonl")))
        # kept: the newest 100 (t300-t399) + older ones younger than 60 days (t281-t299)
        failures += emit("retention keeps newest and recent, prunes the rest", removed == 281 and left == 119, removed=removed, left=left)

        lts._PRUNED_ROOTS.add(str(root))
        store = lts.LocalTraceStore(root)
        started = time.perf_counter()
        newest = store.list_trace_ids(5)
        elapsed = time.perf_counter() - started
        failures += emit("listing is newest first and fast", newest == ["t399", "t398", "t397", "t396", "t395"] and elapsed < 1.0, newest=newest, seconds=round(elapsed, 3))

    from backend.eva.workspace.indexer import search_workspace
    from backend.eva.workspace.reader import safe_read_file

    started = time.perf_counter()
    found = search_workspace("tavily")
    elapsed = time.perf_counter() - started
    refused = all(safe_read_file(p).get("refused") for p in ("../../.env", "a/../../x", ".env.local"))
    failures += emit(
        "workspace search is quick and still refuses escapes",
        found["matches"][0]["path"] == "backend/eva/tools/tavily_search.py" and elapsed < 3.0 and refused,
        seconds=round(elapsed, 2),
    )

    suite = (ROOT / "scripts" / "verify_eva_all.py").read_text(encoding="utf-8")
    conftest = (ROOT / "backend" / "tests" / "conftest.py").read_text(encoding="utf-8")
    failures += emit(
        "suites clean their temp and sweep stale runs",
        "shutil.rmtree(run_root" in suite and 'purge_stale_temp_roots("eva_verify_all_run_")' in suite
        and "shutil.rmtree(_SESSION_ROOT" in conftest and 'purge_stale_temp_roots("eva_pytest_session_"' in conftest,
    )

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    failures += emit("README records Phase 141", "| 141 |" in readme)
except Exception as exc:  # a crash is a failure, never a pass
    failures += emit("verifier crashed", False, error=f"{type(exc).__name__}: {exc}")

print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
sys.exit(0 if failures == 0 else 1)
