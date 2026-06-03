from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))


def emit(case: str, passed: bool, **payload: Any) -> int:
    ok = bool(passed)
    print(json.dumps({"case": case, "pass": ok, **payload}, indent=2, ensure_ascii=False))
    return 0 if ok else 1


def clean_output(value: object) -> bool:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    blocked = ("{'", "HardeningCheck(", "PublicReleaseRisk(", "Traceback", "C:\\Users\\", "sk-", "sqlite3.Row")
    return not any(marker in text for marker in blocked)


def fast(command: str) -> str:
    from eva.core.fast_commands import maybe_handle_fast_command

    result = maybe_handle_fast_command(command, tools=None, memory=None)
    return str(result[0]) if result else ""


def run_verifier(script_name: str) -> bool:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script_name)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=180,
    )
    return completed.returncode == 0


def main() -> int:
    failures = 0
    try:
        from eva.release.hardening import (
            check_docs_public_wording,
            check_gitignore_public_safety,
            check_sample_data_public_safe,
            format_public_release_hardening_status,
            public_release_hardening_status,
            scan_repo_for_public_release_risks,
        )
    except Exception as exc:
        failures += emit("hardening_module_imports", False, error=str(exc))
        print(json.dumps({"overall_pass": False, "failures": failures}, indent=2))
        return 1

    status = public_release_hardening_status(ROOT)
    status_text = format_public_release_hardening_status(ROOT)
    audit_text = fast("eva public release audit")
    env_example = ROOT / ".env.example"
    env_text = env_example.read_text(encoding="utf-8", errors="replace") if env_example.exists() else ""
    gitignore_text = (ROOT / ".gitignore").read_text(encoding="utf-8", errors="replace")
    sample_text = (ROOT / "samples" / "research_memory" / "eva_demo_notes.json").read_text(encoding="utf-8", errors="replace")
    public_docs = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in (ROOT / "docs").glob("PUBLIC_RELEASE*.md")
    )
    checklist_text = (ROOT / "docs" / "PUBLIC_RELEASE_CHECKLIST.md").read_text(encoding="utf-8", errors="replace")
    license_path = ROOT / "LICENSE"
    license_text = license_path.read_text(encoding="utf-8", errors="replace") if license_path.exists() else ""
    readme_text = (ROOT / "README.md").read_text(encoding="utf-8", errors="replace")

    failures += emit("hardening_module_imports", True)
    failures += emit("license_exists", license_path.exists())
    failures += emit("license_mentions_polyform_noncommercial", "PolyForm Noncommercial License 1.0.0" in license_text)
    failures += emit("license_mentions_copyright", "Copyright 2026 Ankit L" in license_text)
    readme_lower = readme_text.lower()
    failures += emit("readme_says_source_available", "source-available" in readme_lower)
    failures += emit("readme_does_not_call_eva_open_source", "eva is open-source" not in readme_lower and "eva agent is open-source" not in readme_lower and "this project is open-source" not in readme_lower)
    failures += emit("readme_mentions_noncommercial_use", "non-commercial use is allowed" in readme_lower or "noncommercial use is allowed" in readme_lower)
    failures += emit("readme_mentions_commercial_permission", "commercial use" in readme_lower and "requires separate written permission" in readme_lower)
    failures += emit("hardening_status_human_readable", "Eva public release hardening" in status_text and clean_output(status_text), output=status_text)
    failures += emit("audit_command_human_readable", "Eva public release hardening" in audit_text and clean_output(audit_text), output=audit_text)
    failures += emit("outputs_no_raw_dict_repr", "{'" not in status_text + audit_text)
    failures += emit("outputs_no_dataclass_repr", "HardeningCheck(" not in status_text + audit_text and "PublicReleaseRisk(" not in status_text + audit_text)
    failures += emit("outputs_no_stack_trace", "Traceback" not in status_text + audit_text)
    failures += emit("env_local_content_not_printed", ".env.local content" not in status_text.lower() + audit_text.lower())

    secret_markers = ("sk-", "AIza", "ghp_", "xoxb-", "-----BEGIN")
    failures += emit("env_example_exists", env_example.exists())
    failures += emit(
        "env_example_no_real_secret_looking_values",
        bool(env_text)
        and all(marker not in env_text for marker in secret_markers)
        and "EVA_PUBLIC_MODE" in env_text
        and "EVA_RELEASE_CHANNEL" in env_text
        and "EVA_RESEARCH_MEMORY_VECTOR_ENABLED=false" in env_text,
    )
    failures += emit("gitignore_protects_backend_eva_data", "backend/eva/data/" in gitignore_text)
    failures += emit("gitignore_protects_env_local", ".env.local" in gitignore_text and ".env.*" in gitignore_text and "!.env.example" in gitignore_text)
    failures += emit(
        "sample_research_memory_notes_fake_public_safe",
        "demo_fake" in sample_text and "personal" not in sample_text.lower() and ".env.local" not in sample_text,
    )
    docs_lower = public_docs.lower()
    checklist_lower = checklist_text.lower()
    failures += emit("docs_do_not_claim_fully_local_first", "fully local-first" not in docs_lower)
    failures += emit(
        "docs_source_available_noncommercial_wording",
        "source-available" in docs_lower and "non-commercial" in docs_lower,
    )
    failures += emit("docs_no_eva_open_source_claim", "eva is open-source." not in docs_lower and "this project is open-source" not in docs_lower)
    failures += emit("checklist_no_missing_license_warning", "license is added" in checklist_lower or "license file is present" in checklist_lower)
    failures += emit("checklist_mentions_no_personal_research_db", "personal research memory" in checklist_lower)
    failures += emit("checklist_mentions_no_secrets", "secrets" in checklist_lower or "api keys" in checklist_lower)
    failures += emit("checklist_mentions_demo_commands", "eva demo scenarios" in checklist_text and "eva safety test" in checklist_text)

    risks = scan_repo_for_public_release_risks(ROOT)
    failures += emit("repo_scan_returns_clean_objects", isinstance(risks, list) and clean_output(status_text), warning_count=len(status.warnings))
    failures += emit("gitignore_check_runs", bool(check_gitignore_public_safety(ROOT).checks))
    failures += emit("docs_wording_check_runs", bool(check_docs_public_wording(ROOT).checks))
    failures += emit("sample_data_check_runs", bool(check_sample_data_public_safe(ROOT).checks))

    for script_name in (
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
