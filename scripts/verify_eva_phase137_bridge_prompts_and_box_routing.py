"""Standalone verifier for Phase 137 (clearer bridge prompts; "box of" routing).

1. The share.to_box approval names the file, the source folder, the in-box path and
   the internet risk; share.from_box names the file, the destination and the care
   needed. Other tools' explanations are unchanged.
2. "add it to your box of tools" is not a request about NOVA's box; real ones still are.
3. README records the phase.
"""
from __future__ import annotations

import json
import sys
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
    from backend.eva.agent.policies import is_agentic_intent, is_sandbox_request
    from backend.eva.agents.explainer import explain_action

    def what(tool, args):
        return explain_action(tool, "Generic description.", "SANDBOX_TRANSFER", "confirm", args).what_it_does

    to_box = what("share.to_box", {"path": "Downloads/report.pdf"})
    failures += emit(
        "to_box prompt names file, folder, in-box path and internet risk",
        all(p in to_box for p in ("`report.pdf`", "your Downloads folder", "/mnt/share/report.pdf", "internet")),
        text=to_box,
    )
    from_box = what("share.from_box", {"name": "out/result.csv", "folder": "documents"})
    failures += emit(
        "from_box prompt names file, destination and the care needed",
        all(p in from_box for p in ("`result.csv`", "your Documents folder", "nothing is overwritten", "made inside his box")),
        text=from_box,
    )
    failures += emit("other tools' explanations unchanged", what("file.copy", {"src": "a", "dst": "b"}) == "Generic description.")

    not_box = ["add it to your box of tools", "put it in your box of chocolates"]
    real = ["put report.txt into your box", "in your box, count the words", "use your sandbox of course", "in your linux box of choice"]
    wrong = [m for m in not_box if is_sandbox_request(m)] + [m for m in real if not (is_sandbox_request(m) and is_agentic_intent(m))]
    failures += emit("'box of ...' is not NOVA's box; real box requests still route", not wrong, wrong=wrong)

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    failures += emit("README records Phase 137", "| 137 |" in readme)
except Exception as exc:  # a crash is a failure, never a pass
    failures += emit("verifier crashed", False, error=f"{type(exc).__name__}: {exc}")

print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
sys.exit(0 if failures == 0 else 1)
