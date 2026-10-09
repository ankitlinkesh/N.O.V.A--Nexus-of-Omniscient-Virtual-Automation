"""Every verifier on disk runs in the suite, or says why it does not.

2026-10-09: 48 of 205 verify_*.py scripts ran nowhere, and the registered ones that
re-run others auto-passed those nested checks under EVA_VERIFY_SKIP_NESTED, so a
nested target that was itself unregistered (planner_v3, capability_permissions,
the research-memory set) was checked by nothing. Skipping a nested check is only
honest when the target also runs at top level; these tests make that structural.
"""
from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest

from scripts import _nested, _source_guard
from scripts import verify_eva_all as va

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
_NAME = re.compile(r"^(?:scripts/)?(verify_\w+\.py)$")
_RUNNER_CALLS = {"run_nested", "run_verifier", "_shared_run_nested"}


def _on_disk() -> set[str]:
    return {path.name for path in SCRIPTS.glob("verify_*.py")} - {"verify_eva_all.py"}


def _runner_names(tree: ast.AST) -> set[str]:
    """Functions that start another Python process (``subprocess.*(... sys.executable ...)``),
    whatever they are called. research_memory_help's ``_run_verifier`` escaped a
    name list and kept re-running seven verifiers under the master profile."""
    names = set(_RUNNER_CALLS)
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef):
            continue
        spawns = any(
            isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and getattr(call.func.value, "id", None) == "subprocess"
            for call in ast.walk(fn)
        )
        python = any(isinstance(n, ast.Attribute) and n.attr == "executable" and getattr(n.value, "id", None) == "sys" for n in ast.walk(fn))
        if spawns and python:
            names.add(fn.name)
    return names


def _runs_nested(tree: ast.AST, source: str) -> bool:
    runners = _runner_names(tree)
    calls = any(isinstance(n, ast.Call) and getattr(n.func, "id", None) in runners for n in ast.walk(tree))
    return calls or "EVA_VERIFY_SKIP_NESTED" in source


_ACTIVE_RUNNERS: set[str] = set(_RUNNER_CALLS)


def _is_runner_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and getattr(node.func, "id", None) in _ACTIVE_RUNNERS


def _names_in(node: ast.AST) -> set[str]:
    names = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            match = _NAME.match(sub.value)
            if match:
                names.add(match.group(1))
    return names


def nested_targets(path: Path) -> set[str]:
    """Verifier names a script actually re-runs: runner-call arguments, and the
    literal lists a runner-calling loop iterates. A list of files scanned for
    markers, or checked to exist, is not nesting."""
    source = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    if not _runs_nested(tree, source):
        return set()
    _ACTIVE_RUNNERS.clear()
    _ACTIVE_RUNNERS.update(_runner_names(tree))
    assigned = {
        target.id: node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign) and isinstance(node.value, (ast.List, ast.Tuple))
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    names = set()
    for node in ast.walk(tree):
        if _is_runner_call(node):
            names |= set().union(*(_names_in(arg) for arg in node.args)) if node.args else set()
        elif isinstance(node, ast.For) and any(_is_runner_call(sub) for sub in ast.walk(node)):
            iterable = assigned.get(node.iter.id) if isinstance(node.iter, ast.Name) else node.iter
            if isinstance(iterable, (ast.List, ast.Tuple)):
                names |= _names_in(iterable)
    return names - {path.name, "verify_eva_all.py"}


def nesting_scripts() -> dict[str, set[str]]:
    found = {}
    for path in sorted(SCRIPTS.glob("verify_*.py")):
        if path.name == "verify_eva_all.py":
            continue
        targets = nested_targets(path)
        if targets:
            found[path.name] = targets
    return found


def test_every_verifier_is_registered_or_explained():
    registered = set(va.FULL_VERIFIERS)
    unaccounted = sorted(_on_disk() - registered - set(va.NOT_IN_SUITE))
    assert not unaccounted, f"never-run verifiers: {unaccounted}"
    assert not registered & set(va.NOT_IN_SUITE), "a script cannot be both registered and set aside"
    assert all((SCRIPTS / name).exists() for name in registered | set(va.NOT_IN_SUITE))


def test_quick_profile_is_a_subset_of_full_and_has_no_duplicates():
    assert set(va.QUICK_VERIFIERS) <= set(va.FULL_VERIFIERS)
    assert len(va.FULL_VERIFIERS) == len(set(va.FULL_VERIFIERS))
    assert len(va.QUICK_VERIFIERS) == len(set(va.QUICK_VERIFIERS))


def test_not_in_suite_reasons_are_explicit():
    for name, reason in va.NOT_IN_SUITE.items():
        assert reason.startswith(("retired: ", "excluded: ")) and len(reason) > 30, name


def test_every_nested_target_runs_at_top_level():
    nesting = nesting_scripts()
    assert "verify_eva_planner_v3_quality.py" in nesting  # the finder still sees real nesting
    uncovered = {script: sorted(t - set(va.FULL_VERIFIERS)) for script, t in nesting.items() if t - set(va.FULL_VERIFIERS)}
    assert not uncovered, f"nested targets that only ever 'pass' by being skipped: {uncovered}"


def test_every_registered_nesting_script_honours_the_skip():
    # agent_framework_v1 ignored it and re-ran planner_v3_quality (~360s) every time.
    ignoring = [
        script for script in nesting_scripts()
        if script in va.FULL_VERIFIERS and "EVA_VERIFY_SKIP_NESTED" not in (SCRIPTS / script).read_text(encoding="utf-8-sig")
    ]
    assert not ignoring


def test_nested_runners_use_the_shared_utf8_runner():
    # Each private copy decoded child output as cp1252 with its own timeout.
    private = []
    for script in nesting_scripts():
        tree = ast.parse((SCRIPTS / script).read_text(encoding="utf-8-sig"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in _runner_names(tree) - {"_shared_run_nested"}:
                if not any(isinstance(n, ast.Name) and n.id == "_shared_run_nested" for n in ast.walk(node)):
                    private.append(script)
    assert not private


def test_guard_catches_an_unregistered_nested_target(tmp_path):
    script = tmp_path / "verify_fake_parent.py"
    script.write_text(
        "import os\nfrom _nested import run_nested as _shared_run_nested\n"
        "if os.environ.get('EVA_VERIFY_SKIP_NESTED') != '1':\n    _shared_run_nested('verify_not_registered_anywhere.py')\n",
        encoding="utf-8",
    )
    assert nested_targets(script) == {"verify_not_registered_anywhere.py"}
    exists_only = tmp_path / "verify_presence_only.py"
    exists_only.write_text("from pathlib import Path\nPath('scripts/verify_x.py').exists()\n", encoding="utf-8")
    assert nested_targets(exists_only) == set()


def test_suite_reports_skips_instead_of_counting_them_as_passes():
    source = (SCRIPTS / "verify_eva_all.py").read_text(encoding="utf-8")
    assert "Nested checks skipped (each runs at top level)" in source
    assert 'child_env.setdefault("EVA_PENDING_ACTION_LEDGER_PATH"' in source


def test_run_nested_is_one_level_deep_utf8_and_times_out_as_failure(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen.update(kwargs, cmd=cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="ok ✓", stderr="")

    monkeypatch.setattr(_nested.subprocess, "run", fake_run)
    monkeypatch.delenv("EVA_VERIFY_SKIP_NESTED", raising=False)
    ok, tail = _nested.run_nested("verify_eva_smoke.py")
    assert ok and tail == "ok ✓"
    assert seen["env"]["EVA_VERIFY_SKIP_NESTED"] == "1" and seen["encoding"] == "utf-8" and seen["errors"] == "replace"
    assert seen["cmd"][-1].endswith(str(Path("scripts") / "verify_eva_smoke.py"))

    def slow(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(_nested.subprocess, "run", slow)
    ok, tail = _nested.run_nested("verify_eva_smoke.py", timeout=5)
    assert not ok and "timed out" in tail


# --- the shared source guard: real code only, not words -------------------------

def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_source_guard_ignores_prose_but_catches_code(tmp_path):
    prose = _write(
        tmp_path, "prose.py",
        '"""No verifier subprocesses, no package installs."""\n'
        'HELP = "run `pip install uiautomation` first"\n'
        "# begin ordinary requests.\n"
        'TOOL = "ai_os.system_map"\nDESC = "no cookie, localStorage, document.cookie access"\n',
    )
    assert _source_guard.no_shell([prose])[0] == []
    assert _source_guard.no_package_install([prose])[0] == []
    assert _source_guard.no_network([prose])[0] == []
    assert _source_guard.no_browser_secret_reads([prose])[0] == []

    code = _write(
        tmp_path, "code.py",
        "import subprocess\nimport os\nimport requests\nfrom playwright.sync_api import sync_playwright\n"
        "os.system('dir')\nsubprocess.run(['pip', 'install', 'x'])\nopen('.env.local')\n"
        "page.evaluate('() => document.cookie')\n",
    )
    assert {f.what for f in _source_guard.no_shell([code])[0]} == {"imports subprocess", "calls os.system"}
    assert any("package install" in f.what for f in _source_guard.no_package_install([code])[0])
    assert [f.what for f in _source_guard.no_network([code])[0]] == ["imports requests"]
    assert _source_guard.no_browser_drivers([code])[0]
    assert _source_guard.no_env_local_read([code])[0]
    assert _source_guard.no_browser_secret_reads([code])[0]


def test_source_guard_exception_is_named_and_reported(tmp_path):
    code = _write(tmp_path, "toast_like.py", "import subprocess\n")
    rel = code.as_posix()
    violations, notes = _source_guard.no_shell([code], allow={rel: "reviewed reason"})
    assert violations == [] and notes == [f"{rel}: allowed (reviewed reason)"]
    assert _source_guard.no_shell([code], allow={"some/other.py": "x"})[0]


def test_runtime_has_exactly_one_reviewed_shell_use():
    runtime = ROOT / "backend" / "eva" / "runtime"
    violations, notes = _source_guard.no_shell([runtime], allow=_source_guard.TOAST_EXCEPTION)
    assert violations == []
    assert len(notes) == 1 and "toast.py" in notes[0]


# --- workspace tools never expose secret files ----------------------------------

@pytest.mark.parametrize("name", [".env", ".env.local", ".ENV.LOCAL", ".env.local.bak-phase121", ".env.bak-20260901-072033", "a.pem", "b.key"])
def test_workspace_refuses_secret_files_even_with_a_custom_exclude_list(name, monkeypatch, tmp_path):
    from backend.eva.workspace.config import is_excluded_file
    from backend.eva.workspace.reader import safe_read_file

    monkeypatch.setenv("EVA_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("EVA_WORKSPACE_EXCLUDE_FILES", "*.log")
    (tmp_path / name).write_text("NVIDIA_API_KEY=nvapi-test-not-real", encoding="utf-8")
    assert is_excluded_file(tmp_path / name)
    result = safe_read_file(name)
    assert result["ok"] is False and result["refused"] is True and "content" not in result


def test_workspace_still_reads_env_example_and_lists_no_secrets(monkeypatch, tmp_path):
    from backend.eva.workspace.indexer import safe_list_files, search_workspace
    from backend.eva.workspace.reader import safe_read_file

    monkeypatch.setenv("EVA_WORKSPACE_ROOT", str(tmp_path))
    (tmp_path / ".env.example").write_text("NVIDIA_API_KEY=\n", encoding="utf-8")
    (tmp_path / ".env.local").write_text("NVIDIA_API_KEY=nvapi-test-not-real\n", encoding="utf-8")
    assert safe_read_file(".env.example")["ok"] is True
    listed = [item["path"] for item in safe_list_files("")["files"]]
    assert listed == [".env.example"]
    hits = search_workspace("nvapi")["matches"]
    assert hits == []


def test_workspace_search_finds_file_names_beyond_the_content_scan_limit(monkeypatch, tmp_path):
    from backend.eva.workspace.indexer import search_workspace

    monkeypatch.setenv("EVA_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("EVA_WORKSPACE_MAX_FILES_PER_SCAN", "10")
    for i in range(40):
        (tmp_path / f"a{i:02d}.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "zz").mkdir()
    (tmp_path / "zz" / "tavily_search.py").write_text("x = 2\n", encoding="utf-8")
    result = search_workspace("tavily")
    assert result["matches"][0]["path"] == "zz/tavily_search.py"
    assert result["searched_files"] == 41 and result["content_searched_files"] == 10 and result["content_truncated"] is True
