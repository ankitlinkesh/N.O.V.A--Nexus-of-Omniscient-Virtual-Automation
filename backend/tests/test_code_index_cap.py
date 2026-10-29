"""The code index must not silently stop at the workspace's 300-file search limit."""

from backend.eva.code import indexer
from backend.eva.code.symbols import find_symbol


def _project(tmp_path, count):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    for i in range(count):
        (pkg / f"m{i:04d}.py").write_text(f"def function_number_{i}():\n    return {i}\n", encoding="utf-8")
    return tmp_path


def test_a_project_bigger_than_the_search_limit_is_fully_indexed(tmp_path, monkeypatch):
    root = _project(tmp_path, 450)
    monkeypatch.setenv("EVA_WORKSPACE_ROOT", str(root))
    monkeypatch.setenv("EVA_WORKSPACE_MAX_FILES_PER_SCAN", "300")
    monkeypatch.setattr(indexer, "INDEX_PATH", tmp_path / "idx" / "code_index.json")
    index = indexer.build_code_index()
    assert index["indexed_files"] >= 450 and index["truncated"] is False
    last = find_symbol("function_number_449")
    assert last["count"] == 1 and "warning" not in last


def test_hitting_the_hard_cap_is_reported_not_hidden(tmp_path, monkeypatch):
    root = _project(tmp_path, 40)
    monkeypatch.setenv("EVA_WORKSPACE_ROOT", str(root))
    monkeypatch.setattr(indexer, "CODE_INDEX_FILE_CAP", 10)
    monkeypatch.setattr(indexer, "INDEX_PATH", tmp_path / "idx" / "code_index.json")
    index = indexer.build_code_index()
    assert index["truncated"] is True and indexer.code_status()["truncated"] is True
    assert "may be missing files" in find_symbol("function_number_1").get("warning", "")
