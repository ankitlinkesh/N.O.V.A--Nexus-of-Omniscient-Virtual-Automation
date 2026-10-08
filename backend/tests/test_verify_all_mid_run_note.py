"""The verifier suite says when the code changed under it.

2026-10-05: a full run failed verify_eva_memory_v3 in 2.8s (normal: 11-13s). It
passed alone 15/15 and after the 38 verifiers that precede it (twice); a simulated
half-written registry.py fails it in 1.9s. The run had overlapped a builder's edits,
and with no note it read as a flaky verifier.
"""
from __future__ import annotations

import os
import time

from scripts import verify_eva_all as va


def _tree(root):
    for rel in ("backend/eva/tools/registry.py", "scripts/verify_x.py", "docs/EVA_X.md", "README.md", "backend/eva/data.json"):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")
    old = time.time() - 3600
    for path in root.rglob("*"):
        if path.is_file():
            os.utime(path, (old, old))


def test_nothing_changed_means_no_note(tmp_path):
    _tree(tmp_path)
    assert va.changed_sources(time.time() - 60, tmp_path) == []


def test_files_edited_after_the_start_are_listed_newest_first(tmp_path):
    _tree(tmp_path)
    start = time.time() - 60
    now = time.time()
    os.utime(tmp_path / "scripts/verify_x.py", (now - 10, now - 10))
    os.utime(tmp_path / "backend/eva/tools/registry.py", (now, now))
    os.utime(tmp_path / "README.md", (now - 5, now - 5))
    assert va.changed_sources(start, tmp_path) == ["backend/eva/tools/registry.py", "README.md", "scripts/verify_x.py"]


def test_unwatched_files_do_not_count(tmp_path):
    _tree(tmp_path)
    now = time.time()
    os.utime(tmp_path / "backend/eva/data.json", (now, now))  # runtime data, not source
    assert va.changed_sources(now - 60, tmp_path) == []


def test_the_note_names_the_files_and_says_to_rerun(tmp_path):
    _tree(tmp_path)
    now = time.time()
    assert va._mid_run_note(now - 60, tmp_path) == ""
    os.utime(tmp_path / "backend/eva/tools/registry.py", (now, now))
    note = va._mid_run_note(now - 60, tmp_path)
    assert "backend/eva/tools/registry.py" in note and "rerun" in note


def test_the_suite_prints_the_note_on_failure_and_in_the_summary():
    source = (va.ROOT / "scripts" / "verify_eva_all.py").read_text(encoding="utf-8")
    # once per failure path (timeout, non-zero exit) and once in the summary
    assert source.count("_mid_run_note(suite_started)") == 3
