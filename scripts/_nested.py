"""One nested-verifier runner for every verifier that re-runs others.

Each copy used to differ: timeouts from 120s to 1200s, and child output decoded
in the console code page (cp1252), which mangled non-ASCII replies. Worse, every
level re-ran its own nested scripts, so a standalone run multiplied: planner_v3
spent 387s and failed only because a grandchild hit its parent's 120s limit.

Now a nested script runs one level deep: its own nested checks are skipped
(EVA_VERIFY_SKIP_NESTED=1), which is safe because test_verify_all_nested_coverage
proves every nested target is also registered at the top level of verify_eva_all.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TIMEOUT_SECONDS = 900.0


def run_nested(script_name: str, *, timeout: float | None = None, tail_chars: int = 2500) -> tuple[bool, str]:
    """Run one verifier; return (passed, output tail). A timeout is a failure."""
    script = ROOT / script_name if "/" in script_name else ROOT / "scripts" / script_name
    env = os.environ.copy()
    env["EVA_VERIFY_SKIP_NESTED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    limit = timeout or float(os.environ.get("EVA_VERIFY_NESTED_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    try:
        completed = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=limit,
        )
    except subprocess.TimeoutExpired:
        return False, f"{script_name} timed out after {limit:.0f}s"
    return completed.returncode == 0, (completed.stdout + completed.stderr)[-tail_chars:]
