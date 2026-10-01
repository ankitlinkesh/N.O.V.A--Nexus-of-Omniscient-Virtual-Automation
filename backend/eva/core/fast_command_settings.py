"""Instant system-setting commands (Phase 127): volume, brightness, theme, Wi-Fi/Bluetooth.

"set volume to 30", "dark mode on", "turn off wifi" used to cost two LLM calls and,
for wifi, ended in "I cannot control hardware settings". These are whole-message,
anchored phrasings (the Phase 125 rules) bound to the registry tools in
``tools/system_settings.py``:

- The WHOLE normalized message must match; there is no prefix or substring match,
  so "set the volume of my voice", "is the wifi password safe" and "dark mode in
  vscode" fall through to the planner untouched.
- A message with a second request ("turn off wifi and open chrome") declines, so
  the agent loop does both halves instead of this doing one and dropping the other.
- Every action runs through ``tools.run`` -- the registry -- so the gate applies:
  ``radio_set`` is confirm-class and comes back as an approval prompt even from
  here. Nothing in this module can approve it.
- Numbers: 0-100 are exact, 101-200 are capped at 100 (said out loud), anything
  else is refused without touching the machine.
"""

from __future__ import annotations

import re
from typing import Any

from .fast_command_instant import _run, normalize_question

_N = r"(?P<n>-?\d{1,4})\s*(?:%|percent)?"
_THE = r"(?:the |my )?"
_VOL = rf"{_THE}(?:system |master )?volume"
_BRI = rf"{_THE}(?:screen |display |laptop )?brightness"
_RADIO = r"(?P<kind>wi-?fi|wi fi|wlan|bluetooth)"
_THEME = r"(?:mode|theme)"

# (kind, regex). fullmatch against the normalized message.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (kind, re.compile(rx))
    for kind, rx in (
        # volume
        ("volume_set", rf"(?:(?:set|change|put|turn|make) )?{_VOL} (?:(?:to|at) )?{_N}"),
        ("volume_set", rf"(?:turn|set|put|bring) {_VOL} (?:down |up )?(?:to|at) {_N}"),
        ("volume_mute", rf"(?P<act>mute|unmute)(?: {_THE}(?:volume|sound|audio|speakers?|computer|laptop|pc))?"),
        ("volume_get", rf"what(?:'s| is) {_VOL}(?: level| setting)?(?: at| set to)?(?: right now| now| currently)?"),
        ("volume_get", rf"(?:what(?:'s| is) )?{_THE}current volume(?: level)?"),
        ("volume_get", r"volume level"),
        ("volume_get", rf"is {_THE}(?:volume|sound|audio) muted"),
        # brightness
        ("brightness_set", rf"(?:(?:set|change|put|turn|make) )?{_BRI} (?:(?:to|at) )?{_N}"),
        ("brightness_set", rf"(?:turn|set|put|bring) {_BRI} (?:down |up )?(?:to|at) {_N}"),
        ("brightness_step", rf"(?:(?:turn|bring|put) )?{_BRI} (?P<dir>up|down)"),
        ("brightness_step", rf"(?P<dir>increase|raise|decrease|lower|reduce) {_BRI}"),
        ("brightness_step", rf"(?P<dir>dim|brighten) {_THE}(?:screen|display)"),
        ("brightness_step", rf"make {_THE}(?:screen|display) (?P<dir>brighter|dimmer)"),
        ("brightness_get", rf"what(?:'s| is) {_BRI}(?: level| setting)?(?: at| set to)?(?: right now| now| currently)?"),
        ("brightness_get", rf"(?:what(?:'s| is) )?{_THE}current (?:screen |display )?brightness(?: level)?"),
        ("brightness_get", r"(?:screen |display )?brightness level"),
        # dark / light mode
        ("theme_onoff", rf"(?:turn|switch) (?P<onoff>on|off) {_THE}(?:windows )?(?P<mode>dark|light) {_THEME}"),
        ("theme_onoff", rf"(?:turn|switch) {_THE}(?:windows )?(?P<mode>dark|light) {_THEME} (?P<onoff>on|off)"),
        ("theme_onoff", rf"(?P<onoff>enable|disable|activate|deactivate) {_THE}(?:windows )?(?P<mode>dark|light) {_THEME}"),
        ("theme_onoff", rf"(?:windows )?(?P<mode>dark|light) {_THEME} (?P<onoff>on|off)"),
        ("theme_to", rf"(?:switch|change|go|set(?: it| windows)?) to {_THE}(?P<mode>dark|light) {_THEME}"),
        ("theme_get", rf"what(?:'s| is) {_THE}(?:current )?(?:windows )?(?:theme|colou?r mode)"),
        ("theme_get", r"is dark mode (?:on|enabled|active)"),
        ("theme_get", r"am i (?:in|using) (?:dark|light) mode"),
        # radios
        ("radio_set", rf"(?:turn|switch|set) (?P<onoff>on|off) {_THE}{_RADIO}"),
        ("radio_set", rf"(?:turn|switch|set) {_THE}{_RADIO}(?: back)? (?P<onoff>on|off)"),
        ("radio_set", rf"(?P<onoff>enable|disable) {_THE}{_RADIO}"),
        ("radio_set", rf"{_RADIO} (?P<onoff>on|off)"),
        ("radio_get", rf"is {_THE}{_RADIO} (?:currently )?(?:on|off|enabled|disabled|turned on|turned off)"),
        ("radio_get", rf"{_RADIO} status"),
        ("radio_get", rf"what(?:'s| is) {_THE}{_RADIO} status"),
    )
)

_LEAD = re.compile(r"^(?:hey\s+)?(?:nova|eva)[,\s]+")


def match_setting_command(text: str) -> tuple[str, dict[str, str]] | None:
    """Pure: which settings phrasing is this, or None. Whole-message only."""
    try:
        from ..agent.policies import split_trailing_request

        _head, tail = split_trailing_request(text)
        if tail:
            return None
    except Exception:
        pass
    norm = _LEAD.sub("", normalize_question(text))
    if not norm:
        return None
    for kind, rx in _PATTERNS:
        m = rx.fullmatch(norm)
        if m:
            return kind, {k: v for k, v in m.groupdict().items() if v}
    return None


def _percent(raw: str, noun: str) -> tuple[int | None, str]:
    """(value, note). value None means refuse; note is an optional caveat or the refusal."""
    n = int(raw)
    if 0 <= n <= 100:
        return n, ""
    if 100 < n <= 200:
        return 100, f" (capped at 100; {noun} can't go higher than 100%)"
    return None, f"{noun.capitalize()} goes from 0 to 100, so {n} isn't something I can set."


def _reply_from(result: Any, early: str | None, what: str) -> str:
    if early:
        return early
    if isinstance(result, dict) and isinstance(result.get("message"), str) and result["message"].strip():
        return result["message"]
    return f"I couldn't confirm the {what} change: the tool answered without a result."


def maybe_handle_setting_command(message: str, tools: Any, session_context: dict | None = None) -> tuple[str, str] | None:
    matched = match_setting_command(message)
    if matched is None:
        return None
    kind, g = matched
    note = ""
    if kind == "volume_set":
        value, note = _percent(g["n"], "volume")
        if value is None:
            return note, "desktop-tool"
        result, early = _run(tools, "system_volume", action="set", level=value)
        what = "volume"
    elif kind == "volume_mute":
        result, early = _run(tools, "system_volume", action="mute" if g["act"] == "mute" else "unmute")
        what = "volume"
    elif kind == "volume_get":
        result, early = _run(tools, "system_volume", action="get")
        what = "volume"
    elif kind == "brightness_set":
        value, note = _percent(g["n"], "brightness")
        if value is None:
            return note, "desktop-tool"
        result, early = _run(tools, "display_brightness", action="set", level=value)
        what = "brightness"
    elif kind == "brightness_step":
        up = g["dir"] in {"up", "increase", "raise", "brighten", "brighter"}
        # "dim the screen" is a bigger step than "brightness down": it is a request to make it noticeably dimmer.
        step = 20 if g["dir"] in {"dim", "dimmer", "brighten", "brighter"} else 10
        result, early = _run(tools, "display_brightness", action="up" if up else "down", level=step)
        what = "brightness"
    elif kind == "brightness_get":
        result, early = _run(tools, "display_brightness", action="get")
        what = "brightness"
    elif kind in {"theme_onoff", "theme_to"}:
        mode = g["mode"]
        if kind == "theme_onoff":
            on = g["onoff"] in {"on", "enable", "activate"}
            mode = mode if on else ("light" if mode == "dark" else "dark")
        result, early = _run(tools, "theme_mode", action="set", mode=mode)
        what = "theme"
    elif kind == "theme_get":
        result, early = _run(tools, "theme_mode", action="get")
        what = "theme"
    elif kind == "radio_set":
        radio = "bluetooth" if g["kind"] == "bluetooth" else "wifi"
        state = "on" if g["onoff"] in {"on", "enable"} else "off"
        result, early = _run(tools, "radio_set", kind=radio, state=state)
        what = radio
    elif kind == "radio_get":
        radio = "bluetooth" if g["kind"] == "bluetooth" else "wifi"
        result, early = _run(tools, "radio_status", kind=radio)
        what = radio
    else:  # pragma: no cover - every kind is handled above
        return None
    reply = _reply_from(result, early, what)
    if note and not early and isinstance(result, dict) and result.get("ok"):
        reply = reply.rstrip() + note
    return reply, "desktop-tool"
