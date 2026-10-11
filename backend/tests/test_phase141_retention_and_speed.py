"""Phase 141: data that only ever grew now has limits, and the slow paths are fast.

- traces/ held 34k files (165 MB); "learn from traces" reads the newest 25. The store
  now keeps the newest MAX_TRACE_FILES plus anything younger than MAX_TRACE_AGE_DAYS.
- Listing traces stat'ed every file (1.3s); it now uses os.scandir + heapq (0.17s).
- Workspace search re-resolved every path (1.7s of 4.6s); in-root paths now skip it.
- The suites left 2,151 temp folders on a C: with ~5 GB free; each run now removes
  its own folder and sweeps stale ones.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from backend.eva.core.data_paths import purge_stale_temp_roots
from backend.eva.observability import local_trace_store as lts

ROOT = Path(__file__).resolve().parents[2]


def _trace(root: Path, name: str, age_days: float) -> Path:
    path = root / f"{name}.jsonl"
    path.write_text("{}\n", encoding="utf-8")
    stamp = time.time() - age_days * 86400
    os.utime(path, (stamp, stamp))
    return path


def test_prune_keeps_the_newest_and_the_recent(tmp_path):
    for i in range(6):
        _trace(tmp_path, f"old{i}", age_days=100 + i)   # beyond the cap and old: pruned
    for i in range(3):
        _trace(tmp_path, f"new{i}", age_days=i)         # newest: kept
    _trace(tmp_path, "recent_overflow", age_days=10)   # beyond the cap but young: kept
    removed = lts.prune_traces(tmp_path, max_files=3, max_age_days=60)
    left = sorted(p.stem for p in tmp_path.glob("*.jsonl"))
    assert removed == 6
    assert left == ["new0", "new1", "new2", "recent_overflow"]


def test_store_prunes_once_per_folder(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(lts, "prune_traces", lambda root, **kw: calls.append(root) or 0)
    lts.LocalTraceStore(tmp_path)
    lts.LocalTraceStore(tmp_path)
    assert calls == [tmp_path]


def test_list_trace_ids_is_newest_first_and_capped(tmp_path):
    for i in range(5):
        _trace(tmp_path, f"t{i}", age_days=5 - i)
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    store = lts.LocalTraceStore(tmp_path)
    assert store.list_trace_ids(3) == ["t4", "t3", "t2"]
    assert store.status()["trace_files"] == 5


def test_purge_removes_only_stale_folders_with_the_prefix(tmp_path):
    stale = tmp_path / "eva_verify_all_run_old"
    fresh = tmp_path / "eva_verify_all_run_new"
    other = tmp_path / "someone_elses_old"
    for folder in (stale, fresh, other):
        (folder / "x").mkdir(parents=True)
    old = time.time() - 7200
    os.utime(stale, (old, old))
    os.utime(other, (old, old))
    assert purge_stale_temp_roots("eva_verify_all_run_", temp_dir=str(tmp_path)) == 1
    assert not stale.exists() and fresh.exists() and other.exists()


def test_workspace_fast_path_still_refuses_escapes(monkeypatch, tmp_path):
    from backend.eva.workspace.config import load_workspace_config, relative_to_root
    from backend.eva.workspace.reader import safe_read_file

    monkeypatch.setenv("EVA_WORKSPACE_ROOT", str(tmp_path))
    (tmp_path / "inside.txt").write_text("ok", encoding="utf-8")
    config = load_workspace_config()
    assert relative_to_root(config.root / "inside.txt", config) == "inside.txt"
    for escape in ("../outside.txt", "a/../../outside.txt", "..\\outside.txt"):
        assert safe_read_file(escape)["refused"] is True
    # Lexically "root/../x" starts with the root's parts; it must still resolve and fail.
    import pytest

    with pytest.raises(ValueError):
        relative_to_root(config.root / ".." / "outside.txt", config)


def test_suites_clean_their_temp_and_sweep_stale_runs():
    suite = (ROOT / "scripts" / "verify_eva_all.py").read_text(encoding="utf-8")
    conftest = (ROOT / "backend" / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert 'child_env["TEMP"] = child_env["TMP"] = run_root' in suite and "shutil.rmtree(run_root" in suite
    assert 'purge_stale_temp_roots("eva_verify_all_run_")' in suite
    assert "tempfile.tempdir = _SESSION_ROOT" in conftest and "shutil.rmtree(_SESSION_ROOT" in conftest
    assert 'purge_stale_temp_roots("eva_pytest_session_"' in conftest
