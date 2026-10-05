"""Standalone verifier for Phase 134 (the file bridge between the user's folders and the box).

Everything runs against a temp share and a temp home; the real D:\\nova-share and the real
user folders are never touched:
1. share.to_box copies a user file into the share and returns /mnt/share/<name>; a name
   collision becomes "name (2).ext" and never overwrites.
2. Key/credential files and folders are refused.
3. share.from_box lands in Downloads, marked untrusted; "..", absolute paths and a
   non-user destination folder are refused.
4. Both tools are confirm-class in BOTH gates, RED for every role, planner-visible, and
   still visible inside the sandbox focus.
5. Through run_agentic_task a share.to_box call pauses for approval, copies nothing until
   approved, and copies after `confirm`.
6. README records the phase.
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
failures = 0


def emit(case: str, ok: bool, **extra: object) -> int:
    payload = {"case": case, "pass": bool(ok)}
    payload.update(extra)
    print(json.dumps(payload, indent=2, default=str))
    return 0 if ok else 1


_real_home = Path.home
try:
    import backend.eva.tools.share_bridge as sb
    from backend.eva.agent import paused_tasks as paused
    from backend.eva.agent.executor import ToolExecutor
    from backend.eva.agent.planner import PlannedToolCall, PlannerDecision
    from backend.eva.agent.runner import run_agentic_task
    from backend.eva.agents.role_policy import ROLE_POLICIES, RoleTier, tier_for
    from backend.eva.permissions.confirmation import handle_confirmation_command
    from backend.eva.security import tool_gate
    from backend.eva.security.permission_gate import PermissionContext, evaluate_action
    from backend.eva.shell.sandbox_focus import open_sandbox_focus
    from backend.eva.tools.registry import ToolRegistry

    tmp = Path(tempfile.mkdtemp(prefix="nova_v134_"))
    home = tmp / "home"
    for name in ("Documents", "Desktop", "Downloads"):
        (home / name).mkdir(parents=True)
    share = tmp / "nova-share"
    share.mkdir()
    Path.home = classmethod(lambda cls: home)  # type: ignore[method-assign,assignment]
    sb.SHARE_ROOT = str(share)

    doc = home / "Documents" / "report.txt"
    doc.write_text("hello", encoding="utf-8")
    a = sb.share_to_box(str(doc))
    b = sb.share_to_box(str(doc))
    failures += emit(
        "to_box copies, returns the box path, collisions get (2)",
        a.get("box_path") == "/mnt/share/report.txt" and b.get("box_path") == "/mnt/share/report (2).txt" and (share / "report.txt").read_text() == "hello",
        first=a.get("box_path"),
        second=b.get("box_path"),
    )

    key = home / "Documents" / "server.pem"
    key.write_text("k", encoding="utf-8")
    (home / "Documents" / "sub").mkdir()
    before = sorted(p.name for p in share.iterdir())
    failures += emit(
        "key files and folders are refused",
        sb.share_to_box(str(key))["ok"] is False and sb.share_to_box(str(home / "Documents" / "sub"))["ok"] is False and sorted(p.name for p in share.iterdir()) == before,
    )

    (share / "out.csv").write_text("a,b", encoding="utf-8")
    out = sb.share_from_box("out.csv")
    failures += emit("from_box lands in Downloads, untrusted", out.get("ok") is True and out.get("untrusted") is True and (home / "Downloads" / "out.csv").exists())

    (home / "secret.txt").write_text("s")
    refused = [sb.share_from_box(x)["ok"] for x in ("../secret.txt", "/etc/passwd", "C:/Windows/win.ini", "")]
    refused.append(sb.share_from_box("out.csv", "C:/Windows")["ok"])
    failures += emit("from_box refuses escapes, absolute paths, bad folders", not any(refused) and not (home / "Downloads" / "secret.txt").exists(), results=refused)

    reg = ToolRegistry()
    tools = ("share.to_box", "share.from_box")
    gates_ok = all(
        tool_gate.classify_tool_call(reg._tools[t]) == "confirm"
        and evaluate_action(SimpleNamespace(action_type=reg._tools[t].action_type, risk_categories=list(reg._tools[t].risk_categories)), PermissionContext()).decision == "ask_confirmation"
        for t in tools
    )
    failures += emit("confirm-class in both gates", gates_ok)
    failures += emit("RED for every role", all(tier_for(r, t) == RoleTier.RED for r in ROLE_POLICIES for t in tools))
    visible = {s["name"] for s in reg.planner_specs()}
    with open_sandbox_focus():
        focused = {s["name"] for s in reg.planner_specs()}
    failures += emit("planner-visible, also inside the sandbox focus", set(tools) <= visible and set(tools) <= focused)

    class Planner:
        def __init__(self, decisions):
            self.decisions, self.n = decisions, 0

        async def plan(self, goal, history, mode="agent_step", task_context=None):
            d = self.decisions[min(self.n, len(self.decisions) - 1)]
            self.n += 1
            return d

    tool_gate.reset_pending_calls()
    paused.clear_all()
    call = PlannerDecision(type="tool_calls", reason="s", tool_calls=[PlannedToolCall(tool="share.to_box", args={"path": str(home / "Documents" / "report.txt")})], final_response="", continue_after_tools=True)
    done = PlannerDecision(type="done", reason="f", tool_calls=[], final_response="in the box", continue_after_tools=False)
    for f in list(share.iterdir()):
        f.unlink()
    r2 = ToolRegistry()
    result = asyncio.run(run_agentic_task("put my report in the sandbox", {"planner": Planner([call, done]), "registry": r2, "executor": ToolExecutor(r2), "execute_tools": True, "session_id": "v134"}))
    paused_ok = result.get("requires_confirmation") is True and list(share.iterdir()) == []
    reply = handle_confirmation_command(f"confirm {result.get('action')}", session_id="v134")
    failures += emit("agent loop: asks first, copies only after approval", paused_ok and (share / "report.txt").exists() and "in the box" in reply)
    tool_gate.reset_pending_calls()
    paused.clear_all()

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    failures += emit("README records Phase 134", "| 134 |" in readme)
except Exception as exc:  # a crash is a failure, never a pass
    failures += emit("verifier crashed", False, error=f"{type(exc).__name__}: {exc}")
finally:
    Path.home = _real_home  # type: ignore[method-assign]

print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
sys.exit(0 if failures == 0 else 1)
