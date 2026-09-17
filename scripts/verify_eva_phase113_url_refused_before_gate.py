"""Standalone verifier for Phase 113 (a URL no handler will open is refused before
the gate, not after the user approves it).

`browser_open_result_and_verify(url="file:///C:/Users/HP/.env")` produced an
OVERRIDE prompt -- Phase 55 escalates a sensitive-looking target -- and the
handler's http(s)-only check ran only after `confirm override`. Found by running
`verify_chrome_execution_skills.py`, which no suite ran; it is registered now.
"""

from __future__ import annotations

import dataclasses
import json
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
    from eva.security import tool_gate
    from eva.tools.registry import _URL_TOOLS, ToolRegistry

    registry = ToolRegistry()
    opened: list[str] = []
    for name in _URL_TOOLS:
        assert name in registry._tools, f"{name} is not registered"
        registry._tools[name] = dataclasses.replace(registry._tools[name], handler=lambda __n=name, **kw: opened.append(__n) or {"ok": True})

    tool_gate.reset_pending_calls()
    leaked = []
    for name in sorted(_URL_TOOLS):
        for url in ("file:///C:/Users/HP/.env", "javascript:alert(1)", "https://user:pw@example.com"):
            try:
                result = registry.run(name, url=url)
                leaked.append((name, url, bool(isinstance(result, dict) and result.get("requires_confirmation"))))
            except ValueError:
                pass
    failures += emit(
        "a non-http URL is refused before any approval prompt, for every URL tool",
        not leaked and opened == [] and tool_gate._PENDING_CALLS == {},
        leaked=leaked,
    )

    registry.run("open_url", url="https://example.com")
    registry.run("browser_summarize_page", url="")
    failures += emit("an ordinary URL and an empty 'current page' URL still reach the handler", opened == ["open_url", "browser_summarize_page"], opened=opened)

    all_src = (ROOT / "scripts" / "verify_eva_all.py").read_text(encoding="utf-8")
    failures += emit("verify_chrome_execution_skills.py is registered", '"verify_chrome_execution_skills.py"' in all_src)

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    failures += emit("README records Phase 113", "| 113 |" in readme)
except Exception as exc:  # pragma: no cover
    failures += emit("behavioural checks ran", False, error=f"{type(exc).__name__}: {exc}")

print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
raise SystemExit(0 if failures == 0 else 1)
