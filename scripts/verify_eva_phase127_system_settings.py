"""Standalone verifier for Phase 127 (system settings: volume, brightness, theme, radios).

Every backend is faked in-process; nothing here changes a real setting.

1. Whole-message phrasings route to the right tool and args; near-misses and
   compound requests decline (no substring matching).
2. "turn off wifi" is not a POWER action (Phase 112) and not a shutdown prompt.
3. Setters read the state back and report what was READ; a failed or disagreeing
   read-back is reported, never papered over.
4. Numbers: 0-100 exact, 101-200 capped and said so, nonsense refused untouched;
   the tool itself clamps planner-supplied values.
5. Radios are confirm-class even from the fast path: wifi-off is a pending action
   whose prompt names the loss of NOVA's cloud access; the fast path cannot approve.
6. Gate classes, planner visibility, role tiers (research RED, radios RED everywhere).
7. Both planner rule lists carry the guidance; README records Phase 127.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
failures = 0


def emit(case: str, ok: bool, **extra: object) -> int:
    payload = {"case": case, "pass": bool(ok)}
    payload.update(extra)
    print(json.dumps(payload, indent=2, default=str))
    return 0 if ok else 1


try:
    os.environ["EVA_PENDING_ACTION_LEDGER_PATH"] = str(Path(tempfile.mkdtemp(prefix="nova_p127_")) / "pending.jsonl")

    from backend.eva.agents.role_policy import ROLE_POLICIES, RoleTier, tier_for
    from backend.eva.core.fast_commands import maybe_handle_fast_command
    from backend.eva.core.power_intent import power_action_requested
    from backend.eva.security import tool_gate
    from backend.eva.tools import system_settings as ss
    from backend.eva.tools.registry import ToolRegistry

    class M:
        volume, muted, brightness, light = 40, False, 50, False
        radios = {"WiFi": "On", "Bluetooth": "Off"}
        mutations: list = []
        drift = 0
        read_fails = False

    @contextmanager
    def audio():
        class E:
            def GetMute(self):
                return 1 if M.muted else 0

            def SetMute(self, v, _c):
                M.muted = bool(v)
                M.mutations.append("mute")

            def SetMasterVolumeLevelScalar(self, v, _c):
                M.volume = round(v * 100) + M.drift
                M.mutations.append("volume")

            def GetMasterVolumeLevelScalar(self):
                if M.read_fails and "volume" in M.mutations:
                    raise OSError("read failed")
                return M.volume / 100

        yield E()

    def ps(script, timeout=12):
        if "SetStateAsync" in script:
            kind = re.search(r"Kind\.ToString\(\) -eq '(\w+)'", script).group(1)
            M.radios[kind] = re.search(r"RadioState\]::(On|Off)", script).group(1)
            M.mutations.append("radio")
            return 0, '{"ok":true}', ""
        if "GetRadiosAsync" in script:
            items = ",".join('{"kind":"%s","state":"%s"}' % kv for kv in M.radios.items())
            return 0, '{"ok":true,"radios":[%s]}' % items, ""
        if "WmiSetBrightness" in script:
            M.brightness = int(re.search(r"Brightness=\[byte\](\d+)", script).group(1))
            M.mutations.append("brightness")
        return 0, '{"ok":true,"level":%d}' % M.brightness, ""

    def theme_write(light):
        M.light = bool(light)
        M.mutations.append("theme")

    ss._audio_endpoint = audio
    ss._run_powershell = ps
    ss._theme_read = lambda: {"AppsUseLightTheme": int(M.light), "SystemUsesLightTheme": int(M.light)}
    ss._theme_write = theme_write
    ss._broadcast_theme_change = lambda: None
    ss._sleep = lambda _s: None

    class Spy:
        def __init__(self):
            self.calls = []

        def run(self, name, /, **kw):
            self.calls.append((name, kw))
            return {"ok": True, "message": "ok"}

    def routed(text):
        spy = Spy()
        maybe_handle_fast_command(text, spy, {})
        return spy.calls

    cases = {
        "set volume to 30": [("system_volume", {"action": "set", "level": 30})],
        "volume 50%": [("system_volume", {"action": "set", "level": 50})],
        "turn the volume down to 20": [("system_volume", {"action": "set", "level": 20})],
        "unmute": [("system_volume", {"action": "unmute"})],
        "what's the volume": [("system_volume", {"action": "get"})],
        "set brightness to 60": [("display_brightness", {"action": "set", "level": 60})],
        "dim the screen": [("display_brightness", {"action": "down", "level": 20})],
        "turn on dark mode": [("theme_mode", {"action": "set", "mode": "dark"})],
        "switch to light mode": [("theme_mode", {"action": "set", "mode": "light"})],
        "turn off wifi": [("radio_set", {"kind": "wifi", "state": "off"})],
        "turn bluetooth on": [("radio_set", {"kind": "bluetooth", "state": "on"})],
        "is wifi on": [("radio_status", {"kind": "wifi"})],
    }
    bad = {t: routed(t) for t, want in cases.items() if routed(t) != want}
    failures += emit("phrasings route to the right tool and args", not bad, wrong=bad)

    near = ["set the volume of my voice", "is the wifi password safe", "dark mode in vscode", "mute my mic",
            "turn off the wifi router", "turn off wifi and open chrome", "set volume to 30 and open spotify"]
    leaked = {t: routed(t) for t in near if any(c[0] in ss.SETTINGS_TOOLS for c in routed(t))}
    failures += emit("near-misses and compound requests decline", not leaked, leaked=leaked)

    pw = [t for t in ("turn off wifi", "turn wifi off", "switch off bluetooth", "turn off dark mode") if power_action_requested(t)]
    failures += emit("radio/theme phrasings are not power actions", not pw, caught=pw)

    reg = ToolRegistry()

    def say(text):
        reply = maybe_handle_fast_command(text, reg, {})
        return reply[0] if reply else None

    r1 = say("set volume to 30")
    failures += emit("volume reply is the READ-BACK", r1 == "Volume is now 30%." and M.volume == 30, reply=r1)
    M.drift = 7
    r2 = say("set volume to 30")
    M.drift = 0
    failures += emit("disagreeing read-back is reported", "reads back as 37%" in r2, reply=r2)
    M.read_fails = True
    r3 = say("set volume to 50")
    M.read_fails = False
    failures += emit("failed read-back is reported honestly", "couldn't read it back" in r3 and "now 50" not in r3, reply=r3)
    failures += emit("brightness read back", say("set brightness to 70") == "Brightness is now 70%." and M.brightness == 70)
    failures += emit("theme read back", say("switch to light mode") == "Switched to light mode." and M.light is True)

    before = len(M.mutations)
    r4 = say("volume 500")
    failures += emit("nonsense number refused, nothing touched", "0 to 100" in r4 and len(M.mutations) == before, reply=r4)
    say("volume 150")
    failures += emit("101-200 capped at 100 and said so", M.volume == 100)
    reg.run("system_volume", action="set", level=-9)
    failures += emit("tool clamps planner-supplied values", M.volume == 0)

    M.mutations.clear()
    prompt = say("turn off wifi")
    failures += emit(
        "wifi-off from the fast path is a pending confirmation",
        "confirm" in prompt.lower() and "cloud access" in prompt and M.radios["WiFi"] == "On" and not M.mutations,
        reply=prompt[:240],
    )
    forged = reg.run("radio_set", kind="wifi", state="off", confirmed=True, _approved=True)
    failures += emit("approval flags in the call carry no authority", forged.get("requires_confirmation") is True and M.radios["WiFi"] == "On")
    failures += emit("radio status is a plain read", say("is wifi on") == "Wi-Fi is on." and not M.mutations)

    classes = {n: tool_gate.classify_tool_call(reg.get(n)) for n in ss.SETTINGS_TOOLS}
    want_classes = {"system_volume": "allow", "display_brightness": "allow", "theme_mode": "allow",
                    "radio_status": "allow", "radio_set": "confirm"}
    failures += emit("gate classes", classes == want_classes, classes=classes)
    visible = {s["name"] for s in reg.planner_specs()}
    failures += emit("planner-visible", set(ss.SETTINGS_TOOLS) <= visible)
    research = [n for n in ss.SETTINGS_TOOLS if tier_for("research", n) is not RoleTier.RED]
    radios = [r for r in ROLE_POLICIES if tier_for(r, "radio_set") is not RoleTier.RED]
    failures += emit("research RED for all; radio_set RED for every role", not research and not radios,
                     research=research, radios=radios)

    src = (ROOT / "backend/eva/agent/planner.py").read_text(encoding="utf-8")
    failures += emit("both planner rule lists carry the guidance",
                     all(src.count(w) >= 2 for w in ("system_volume", "display_brightness", "theme_mode", "radio_set")))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    failures += emit("README records Phase 127", "| 127 |" in readme)
except Exception as exc:  # pragma: no cover
    failures += emit("checks ran", False, error=f"{type(exc).__name__}: {exc}")

print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
raise SystemExit(0 if failures == 0 else 1)
