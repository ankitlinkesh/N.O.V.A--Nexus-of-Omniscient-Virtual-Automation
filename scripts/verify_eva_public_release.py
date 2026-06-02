from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
os.environ.pop("EVA_PUBLIC_MODE", None)
os.environ.pop("EVA_RELEASE_CHANNEL", None)
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))


def emit(case: str, passed: bool, **payload: Any) -> int:
    ok = bool(passed)
    print(json.dumps({"case": case, "pass": ok, **payload}, indent=2, ensure_ascii=False))
    return 0 if ok else 1


def clean_output(value: object) -> bool:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    blocked = (
        "{'",
        "EvaResource(",
        "ResearchMemoryItem(",
        "sqlite3.Row",
        "Traceback",
        "C:\\",
        "backend/eva/data",
        "research_memory.sqlite3",
        "vector_json",
        "raw vector",
    )
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
        from eva.demo.runner import format_demo_run
        from eva.demo.safety_simulator import simulate_public_safety
        from eva.demo.scenarios import list_demo_scenarios
        from eva.release.doctor import format_public_doctor
        from eva.release.status import format_public_release_checklist, format_release_status
    except Exception as exc:
        failures += emit("release_and_demo_modules_import", False, error=str(exc))
        print(json.dumps({"overall_pass": False, "failures": failures}, indent=2))
        return 1

    failures += emit("release_and_demo_modules_import", True)

    release_text = format_release_status()
    checklist_text = format_public_release_checklist()
    failures += emit(
        "release_status_human_readable",
        "Eva release status" in release_text and "development" in release_text.lower() and clean_output(release_text),
        output=release_text,
    )
    failures += emit(
        "public_checklist_mentions_no_secrets_personal_runtime",
        all(phrase in checklist_text.lower() for phrase in ("api keys", "personal research memory", "runtime data", ".env.local"))
        and clean_output(checklist_text),
        output=checklist_text,
    )

    required_scenarios = {
        "open-chatgpt",
        "research-memory",
        "whatsapp-confirmation",
        "unsafe-env-request",
        "delete-downloads-refusal",
        "github-mcp-refusal",
        "vector-search-disabled",
    }
    scenarios = list_demo_scenarios()
    scenario_ids = {scenario.scenario_id for scenario in scenarios}
    failures += emit("required_demo_scenarios_present", required_scenarios.issubset(scenario_ids), missing=sorted(required_scenarios - scenario_ids))
    for scenario_id in sorted(required_scenarios):
        output = format_demo_run(scenario_id)
        failures += emit(
            f"demo_{scenario_id}_no_real_action",
            "Demo mode: no real action executed." in output and clean_output(output),
            output=output,
        )

    env_sim = simulate_public_safety("read .env.local")
    whatsapp_sim = simulate_public_safety("send WhatsApp to mom saying hi")
    delete_sim = simulate_public_safety("delete Downloads folder")
    mcp_sim = simulate_public_safety("use GitHub MCP to merge PR")
    failures += emit("safety_env_local_blocked", env_sim.decision == "hard_block" and ".env.local" in env_sim.reason, output=env_sim.as_text())
    failures += emit("safety_whatsapp_confirmation_or_refused", whatsapp_sim.decision in {"ask_confirmation", "public_refuse"} and "WhatsApp" in whatsapp_sim.as_text(), output=whatsapp_sim.as_text())
    failures += emit("safety_delete_downloads_override_or_refused", delete_sim.decision in {"ask_override", "public_refuse"} and "destructive" in delete_sim.as_text().lower(), output=delete_sim.as_text())
    failures += emit("safety_github_mcp_merge_refused", mcp_sim.decision == "public_refuse" and "MCP" in mcp_sim.as_text(), output=mcp_sim.as_text())

    for command, expected in {
        "resources safe": "Safe resources",
        "resources experimental": "Experimental resources",
        "resources blocked": "Blocked resources",
        "resource categories": "Resource categories",
    }.items():
        output = fast(command)
        failures += emit(
            f"command_{command.replace(' ', '_')}",
            expected in output and clean_output(output),
            output=output,
        )

    sample_path = ROOT / "samples" / "research_memory" / "eva_demo_notes.json"
    sample_text = sample_path.read_text(encoding="utf-8") if sample_path.exists() else ""
    failures += emit(
        "research_memory_demo_sample_exists_fake_only",
        sample_path.exists()
        and "demo_fake" in sample_text
        and "personal" not in sample_text.lower()
        and ".env.local" not in sample_text,
    )

    import_output = fast("research memory import demo")
    failures += emit(
        "research_memory_import_demo_clean",
        "Imported Research Memory demo pack" in import_output
        and "no network" in import_output.lower()
        and clean_output(import_output),
        output=import_output,
    )

    doctor_output = format_public_doctor()
    failures += emit(
        "eva_doctor_public_human_readable",
        "Eva public setup doctor" in doctor_output and "PASS" in doctor_output and clean_output(doctor_output),
        output=doctor_output,
    )

    public_doc = ROOT / "docs" / "PUBLIC_RELEASE.md"
    checklist_doc = ROOT / "docs" / "PUBLIC_RELEASE_CHECKLIST.md"
    public_doc_text = public_doc.read_text(encoding="utf-8") if public_doc.exists() else ""
    failures += emit("public_release_doc_exists", public_doc.exists())
    failures += emit("public_release_checklist_doc_exists", checklist_doc.exists())
    failures += emit(
        "docs_avoid_fully_local_first_claim",
        "fully local-first" not in public_doc_text.lower()
        and "local data/control with API-backed LLM reasoning when configured" in public_doc_text,
    )

    outputs = "\n\n".join(
        [
            release_text,
            checklist_text,
            env_sim.as_text(),
            whatsapp_sim.as_text(),
            delete_sim.as_text(),
            mcp_sim.as_text(),
            doctor_output,
            import_output,
            fast("eva demo scenarios"),
            fast("eva demo run open-chatgpt"),
            fast("eva safety test read .env.local"),
            fast("eva doctor public"),
        ]
    )
    failures += emit("outputs_no_raw_dict_repr", "{'" not in outputs)
    failures += emit("outputs_no_dataclass_repr", "EvaResource(" not in outputs and "ResearchMemoryItem(" not in outputs)
    failures += emit("outputs_no_sqlite_row_repr", "sqlite3.Row" not in outputs)
    failures += emit("outputs_no_stack_trace", "Traceback" not in outputs)
    failures += emit("outputs_no_absolute_windows_paths", "C:\\" not in outputs)

    source_roots = [
        ROOT / "backend" / "eva" / "release",
        ROOT / "backend" / "eva" / "demo",
        ROOT / "backend" / "eva" / "core" / "fast_commands.py",
    ]
    source_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace").lower()
        for root in source_roots
        if root.exists()
        for path in ([root] if root.is_file() else root.rglob("*.py"))
    )
    failures += emit("no_env_local_read", "open('.env.local" not in source_text and 'open(".env.local' not in source_text)
    failures += emit("no_package_install_attempt", "pip install" not in source_text and "subprocess.run" not in source_text)
    failures += emit("no_network_call_attempt", "requests." not in source_text and "urllib.request" not in source_text and "httpx." not in source_text)

    for script_name in (
        "verify_eva_v2_dry_run.py",
        "verify_eva_resource_registry.py",
        "verify_eva_research_memory_help.py",
        "verify_eva_stabilization_v1.py",
    ):
        failures += emit(f"nested_{script_name}", run_verifier(script_name))

    print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
