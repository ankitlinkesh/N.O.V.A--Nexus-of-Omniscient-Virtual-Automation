"""One place to get the ``uiautomation`` module, ready for the thread asking.

Windows UI Automation is COM, and COM is initialised per thread. NOVA calls it from the web
server's worker threads and from the agent runner's thread, not only from the thread that first
imported the library. On a thread where COM was never initialised (or was torn down by other
code), a call prints ``[WinError -2147221008] CoInitialize has not been called``, and every
caller here catches the failure and reports "unknown" or "no controls", which quietly turns off
grounding, the typing readback and the input-ready wait for that step.

``get_uia()`` initialises UI Automation once for the calling thread (a thread-local flag) and
returns the module, or None when the library is unavailable. It never raises.
"""

from __future__ import annotations

import threading
from types import ModuleType

_local = threading.local()


def get_uia() -> ModuleType | None:
    try:
        import uiautomation as auto  # type: ignore
    except Exception:
        return None
    if not getattr(_local, "ready", False):
        try:
            auto.InitializeUIAutomationInCurrentThread()
        except Exception:
            pass  # an older uiautomation, or COM already fine on this thread: the call below decides
        _local.ready = True
    return auto
