from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))


FIXTURE_MARKER = "Intentional fake secret-pattern fixture"
# Intentional fake secret-pattern fixture for release-scanner tests. Not a real secret.
PUBLIC_DOCS = [
    ROOT / "README.md",
    ROOT / "docs" / "PUBLIC_RELEASE.md",
    ROOT / "docs" / "PUBLIC_RELEASE_CHECKLIST.md",
    ROOT / "docs" / "EVA_RESEARCH_MEMORY.md",
    ROOT / "docs" / "EVA_CURRENT_STATE.md",
    ROOT / "docs" / "EVA_BUG_QUEUE.md",
]


def emit(case: str, passed: bool, **payload: Any) -> int:
    ok = bool(passed)
    print(json.dumps({"case": case, "pass": ok, **payload}, indent=2, ensure_ascii=False))
    return 0 if ok else 1


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def clean_output(value: object) -> bool:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    blocked = ("{'", "HardeningCheck(", "PublicReleaseRisk(", "Traceback", "sqlite3.Row", "sk-test")
    return not any(marker in text for marker in blocked)


def run_verifier(script_name: str) -> bool:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script_name)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=180,
    )
    return completed.returncode == 0


def public_docs_text() -> str:
    return "\n".join(read(path) for path in PUBLIC_DOCS if path.exists())


def public_docs_path_leaks() -> list[str]:
    leaks: list[str] = []
    markers = ("C:\\Users\\", "C:/Users/", "\\Users\\HP", "Documents\\Codex", "Documents/Codex")
    for path in PUBLIC_DOCS:
        text = read(path)
        for marker in markers:
            if marker in text:
                leaks.append(f"{path.relative_to(ROOT).as_posix()}: {marker}")
    return leaks


def fixture_marking_issues() -> list[str]:
    issues: list[str] = []
    fixture_files = [
        ROOT / "scripts" / "verify_eva_research_memory_io.py",
        ROOT / "scripts" / "verify_eva_research_memory_quality.py",
        ROOT / "scripts" / "verify_eva_research_memory_v2.py",
        ROOT / "scripts" / "verify_hybrid_local_agent_mode.py",
        ROOT / "scripts" / "verify_eva_v2_dry_run.py",
        ROOT / "scripts" / "verify_eva_v2_runtime_skeleton.py",
        ROOT / "scripts" / "verify_eva_v2_safe_execution_bridge.py",
    ]
    fake_markers = ("sk-test", "ghp_abcdefghijklmnopqrstuvwxyz", "-----BEGIN PRIVATE KEY-----")
    for path in fixture_files:
        text = read(path)
        if not any(marker in text for marker in fake_markers):
            continue
        if FIXTURE_MARKER in text:
            continue
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if not any(marker in line for marker in fake_markers):
                continue
            issues.append(f"{path.relative_to(ROOT).as_posix()}:{index + 1}")
    return issues


def hardening_output_status(text: str) -> str:
    if "Status:\nReady for manual release review." in text:
        return "Ready"
    if "Status:\nWarnings found." in text:
        return "Ready with warnings"
    return "Not ready"


def main() -> int:
    failures = 0

    try:
        from eva.core.fast_commands import maybe_handle_fast_command
        from eva.release.hardening import format_public_release_hardening_status
    except Exception as exc:
        failures += emit("imports", False, error=str(exc))
        print(json.dumps({"overall_pass": False, "failures": failures}, indent=2))
        return 1

    readme = read(ROOT / "README.md")
    readme_lower = readme.lower()
    license_text = read(ROOT / "LICENSE")
    gitignore = read(ROOT / ".gitignore")
    env_example = read(ROOT / ".env.example")
    docs = public_docs_text()
    hardening_text = format_public_release_hardening_status(ROOT)
    ready = maybe_handle_fast_command("eva public ready check", tools=None, session_context={})
    demo_notes = read(ROOT / "samples" / "research_memory" / "eva_demo_notes.json")

    failures += emit("readme_exists", (ROOT / "README.md").exists())
    failures += emit("license_exists", (ROOT / "LICENSE").exists())
    failures += emit("license_polyform_noncommercial", "PolyForm Noncommercial License 1.0.0" in license_text)
    failures += emit("readme_source_available_noncommercial", "source-available" in readme_lower and "non-commercial use is allowed" in readme_lower)
    failures += emit("readme_not_open_source", "eva is open-source" not in readme_lower and "this project is open-source" not in readme_lower)
    failures += emit("readme_not_fully_local_first", "fully local-first" not in readme_lower)

    leaks = public_docs_path_leaks()
    failures += emit("public_docs_no_absolute_windows_paths", not leaks, leaks=leaks)
    failures += emit("public_docs_use_repo_relative_paths", "backend/eva/" in docs and "scripts/" in docs)

    secret_markers = ("sk-", "AIza", "ghp_", "xoxb-", "-----BEGIN")
    failures += emit("env_example_exists", (ROOT / ".env.example").exists())
    failures += emit("env_example_placeholders_only", bool(env_example) and not any(marker in env_example for marker in secret_markers))
    failures += emit("gitignore_protects_env", ".env" in gitignore and ".env.local" in gitignore and ".env.*" in gitignore and "!.env.example" in gitignore)
    failures += emit("gitignore_protects_backend_data", "backend/eva/data/" in gitignore)
    failures += emit("gitignore_protects_runtime_artifacts", all(item in gitignore for item in ("exports/", "traces/", "*.trace", "*.cache", ".pytest_cache/")))

    failures += emit("demo_sample_notes_public_safe", "demo_fake" in demo_notes and "personal" not in demo_notes.lower() and ".env.local" not in demo_notes)

    fixture_issues = fixture_marking_issues()
    failures += emit("secret_pattern_fixtures_marked", not fixture_issues, issues=fixture_issues)

    failures += emit("hardening_audit_human_readable", "Eva public release hardening" in hardening_text and clean_output(hardening_text), output=hardening_text)
    failures += emit("hardening_audit_env_local_content_not_printed", ".env.local content" not in hardening_text.lower())
    failures += emit("hardening_audit_no_raw_dict_repr", "{'" not in hardening_text)
    failures += emit("hardening_audit_no_dataclass_repr", "HardeningCheck(" not in hardening_text and "PublicReleaseRisk(" not in hardening_text)
    failures += emit("hardening_audit_readiness_status", hardening_output_status(hardening_text) in {"Ready", "Ready with warnings", "Not ready"}, status=hardening_output_status(hardening_text))
    failures += emit(
        "public_ready_check_command",
        bool(ready and ready[1] == "fast-command" and any(label in ready[0] for label in ("Ready", "Ready with warnings", "Not ready")) and clean_output(ready[0])),
        reply=ready,
    )

    for script_name in (
        "verify_eva_public_release_hardening.py",
        "verify_eva_public_release.py",
        "verify_eva_research_memory_help.py",
        "verify_eva_resource_registry.py",
        "verify_eva_stabilization_v1.py",
    ):
        failures += emit(f"nested_{script_name}", run_verifier(script_name))

    print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
