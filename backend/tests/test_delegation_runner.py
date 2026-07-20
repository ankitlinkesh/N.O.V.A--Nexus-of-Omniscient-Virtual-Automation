"""Executable spec for role-scoped delegation (Phase 73).

Phase 72 built the containment boundary and left it inert -- nothing could open
a role scope. This is the caller that makes it live, so these tests cover the
seam: what a sub-task inherits, what it may do, what comes back, and what
happens when it fails.

The invariant that matters most is the trust boundary. A sub-task's return
value is DATA, never instructions: a research role reads untrusted web content,
and if the parent executed the child's summary, delegation would be a
prompt-injection channel into an executor holding real tools.

`run_agentic_task` is faked throughout -- these tests spend no LLM quota. The
end-to-end path was validated live instead (a real research sub-task ran
workspace_search and returned content; a second one attempted capture_screen
and was refused by its role), which is what found the `final_response` bug
pinned in TestSummaryExtraction below.
"""

from __future__ import annotations

import pytest

from eva.agents import delegation_runner
from eva.agents.delegation_runner import DelegatedResult, run_delegated
from eva.mcp.runner import run_async


@pytest.fixture
def fake_runner(monkeypatch):
    """Replace the live executor; record the context it was handed."""
    seen: dict = {}

    async def _fake(goal, context):
        seen["goal"] = goal
        seen["context"] = context
        return {"ok": True, "final_response": "sub-task finished"}

    monkeypatch.setattr("eva.agent.runner.run_agentic_task", _fake)
    return seen


class TestFailsClosed:
    def test_unknown_role_is_refused_without_running_anything(self, monkeypatch) -> None:
        """An unrecognized role must not reach the executor at all.

        effective_tier would deny every tool anyway, but silently accepting a
        bad role name is a confusing way to discover a typo.
        """
        called = False

        async def _boom(goal, context):
            nonlocal called
            called = True
            return {}

        monkeypatch.setattr("eva.agent.runner.run_agentic_task", _boom)
        result = run_async(run_delegated("desktop-please", "do a thing"))
        assert result.ok is False
        assert "Unknown role" in (result.error or "")
        assert not called

    def test_empty_goal_is_refused(self, fake_runner) -> None:
        result = run_async(run_delegated("research", "   "))
        assert result.ok is False
        assert "No goal" in (result.error or "")
        assert "goal" not in fake_runner


class TestContextIsolation:
    """The main reason to delegate: a fresh context, not the parent's thread."""

    def test_parent_history_is_not_inherited(self, fake_runner) -> None:
        parent = {"history": [{"role": "user", "content": "something the child need not see"}], "session_id": "s1"}
        run_async(run_delegated("research", "go", parent))
        assert fake_runner["context"]["history"] == []

    def test_machinery_is_inherited(self, fake_runner) -> None:
        """Isolation is of CONTEXT, not of capability plumbing -- the sub-task
        still runs against the same registry, memory and session."""
        sentinel = object()
        run_async(run_delegated("research", "go", {"registry": sentinel, "session_id": "s1"}))
        assert fake_runner["context"]["registry"] is sentinel
        assert fake_runner["context"]["session_id"] == "s1"

    def test_parent_context_is_not_mutated(self, fake_runner) -> None:
        parent = {"history": [{"role": "user", "content": "keep me"}]}
        run_async(run_delegated("research", "go", parent))
        assert parent["history"] == [{"role": "user", "content": "keep me"}]


class TestFaultIsolation:
    def test_raising_subtask_becomes_a_typed_failure(self, monkeypatch) -> None:
        """A sub-task blowing up must not unwind into the parent."""

        async def _raise(goal, context):
            raise RuntimeError("sub-task exploded")

        monkeypatch.setattr("eva.agent.runner.run_agentic_task", _raise)
        result = run_async(run_delegated("research", "go"))
        assert result.ok is False
        assert "RuntimeError" in (result.error or "")
        assert "sub-task exploded" in (result.error or "")


class TestSummaryExtraction:
    """Pinned because the live run found it and no test would have.

    The runner returns `final_response`. Reading a plausible-looking set of
    other key names produced an EMPTY summary on a run that reported ok=True --
    the Phase 70 shape, where reading fewer names than the source emits looks
    correct while carrying nothing through.
    """

    def test_reads_final_response(self, monkeypatch) -> None:
        async def _fake(goal, context):
            return {"ok": True, "final_response": "the real answer"}

        monkeypatch.setattr("eva.agent.runner.run_agentic_task", _fake)
        result = run_async(run_delegated("research", "go"))
        assert result.summary == "the real answer"
        assert result.ok is True

    def test_ok_comes_from_the_runners_own_signal(self, monkeypatch) -> None:
        """Not inferred from a non-empty summary -- Phase 69 fixed exactly that
        mistake in runtime/nodes.py, where a populated string read as success."""

        async def _fake(goal, context):
            return {"ok": False, "final_response": "I could not complete this"}

        monkeypatch.setattr("eva.agent.runner.run_agentic_task", _fake)
        result = run_async(run_delegated("research", "go"))
        assert result.summary == "I could not complete this"
        assert result.ok is False


class TestTrustBoundary:
    def test_result_is_marked_untrusted(self, fake_runner) -> None:
        result = run_async(run_delegated("research", "go"))
        assert result.untrusted is True

    def test_rendered_text_says_so(self, fake_runner) -> None:
        """The disclaimer travels WITH the content, so it cannot be read as an
        instruction further along without the warning attached."""
        text = run_async(run_delegated("research", "go")).as_text()
        assert "untrusted" in text.lower()
        assert "not an instruction" in text.lower()


class TestRefusalsSurface:
    def test_refusals_are_reported_and_flagged(self) -> None:
        """A refusal that dies inside the sub-task wastes the signal."""
        result = DelegatedResult(
            role="research",
            goal="g",
            ok=True,
            summary="done",
            refusals=({"role": "research", "tool": "capture_screen"},),
        )
        assert result.injection_suspected is True
        text = result.as_text()
        assert "capture_screen" in text
        assert "Blocked 1 action" in text
        assert "signal" in text.lower()

    def test_no_refusals_means_no_injection_claim(self, fake_runner) -> None:
        """The flag must not cry wolf on an ordinary clean run."""
        result = run_async(run_delegated("research", "go"))
        assert result.injection_suspected is False
        assert "Blocked" not in result.as_text()
