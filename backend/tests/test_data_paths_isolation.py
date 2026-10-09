"""Tests and verifiers never write NOVA's live stores.

2026-10-09: the suites wrote test chats into the real chat history (data/eva.sqlite3),
an "allergy: shellfish" / "location: Bangalore" belief about the user, a 17 MB
approval ledger of test actions, 34k trace files and a 15-byte latest_screen.jpg.
Every store now resolves through backend.eva.core.data_paths, and EVA_DATA_DIR
(set by conftest and verify_eva_all) moves the whole layout to a temp root.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path

from backend.eva.core import data_paths

ROOT = Path(__file__).resolve().parents[2]
EVA = ROOT / "backend" / "eva"


def _label(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


def _is_data_join(node: ast.AST) -> bool:
    return isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) and isinstance(node.right, ast.Constant) and node.right.value == "data"


def _inside_data_path(node: ast.AST, parents: dict) -> bool:
    while node in parents:
        node = parents[node]
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "data_path":
            return True
    return False


def _statement(node: ast.AST, parents: dict) -> ast.AST:
    while node in parents and not isinstance(node, ast.stmt):
        node = parents[node]
    return node


def unrouted_data_paths(path: Path) -> list[str]:
    """``... / "data"`` paths that never pass through data_path(). A module constant
    is fine when every use of it (and of constants built from it) is inside
    data_path(...)."""
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    constants: set[str] = set()
    problems = []
    for join in [n for n in ast.walk(tree) if _is_data_join(n)]:
        if _inside_data_path(join, parents):
            continue
        stmt = _statement(join, parents)
        if isinstance(stmt, ast.Assign) and stmt in tree.body and all(isinstance(t, ast.Name) for t in stmt.targets):
            constants.update(t.id for t in stmt.targets)
            continue
        problems.append(f"{_label(path)}:{join.lineno}")
    changed = True
    while changed:  # constants built from a data constant are data constants too
        changed = False
        for stmt in tree.body:
            if isinstance(stmt, ast.Assign) and any(isinstance(n, ast.Name) and n.id in constants for n in ast.walk(stmt.value)):
                for target in stmt.targets:
                    if isinstance(target, ast.Name) and target.id not in constants:
                        constants.add(target.id)
                        changed = True
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id in constants:
            stmt = _statement(node, parents)
            derived = isinstance(stmt, ast.Assign) and stmt in tree.body and all(isinstance(t, ast.Name) and t.id in constants for t in stmt.targets)
            if not derived and not _inside_data_path(node, parents):
                problems.append(f"{_label(path)}:{node.lineno} uses {node.id} outside data_path()")
    return problems


def test_every_store_path_goes_through_data_path():
    problems = []
    for path in sorted(EVA.rglob("*.py")):
        if path.name != "data_paths.py":
            problems += unrouted_data_paths(path)
    assert not problems, problems


def test_guard_catches_a_store_that_bypasses_the_helper(tmp_path):
    sample = tmp_path / "store.py"
    sample.write_text(
        "from pathlib import Path\n"
        "DB = Path(__file__).parents[1] / 'data' / 'x.sqlite3'\n"
        "def open_db():\n    return DB.open()\n"
        "def other():\n    return Path('.') / 'data'\n"
        "def fine():\n    return data_path(DB)\n",
        encoding="utf-8",
    )
    problems = unrouted_data_paths(sample)
    assert "store.py:4 uses DB outside data_path()" in problems
    assert "store.py:6" in problems
    assert len(problems) == 2


def test_data_path_maps_the_repo_layout_under_the_override(monkeypatch, tmp_path):
    default = data_paths.REPO_ROOT / "backend" / "eva" / "data" / "permissions" / "pending_actions.jsonl"
    monkeypatch.setenv("EVA_DATA_DIR", str(tmp_path))
    assert data_paths.data_path(default) == tmp_path / "backend" / "eva" / "data" / "permissions" / "pending_actions.jsonl"
    outside = tmp_path.parent / "elsewhere.db"
    assert data_paths.data_path(outside) == outside
    monkeypatch.delenv("EVA_DATA_DIR")
    assert data_paths.data_path(default) == default


def test_the_suite_itself_runs_on_a_temp_data_root():
    root = Path(os.environ["EVA_DATA_DIR"])
    assert not str(root).startswith(str(ROOT))
    from backend.eva.llm.rate_limiter import LLMRateLimiter
    from backend.eva.permissions.ledger import ledger_path

    assert str(LLMRateLimiter().path).startswith(str(root))
    assert not str(ledger_path()).startswith(str(ROOT))  # conftest's own temp ledger still wins


def test_live_snapshot_sees_new_files_in_large_folders(tmp_path):
    (tmp_path / "traces").mkdir()
    for i in range(5):
        (tmp_path / "traces" / f"{i}.json").write_text("{}", encoding="utf-8")
    (tmp_path / "eva.sqlite3").write_text("x", encoding="utf-8")
    snap = lambda: data_paths.live_data_snapshot((tmp_path,), file_depth=1)  # noqa: E731
    before = snap()
    assert data_paths.live_data_changes(before, snap()) == []
    (tmp_path / "traces" / "new.json").write_text("{}", encoding="utf-8")
    (tmp_path / "eva.sqlite3").write_text("xy", encoding="utf-8")
    changed = data_paths.live_data_changes(before, snap())
    assert str(tmp_path / "traces") in changed and str(tmp_path / "eva.sqlite3") in changed
