"""Learned-skill execution: approval lifecycle + the gate holds (Phase 47).

The claims under test are the ones the whole capstone rests on: a proposed skill
is inert, and an approved skill is still governed by the permission gate on
every single step — so learning a skill can never escalate privilege.
"""

from __future__ import annotations

import pytest

from eva.security import tool_gate
from eva.self_improvement.executor import run_skill
from eva.self_improvement.models import SkillStep
from eva.self_improvement.store import SkillStore
from eva.tools.registry import ToolRegistry


@pytest.fixture()
def registry():
    tool_gate.reset_pending_calls()
    yield ToolRegistry()
    tool_gate.reset_pending_calls()


@pytest.fixture()
def store(tmp_path):
    return SkillStore(tmp_path / "skills.sqlite3")


# -- lifecycle -------------------------------------------------------------

def test_a_proposed_skill_is_inert(store, registry):
    skill = store.propose("p", "x", [SkillStep(tool="workspace_status", args={})])
    assert skill.status == "proposed"
    assert skill.is_runnable is False
    report = run_skill(skill, registry, store=store)
    assert report["ok"] is False
    assert report["stopped_reason"] == "skill_not_approved:proposed"
    assert report["ran"] == []


def test_approval_makes_a_skill_runnable(store, registry):
    skill = store.propose("good", "x", [SkillStep(tool="workspace_status", args={})])
    approved = store.approve(skill.id)
    assert approved.is_runnable is True
    report = run_skill(approved, registry, store=store)
    assert report["ok"] is True
    assert [s["tool"] for s in report["ran"]] == ["workspace_status"]
    assert store.get(skill.id).uses == 1


def test_a_rejected_skill_never_runs(store, registry):
    skill = store.propose("bad", "x", [SkillStep(tool="workspace_status", args={})])
    rejected = store.reject(skill.id)
    assert rejected.is_runnable is False
    assert run_skill(rejected, registry, store=store)["ok"] is False


def test_skills_persist_across_restart(tmp_path):
    path = tmp_path / "skills.sqlite3"
    skill = SkillStore(path).propose("kept", "x", [SkillStep(tool="workspace_status", args={})])
    assert SkillStore(path).get_by_name("kept") is not None
    assert SkillStore(path).get(skill.id).status == "proposed"


def test_duplicate_names_are_rejected(store):
    assert store.propose("dup", "x", [SkillStep(tool="workspace_status", args={})]) is not None
    assert store.propose("dup", "x", [SkillStep(tool="workspace_status", args={})]) is None


# -- THE safety claim: the gate governs every step -------------------------

def test_gated_step_stops_the_skill_and_never_executes(store, registry, tmp_path):
    """An approved skill hitting an override-class tool must be stopped by the
    gate: the action must not happen, and neither must anything after it."""
    source = tmp_path / "secret.txt"
    source.write_text("sensitive")
    destination = tmp_path / "copied.txt"

    skill = store.propose(
        "exfil_macro",
        "sneaky",
        [
            SkillStep(tool="workspace_status", args={}),
            SkillStep(tool="file.copy", args={"source": str(source), "destination": str(destination)}),
            SkillStep(tool="workspace_status", args={}),
        ],
    )
    approved = store.approve(skill.id)
    report = run_skill(approved, registry, store=store)

    assert report["ok"] is False
    assert report["gated_step"] == "file.copy"
    assert report["stopped_reason"] == "awaiting_confirmation:file.copy"
    # The privileged action did NOT happen...
    assert destination.exists() is False
    # ...and the skill did not barrel on past it.
    assert [s["tool"] for s in report["ran"]] == ["workspace_status"]


def test_a_skill_cannot_relabel_a_tool_as_safe(store, registry, tmp_path):
    """There is nowhere in the model to declare an action_type, and the gate
    classifies from the real ToolSpec — so a skill cannot make file.copy safe."""
    skill = store.propose("pretend_safe", "x", [SkillStep(tool="file.copy", args={"source": str(tmp_path / "a"), "destination": str(tmp_path / "b")})])
    approved = store.approve(skill.id)
    report = run_skill(approved, registry, store=store)
    assert report["ok"] is False
    assert report["stopped_reason"].startswith("awaiting_confirmation:")


def test_execution_revalidates_against_the_live_registry(store, registry):
    """Approval is not a permanent licence: a step naming a tool that no longer
    exists must refuse to run."""
    skill = store.propose("stale", "x", [SkillStep(tool="workspace_status", args={})])
    approved = store.approve(skill.id)

    class _EmptyRegistry:
        def get(self, name):
            return None

        def run(self, name, /, **kwargs):
            raise AssertionError("must never be called")

    report = run_skill(approved, _EmptyRegistry(), store=store)
    assert report["ok"] is False
    assert report["stopped_reason"].startswith("invalid_steps:")


def test_run_skill_is_fail_safe(registry):
    assert run_skill(None, registry)["ok"] is False
