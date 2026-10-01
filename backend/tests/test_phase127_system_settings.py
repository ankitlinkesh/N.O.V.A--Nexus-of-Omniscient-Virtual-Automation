"""Phase 127: system settings -- volume, brightness, theme, Wi-Fi/Bluetooth.

Every backend (Core Audio, PowerShell/WMI/WinRT, the registry) is faked by
``FakeMachine``; conftest's autouse guard makes any un-faked touch of a real
backend fail the test, so no setting can change during pytest.
"""

from __future__ import annotations

import re
from contextlib import contextmanager

import pytest

from backend.eva.agents.role_policy import RoleTier, ROLE_POLICIES, tier_for
from backend.eva.core import fast_command_settings as fcs
from backend.eva.core.fast_commands import maybe_handle_fast_command
from backend.eva.core.power_intent import power_action_requested
from backend.eva.tools import system_settings as ss
from backend.eva.tools.registry import ToolRegistry


class FakeMachine:
    """A fake Windows: volume, brightness, theme and radios, with a mutation log."""

    def __init__(self):
        self.volume = 40
        self.muted = False
        self.brightness = 50
        self.light_theme = False  # dark
        self.theme_split = False
        self.radios = {"WiFi": "On", "Bluetooth": "Off"}
        self.mutations: list[tuple] = []
        # fault injection
        self.audio_unavailable = False
        self.volume_drift = 0
        self.volume_read_fails_after_set = False
        self.no_brightness_panel = False
        self.brightness_readback_fails = False
        self.radio_set_error = None
        self.radio_ignores_set = False
        self.theme_readback_fails = False
        self.keys_ok = True
        self.key_scripts: list[str] = []
        self._volume_set_done = False

    # --- Core Audio
    @contextmanager
    def audio(self):
        if self.audio_unavailable:
            raise OSError("no audio endpoint")
        machine = self

        class Endpoint:
            def GetMute(self):
                return 1 if machine.muted else 0

            def SetMute(self, value, _ctx):
                machine.muted = bool(value)
                machine.mutations.append(("mute", bool(value)))

            def SetMasterVolumeLevelScalar(self, value, _ctx):
                machine.volume = round(value * 100) + machine.volume_drift
                machine._volume_set_done = True
                machine.mutations.append(("volume", round(value * 100)))

            def GetMasterVolumeLevelScalar(self):
                if machine.volume_read_fails_after_set and machine._volume_set_done:
                    raise OSError("read failed")
                return machine.volume / 100.0

        yield Endpoint()

    # --- PowerShell
    def powershell(self, script, timeout=12):
        if "SetStateAsync" in script:
            kind = re.search(r"Kind\.ToString\(\) -eq '(\w+)'", script).group(1)
            state = re.search(r"RadioState\]::(On|Off)", script).group(1)
            self.mutations.append(("radio", kind, state))
            if self.radio_set_error:
                return 0, '{"ok":false,"error":"%s"}' % self.radio_set_error, ""
            if not self.radio_ignores_set:
                self.radios[kind] = state
            return 0, '{"ok":true}', ""
        if "GetRadiosAsync" in script:
            items = ",".join('{"kind":"%s","state":"%s"}' % kv for kv in self.radios.items())
            return 0, '{"ok":true,"radios":[%s]}' % items, ""
        if "WmiSetBrightness" in script:
            level = int(re.search(r"Brightness=\[byte\](\d+)", script).group(1))
            if self.no_brightness_panel:
                return 0, '{"ok":false,"error":"unsupported"}', ""
            self.brightness = level
            self.mutations.append(("brightness", level))
            if self.brightness_readback_fails:
                return 1, "", "WMI exploded"
            return 0, '{"ok":true,"level":%d}' % self.brightness, ""
        if "WmiMonitorBrightness " in script or "ClassName WmiMonitorBrightness |" in script:
            if self.no_brightness_panel:
                return 0, '{"ok":false,"error":"unsupported"}', ""
            if self.brightness_readback_fails and any(m[0] == "brightness" for m in self.mutations):
                return 1, "", "WMI exploded"
            return 0, '{"ok":true,"level":%d}' % self.brightness, ""
        if "keybd_event" in script:
            self.key_scripts.append(script)
            self.mutations.append(("keys",))
            return (0 if self.keys_ok else 1), "", ""
        raise AssertionError(f"unexpected PowerShell script: {script[:80]}")

    # --- theme
    def theme_read(self):
        if self.theme_readback_fails and any(m[0] == "theme" for m in self.mutations):
            raise OSError("registry read failed")
        light = 1 if self.light_theme else 0
        return {"AppsUseLightTheme": light, "SystemUsesLightTheme": (1 - light) if self.theme_split else light}

    def theme_write(self, light):
        self.light_theme = bool(light)
        self.mutations.append(("theme", "light" if light else "dark"))


@pytest.fixture
def machine(monkeypatch):
    m = FakeMachine()
    monkeypatch.setattr(ss, "_audio_endpoint", m.audio)
    monkeypatch.setattr(ss, "_run_powershell", m.powershell)
    monkeypatch.setattr(ss, "_theme_read", m.theme_read)
    monkeypatch.setattr(ss, "_theme_write", m.theme_write)
    monkeypatch.setattr(ss, "_broadcast_theme_change", lambda: None)
    monkeypatch.setattr(ss, "_sleep", lambda _s: None)
    return m


def say(text, tools=None):
    reply = maybe_handle_fast_command(text, tools or ToolRegistry(), {})
    return reply[0] if reply else None


class SpyTools:
    def __init__(self):
        self.calls = []

    def run(self, name, /, **kwargs):
        self.calls.append((name, kwargs))
        return {"ok": True, "message": "spy ok"}


# ---------------------------------------------------------------- routing
@pytest.mark.parametrize(
    "text, call",
    [
        ("set volume to 30", ("system_volume", {"action": "set", "level": 30})),
        ("Set the volume to 30.", ("system_volume", {"action": "set", "level": 30})),
        ("volume 50%", ("system_volume", {"action": "set", "level": 50})),
        ("volume 50", ("system_volume", {"action": "set", "level": 50})),
        ("turn the volume down to 20", ("system_volume", {"action": "set", "level": 20})),
        ("turn the volume up to 80 please", ("system_volume", {"action": "set", "level": 80})),
        ("make the volume 15 percent", ("system_volume", {"action": "set", "level": 15})),
        ("mute", ("system_volume", {"action": "mute"})),
        ("unmute", ("system_volume", {"action": "unmute"})),
        ("unmute the sound", ("system_volume", {"action": "unmute"})),
        ("what's the volume", ("system_volume", {"action": "get"})),
        ("what is the volume right now?", ("system_volume", {"action": "get"})),
        ("set brightness to 60", ("display_brightness", {"action": "set", "level": 60})),
        ("brightness 70%", ("display_brightness", {"action": "set", "level": 70})),
        ("set the screen brightness to 25", ("display_brightness", {"action": "set", "level": 25})),
        ("brightness up", ("display_brightness", {"action": "up", "level": 10})),
        ("brightness down", ("display_brightness", {"action": "down", "level": 10})),
        ("dim the screen", ("display_brightness", {"action": "down", "level": 20})),
        ("what's the brightness", ("display_brightness", {"action": "get"})),
        ("dark mode on", ("theme_mode", {"action": "set", "mode": "dark"})),
        ("dark mode off", ("theme_mode", {"action": "set", "mode": "light"})),
        ("turn on dark mode", ("theme_mode", {"action": "set", "mode": "dark"})),
        ("turn off dark mode", ("theme_mode", {"action": "set", "mode": "light"})),
        ("switch to light mode", ("theme_mode", {"action": "set", "mode": "light"})),
        ("enable dark mode", ("theme_mode", {"action": "set", "mode": "dark"})),
        ("light mode on", ("theme_mode", {"action": "set", "mode": "light"})),
        ("turn wifi off", ("radio_set", {"kind": "wifi", "state": "off"})),
        ("turn off wifi", ("radio_set", {"kind": "wifi", "state": "off"})),
        ("turn off wi-fi", ("radio_set", {"kind": "wifi", "state": "off"})),
        ("turn wifi on", ("radio_set", {"kind": "wifi", "state": "on"})),
        ("turn bluetooth on", ("radio_set", {"kind": "bluetooth", "state": "on"})),
        ("turn off bluetooth", ("radio_set", {"kind": "bluetooth", "state": "off"})),
        ("disable the wifi", ("radio_set", {"kind": "wifi", "state": "off"})),
        ("is wifi on", ("radio_status", {"kind": "wifi"})),
        ("is the wifi on?", ("radio_status", {"kind": "wifi"})),
        ("bluetooth status", ("radio_status", {"kind": "bluetooth"})),
    ],
)
def test_each_phrasing_goes_to_the_right_tool_and_args(text, call):
    spy = SpyTools()
    reply = maybe_handle_fast_command(text, spy, {})
    assert spy.calls == [call], text
    assert reply and reply[0] == "spy ok"


@pytest.mark.parametrize(
    "text",
    [
        "set the volume of my voice",
        "is the wifi password safe",
        "dark mode in vscode",
        "turn up the volume of the video",
        "what's the volume of the video",
        "mute my mic",
        "wifi password",
        "turn off the wifi router",
        "dim the lights",
        "bluetooth speaker recommendations",
        "make the screen reader louder",
        "set a timer for 5 minutes",
        "how do i turn off wifi on a mac",
        "volume up",  # the old key path owns relative nudges
        "turn the volume down",
    ],
)
def test_near_misses_decline(text):
    assert fcs.match_setting_command(text) is None, text
    spy = SpyTools()
    reply = maybe_handle_fast_command(text, spy, {})
    assert not [c for c in spy.calls if c[0] in {"system_volume", "display_brightness", "theme_mode", "radio_set", "radio_status"}]


@pytest.mark.parametrize(
    "text",
    [
        "turn off wifi and open chrome",
        "set volume to 30 and open spotify",
        "dark mode on and then open notepad",
        "mute and lock the laptop",
    ],
)
def test_compound_requests_decline(text):
    assert fcs.match_setting_command(text) is None, text


def test_numbers_clamp_and_nonsense_is_refused_without_touching_anything():
    spy = SpyTools()
    refused = maybe_handle_fast_command("volume 500", spy, {})
    assert spy.calls == [] and "0 to 100" in refused[0]
    assert maybe_handle_fast_command("brightness -5", spy, {})[0].startswith("Brightness goes from 0 to 100")
    assert spy.calls == []
    # 101-200 is capped at 100 (said out loud); 0 is a real value.
    maybe_handle_fast_command("volume 150", spy, {})
    maybe_handle_fast_command("volume 0", spy, {})
    assert spy.calls == [
        ("system_volume", {"action": "set", "level": 100}),
        ("system_volume", {"action": "set", "level": 0}),
    ]


def test_capped_number_is_said_out_loud(machine):
    assert "capped at 100" in say("volume 150")
    assert machine.volume == 100


# ------------------------------------------------------ power words (Phase 112)
@pytest.mark.parametrize(
    "text",
    [
        "turn off wifi", "turn wifi off", "switch off bluetooth", "turn off bluetooth", "turn off dark mode",
        "turn off the wifi", "disable wifi", "turn bluetooth off", "switch wifi off", "turn off wi-fi",
    ],
)
def test_radio_and_theme_phrasings_are_not_power_actions(text):
    assert power_action_requested(text) is None, text


def test_real_power_words_still_are_power_actions():
    assert power_action_requested("turn off the laptop") == "shutdown"
    assert power_action_requested("shut down") == "shutdown"


# ----------------------------------------------------------------- volume
def test_set_volume_reads_back_and_reports_the_read_value(machine):
    assert say("set volume to 30") == "Volume is now 30%."
    assert machine.volume == 30


def test_set_volume_while_muted_unmutes_and_says_so(machine):
    machine.muted = True
    reply = say("set volume to 30")
    assert machine.muted is False and "unmuted" in reply and "30%" in reply


def test_volume_zero_while_muted_stays_muted(machine):
    machine.muted = True
    assert machine.volume == 40
    say("volume 0")
    assert machine.muted is True and machine.volume == 0


def test_whats_the_volume_reads_without_changing(machine):
    machine.volume, machine.muted = 33, True
    assert say("what's the volume") == "Volume is 33% and muted."
    assert machine.mutations == []


def test_mute_and_unmute_are_explicit_not_a_toggle(machine):
    assert say("mute") == "Muted."
    assert say("mute") == "Muted."  # twice stays muted; the key path would have toggled it back
    assert machine.muted is True
    assert "Unmuted" in say("unmute")
    assert say("unmute").startswith("Unmuted") and machine.muted is False


def test_readback_that_disagrees_is_reported_not_papered_over(machine):
    machine.volume_drift = 7
    reply = say("set volume to 30")
    assert "reads back as 37%" in reply and "30%" in reply


def test_readback_that_fails_is_reported_honestly(machine):
    machine.volume_read_fails_after_set = True
    reply = say("set volume to 30")
    assert "couldn't read it back" in reply
    assert "Volume is now" not in reply


def test_audio_api_unavailable_falls_back_to_keys_and_says_it_is_approximate(machine):
    machine.audio_unavailable = True
    reply = say("set volume to 30")
    assert machine.mutations == [("keys",)]
    assert "approximate" in reply and "can't read" in reply
    assert "1..50" in machine.key_scripts[0] and "1..15" in machine.key_scripts[0]


def test_audio_api_and_keys_both_failing_is_an_error_not_success(machine):
    machine.audio_unavailable = True
    machine.keys_ok = False
    assert "both failed" in say("set volume to 30")


def test_volume_get_failure_is_reported(machine):
    machine.audio_unavailable = True
    assert "couldn't read the volume" in say("what's the volume")


# ------------------------------------------------- tool-level clamping (planner path)
@pytest.mark.parametrize("given, expected", [(150, 100), (-5, 0), (100, 100), (0, 0), (30.4, 30), ("45", 45)])
def test_tool_clamps_to_0_100(machine, given, expected):
    result = ToolRegistry().run("system_volume", action="set", level=given)
    assert result["ok"] and machine.volume == expected


@pytest.mark.parametrize("bad", [True, None, "loud", float("nan")])
def test_tool_rejects_non_numbers(machine, bad):
    result = ToolRegistry().run("system_volume", action="set", level=bad)
    assert result["ok"] is False and machine.mutations == []


def test_clamp_percent_directly():
    assert ss.clamp_percent(1000) == 100 and ss.clamp_percent(-1) == 0
    assert ss.clamp_percent(True) is None and ss.clamp_percent("x") is None


# -------------------------------------------------------------- brightness
def test_set_brightness_reads_back(machine):
    assert say("set brightness to 60") == "Brightness is now 60%."
    assert machine.brightness == 60


def test_brightness_up_down_and_dim_step_from_the_current_level(machine):
    say("brightness up")
    assert machine.brightness == 60
    say("brightness down")
    assert machine.brightness == 50
    say("dim the screen")
    assert machine.brightness == 30


def test_brightness_steps_clamp_at_the_ends(machine):
    machine.brightness = 5
    say("dim the screen")
    assert machine.brightness == 0
    machine.brightness = 98
    say("brightness up")
    assert machine.brightness == 100


def test_whats_the_brightness(machine):
    assert say("what's the brightness") == "Brightness is 50%."


def test_external_monitor_is_declined_honestly(machine):
    machine.no_brightness_panel = True
    assert "doesn't support software brightness" in say("set brightness to 60")
    assert "doesn't support software brightness" in say("what's the brightness")
    assert machine.mutations == []


def test_brightness_readback_failure_is_reported(machine):
    machine.brightness_readback_fails = True
    reply = say("set brightness to 60")
    assert "couldn't confirm" in reply and "Brightness is now" not in reply


# ------------------------------------------------------------------- theme
def test_dark_and_light_mode_set_and_read_back(machine):
    assert say("switch to light mode") == "Switched to light mode."
    assert machine.light_theme is True
    assert say("turn on dark mode") == "Switched to dark mode."
    assert say("dark mode on") == "Already in dark mode."


def test_theme_off_means_the_other_mode(machine):
    say("light mode on")
    say("turn off light mode")
    assert machine.light_theme is False


def test_theme_get_and_mixed_state(machine):
    assert say("is dark mode on") == "Windows is in dark mode."
    machine.theme_split = True
    assert "different modes" in say("what's the theme")


def test_theme_readback_failure_is_reported(machine):
    machine.theme_readback_fails = True
    reply = say("dark mode off")
    assert "couldn't read it back" in reply


def test_theme_readback_mismatch_is_reported(machine, monkeypatch):
    monkeypatch.setattr(ss, "_theme_write", lambda light: None)  # the write is silently lost
    assert "reads back as dark" in say("switch to light mode")


# ------------------------------------------------------------------ radios
def test_wifi_off_is_a_pending_confirmation_not_an_execution(machine):
    reply = say("turn off wifi")
    assert machine.mutations == [] and machine.radios["WiFi"] == "On"
    assert "confirm" in reply.lower()
    assert "NOVA loses its own cloud access" in reply


def test_every_radio_toggle_asks_even_turning_on(machine):
    for phrase in ("turn wifi on", "turn bluetooth on", "turn bluetooth off"):
        reply = say(phrase)
        assert "confirm" in reply.lower(), phrase
    assert machine.mutations == []


def test_approving_the_pending_action_really_runs_it_and_reads_back(machine):
    from backend.eva.permissions.confirmation import handle_confirmation_command

    result = ToolRegistry().run("radio_set", kind="bluetooth", state="on")
    assert result["requires_confirmation"] and machine.radios["Bluetooth"] == "Off"
    reply = handle_confirmation_command(f"confirm {result['pending_id']}")
    assert machine.radios["Bluetooth"] == "On"
    assert "Bluetooth is now on" in reply


def test_the_fast_path_cannot_self_approve(machine):
    # Smuggling approval flags through the tool call must not execute anything.
    result = ToolRegistry().run("radio_set", kind="wifi", state="off", confirmed=True, _approved=True)
    assert result["requires_confirmation"] is True and machine.mutations == []


def test_radio_status_is_read_only_and_ungated(machine):
    assert say("is wifi on") == "Wi-Fi is on."
    assert say("bluetooth status") == "Bluetooth is off."
    assert machine.mutations == []


def test_radio_already_in_state_changes_nothing(machine):
    result = ss.radio_set("wifi", "on")
    assert result["ok"] and result["changed"] is False and "already on" in result["message"]
    assert machine.mutations == []


def test_radio_set_reads_back_and_reports_the_read_state(machine):
    result = ss.radio_set("wifi", "off")
    assert result["ok"] and result["verified"] and machine.radios["WiFi"] == "Off"
    assert "Wi-Fi is now off" in result["message"] and "offline" in result["message"]


def test_radio_that_ignores_the_set_is_reported(machine):
    machine.radio_ignores_set = True
    result = ss.radio_set("bluetooth", "on")
    assert result["ok"] is False and "reads back as off" in result["message"]


def test_radio_access_denied_is_an_error(machine):
    machine.radio_set_error = "access_DeniedByUser"
    result = ss.radio_set("bluetooth", "on")
    assert result["ok"] is False and "access_DeniedByUser" in result["message"]


def test_absent_radio_is_reported(machine):
    machine.radios.pop("Bluetooth")
    assert "no Bluetooth radio" in ss.radio_status("bluetooth")["message"]
    assert ss.radio_set("bluetooth", "on")["ok"] is False


def test_radio_powershell_failure_changes_nothing(machine, monkeypatch):
    monkeypatch.setattr(ss, "_run_powershell", lambda *a, **k: (1, "", "boom"))
    result = ss.radio_set("wifi", "off")
    assert result["ok"] is False and "changed nothing" in result["message"]


def test_no_user_text_reaches_a_powershell_script(machine, monkeypatch):
    # The scripts are built from a clamped int and fixed enums only.
    scripts = []
    orig = machine.powershell
    monkeypatch.setattr(ss, "_run_powershell", lambda s, timeout=12: (scripts.append(s), orig(s, timeout))[1])
    ss.brightness_set("60; Remove-Item C:\\ -Recurse")
    ss.radio_set("wifi; calc", "off")
    assert scripts == []  # hostile strings never became a script at all
    ss.brightness_set(60)
    ss.radio_set("wifi", "off")
    assert scripts and all("Remove-Item" not in s and "calc" not in s for s in scripts)
    assert any("Brightness=[byte]60" in s for s in scripts)


# --------------------------------------------------- gating / registry / roles
NEW_TOOLS = ("system_volume", "display_brightness", "theme_mode", "radio_status", "radio_set")


def test_gate_classes():
    from backend.eva.security import tool_gate

    reg = ToolRegistry()
    classes = {t: tool_gate.classify_tool_call(reg.get(t)) for t in NEW_TOOLS}
    assert classes == {
        "system_volume": "allow", "display_brightness": "allow", "theme_mode": "allow",
        "radio_status": "allow", "radio_set": "confirm",
    }
    assert all(reg.get(t).action_type for t in NEW_TOOLS)


def test_radio_gate_cannot_be_downgraded_by_the_tool_description_or_args(machine):
    reg = ToolRegistry()
    spec = reg.get("radio_set")
    assert spec.requires_confirmation is True and spec.safety_level == "sensitive"
    assert "cloud AI access" in spec.description


def test_all_five_are_planner_visible():
    names = {s["name"] for s in ToolRegistry().planner_specs()}
    assert set(NEW_TOOLS) <= names


def test_planner_guidance_in_both_rule_lists_and_no_cannot_claim():
    from pathlib import Path

    src = Path(__file__).resolve().parents[1].joinpath("eva/agent/planner.py").read_text(encoding="utf-8")
    assert src.count("Use system_volume") >= 1 and src.count("radio_set") >= 2
    assert src.count("system_volume") >= 2 and src.count("display_brightness") >= 2
    assert src.count("theme_mode") >= 2
    persona = Path(__file__).resolve().parents[1].joinpath("eva/core/persona.py").read_text(encoding="utf-8")
    assert "exact system volume" in persona


def test_role_tiers():
    tiers = {role: {t: tier_for(role, t) for t in NEW_TOOLS} for role in ROLE_POLICIES}
    # research reads untrusted pages: none of them, in any tier but RED.
    assert all(v is RoleTier.RED for v in tiers["research"].values())
    # nobody gets the radios.
    assert all(tiers[r]["radio_set"] is RoleTier.RED for r in tiers)
    assert tiers["media"]["system_volume"] is RoleTier.GREEN
    for t in ("system_volume", "display_brightness", "theme_mode"):
        assert tiers["desktop"][t] is RoleTier.ORANGE
    assert tiers["file"]["system_volume"] is RoleTier.RED and tiers["code"]["theme_mode"] is RoleTier.RED


def test_research_subtask_cannot_change_a_setting(machine):
    from backend.eva.agents.role_context import role_scope

    with role_scope("research"):
        result = ToolRegistry().run("system_volume", action="set", level=10)
    assert result.get("role_denied") is True and machine.mutations == []


def test_desktop_subtask_changing_volume_needs_confirmation(machine):
    from backend.eva.agents.role_context import role_scope

    with role_scope("desktop"):
        result = ToolRegistry().run("system_volume", action="set", level=10)
    assert result.get("requires_confirmation") is True and machine.mutations == []


def test_synthesis_uses_the_tool_message():
    from backend.eva.core.fast_command_instant import synthesize_single_result
    from backend.eva.agent.executor import ToolExecutionResult

    r = ToolExecutionResult(tool="system_volume", ok=True, result={"ok": True, "message": "Volume is now 30%."})
    assert synthesize_single_result("set volume to 30", [r]) == "Volume is now 30%."
