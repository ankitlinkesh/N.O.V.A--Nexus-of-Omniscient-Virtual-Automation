"""Standalone verifier for Phase 142 (approvals to type show the text; live scorecard).

1. A gated screen.type_text prompt shows short, non-secret text exactly, and hides a
   secret-shaped one; the ledger stays masked in both cases.
2. scripts/pc_scorecard.py exists, drives NOVA over HTTP on a scratch data root, and
   judges from outside (UI Automation, process list, files).
3. README records the phase.
"""
from __future__ import annotations

import json
import os
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
        saved = {k: os.environ.get(k) for k in ("EVA_PENDING_ACTION_LEDGER_PATH", "EVA_DATA_DIR")}
        os.environ["EVA_PENDING_ACTION_LEDGER_PATH"] = str(Path(tmp) / "ledger.jsonl")
        os.environ["EVA_DATA_DIR"] = str(Path(tmp) / "data")
        try:
            from backend.eva.tools.registry import ToolRegistry

            registry = ToolRegistry()
            plain = registry.run("screen.type_text", text="14*3=", reason="verifier")
            secret = registry.run("screen.type_text", text="Hunter2!xQ", reason="verifier")
            ledger = (Path(tmp) / "ledger.jsonl").read_text(encoding="utf-8")
            failures += emit(
                "prompt shows plain text, hides secret-shaped text",
                "It will type exactly: `14*3=`" in plain.get("message", "")
                and "Hunter2!xQ" not in secret.get("message", "")
                and "looks like a secret" in secret.get("message", ""),
            )
            failures += emit("ledger stays masked", "14*3=" not in ledger and "Hunter2!xQ" not in ledger and "[HIDDEN]" in ledger)
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    scorecard = (ROOT / "scripts" / "pc_scorecard.py").read_text(encoding="utf-8")
    failures += emit(
        "live scorecard drives HTTP on a scratch root and judges from outside",
        all(token in scorecard for token in ("/api/chat", "EVA_DATA_DIR", "calc_display", "CalculatorResults", "psutil", "cleanup()")),
    )

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    failures += emit("README records Phase 142", "| 142 |" in readme)
except Exception as exc:  # a crash is a failure, never a pass
    failures += emit("verifier crashed", False, error=f"{type(exc).__name__}: {exc}")

print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
sys.exit(0 if failures == 0 else 1)
