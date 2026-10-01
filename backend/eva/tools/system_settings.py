"""System settings tools (Phase 127): volume, brightness, theme, Wi-Fi/Bluetooth.

Each setter does the change and then READS THE STATE BACK, and the reply states
what was read, not what was asked for. A setter that returns "done" because the
call did not raise is the "green proved storage, never arrival" failure this
project has paid for before.

Backends (each isolated behind one small seam so tests fake it and no pytest
run can touch a real setting -- see conftest.py):

- volume:      Core Audio via ``pycaw`` (``_audio_endpoint``). If the Core Audio
               call is unavailable, a repeated-volume-key fallback is used and
               the reply SAYS it is approximate and unverified.
- brightness:  WMI ``WmiMonitorBrightnessMethods`` / ``WmiMonitorBrightness``
               through one bounded PowerShell call (``_run_powershell``). Laptop
               panels only; an external monitor answers "not supported".
- theme:       HKCU ``...\\Themes\\Personalize`` through ``winreg``
               (``_theme_read`` / ``_theme_write``), then a WM_SETTINGCHANGE
               broadcast so open apps and the taskbar repaint.
- radios:      ``Windows.Devices.Radios`` through PowerShell WinRT. No admin, and
               it flips the radio rather than disabling the adapter
               (``netsh interface set`` needs admin and kills the adapter).

No user-controlled string is ever interpolated into a PowerShell script: the only
values substituted are an int clamped to 0..100 and members of fixed enums.
"""

from __future__ import annotations

import json
import subprocess
import time
from contextlib import contextmanager
from typing import Any, Iterator

PS_TIMEOUT_SECONDS = 12

_RADIO_KINDS = {"wifi": ("WiFi", "Wi-Fi"), "bluetooth": ("Bluetooth", "Bluetooth")}
_THEME_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
_THEME_VALUES = ("AppsUseLightTheme", "SystemUsesLightTheme")

_sleep = time.sleep  # seam: tests do not really wait


def clamp_percent(value: Any) -> int | None:
    """0..100 int, or None when the value is not a usable number (bool is not one)."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError, OverflowError):
        return None
    return max(0, min(100, number))


# ------------------------------------------------------------------ PowerShell
def _run_powershell(script: str, timeout: int = PS_TIMEOUT_SECONDS) -> tuple[int, str, str]:
    """The single place PowerShell is spawned. Bounded, no profile, no prompt."""
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _ps_json(script: str) -> dict[str, Any]:
    """Run a script that prints one JSON object; fold every failure into {"ok": False, ...}."""
    try:
        code, out, err = _run_powershell(script)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except Exception as exc:  # powershell missing, spawn failure
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    if lines:
        try:
            data = json.loads(lines[-1])
            if isinstance(data, (dict, list)):
                return data if isinstance(data, dict) else {"ok": True, "items": data}
        except json.JSONDecodeError:
            pass
    detail = (err.strip() or out.strip() or f"exit code {code}")[:200]
    return {"ok": False, "error": detail}


# ---------------------------------------------------------------------- volume
@contextmanager
def _audio_endpoint() -> Iterator[Any]:
    """Yield the default speakers' IAudioEndpointVolume. COM is per-thread, so it is
    initialised here and released on exit -- the tool may run on any worker thread."""
    import comtypes

    comtypes.CoInitialize()
    try:
        from pycaw.pycaw import AudioUtilities

        device = AudioUtilities.GetSpeakers()
        endpoint = getattr(device, "EndpointVolume", None)
        if endpoint is None:  # older pycaw returns the raw IMMDevice
            from ctypes import POINTER, cast

            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import IAudioEndpointVolume

            iface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            endpoint = cast(iface, POINTER(IAudioEndpointVolume))
        yield endpoint
    finally:
        comtypes.CoUninitialize()


def _read_volume(ep: Any) -> tuple[int, bool]:
    return int(round(float(ep.GetMasterVolumeLevelScalar()) * 100)), bool(ep.GetMute())


def _volume_keys(presses_down: int, presses_up: int, mute_toggle: bool = False) -> bool:
    """Fallback only: send volume keys in ONE PowerShell call. Returns whether it ran."""
    body = []
    if mute_toggle:
        body.append("$k.Invoke(0xAD)")
    if presses_down:
        body.append(f"1..{int(presses_down)} | ForEach-Object {{ $k.Invoke(0xAE) }}")
    if presses_up:
        body.append(f"1..{int(presses_up)} | ForEach-Object {{ $k.Invoke(0xAF) }}")
    script = (
        "$sig='[DllImport(\"user32.dll\")] public static extern void keybd_event(byte b, byte s, uint f, UIntPtr e);';"
        "$t=Add-Type -MemberDefinition $sig -Name EvaVolKeys -Namespace Eva -PassThru;"
        "$k={param($c) $t::keybd_event($c,0,0,[UIntPtr]::Zero); $t::keybd_event($c,0,2,[UIntPtr]::Zero)};"
        + ";".join(body)
    )
    try:
        code, _out, _err = _run_powershell(script, timeout=30)
    except Exception:
        return False
    return code == 0


def volume_get() -> dict[str, Any]:
    try:
        with _audio_endpoint() as ep:
            level, muted = _read_volume(ep)
    except Exception as exc:
        return {"ok": False, "setting": "volume", "error": f"{type(exc).__name__}: {exc}",
                "message": "I couldn't read the volume: the Windows audio API isn't available."}
    note = " and muted" if muted else ""
    return {"ok": True, "setting": "volume", "level": level, "muted": muted, "method": "core_audio",
            "message": f"Volume is {level}%{note}."}


def volume_set(level: Any) -> dict[str, Any]:
    target = clamp_percent(level)
    if target is None:
        return {"ok": False, "setting": "volume", "error": "bad_level",
                "message": "Volume needs a number from 0 to 100."}
    try:
        ep_cm = _audio_endpoint()
        ep = ep_cm.__enter__()
    except Exception as exc:
        return _volume_set_by_keys(target, exc)
    try:
        was_muted = False
        try:
            was_muted = bool(ep.GetMute())
            ep.SetMasterVolumeLevelScalar(target / 100.0, None)
            unmuted = False
            if target > 0 and was_muted:
                ep.SetMute(0, None)
                unmuted = True
        except Exception as exc:
            return {"ok": False, "setting": "volume", "requested": target, "verified": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "message": f"I couldn't set the volume: {type(exc).__name__}."}
        try:
            read, muted = _read_volume(ep)
        except Exception as exc:
            return {"ok": True, "setting": "volume", "requested": target, "verified": False,
                    "method": "core_audio", "error": f"readback: {type(exc).__name__}",
                    "message": f"I asked Windows to set the volume to {target}%, but I couldn't read it back to confirm."}
    finally:
        try:
            ep_cm.__exit__(None, None, None)
        except Exception:
            pass
    extra = " (it was muted, so I unmuted it)" if unmuted else ""
    if abs(read - target) <= 1:
        message = f"Volume is now {read}%{extra}."
        if muted:
            message += " It is still muted."
        return {"ok": True, "setting": "volume", "requested": target, "level": read, "muted": muted,
                "verified": True, "method": "core_audio", "message": message}
    return {"ok": False, "setting": "volume", "requested": target, "level": read, "muted": muted,
            "verified": False, "method": "core_audio",
            "message": f"I set the volume to {target}%, but it reads back as {read}%."}


def _volume_set_by_keys(target: int, cause: Exception) -> dict[str, Any]:
    """Core Audio unavailable: 50 steps down to the floor, then up. Each key press is 2%."""
    ran = _volume_keys(50, (target + 1) // 2)
    if not ran:
        return {"ok": False, "setting": "volume", "requested": target, "verified": False,
                "error": f"{type(cause).__name__}: {cause}",
                "message": "I couldn't set the volume: the Windows audio API and the key fallback both failed."}
    return {"ok": True, "setting": "volume", "requested": target, "verified": False, "method": "keys",
            "message": (f"The Windows audio API wasn't available, so I pressed the volume keys to land near {target}%. "
                        "That is approximate and I can't read the level back to confirm it.")}


def volume_mute(muted: bool) -> dict[str, Any]:
    try:
        ep_cm = _audio_endpoint()
        ep = ep_cm.__enter__()
    except Exception as exc:
        ran = _volume_keys(0, 0, mute_toggle=True)
        return {"ok": ran, "setting": "volume", "verified": False, "method": "keys", "error": f"{type(exc).__name__}",
                "message": ("The Windows audio API wasn't available, so I sent the mute key, which toggles. "
                            "I can't read the state back to confirm it.") if ran
                else "I couldn't change mute: the Windows audio API and the key fallback both failed."}
    try:
        try:
            ep.SetMute(1 if muted else 0, None)
        except Exception as exc:
            return {"ok": False, "setting": "volume", "verified": False, "error": f"{type(exc).__name__}: {exc}",
                    "message": f"I couldn't change mute: {type(exc).__name__}."}
        try:
            level, now_muted = _read_volume(ep)
        except Exception as exc:
            return {"ok": True, "setting": "volume", "verified": False, "method": "core_audio",
                    "message": f"I asked Windows to {'mute' if muted else 'unmute'}, but I couldn't read it back to confirm."}
    finally:
        try:
            ep_cm.__exit__(None, None, None)
        except Exception:
            pass
    if now_muted == bool(muted):
        if now_muted:
            message = "Muted."
        else:
            message = f"Unmuted, volume is {level}%."
            if level == 0:
                message += " (The volume itself is 0%, so you still won't hear anything.)"
        return {"ok": True, "setting": "volume", "level": level, "muted": now_muted, "verified": True,
                "method": "core_audio", "message": message}
    return {"ok": False, "setting": "volume", "level": level, "muted": now_muted, "verified": False,
            "method": "core_audio",
            "message": f"I asked Windows to {'mute' if muted else 'unmute'}, but it reads back as {'muted' if now_muted else 'not muted'}."}


def system_volume(action: str = "get", level: Any = None) -> dict[str, Any]:
    """Tool handler: get | set (needs level) | mute | unmute."""
    action = str(action or "get").strip().lower()
    if action == "get":
        return volume_get()
    if action == "set":
        return volume_set(level)
    if action == "mute":
        return volume_mute(True)
    if action == "unmute":
        return volume_mute(False)
    return {"ok": False, "setting": "volume", "error": "bad_action",
            "message": "Volume actions are get, set, mute and unmute."}


# ------------------------------------------------------------------ brightness
_BRIGHTNESS_GET = (
    "$ErrorActionPreference='Stop';"
    "$b=Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness | Select-Object -First 1;"
    "if($null -eq $b){'{\"ok\":false,\"error\":\"unsupported\"}'}"
    "else{'{\"ok\":true,\"level\":'+[int]$b.CurrentBrightness+'}'}"
)


def _brightness_set_script(level: int) -> str:
    level = int(level)
    return (
        "$ErrorActionPreference='Stop';"
        "$m=Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | Select-Object -First 1;"
        "if($null -eq $m){'{\"ok\":false,\"error\":\"unsupported\"}';exit 0};"
        f"Invoke-CimMethod -InputObject $m -MethodName WmiSetBrightness -Arguments @{{Timeout=[uint32]1;Brightness=[byte]{level}}} | Out-Null;"
        "Start-Sleep -Milliseconds 400;"
        "$b=Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness | Select-Object -First 1;"
        "'{\"ok\":true,\"level\":'+[int]$b.CurrentBrightness+'}'"
    )


_BRIGHTNESS_UNSUPPORTED = ("This display doesn't support software brightness (that is normal for external monitors; "
                           "use the buttons on the monitor).")


def _brightness_read() -> tuple[int | None, dict[str, Any]]:
    data = _ps_json(_BRIGHTNESS_GET)
    if data.get("ok") and isinstance(data.get("level"), int):
        return int(data["level"]), data
    return None, data


def brightness_get() -> dict[str, Any]:
    level, data = _brightness_read()
    if level is None:
        unsupported = data.get("error") == "unsupported"
        return {"ok": False, "setting": "brightness", "error": str(data.get("error")),
                "message": _BRIGHTNESS_UNSUPPORTED if unsupported else "I couldn't read the brightness."}
    return {"ok": True, "setting": "brightness", "level": level, "method": "wmi",
            "message": f"Brightness is {level}%."}


def brightness_set(level: Any) -> dict[str, Any]:
    target = clamp_percent(level)
    if target is None:
        return {"ok": False, "setting": "brightness", "error": "bad_level",
                "message": "Brightness needs a number from 0 to 100."}
    data = _ps_json(_brightness_set_script(target))
    if data.get("error") == "unsupported":
        return {"ok": False, "setting": "brightness", "requested": target, "error": "unsupported",
                "message": _BRIGHTNESS_UNSUPPORTED}
    read = data.get("level") if data.get("ok") else None
    if not isinstance(read, int):
        # The set may or may not have happened; the read-back is what tells us.
        read, _ = _brightness_read()
        if read is None:
            return {"ok": False, "setting": "brightness", "requested": target, "verified": False,
                    "error": str(data.get("error") or "readback_failed"),
                    "message": f"I tried to set the brightness to {target}%, but I couldn't confirm it: the change or the read-back failed."}
    if abs(read - target) <= 2:
        return {"ok": True, "setting": "brightness", "requested": target, "level": read, "verified": True,
                "method": "wmi", "message": f"Brightness is now {read}%."}
    return {"ok": False, "setting": "brightness", "requested": target, "level": read, "verified": False,
            "method": "wmi", "message": f"I set the brightness to {target}%, but it reads back as {read}%."}


def display_brightness(action: str = "get", level: Any = None) -> dict[str, Any]:
    """Tool handler: get | set (needs level) | up | down (steps of 10)."""
    action = str(action or "get").strip().lower()
    if action == "get":
        return brightness_get()
    if action == "set":
        return brightness_set(level)
    if action in {"up", "down"}:
        step = clamp_percent(level) if level is not None else 10
        step = 10 if step is None or step == 0 else step
        current, data = _brightness_read()
        if current is None:
            return brightness_get()
        return brightness_set(current + step if action == "up" else current - step)
    return {"ok": False, "setting": "brightness", "error": "bad_action",
            "message": "Brightness actions are get, set, up and down."}


# ----------------------------------------------------------------------- theme
def _theme_read() -> dict[str, int | None]:
    import winreg

    out: dict[str, int | None] = {}
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _THEME_KEY) as key:
        for name in _THEME_VALUES:
            try:
                out[name] = int(winreg.QueryValueEx(key, name)[0])
            except FileNotFoundError:
                out[name] = None
    return out


def _theme_write(light: bool) -> None:
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _THEME_KEY, 0, winreg.KEY_SET_VALUE) as key:
        for name in _THEME_VALUES:
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, 1 if light else 0)


def _broadcast_theme_change() -> None:
    """Tell open windows and the shell to re-read the theme (no restart needed)."""
    import ctypes
    from ctypes import wintypes

    send = ctypes.windll.user32.SendMessageTimeoutW
    send.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, ctypes.c_wchar_p,
                     wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
    send.restype = wintypes.LPARAM
    result = ctypes.c_size_t()
    send(0xFFFF, 0x001A, 0, "ImmersiveColorSet", 0x0002, 2000, ctypes.byref(result))


def _theme_mode(values: dict[str, int | None]) -> str:
    apps, system = values.get("AppsUseLightTheme"), values.get("SystemUsesLightTheme")
    if apps == 0 and system == 0:
        return "dark"
    if apps == 1 and system == 1:
        return "light"
    return "mixed"


def theme_get() -> dict[str, Any]:
    try:
        values = _theme_read()
    except Exception as exc:
        return {"ok": False, "setting": "theme", "error": f"{type(exc).__name__}: {exc}",
                "message": "I couldn't read the theme setting."}
    mode = _theme_mode(values)
    words = {"dark": "Windows is in dark mode.", "light": "Windows is in light mode.",
             "mixed": "Apps and the taskbar use different modes (one dark, one light)."}
    return {"ok": True, "setting": "theme", "mode": mode, "values": values, "message": words[mode]}


def theme_set(mode: Any) -> dict[str, Any]:
    wanted = str(mode or "").strip().lower()
    if wanted not in {"dark", "light"}:
        return {"ok": False, "setting": "theme", "error": "bad_mode", "message": "Theme mode is dark or light."}
    try:
        before = _theme_mode(_theme_read())
    except Exception:
        before = None
    try:
        _theme_write(wanted == "light")
    except Exception as exc:
        return {"ok": False, "setting": "theme", "requested": wanted, "verified": False,
                "error": f"{type(exc).__name__}: {exc}", "message": f"I couldn't change the theme: {type(exc).__name__}."}
    try:
        _broadcast_theme_change()
    except Exception:
        pass  # the registry value is the setting; the broadcast is only the repaint nudge
    try:
        now = _theme_mode(_theme_read())
    except Exception:
        return {"ok": True, "setting": "theme", "requested": wanted, "verified": False,
                "message": f"I wrote the {wanted} mode setting, but I couldn't read it back to confirm."}
    if now == wanted:
        message = f"Already in {wanted} mode." if before == wanted else f"Switched to {wanted} mode."
        return {"ok": True, "setting": "theme", "requested": wanted, "mode": now, "verified": True, "message": message}
    return {"ok": False, "setting": "theme", "requested": wanted, "mode": now, "verified": False,
            "message": f"I set {wanted} mode, but the setting reads back as {now}."}


def theme_mode(action: str = "get", mode: Any = None) -> dict[str, Any]:
    """Tool handler: get | set (needs mode dark|light)."""
    action = str(action or "get").strip().lower()
    if action == "get":
        return theme_get()
    if action == "set":
        return theme_set(mode)
    return {"ok": False, "setting": "theme", "error": "bad_action", "message": "Theme actions are get and set."}


# ---------------------------------------------------------------------- radios
_RADIO_PRELUDE = (
    "$ErrorActionPreference='Stop';"
    "Add-Type -AssemblyName System.Runtime.WindowsRuntime;"
    "$asTask=([System.WindowsRuntimeSystemExtensions].GetMethods()|Where-Object{$_.Name -eq 'AsTask' -and "
    "$_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'})[0];"
    "function Await($op,$type){$t=$asTask.MakeGenericMethod($type).Invoke($null,@($op));$t.Wait(8000)|Out-Null;$t.Result};"
    "[Windows.Devices.Radios.Radio,Windows.System.Devices,ContentType=WindowsRuntime]|Out-Null;"
    "[Windows.Devices.Radios.RadioAccessStatus,Windows.System.Devices,ContentType=WindowsRuntime]|Out-Null;"
    "[Windows.Devices.Radios.RadioState,Windows.System.Devices,ContentType=WindowsRuntime]|Out-Null;"
)
_RADIO_LIST = (
    _RADIO_PRELUDE
    + "$r=Await ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]]);"
    "$items=@($r|ForEach-Object{[pscustomobject]@{kind=$_.Kind.ToString();state=$_.State.ToString()}});"
    "'{\"ok\":true,\"radios\":'+(ConvertTo-Json -InputObject $items -Compress)+'}'"
)


def _radio_set_script(kind_ps: str, on: bool) -> str:
    state = "On" if on else "Off"
    return (
        _RADIO_PRELUDE
        + "$a=Await ([Windows.Devices.Radios.Radio]::RequestAccessAsync()) ([Windows.Devices.Radios.RadioAccessStatus]);"
        "if($a.ToString() -ne 'Allowed'){'{\"ok\":false,\"error\":\"access_'+$a.ToString()+'\"}';exit 0};"
        "$r=Await ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]]);"
        f"$hit=@($r|Where-Object{{$_.Kind.ToString() -eq '{kind_ps}'}});"
        "if($hit.Count -eq 0){'{\"ok\":false,\"error\":\"not_found\"}';exit 0};"
        "$bad=@();"
        f"foreach($x in $hit){{$s=Await ($x.SetStateAsync([Windows.Devices.Radios.RadioState]::{state})) ([Windows.Devices.Radios.RadioAccessStatus]);"
        "if($s.ToString() -ne 'Allowed'){$bad+=$s.ToString()}};"
        "if($bad.Count -gt 0){'{\"ok\":false,\"error\":\"set_'+$bad[0]+'\"}'}else{'{\"ok\":true}'}"
    )


def _radio_states(kind: str) -> tuple[list[str] | None, dict[str, Any]]:
    """The lower-cased state of every radio of this kind, or None when unreadable."""
    data = _ps_json(_RADIO_LIST)
    radios = data.get("radios") if data.get("ok") else None
    if isinstance(radios, dict):  # ConvertTo-Json of a single item is an object, not a list
        radios = [radios]
    if not isinstance(radios, list):
        return None, data
    ps_kind = _RADIO_KINDS[kind][0].lower()
    return [str(r.get("state", "")).lower() for r in radios if isinstance(r, dict) and str(r.get("kind", "")).lower() == ps_kind], data


def _normalise_radio(kind: Any) -> str | None:
    k = str(kind or "").strip().lower().replace("-", "").replace(" ", "")
    return k if k in _RADIO_KINDS else None


def _radio_summary(states: list[str]) -> str:
    if not states:
        return "absent"
    if "on" in states:
        return "on"
    if all(s == "off" for s in states):
        return "off"
    if "disabled" in states:
        return "disabled"
    return "unknown"


def radio_status(kind: Any) -> dict[str, Any]:
    k = _normalise_radio(kind)
    if k is None:
        return {"ok": False, "setting": "radio", "error": "bad_kind", "message": "Radio kind is wifi or bluetooth."}
    label = _RADIO_KINDS[k][1]
    states, data = _radio_states(k)
    if states is None:
        return {"ok": False, "setting": k, "error": str(data.get("error")),
                "message": f"I couldn't read the {label} state."}
    state = _radio_summary(states)
    words = {
        "on": f"{label} is on.",
        "off": f"{label} is off.",
        "absent": f"This computer has no {label} radio that Windows reports.",
        "disabled": f"{label} is disabled by the system (a hardware switch or device setting), so Windows can't toggle it.",
        "unknown": f"Windows reports the {label} state as unknown.",
    }
    return {"ok": True, "setting": k, "state": state, "method": "winrt_radios", "message": words[state]}


def radio_set(kind: Any, state: Any) -> dict[str, Any]:
    """Tool handler. The read-back sentence is also exposed as ``summary``: the approval
    flow prints ``summary`` after a confirmed run, so the user sees what was READ BACK
    rather than a bare "Executed successfully"."""
    result = _radio_set_impl(kind, state)
    if result.get("ok") and result.get("message"):
        result["summary"] = result["message"]
    return result


def _radio_set_impl(kind: Any, state: Any) -> dict[str, Any]:
    k = _normalise_radio(kind)
    want = str(state or "").strip().lower()
    if k is None or want not in {"on", "off"}:
        return {"ok": False, "setting": "radio", "error": "bad_args",
                "message": "Radio changes need a kind (wifi or bluetooth) and a state (on or off)."}
    label = _RADIO_KINDS[k][1]
    before, data = _radio_states(k)
    if before is None:
        return {"ok": False, "setting": k, "requested": want, "verified": False, "error": str(data.get("error")),
                "message": f"I couldn't read the {label} state, so I changed nothing."}
    if not before:
        return {"ok": False, "setting": k, "requested": want, "error": "absent",
                "message": f"This computer has no {label} radio that Windows reports."}
    if _radio_summary(before) == want:
        return {"ok": True, "setting": k, "requested": want, "state": want, "verified": True, "changed": False,
                "message": f"{label} is already {want}."}
    return _radio_set_raw(k, want == "on")


def _radio_set_raw(kind: str, on: bool) -> dict[str, Any]:
    """Flip the radio and read the state back. Callers outside the tool must go through the gate."""
    label = _RADIO_KINDS[kind][1]
    want = "on" if on else "off"
    result = _ps_json(_radio_set_script(_RADIO_KINDS[kind][0], on))
    if not result.get("ok"):
        err = str(result.get("error") or "failed")
        return {"ok": False, "setting": kind, "requested": want, "verified": False, "error": err,
                "message": f"I couldn't turn {label} {want}: Windows said {err}."}
    after: list[str] | None = None
    for attempt in range(4):  # a radio takes a moment to settle
        after, _ = _radio_states(kind)
        if after is not None and _radio_summary(after) == want:
            break
        if attempt < 3:
            _sleep(0.7)
    if after is None:
        return {"ok": True, "setting": kind, "requested": want, "verified": False,
                "message": f"Windows accepted the request to turn {label} {want}, but I couldn't read it back to confirm."}
    now = _radio_summary(after)
    if now == want:
        note = " I'm offline until it's back on." if kind == "wifi" and not on else ""
        return {"ok": True, "setting": kind, "requested": want, "state": now, "verified": True, "changed": True,
                "method": "winrt_radios", "message": f"{label} is now {want}.{note}"}
    return {"ok": False, "setting": kind, "requested": want, "state": now, "verified": False,
            "message": f"I asked Windows to turn {label} {want}, but it reads back as {now}."}


SETTINGS_TOOLS = ("system_volume", "display_brightness", "theme_mode", "radio_status", "radio_set")
