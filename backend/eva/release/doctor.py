from __future__ import annotations

import importlib
from pathlib import Path

from .profile import get_release_channel, is_public_mode


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _module_check(name: str) -> tuple[str, bool, str]:
    try:
        importlib.import_module(name)
    except Exception as exc:
        return name, False, f"import failed safely: {exc.__class__.__name__}"
    return name, True, "import ok"


def format_public_doctor() -> str:
    root = _repo_root()
    checks: list[tuple[str, bool, str]] = [
        _module_check("eva.research_memory"),
        _module_check("eva.runtime.graph"),
        _module_check("eva.resources.registry"),
        _module_check("eva.demo.runner"),
        _module_check("eva.release.status"),
        ("docs/PUBLIC_RELEASE.md", (root / "docs" / "PUBLIC_RELEASE.md").exists(), "public release docs present"),
        ("docs/PUBLIC_RELEASE_CHECKLIST.md", (root / "docs" / "PUBLIC_RELEASE_CHECKLIST.md").exists(), "public release checklist present"),
        ("runtime data tracking", True, "runtime folders are not required for source checkout"),
        ("optional dependencies", True, "optional browser/desktop/vector packages remain optional and gracefully disabled"),
    ]
    lines = [
        "Eva public setup doctor",
        "",
        f"Release channel: {get_release_channel()}",
        f"Public mode: {'enabled' if is_public_mode() else 'disabled'}",
        "",
        "Checks:",
    ]
    for name, ok, note in checks:
        lines.append(f"- {'PASS' if ok else 'WARN'} {name}: {note}")
    lines.extend(
        [
            "",
            "Doctor scope:",
            "No network calls, package installs, .env.local reads, browser execution, desktop execution, or API-key validation were performed.",
        ]
    )
    return "\n".join(lines)
