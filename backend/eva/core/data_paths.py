"""Where NOVA's mutable state lives, with one override for tests.

Every store (chat memory, approval ledger, traces, usage counters, checkpoints,
research DBs, screen frames ...) used to build its own path under one of three
repo folders: data/, backend/data/ and backend/eva/data/. The test suites wrote
into all of them: test chats in the real history, a 17 MB approval ledger of test
actions, a fake "allergy: shellfish" belief, 34k trace files, a 15-byte
latest_screen.jpg.

``data_path(default)`` returns ``default`` unless EVA_DATA_DIR is set, in which case
the same repo-relative layout is placed under that directory. Call it where the
path is USED, not in a module constant or a def-time default, so a test that sets
EVA_DATA_DIR after import is still honoured. A store's own specific override
(EVA_PENDING_ACTION_LEDGER_PATH ...) still wins over this.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def data_root_override() -> Path | None:
    raw = os.environ.get("EVA_DATA_DIR", "").strip()
    return Path(raw) if raw else None


def data_path(default: Path | str) -> Path:
    default = Path(default)
    root = data_root_override()
    if root is None:
        return default
    try:
        relative = default.resolve().relative_to(REPO_ROOT)
    except ValueError:
        return default
    return root / relative


LIVE_DATA_ROOTS = (
    REPO_ROOT / "data",
    REPO_ROOT / "backend" / "data",
    REPO_ROOT / "backend" / "eva" / "data",
)


def live_data_snapshot(roots: tuple[Path, ...] = LIVE_DATA_ROOTS, *, file_depth: int = 2) -> dict[str, tuple[int, int]]:
    """Cheap fingerprint of the live stores: every directory's mtime and entry count
    (a new trace file changes its folder's) plus size/mtime of files near the top.
    Walking traces/ file by file (34k files) would cost more than the check is worth."""
    snapshot: dict[str, tuple[int, int]] = {}
    for root in roots:
        if not root.exists():
            continue
        stack = [(root, 0)]
        while stack:
            folder, depth = stack.pop()
            try:
                entries = list(os.scandir(folder))
                stat = folder.stat()
            except OSError:
                continue
            snapshot[str(folder)] = (stat.st_mtime_ns, len(entries))
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append((Path(entry.path), depth + 1))
                    elif depth < file_depth:
                        info = entry.stat(follow_symlinks=False)
                        snapshot[entry.path] = (info.st_mtime_ns, info.st_size)
                except OSError:
                    continue
    return snapshot


def live_data_changes(before: dict[str, tuple[int, int]], after: dict[str, tuple[int, int]] | None = None) -> list[str]:
    """Paths whose fingerprint differs between two snapshots (added, removed or changed)."""
    after = live_data_snapshot() if after is None else after
    changed = {key for key in before.keys() | after.keys() if before.get(key) != after.get(key)}
    return sorted(changed)


def repo_data_dir(*parts: str) -> Path:
    """``<repo>/data/<parts>``, honouring EVA_DATA_DIR."""
    return data_path(REPO_ROOT.joinpath("data", *parts))


def backend_data_dir(*parts: str) -> Path:
    """``<repo>/backend/data/<parts>``, honouring EVA_DATA_DIR."""
    return data_path(REPO_ROOT.joinpath("backend", "data", *parts))


def eva_data_dir(*parts: str) -> Path:
    """``<repo>/backend/eva/data/<parts>``, honouring EVA_DATA_DIR."""
    return data_path(REPO_ROOT.joinpath("backend", "eva", "data", *parts))
