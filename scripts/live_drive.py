"""Phase 77 CLI: prove a model actually ran, or refuse to claim it did.

    python scripts/live_drive.py "optional prompt"

Unlike a bare ``python -c ...`` snippet, this loads ``.env.local`` first (via
the harness), so a live run is actually possible -- and it decides "was this
live?" from the router's own response, never from a hopeful assumption. Exit
code: 0 = a model ran, 1 = a provider was tried and no model ran, 2 = refused
because nothing could run.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for path in (ROOT, BACKEND):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def main(argv: list[str]) -> int:
    from eva.diagnostics.live_drive import format_report, run_and_report

    prompt = argv[1] if len(argv) > 1 else "Reply with exactly: ok"
    report = run_and_report(prompt)
    print(format_report(report))
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
