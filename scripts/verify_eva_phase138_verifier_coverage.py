"""Standalone verifier for Phase 138 (every verifier runs; workspace secrets stay secret).

1. Every scripts/verify_*.py is registered in verify_eva_all or listed in NOT_IN_SUITE
   with a reason, and every nested target of a nesting verifier runs at top level.
2. Workspace tools refuse .env.local and every .env.* backup (only ".env" used to be
   blocked), whatever EVA_WORKSPACE_EXCLUDE_FILES says; .env.example stays readable.
3. Workspace search matches file names across the whole tree, not the first 300.
4. The shared source guard flags real imports/calls, not prose.
5. README records the phase and leaks no local home path.
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
    import verify_eva_all as va  # scripts/ is sys.path[0] when run as a script
    from _source_guard import no_network, no_shell

    on_disk = {p.name for p in (ROOT / "scripts").glob("verify_*.py")} - {"verify_eva_all.py"}
    unaccounted = sorted(on_disk - set(va.FULL_VERIFIERS) - set(va.NOT_IN_SUITE))
    failures += emit("every verifier registered or explained", not unaccounted, unaccounted=unaccounted)
    failures += emit(
        "set-aside verifiers carry a reason",
        all(r.startswith(("retired: ", "excluded: ")) for r in va.NOT_IN_SUITE.values()),
        not_in_suite=va.NOT_IN_SUITE,
    )
    nested = {
        "verify_eva_planner_v3_quality.py": ["verify_eva_planner_v3.py", "verify_eva_capability_permissions.py"],
        "verify_eva_research_memory_ranking.py": ["verify_eva_capabilities.py", "verify_eva_research_memory_vectors.py"],
        "verify_eva_public_release_hardening.py": ["verify_eva_public_release.py", "verify_eva_resource_registry.py"],
    }
    missing = {k: [t for t in v if t not in va.FULL_VERIFIERS] for k, v in nested.items()}
    failures += emit("nested targets that used to run nowhere now run at top level", not any(missing.values()), missing=missing)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name in (".env.local", ".env.local.bak-phase121", ".env.example"):
            (root / name).write_text("NVIDIA_API_KEY=nvapi-test-not-real\n", encoding="utf-8")
        (root / "deep").mkdir()
        for i in range(30):
            (root / f"a{i:02d}.py").write_text("x = 1\n", encoding="utf-8")
        (root / "deep" / "tavily_search.py").write_text("x = 2\n", encoding="utf-8")
        saved = {k: os.environ.get(k) for k in ("EVA_WORKSPACE_ROOT", "EVA_WORKSPACE_EXCLUDE_FILES", "EVA_WORKSPACE_MAX_FILES_PER_SCAN")}
        os.environ.update({"EVA_WORKSPACE_ROOT": str(root), "EVA_WORKSPACE_EXCLUDE_FILES": "*.log", "EVA_WORKSPACE_MAX_FILES_PER_SCAN": "10"})
        try:
            from backend.eva.workspace.indexer import safe_list_files, search_workspace
            from backend.eva.workspace.reader import safe_read_file

            secret = safe_read_file(".env.local")
            backup = safe_read_file(".env.local.bak-phase121")
            example = safe_read_file(".env.example")
            listed = [item["path"] for item in safe_list_files("")["files"] if item["path"].startswith(".env")]
            failures += emit(
                "workspace refuses .env.local and backups, keeps .env.example",
                secret.get("refused") and backup.get("refused") and example.get("ok") and listed == [".env.example"],
                listed=listed,
            )
            found = search_workspace("tavily")
            failures += emit(
                "workspace search finds names beyond the content scan limit",
                bool(found["matches"]) and found["matches"][0]["path"] == "deep/tavily_search.py" and found["content_truncated"],
                searched=found.get("searched_files"),
            )
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        prose = root / "prose.py"
        prose.write_text('"""No verifier subprocesses."""\n# ordinary requests.\nX = "ai_os.system_map"\n', encoding="utf-8")
        code = root / "code.py"
        code.write_text("import subprocess\nimport requests\n", encoding="utf-8")
        failures += emit(
            "source guard flags code, not prose",
            not no_shell([prose])[0] and not no_network([prose])[0] and no_shell([code])[0] and no_network([code])[0],
        )

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    failures += emit("README records Phase 138 and leaks no home path", "| 138 |" in readme and "C:/Users/" not in readme)
except Exception as exc:  # a crash is a failure, never a pass
    failures += emit("verifier crashed", False, error=f"{type(exc).__name__}: {exc}")

print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
sys.exit(0 if failures == 0 else 1)
