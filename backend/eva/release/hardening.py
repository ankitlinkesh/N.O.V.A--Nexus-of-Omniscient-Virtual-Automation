from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


SOURCE_SUFFIXES = {".py", ".js", ".ts", ".html", ".css", ".md", ".json", ".toml", ".yml", ".yaml", ".example"}
INTENTIONAL_FIXTURE_MARKER = "Intentional fake secret-pattern fixture"
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "backend/eva/data",
    "backend/data/checkpoints",
    "data",
    "bin",
    "models",
    "frontend/assets",
    "logs",
    "screenshots",
}


@dataclass(frozen=True)
class HardeningCheck:
    name: str
    status: str
    detail: str
    next_action: str = ""


@dataclass(frozen=True)
class PublicReleaseRisk:
    status: str
    path: str
    detail: str


@dataclass(frozen=True)
class HardeningResult:
    checks: list[HardeningCheck]
    risks: list[PublicReleaseRisk]


@dataclass(frozen=True)
class PublicReleaseHardeningStatus:
    checks: list[HardeningCheck]
    risks: list[PublicReleaseRisk]
    warnings: list[str]
    failures: list[str]


def public_release_hardening_status(repo_root: str | Path | None = None) -> PublicReleaseHardeningStatus:
    root = _repo_root(repo_root)
    checks: list[HardeningCheck] = []
    checks.extend(_license_checks(root))
    checks.extend(check_gitignore_public_safety(root).checks)
    checks.extend(check_docs_public_wording(root).checks)
    checks.extend(check_sample_data_public_safe(root).checks)
    checks.extend(_env_example_checks(root))
    checks.extend(_readme_checks(root))
    risks = scan_repo_for_public_release_risks(root)
    checks.append(_risk_summary_check(risks))
    warnings = [check.name for check in checks if check.status == "WARN"]
    failures = [check.name for check in checks if check.status == "FAIL"]
    return PublicReleaseHardeningStatus(checks=checks, risks=risks, warnings=warnings, failures=failures)


def format_public_release_hardening_status(repo_root: str | Path | None = None) -> str:
    status = public_release_hardening_status(repo_root)
    if status.failures:
        state = "Failures found."
    elif status.warnings:
        state = "Warnings found."
    else:
        state = "Ready for manual release review."
    lines = [
        "Eva public release hardening",
        "",
        "Status:",
        state,
        "",
        "Checks:",
    ]
    for check in status.checks:
        lines.append(f"- {check.name}: {check.status} - {check.detail}")
    if status.risks:
        lines.extend(["", "Repo-scope findings:"])
        for risk in status.risks[:20]:
            lines.append(f"- {risk.status} {risk.path}: {risk.detail}")
    lines.extend(["", "Next:"])
    next_actions = [check.next_action for check in status.checks if check.next_action]
    if next_actions:
        for action in next_actions[:8]:
            lines.append(f"- {action}")
    else:
        lines.append("- Run the public verifier suite, then review staged files before publishing.")
    lines.extend(
        [
            "",
            "Audit scope:",
            "Repo files only. No network, package install, MCP, Playwright, PyAutoGUI, secret-file read, or secret printing was performed.",
        ]
    )
    return "\n".join(lines)


def format_public_ready_check(repo_root: str | Path | None = None) -> str:
    status = public_release_hardening_status(repo_root)
    if status.failures:
        state = "Not ready"
        next_line = "Resolve blocking failures before publishing."
    elif status.warnings:
        state = "Ready with warnings"
        next_line = "Review warnings and staged files before publishing."
    else:
        state = "Ready"
        next_line = "Run the verifier suite and review staged files before publishing."
    return "\n".join(
        [
            "Eva public readiness check",
            "",
            f"Status: {state}",
            f"Blocking failures: {len(status.failures)}",
            f"Warnings: {len(status.warnings)}",
            "",
            "Summary:",
            "Source/docs/license checks are based on the repo-local public hardening audit.",
            "Secret environment files are reported by name only; contents are not read.",
            "",
            "Next:",
            f"- {next_line}",
        ]
    )


def scan_repo_for_public_release_risks(repo_root: str | Path | None = None) -> list[PublicReleaseRisk]:
    root = _repo_root(repo_root)
    risks: list[PublicReleaseRisk] = []
    for path in _iter_repo_source_files(root):
        rel = _rel(root, path)
        name = path.name.lower()
        if name in {".env", ".env.local"}:
            risks.append(PublicReleaseRisk("WARN", rel, "secret environment file is present locally; file contents were not read"))
            continue
        if path.suffix.lower() in {".sqlite3", ".db"}:
            risks.append(PublicReleaseRisk("FAIL", rel, "runtime database file must not be part of public source"))
            continue
        text = _safe_read(path)
        if not text:
            continue
        for detail in _secret_findings(text):
            risks.append(PublicReleaseRisk("WARN", rel, detail))
        lowered = text.lower()
        if _has_unqualified_fully_local_first_claim(text):
            risks.append(PublicReleaseRisk("WARN", rel, "wording claims fully local-first; use the public release wording instead"))
        if _has_active_risky_public_claim(text):
            risks.append(PublicReleaseRisk("WARN", rel, "wording may imply risky automation is active in public mode"))
        if "c:\\users\\" in lowered and path.suffix.lower() in {".md", ".example"}:
            risks.append(PublicReleaseRisk("WARN", rel, "user-facing file contains an absolute Windows user path"))
    return risks


def check_gitignore_public_safety(repo_root: str | Path | None = None) -> HardeningResult:
    root = _repo_root(repo_root)
    text = _safe_read(root / ".gitignore")
    required = [
        ".env",
        ".env.*",
        "!.env.example",
        "backend/eva/data/",
        "data/",
        "models/",
        "bin/",
        "frontend/assets/",
        "__pycache__/",
        ".pytest_cache/",
        "screenshots/",
        "logs/",
        "exports/",
        "traces/",
        "*.trace",
        "*.cache",
    ]
    checks = []
    for item in required:
        ok = item in text
        checks.append(
            HardeningCheck(
                f".gitignore protects {item}",
                "PASS" if ok else "WARN",
                "covered" if ok else "missing",
                f"Add `{item}` to .gitignore." if not ok else "",
            )
        )
    return HardeningResult(checks=checks, risks=[])


def check_docs_public_wording(repo_root: str | Path | None = None) -> HardeningResult:
    root = _repo_root(repo_root)
    docs = [
        root / "docs" / "PUBLIC_RELEASE.md",
        root / "docs" / "PUBLIC_RELEASE_CHECKLIST.md",
        root / "docs" / "EVA_RESEARCH_MEMORY.md",
        root / "README.md",
    ]
    text = "\n".join(_safe_read(path) for path in docs if path.exists())
    lowered = text.lower()
    checks = [
        HardeningCheck(
            "Public wording",
            "PASS" if "local data/control with api-backed llm reasoning when configured" in lowered else "WARN",
            "uses public release wording" if "local data/control with api-backed llm reasoning when configured" in lowered else "missing public release wording",
            "" if "local data/control with api-backed llm reasoning when configured" in lowered else "Use `local data/control with API-backed LLM reasoning when configured`.",
        ),
        HardeningCheck(
            "Fully local-first claim",
            "WARN" if "fully local-first" in lowered else "PASS",
            "no fully local-first claim" if "fully local-first" not in lowered else "found fully local-first wording",
            "Replace fully local-first wording with the public release wording." if "fully local-first" in lowered else "",
        ),
        HardeningCheck(
            "Source-available/non-commercial wording",
            "PASS" if "source-available" in lowered and ("non-commercial" in lowered or "noncommercial" in lowered) else "WARN",
            "source-available/non-commercial wording present" if "source-available" in lowered else "license positioning is incomplete",
            "" if "source-available" in lowered and ("non-commercial" in lowered or "noncommercial" in lowered) else "Add source-available/non-commercial release wording before publishing.",
        ),
    ]
    return HardeningResult(checks=checks, risks=[])


def check_sample_data_public_safe(repo_root: str | Path | None = None) -> HardeningResult:
    root = _repo_root(repo_root)
    sample = root / "samples" / "research_memory" / "eva_demo_notes.json"
    text = _safe_read(sample)
    lowered = text.lower()
    ok = sample.exists() and "demo_fake" in text and ".env.local" not in lowered and "personal" not in lowered
    return HardeningResult(
        checks=[
            HardeningCheck(
                "Sample Research Memory demo data",
                "PASS" if ok else "WARN",
                "fake/public-safe sample notes" if ok else "sample notes need review",
                "" if ok else "Keep sample notes fake only; do not use a personal Research Memory database.",
            )
        ],
        risks=[],
    )


def _repo_root(repo_root: str | Path | None = None) -> Path:
    return Path(repo_root).resolve() if repo_root else Path(__file__).resolve().parents[3]


def _license_checks(root: Path) -> list[HardeningCheck]:
    license_path = next((root / name for name in ("LICENSE", "LICENSE.md", "LICENSE.txt") if (root / name).exists()), None)
    license_text = _safe_read(license_path) if license_path else ""
    license_exists = license_path is not None
    polyform = "PolyForm Noncommercial License 1.0.0" in license_text
    copyright_ok = "Copyright 2026 Ankit L" in license_text
    return [
        HardeningCheck(
            "License file",
            "PASS" if license_exists else "WARN",
            "present" if license_exists else "missing",
            "No LICENSE file found. Add PolyForm Noncommercial License 1.0.0 before public release if you do not want commercial resale."
            if not license_exists
            else "",
        ),
        HardeningCheck(
            "PolyForm Noncommercial license",
            "PASS" if polyform else "WARN",
            "PolyForm Noncommercial License 1.0.0 detected" if polyform else "PolyForm Noncommercial License 1.0.0 not detected",
            "Use PolyForm Noncommercial License 1.0.0 for the public source-available release." if not polyform else "",
        ),
        HardeningCheck(
            "License copyright notice",
            "PASS" if copyright_ok else "WARN",
            "Copyright 2026 Ankit L detected" if copyright_ok else "copyright notice missing or unexpected",
            "Add `Eva` and `Copyright 2026 Ankit L` at the top of LICENSE." if not copyright_ok else "",
        ),
    ]


def _env_example_checks(root: Path) -> list[HardeningCheck]:
    path = root / ".env.example"
    text = _safe_read(path)
    safe = bool(text) and not any(marker in text for marker in ("sk-", "AIza", "ghp_", "xoxb-", "-----BEGIN"))
    public_flags = all(flag in text for flag in ("EVA_PUBLIC_MODE", "EVA_RELEASE_CHANNEL", "EVA_RESEARCH_MEMORY_VECTOR_ENABLED=false"))
    no_user_paths = "C:\\Users\\" not in text
    return [
        HardeningCheck(".env.example", "PASS" if path.exists() else "WARN", "present" if path.exists() else "missing", "" if path.exists() else "Add a safe placeholder .env.example."),
        HardeningCheck(".env.example secrets", "PASS" if safe else "FAIL", "no real secret-looking values" if safe else "secret-looking value found", "" if safe else "Replace secret-looking values with empty placeholders."),
        HardeningCheck(".env.example public flags", "PASS" if public_flags else "WARN", "public flags present" if public_flags else "missing public release flags", "" if public_flags else "Add EVA_PUBLIC_MODE, EVA_RELEASE_CHANNEL, and EVA_RESEARCH_MEMORY_VECTOR_ENABLED=false."),
        HardeningCheck(".env.example private paths", "PASS" if no_user_paths else "WARN", "no absolute user paths" if no_user_paths else "absolute Windows user path found", "" if no_user_paths else "Replace private absolute paths with placeholders."),
    ]


def _readme_checks(root: Path) -> list[HardeningCheck]:
    readme = root / "README.md"
    text = _safe_read(readme).lower()
    return [
        HardeningCheck("README", "PASS" if readme.exists() else "WARN", "present" if readme.exists() else "missing", "" if readme.exists() else "Add a concise public README before publishing."),
        HardeningCheck(
            "README source-available wording",
            "PASS" if "source-available" in text and "open-source" not in text else "WARN",
            "source-available wording present" if "source-available" in text else "needs source-available wording",
            "" if "source-available" in text and "open-source" not in text else "Avoid calling the release open-source if you plan a non-commercial/source-available license.",
        ),
        HardeningCheck(
            "README non-commercial permission wording",
            "PASS" if "non-commercial use is allowed" in text and "requires separate written permission" in text else "WARN",
            "commercial permission wording present" if "requires separate written permission" in text else "commercial permission wording missing",
            "State that non-commercial use is allowed and commercial use/resale requires separate written permission." if "requires separate written permission" not in text else "",
        ),
    ]


def _risk_summary_check(risks: list[PublicReleaseRisk]) -> HardeningCheck:
    failures = [risk for risk in risks if risk.status == "FAIL"]
    warnings = [risk for risk in risks if risk.status == "WARN"]
    if failures:
        return HardeningCheck("Repo risk scan", "FAIL", f"{len(failures)} blocking finding(s), {len(warnings)} warning(s)", "Review repo-scope findings before publishing.")
    if warnings:
        return HardeningCheck("Repo risk scan", "WARN", f"{len(warnings)} warning(s)", "Review warnings before publishing.")
    return HardeningCheck("Repo risk scan", "PASS", "no obvious source/doc/sample secrets or public wording risks found")


def _iter_repo_source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = _rel(root, path).replace("\\", "/")
        parts = rel.split("/")
        if any(rel == skip or rel.startswith(f"{skip}/") for skip in SKIP_DIRS):
            continue
        if ".env.local" == path.name or ".env" == path.name:
            files.append(path)
            continue
        if path.suffix.lower() in SOURCE_SUFFIXES or path.name in {"README.md", ".gitignore", ".env.example"}:
            files.append(path)
    return files


def _secret_findings(text: str) -> list[str]:
    findings: list[str] = []
    fixture_marked = INTENTIONAL_FIXTURE_MARKER in text
    for line in text.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if not stripped or lowered.startswith("#") or "secret_markers" in lowered or "blocked =" in lowered:
            continue
        if _is_secret_pattern_definition(stripped):
            continue
        if fixture_marked and _is_intentional_fake_secret_fixture(stripped):
            continue
        if re.search(r"=\s*(sk-[A-Za-z0-9_-]{10,}|AIza[A-Za-z0-9_-]{10,}|ghp_[A-Za-z0-9_]{10,}|xoxb-[A-Za-z0-9-]{10,})", stripped):
            findings.append("secret-looking API key value")
        if re.search(r"bearer\s+[A-Za-z0-9._-]{20,}", stripped, flags=re.IGNORECASE):
            findings.append("bearer token-looking value")
        if "-----BEGIN" in stripped and "PRIVATE KEY" in stripped:
            findings.append("private-key block marker")
    return sorted(set(findings))


def _is_secret_pattern_definition(line: str) -> bool:
    if "re.compile" in line or "re.search" in line:
        return True
    if "PRIVATE KEY" in line and ("in stripped" in line or "marker in line" in line):
        return True
    return bool(("r\"" in line or "r'" in line) and any(marker in line for marker in ("sk-", "ghp_", "AIza", "-----BEGIN")))


def _is_intentional_fake_secret_fixture(line: str) -> bool:
    return any(marker in line for marker in ("sk-test", "ghp_abcdefghijklmnopqrstuvwxyz", "-----BEGIN PRIVATE KEY-----"))


def _has_unqualified_fully_local_first_claim(text: str) -> bool:
    for line in text.splitlines():
        lowered = line.lower()
        if "fully local-first" not in lowered:
            continue
        if any(marker in lowered for marker in ("not in", "in lowered", "no fully local-first", "fully local-first claim", "does not claim", "avoid", "claims fully-local", "claims fully local-first", "replace fully local-first")):
            continue
        return True
    return False


def _has_active_risky_public_claim(text: str) -> bool:
    risky = ("public mode sends", "public mode deletes", "public mode runs mcp", "public mode uses pyautogui", "public mode uses playwright")
    for line in text.splitlines():
        lowered = line.lower().strip()
        if not any(phrase in lowered for phrase in risky):
            continue
        if "risky =" in lowered or lowered.startswith("\"") or lowered.startswith("'"):
            continue
        return True
    return False


def _safe_read(path: Path) -> str:
    if path.name in {".env.local", ".env"}:
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _rel(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name
