from __future__ import annotations

import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def eva_pending_action_ledger_path(tmp_path, monkeypatch):
    """Point EVA_PENDING_ACTION_LEDGER_PATH at a throwaway file for every test.

    backend/eva/permissions/ledger.py reads this env var (see ledger_path()),
    so this keeps tests from ever touching the real
    backend/eva/data/permissions/pending_actions.jsonl ledger.
    """
    ledger_file = tmp_path / "pending_actions.jsonl"
    monkeypatch.setenv("EVA_PENDING_ACTION_LEDGER_PATH", str(ledger_file))
    yield ledger_file


@pytest.fixture(autouse=True)
def _reset_tool_gate_between_tests():
    """Best-effort reset of the in-memory tool_gate pending-call store.

    backend.eva.security.tool_gate does not exist yet on this branch -- it is
    the module the upcoming hardening/tool-gate fix is expected to add. Until
    then this fixture is a silent no-op so it never masks (or turns into) the
    intentional test failures the rest of this suite is built to produce.
    Once tool_gate exists, this keeps its module-level state clean across
    tests instead of leaking pending calls between them.
    """
    try:
        from backend.eva.security import tool_gate
    except ImportError:
        yield
        return
    tool_gate.reset_pending_calls()
    yield
    tool_gate.reset_pending_calls()


@pytest.fixture
def sandbox_dir():
    """A throwaway directory under the repo root.

    backend/eva/tools/safe_file_tools.py's SAFE_ROOT is the repo root, so
    anything under here is inside the path allowlist and safe for file-tool
    tests to read/write/delete without touching real user files.
    """
    path = REPO_ROOT / "backend" / "tests" / "tmp_sandbox"
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)


def import_tool_gate():
    """Import backend.eva.security.tool_gate, or fail the calling test.

    This is meant to be called from inside a test function body (not a
    fixture), so that a missing module surfaces as a normal FAILED test --
    which is the correct outcome pre-fix -- rather than a setup ERROR or a
    silently SKIPPED test. Most of this suite is an executable spec for
    work that has not landed yet, so "the module doesn't exist" must show
    up as a failing assertion, not a skip.
    """
    try:
        from backend.eva.security import tool_gate
    except ImportError as exc:
        pytest.fail(
            "backend.eva.security.tool_gate is not implemented yet (expected "
            "register_pending_call/get_pending_call/reset_pending_calls). "
            f"ImportError: {exc}",
            pytrace=False,
        )
    return tool_gate
