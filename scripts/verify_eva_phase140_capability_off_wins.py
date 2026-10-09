"""Standalone verifier for Phase 140 (a process can force NOVA's capabilities off).

1. In a fresh process started with EVA_ENABLE_REAL_INPUT=0, loading a .env.local that
   says 1 leaves it 0; an undenied flag and an ordinary key still follow the file.
2. verify_eva_all forces every capability flag off for its children.
3. The two click-path verifiers that were excluded for safety are now registered.
4. README records the phase.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
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
    with tempfile.TemporaryDirectory() as tmp:
        envfile = Path(tmp) / ".env.local"
        envfile.write_text("EVA_ENABLE_REAL_INPUT=1\nEVA_MCP_ENABLED=1\nNVIDIA_NIM_MODEL=from-file\n", encoding="utf-8")
        probe = (
            f"import os, sys; from pathlib import Path; sys.path.insert(0, {str(ROOT)!r});"
            "from backend.eva.core.config import load_local_env;"
            f"load_local_env(Path({str(envfile)!r}), override=True);"
            "print(os.environ.get('EVA_ENABLE_REAL_INPUT'), os.environ.get('EVA_MCP_ENABLED'), os.environ.get('NVIDIA_NIM_MODEL'))"
        )
        env = {k: v for k, v in os.environ.items() if k not in {"EVA_ENABLE_REAL_INPUT", "EVA_MCP_ENABLED", "NVIDIA_NIM_MODEL"}}
        env.update(EVA_ENABLE_REAL_INPUT="0", NVIDIA_NIM_MODEL="from-shell")
        out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, env=env, timeout=60).stdout.split()
        failures += emit("process off beats .env.local; other keys unchanged", out == ["0", "1", "from-file"], got=out)

    import verify_eva_all as va  # scripts/ is sys.path[0] when run as a script

    source = (ROOT / "scripts" / "verify_eva_all.py").read_text(encoding="utf-8")
    failures += emit("verify_eva_all forces every capability flag off", 'child_env[flag] = "0"' in source)
    clicks = ["verify_visual_desktop_control.py", "verify_eva_v2_runtime_skeleton.py"]
    failures += emit(
        "click-path verifiers now run in the suite",
        all(c in va.FULL_VERIFIERS and c not in va.NOT_IN_SUITE for c in clicks),
    )

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    failures += emit("README records Phase 140", "| 140 |" in readme)
except Exception as exc:  # a crash is a failure, never a pass
    failures += emit("verifier crashed", False, error=f"{type(exc).__name__}: {exc}")

print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
sys.exit(0 if failures == 0 else 1)
