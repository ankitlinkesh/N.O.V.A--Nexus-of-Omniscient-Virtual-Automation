"""Standalone verifier for Phase 112 (bugs found by a routing sweep and by running
the 45 verifier scripts that no suite ever ran).

  1. "turn off wifi" / "turn off dark mode" asked to SHUT DOWN the laptop;
     "restart spotify" asked to restart it. Power words were substrings in two
     routing layers. Now one whole-request matcher (core/power_intent.py).
  2. "google best laptops 2026 and open the first result" searched for the whole
     sentence; "play lofi on spotify and turn the volume up" searched Spotify for
     "lofi on spotify and turn the volume up". Both now decline to the agent loop.
  3. "minimize all windows and lock the laptop" did half: "lock"/"google" were not
     request words.
  4. "what do u know abt me" fell through to the LLM.

Validated live through the chat route: "shut down my laptop" still asks for
confirmation; "turn off dark mode" no longer does.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

failures = 0


def emit(case: str, ok: bool, **extra: object) -> int:
    payload = {"case": case, "pass": bool(ok)}
    payload.update(extra)
    print(json.dumps(payload, indent=2, default=str))
    return 0 if ok else 1


try:
    from eva.agent.executor import ToolExecutor
    from eva.agent.planner import ToolCallPlanner
    from eva.agent.policies import is_agentic_intent
    from eva.core.config import ModelSettings
    from eva.core.fast_commands import maybe_handle_fast_command
    from eva.core.intent_router import classify_capability_intent
    from eva.core.operator_commands import handle_operator_command
    from eva.core.power_intent import power_action_requested
    from eva.tools.registry import ToolRegistry

    class RefusingExecutor(ToolExecutor):
        def execute(self, call, *args, **kwargs):
            raise RuntimeError(f"ran {call.tool}")

    def operator(message: str):
        registry = ToolRegistry()
        try:
            return handle_operator_command(message, {"registry": registry, "executor": RefusingExecutor(registry), "session_context": {}})
        except RuntimeError as exc:
            return {"tool": str(exc)}

    planner = ToolCallPlanner(ModelSettings(), ToolRegistry())

    lookalikes = ["turn off wifi", "turn off dark mode", "restart spotify", "reboot the router", "sleep mode on my screen timer", "sign out of gmail"]
    misfires = [
        m
        for m in lookalikes
        if power_action_requested(m) is not None
        or (operator(m) or {}).get("tool") == "guarded_power_action"
        or (planner._forced_decision(m) or None) is not None and planner._forced_decision(m).type == "confirmation_required"
    ]
    failures += emit("a power verb aimed at something else never prompts a laptop power action", not misfires, misfires=misfires)

    real = {"shut down my laptop": "shutdown", "restart the computer": "restart", "put the laptop to sleep": "sleep", "sign out": "sign_out"}
    missed = [
        m
        for m, action in real.items()
        if (operator(m) or {}).get("args", {}).get("action") != action or (planner._forced_decision(m) or None) is None
    ]
    failures += emit("a real power request still asks for confirmation in both layers", not missed, missed=missed)

    from eva.core import operator_commands

    failures += emit("the substring power table is gone", not hasattr(operator_commands, "POWER_ACTIONS"))

    polluted = [m for m in ("google best laptops 2026 and open the first result", "web search cheap flights and open the first result") if operator(m) is not None]
    failures += emit("a web search carrying a second request is declined, not polluted", not polluted, polluted=polluted)

    spotify_bad = classify_capability_intent("play lofi on spotify and turn the volume up", {}).get("suggested_route")
    spotify_ok = classify_capability_intent("play lofi and chill beats", {})
    failures += emit(
        "Spotify declines a query carrying a second request and still plays ordinary ones",
        spotify_bad is None and spotify_ok.get("suggested_route") == "spotify_play_desktop" and spotify_ok.get("query") == "lofi and chill beats",
    )

    failures += emit(
        "lock/google errands reach the agent loop; single requests stay single",
        is_agentic_intent("minimize all windows and lock the laptop")
        and is_agentic_intent("google best laptops 2026 and open the first result")
        and not is_agentic_intent("tell me about cats and dogs")
        and not is_agentic_intent("search for milk and eggs"),
    )

    about = maybe_handle_fast_command("what do u know abt me", ToolRegistry())
    failures += emit("the shorthand about-me question is answered locally", about is not None and about[1] == "fast-command")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    failures += emit("README records Phase 112", "| 112 |" in readme)
except Exception as exc:  # pragma: no cover
    failures += emit("behavioural checks ran", False, error=f"{type(exc).__name__}: {exc}")

print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
raise SystemExit(0 if failures == 0 else 1)
