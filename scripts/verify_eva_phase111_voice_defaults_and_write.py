"""Standalone verifier for Phase 111 (two of Phase 110's disclosed gaps).

1. Voice defaults never applied. `clampNumber(localStorage.getItem(...))` read a
   missing setting as 0 (`Number(null)` is 0), so every browser without saved
   voice settings clamped rate/pitch/volume to their minimums -- measured live
   as rate 0.85, pitch 0.9, volume 0.4. The backend defaulted the rate to 2.35,
   above the UI's 1.25 maximum. `verify_voice_ui.py`, which should have caught
   this, was red at HEAD and registered nowhere; it is now registered, with its
   two checks that pinned replaced designs (female voices, the "Eva" label)
   updated to the current ones.
2. Typing unlocked only on the word "type". "write"/"enter" now do too, with a
   quoted string or "into"; the exact-words grant is unchanged.

Validated live through the chat route: `open calculator and enter "12+7=" into
it` ran with no confirmation and Calculator's display read back "Display is 19".
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
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
    js = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    node = shutil.which("node")
    if node is None:
        failures += emit("node is available to run the real clampNumber", False)
    else:
        start = js.index("function clampNumber(")
        body = js[start : js.index("\n}\n", start) + 3]
        script = body + "\nprocess.stdout.write(JSON.stringify([clampNumber(null, 1.08, 0.85, 1.25), clampNumber('', 0.82, 0.4, 1), clampNumber('0.95', 1.08, 0.85, 1.25)]));"
        out = json.loads(subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30, check=True).stdout)
        failures += emit("a missing voice setting falls back to the default, not the minimum", out == [1.08, 0.82, 0.95], got=out)

    from fastapi.testclient import TestClient

    from eva.main import app

    for name in ("EVA_VOICE_RATE", "EVA_VOICE_PITCH", "EVA_VOICE_VOLUME"):
        os.environ.pop(name, None)
    voice = TestClient(app).get("/api/health").json()["voice"]

    def const(name: str) -> float:
        return float(js.split(f"const {name} = ", 1)[1].split(";", 1)[0])

    agree = all(
        voice[key] == const(f"DEFAULT_{prefix}") and const(f"MIN_{prefix}") <= voice[key] <= const(f"MAX_{prefix}")
        for key, prefix in (("rate", "VOICE_RATE"), ("pitch", "VOICE_PITCH"), ("volume", "VOICE_VOLUME"))
    )
    failures += emit("backend voice defaults equal the UI's and fit its bounds", agree, voice={k: voice[k] for k in ("rate", "pitch", "volume")})

    from eva.screen.type_grant import user_asked_to_type

    cases = {
        'open notepad and write "hello" in it': True,
        "open notepad and write hello into it": True,
        'open calculator and enter "12+7="': True,
        "open notepad and type hello": True,
        "write me an email and save it": False,
        "enter the room": False,
    }
    wrong = {m: e for m, e in cases.items() if user_asked_to_type(m) is not e}
    failures += emit("write/enter unlock typing only with a quoted string or 'into'", not wrong, wrong=wrong)

    all_src = (ROOT / "scripts" / "verify_eva_all.py").read_text(encoding="utf-8")
    failures += emit("verify_voice_ui.py is registered in the suite", '"verify_voice_ui.py"' in all_src)

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    failures += emit("README records Phase 111", "| 111 |" in readme)
except Exception as exc:  # pragma: no cover
    failures += emit("behavioural checks ran", False, error=f"{type(exc).__name__}: {exc}")

print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
raise SystemExit(0 if failures == 0 else 1)
