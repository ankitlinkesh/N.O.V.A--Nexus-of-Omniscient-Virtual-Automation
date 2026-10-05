"""Phase 134: the file bridge between the user's folders and NOVA's sandbox share.

Everything runs against a tmp share dir and a tmp home -- the real D:\\nova-share and the
real user folders are never touched. The agent-loop tests go through the real
`run_agentic_task` + gate + `handle_confirmation_command`.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import backend.eva.tools.share_bridge as sb
from backend.eva.agent import paused_tasks as paused_tasks_mod
from backend.eva.agent.executor import ToolExecutor
from backend.eva.agent.planner import PlannedToolCall, PlannerDecision
from backend.eva.agent.policies import describe_tool_observation
from backend.eva.agent.runner import run_agentic_task
from backend.eva.agents.role_policy import ROLE_POLICIES, RoleTier, tier_for
from backend.eva.permissions.confirmation import handle_confirmation_command
from backend.eva.security import tool_gate
from backend.eva.security.permission_gate import PermissionContext, evaluate_action
from backend.eva.tools.registry import ToolRegistry

TOOLS = ("share.to_box", "share.from_box")


@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    for name in ("Documents", "Desktop", "Downloads"):
        (home / name).mkdir(parents=True)
    share = tmp_path / "nova-share"
    share.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(sb, "SHARE_ROOT", str(share))
    tool_gate.reset_pending_calls()
    paused_tasks_mod.clear_all()
    yield SimpleNamespace(home=home, share=share)
    tool_gate.reset_pending_calls()
    paused_tasks_mod.clear_all()


def _doc(env, name="report.txt", text="hello", folder="Documents"):
    p = env.home / folder / name
    p.write_text(text, encoding="utf-8")
    return p


# ------------------------------------------------------------------ to_box
def test_user_file_lands_in_the_share_with_the_box_path(env):
    src = _doc(env)
    out = sb.share_to_box(str(src))
    assert out["ok"] and out["box_path"] == "/mnt/share/report.txt"
    assert (env.share / "report.txt").read_text(encoding="utf-8") == "hello"
    assert src.exists()  # a copy, not a move


def test_folder_anchored_path_works(env):
    _doc(env, "n.txt")
    assert sb.share_to_box("Documents/n.txt")["box_path"] == "/mnt/share/n.txt"


def test_name_collisions_get_a_number_and_never_overwrite(env):
    src = _doc(env, text="new")
    (env.share / "report.txt").write_text("OLD", encoding="utf-8")
    first = sb.share_to_box(str(src))
    second = sb.share_to_box(str(src))
    assert first["box_path"] == "/mnt/share/report (2).txt"
    assert second["box_path"] == "/mnt/share/report (3).txt"
    assert (env.share / "report.txt").read_text(encoding="utf-8") == "OLD"
    assert (env.share / "report (2).txt").read_text(encoding="utf-8") == "new"


@pytest.mark.parametrize("name", ["server.pem", "my.key", "aws-credentials.txt", "gh-token.json", "id_rsa", "x.kdbx"])
def test_key_and_credential_files_are_refused(env, name):
    src = _doc(env, name, "secret")
    out = sb.share_to_box(str(src))
    assert out["ok"] is False
    assert list(env.share.iterdir()) == []


def test_a_folder_is_refused(env):
    (env.home / "Documents" / "sub").mkdir()
    out = sb.share_to_box(str(env.home / "Documents" / "sub"))
    assert out["ok"] is False and out["error"] == "not_a_file"
    assert list(env.share.iterdir()) == []


def test_outside_the_allowed_roots_is_refused(env, tmp_path):
    stray = tmp_path / "stray.txt"
    stray.write_text("x")
    assert sb.share_to_box(str(stray))["ok"] is False
    assert list(env.share.iterdir()) == []


def test_missing_file_is_refused(env):
    assert sb.share_to_box(str(env.home / "Documents" / "nope.txt"))["error"] == "not_found"


def test_size_cap(env, monkeypatch):
    src = _doc(env, text="x" * 50)
    monkeypatch.setattr(sb, "MAX_BYTES", 10)
    out = sb.share_to_box(str(src))
    assert out["ok"] is False and out["error"] == "too_large"
    assert list(env.share.iterdir()) == []


# ------------------------------------------------------------------ from_box
def test_from_box_lands_in_downloads_and_is_untrusted(env):
    (env.share / "out.csv").write_text("a,b", encoding="utf-8")
    out = sb.share_from_box("out.csv")
    assert out["ok"] and out["untrusted"] is True
    assert (env.home / "Downloads" / "out.csv").read_text(encoding="utf-8") == "a,b"


def test_from_box_accepts_the_guest_path_and_a_folder_choice(env):
    (env.share / "a.txt").write_text("1")
    out = sb.share_from_box("/mnt/share/a.txt", "documents")
    assert out["ok"] and (env.home / "Documents" / "a.txt").exists()


def test_from_box_never_overwrites(env):
    (env.share / "a.txt").write_text("box")
    (env.home / "Downloads" / "a.txt").write_text("MINE")
    out = sb.share_from_box("a.txt")
    assert out["name"] == "a (2).txt"
    assert (env.home / "Downloads" / "a.txt").read_text() == "MINE"


@pytest.mark.parametrize("bad", ["../secret.txt", "sub/../../secret.txt", "..", "C:/Windows/win.ini", "C:\\x.txt", "/etc/passwd", "", "   "])
def test_from_box_refuses_escapes_and_absolute_paths(env, bad):
    (env.home / "secret.txt").write_text("s")
    out = sb.share_from_box(bad)
    assert out["ok"] is False
    assert not (env.home / "Downloads" / "secret.txt").exists()
    assert list((env.home / "Downloads").iterdir()) == []


def test_from_box_refuses_a_folder_and_a_missing_file(env):
    (env.share / "d").mkdir()
    assert sb.share_from_box("d")["error"] == "not_a_file"
    assert sb.share_from_box("nope.txt")["error"] == "not_found"


def test_from_box_only_into_the_three_user_folders(env):
    (env.share / "a.txt").write_text("1")
    assert sb.share_from_box("a.txt", "C:/Windows")["error"] == "bad_folder"
    assert sb.share_from_box("a.txt", "../x")["error"] == "bad_folder"


def test_from_box_refuses_a_symlink_pointing_outside_the_share(env, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("SECRET")
    link = env.share / "link.txt"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("this OS cannot create symlinks without admin")
    out = sb.share_from_box("link.txt")
    assert out["ok"] is False and out["error"] == "outside_share"
    assert list((env.home / "Downloads").iterdir()) == []


def test_from_box_refuses_a_denied_destination_name(env):
    (env.share / ".env").write_text("K=V")
    assert sb.share_from_box(".env")["ok"] is False


# ------------------------------------------------------------------ classification
def test_both_are_confirm_class_in_both_gates():
    reg = ToolRegistry()
    for name in TOOLS:
        spec = reg._tools[name]
        assert tool_gate.classify_tool_call(spec) == "confirm"
        decision = evaluate_action(SimpleNamespace(action_type=spec.action_type, risk_categories=list(spec.risk_categories)), PermissionContext())
        assert decision.decision == "ask_confirmation"


def test_red_for_every_role():
    for role in ROLE_POLICIES:
        for name in TOOLS:
            assert tier_for(role, name) == RoleTier.RED, (role, name)


def test_planner_visible_and_guidance_present():
    names = {s["name"] for s in ToolRegistry().planner_specs()}
    assert set(TOOLS) <= names
    import backend.eva.agent.planner as planner_mod

    src = Path(planner_mod.__file__).read_text(encoding="utf-8")
    assert src.count("share.to_box(path)") == 2 and src.count("share.from_box(name)") == 2


def test_stay_visible_inside_the_sandbox_focus():
    from backend.eva.shell.sandbox_focus import open_sandbox_focus

    with open_sandbox_focus():
        names = {s["name"] for s in ToolRegistry().planner_specs()}
    assert set(TOOLS) <= names


def test_describers():
    assert describe_tool_observation("share.to_box", {"ok": True, "name": "report.pdf", "box_path": "/mnt/share/report.pdf"}) == (
        "share.to_box copied report.pdf into your sandbox at /mnt/share/report.pdf"
    )
    text = describe_tool_observation("share.from_box", {"ok": True, "name": "o.txt", "folder": "Downloads", "dst": "X"})
    assert "o.txt" in text and "untrusted" in text
    assert "did not copy" in describe_tool_observation("share.to_box", {"ok": False, "message": "nope"})


# ------------------------------------------------------------------ through the agent loop
class ScriptedPlanner:
    def __init__(self, decisions):
        self._decisions = list(decisions)
        self.calls = 0

    async def plan(self, goal, history, mode="agent_step", task_context=None):
        d = self._decisions[min(self.calls, len(self._decisions) - 1)]
        self.calls += 1
        return d


def _call(tool, **args):
    return PlannerDecision(type="tool_calls", reason="step", tool_calls=[PlannedToolCall(tool=tool, args=args)], final_response="", continue_after_tools=True)


def _done(text="done"):
    return PlannerDecision(type="done", reason="finished", tool_calls=[], final_response=text, continue_after_tools=False)


def _run(decisions, session_id="s134"):
    registry = ToolRegistry()
    return asyncio.run(
        run_agentic_task(
            "put my report in the sandbox",
            {"planner": ScriptedPlanner(decisions), "registry": registry, "executor": ToolExecutor(registry), "execute_tools": True, "session_id": session_id},
        )
    )


def test_to_box_asks_first_and_copies_nothing_until_approved(env):
    src = _doc(env)
    result = _run([_call("share.to_box", path=str(src)), _done("it is in the box")])
    assert result["requires_confirmation"] is True
    assert result["action"].startswith("act_")
    assert list(env.share.iterdir()) == [], "nothing may be copied before approval"

    reply = handle_confirmation_command(f"confirm {result['action']}", session_id="s134")
    assert (env.share / "report.txt").read_text(encoding="utf-8") == "hello"
    assert "it is in the box" in reply


def test_from_box_asks_first_then_copies_untrusted(env):
    (env.share / "o.txt").write_text("made in box")
    result = _run([_call("share.from_box", name="o.txt"), _done("delivered")])
    assert result["requires_confirmation"] is True
    assert not (env.home / "Downloads" / "o.txt").exists()
    handle_confirmation_command(f"confirm {result['action']}", session_id="s134")
    assert (env.home / "Downloads" / "o.txt").read_text() == "made in box"


def test_from_box_refuses_a_junction_pointing_outside_the_share(env, tmp_path):
    """Windows junctions need no admin, unlike symlinks, so this runs where the symlink test skips."""
    import subprocess

    if os.name != "nt":
        pytest.skip("junctions are Windows-only")
    outside = tmp_path / "outside_dir"
    outside.mkdir()
    (outside / "x.txt").write_text("SECRET")
    made = subprocess.run(["cmd", "/c", "mklink", "/J", str(env.share / "jct"), str(outside)], capture_output=True)
    if made.returncode != 0:
        pytest.skip("cannot create a junction here")
    out = sb.share_from_box("jct/x.txt")
    assert out["ok"] is False and out["error"] == "outside_share"
    assert list((env.home / "Downloads").iterdir()) == []


def test_from_box_refuses_dotdot_even_when_it_would_stay_inside(env):
    """The `..` check is its own layer: containment alone would let `sub/../a.txt` through."""
    (env.share / "sub").mkdir()
    (env.share / "a.txt").write_text("1")
    out = sb.share_from_box("sub/../a.txt")
    assert out["ok"] is False and out["error"] == "bad_name"
    assert list((env.home / "Downloads").iterdir()) == []


@pytest.mark.parametrize("message", [
    "put report.txt from my downloads into your box and count the words",
    "copy results.csv from your sandbox to my documents",
    "send this file to your terminal",
])
def test_bridge_requests_reach_the_agent_loop(message):
    # Live: "into your box" missed the Phase 130 rule (in/on/using/... only), so the
    # single-turn planner handled it and an approved copy never resumed to `wc -w`.
    from backend.eva.agent.policies import is_agentic_intent

    assert is_agentic_intent(message)


@pytest.mark.parametrize("message", ["reply to your email", "listen to your music", "put it in the box", "check my inbox"])
def test_ordinary_to_your_phrases_stay_out(message):
    from backend.eva.agent.policies import is_sandbox_request

    assert not is_sandbox_request(message)
