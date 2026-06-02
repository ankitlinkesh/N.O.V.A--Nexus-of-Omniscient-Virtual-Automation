from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
os.environ.pop("EVA_RESEARCH_MEMORY_VECTOR_ENABLED", None)
sys.path.insert(0, str(ROOT / "backend"))


def _case(name: str, passed: bool, **extra: object) -> bool:
    print(json.dumps({"case": name, "pass": bool(passed), **extra}, indent=2, ensure_ascii=False))
    return bool(passed)


def _clean(value: object) -> bool:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    blocked = (
        "{'",
        "ResearchMemoryItem(",
        "ResearchSearchResult(",
        "EvaResearch",
        "sqlite3.Row",
        "Traceback",
        "C:\\",
        "backend/eva/data",
        "research_memory.sqlite3",
        "vector_json",
        "raw vector",
    )
    return not any(marker in text for marker in blocked)


def _fast(command: str) -> str:
    from eva.core.fast_commands import maybe_handle_fast_command

    result = maybe_handle_fast_command(command, tools=None, memory=None)
    if not result:
        return ""
    return str(result[0])


def _run_verifier(script_name: str) -> bool:
    command = [sys.executable, str(ROOT / "scripts" / script_name)]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=120)
    return completed.returncode == 0


def main() -> int:
    failures = 0

    try:
        from eva.research_memory.help import (
            format_research_memory_command_reference,
            format_research_memory_examples,
            format_research_memory_help,
            format_research_memory_phase_summary,
            format_research_memory_safety,
        )
    except Exception as exc:
        failures += 0 if _case("help_module_imports", False, error=str(exc)) else 1
        print(json.dumps({"overall_pass": False, "failures": failures}, indent=2))
        return 1

    help_text = format_research_memory_help()
    commands_text = format_research_memory_command_reference()
    examples_text = format_research_memory_examples()
    safety_text = format_research_memory_safety()
    phase_text = format_research_memory_phase_summary()
    all_text = "\n\n".join([help_text, commands_text, examples_text, safety_text, phase_text])

    failures += 0 if _case("help_module_imports", callable(format_research_memory_help)) else 1
    failures += 0 if _case(
        "research_memory_help_output_human_readable",
        "Research Memory" in help_text and "Main commands" in help_text and _clean(help_text),
        output=help_text,
    ) else 1
    failures += 0 if _case(
        "commands_output_includes_full_command_families",
        all(
            phrase in commands_text
            for phrase in (
                "research memory save topic <topic> note <text>",
                "research memory search <query>",
                "research memory retrieve <query>",
                "research memory export",
                "research memory delete item <item_id>",
                "research memory clear topic <topic> confirm",
                "research memory vector search <query>",
                "research memory semantic search <query>",
            )
        ),
        output=commands_text,
    ) else 1
    failures += 0 if _case(
        "examples_output_copy_paste_ready",
        all(
            phrase in examples_text
            for phrase in (
                "research memory save topic Eva note",
                "research memory search Eva",
                "research memory retrieve Eva",
                "eva v2 plan use my saved research about Eva memory",
            )
        ),
        output=examples_text,
    ) else 1
    lower_safety = safety_text.lower()
    failures += 0 if _case("safety_mentions_no_env_local_reads", ".env.local" in safety_text and "does not read" in lower_safety, output=safety_text) else 1
    failures += 0 if _case(
        "safety_mentions_no_cookies_tokens_storage_passwords",
        all(word in safety_text for word in ("cookies", "tokens", "localStorage", "passwords")),
        output=safety_text,
    ) else 1
    failures += 0 if _case(
        "safety_mentions_no_private_gmail_chat_paywall_scraping",
        all(word in lower_safety for word in ("private", "gmail", "chat", "paywall", "scrape")),
        output=safety_text,
    ) else 1
    failures += 0 if _case("safety_mentions_vector_disabled_default", "disabled by default" in lower_safety and "vector" in lower_safety, output=safety_text) else 1
    failures += 0 if _case(
        "safety_does_not_claim_fully_local_first",
        "fully local-first" not in lower_safety and "local research data and local control" in lower_safety,
        output=safety_text,
    ) else 1
    failures += 0 if _case("phase_summary_mentions_v2_context_injection", "v2 explicit context" in phase_text.lower(), output=phase_text) else 1

    doc_path = ROOT / "docs" / "EVA_RESEARCH_MEMORY.md"
    doc_text = doc_path.read_text(encoding="utf-8") if doc_path.exists() else ""
    failures += 0 if _case("research_memory_doc_exists", doc_path.exists()) else 1
    failures += 0 if _case(
        "doc_mentions_api_backed_llm_or_avoids_full_local_claim",
        bool(doc_text)
        and "API-backed LLM" in doc_text
        and "vector search is disabled by default" in doc_text.lower()
        and "Chroma/Qdrant are not active" in doc_text,
    ) else 1
    failures += 0 if _case("help_outputs_no_raw_dict_repr", "{'" not in all_text) else 1
    failures += 0 if _case("help_outputs_no_dataclass_repr", "EvaResearch" not in all_text and "ResearchMemoryItem(" not in all_text) else 1
    failures += 0 if _case("help_outputs_no_sqlite_row_repr", "sqlite3.Row" not in all_text) else 1
    failures += 0 if _case("help_outputs_no_stack_trace", "Traceback" not in all_text) else 1
    failures += 0 if _case("help_outputs_no_absolute_windows_paths", "C:\\" not in all_text) else 1
    failures += 0 if _case("help_outputs_no_raw_vectors", "raw vector" not in all_text and "vector_json" not in all_text) else 1

    fast_commands = {
        "research memory help": help_text,
        "research memory commands": commands_text,
        "research memory examples": examples_text,
        "research memory safety": safety_text,
        "research memory phase summary": phase_text,
    }
    for command, expected in fast_commands.items():
        actual = _fast(command)
        failures += 0 if _case(
            f"fast_command_{command.replace(' ', '_')}",
            bool(actual) and expected.splitlines()[0] in actual and _clean(actual),
            output=actual,
        ) else 1

    for script_name in (
        "verify_eva_research_memory_v2.py",
        "verify_eva_research_memory_io.py",
        "verify_eva_research_memory_quality.py",
        "verify_eva_research_memory_vectors.py",
        "verify_eva_research_memory_retrieval.py",
        "verify_eva_research_memory_context.py",
        "verify_eva_v2_readonly_delegation.py",
        "verify_eva_stabilization_v1.py",
    ):
        failures += 0 if _case(f"nested_{script_name}", _run_verifier(script_name)) else 1

    print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
