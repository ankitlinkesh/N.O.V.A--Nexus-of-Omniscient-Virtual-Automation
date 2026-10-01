"""Battery and memory, read straight from Windows (Phase 122).

Live, "what's my battery level?" answered "I don't have access to battery level
information" -- while NOVA's own capability list claimed it could show "CPU,
memory, battery". `status` returned only the OS name, the shell and the working
directory. psutil is not a dependency here, and these two kernel32 calls are all
that is needed. Read-only; returns {} off Windows or on any failure.
"""

from __future__ import annotations

import ctypes
import sys
from typing import Any


class _PowerStatus(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_ubyte),
        ("BatteryFlag", ctypes.c_ubyte),
        ("BatteryLifePercent", ctypes.c_ubyte),
        ("SystemStatusFlag", ctypes.c_ubyte),
        ("BatteryLifeTime", ctypes.c_ulong),
        ("BatteryFullLifeTime", ctypes.c_ulong),
    ]


class _MemoryStatus(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def battery_from_status(status: _PowerStatus) -> dict[str, Any]:
    """Pure: interpret a SYSTEM_POWER_STATUS. 255 means unknown; flag 128 = no battery."""
    if status.BatteryFlag == 128 or status.BatteryLifePercent == 255:
        return {"battery_present": False}
    info: dict[str, Any] = {
        "battery_present": True,
        "battery_percent": int(status.BatteryLifePercent),
        "plugged_in": {0: False, 1: True}.get(int(status.ACLineStatus)),
    }
    if status.BatteryLifeTime not in (0xFFFFFFFF, 4294967295):
        info["battery_minutes_left"] = int(status.BatteryLifeTime) // 60
    return info


def power_and_memory() -> dict[str, Any]:
    if sys.platform != "win32":
        return {}
    out: dict[str, Any] = {}
    try:
        kernel32 = ctypes.windll.kernel32
        power = _PowerStatus()
        if kernel32.GetSystemPowerStatus(ctypes.byref(power)):
            out.update(battery_from_status(power))
        memory = _MemoryStatus()
        memory.dwLength = ctypes.sizeof(_MemoryStatus)
        if kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
            out["memory_percent_used"] = int(memory.dwMemoryLoad)
            out["memory_total_gb"] = round(memory.ullTotalPhys / 1024**3, 1)
    except Exception:
        return out
    return out
