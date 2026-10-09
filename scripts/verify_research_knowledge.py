from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.eva.core.config import load_project_env
from backend.eva.core.fast_commands import maybe_handle_fast_command
from backend.eva.research.store import ResearchStore
from backend.eva.research.skills import (
    research_recall,
    research_save_note,
    research_start_topic,
    research_status,
    research_summary,
)
from backend.eva.tools.registry import ToolRegistry


def emit(case: str, passed: bool, **payload: object) -> int:
    print(json.dumps({"case": case, "pass": passed, **payload}, indent=2, ensure_ascii=False))
    return 0 if passed else 1


def main() -> int:
    load_project_env(ROOT)
    failures = 0

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "research_knowledge.sqlite3"
        store = ResearchStore(db_path)

        topic = research_start_topic("test ai agents", "Temporary verification topic", store=store)
        failures += emit("create_topic", topic.get("ok") is True and topic.get("topic", {}).get("name") == "test ai agents", result=topic)

        note = research_save_note("test ai agents", "Agent systems need tool use, memory, planning, and safety limits.", "agents,safety", store=store)
        failures += emit("save_note", note.get("ok") is True and bool(note.get("note", {}).get("note")), result=note)

        recall = research_recall("test ai agents", "tool memory safety", limit=5, store=store)
        failures += emit(
            "keyword_recall_without_embeddings",
            recall.get("ok") is True
            and recall.get("embedding_model") == "keyword"
            and any("tool use" in str(item.get("text", "")) for item in recall.get("matches", [])),
            result=recall,
        )

        mocked_result = {
            "title": "OpenHuman",
            "url": "https://github.com/tinyhumansai/openhuman",
            "source": "mock",
            "snippet": "A local agent project with voice and tool ideas.",
            "content_summary": "Useful reference for Eva-style agent architecture.",
            "credibility_note": "GitHub source",
        }
        saved = store.save_web_results("test ai agents", "best github repos for AI agents", [mocked_result], source="mock")
        failures += emit("save_mocked_web_result", len(saved) == 1 and saved[0]["url"].startswith("https://github.com/"), saved=saved)

        summary = research_summary("test ai agents", store=store)
        failures += emit(
            "summarize_topic",
            summary.get("ok") is True and "OpenHuman" in summary.get("summary", "") and "tool use" in summary.get("summary", ""),
            result=summary,
        )

        status = research_status(store=store)
        failures += emit(
            "research_status_counts",
            status.get("ok") is True and status.get("topic_count") == 1 and status.get("item_count") == 1 and status.get("note_count") == 1,
            result=status,
        )

        failures += emit("sqlite_file_created", db_path.exists() and db_path.name == "research_knowledge.sqlite3", path=str(db_path))

    real_default_path = ROOT / "backend" / "eva" / "data" / "research_knowledge.sqlite3"
    default_store = ResearchStore(real_default_path)
    default_store.ensure_schema()
    failures += emit(
        "default_sqlite_under_backend_data",
        default_store.path == real_default_path and default_store.path.parent.name == "data",
        path=str(default_store.path),
    )

    registry = ToolRegistry()
    tools = {tool["name"] for tool in registry.list_tools()}
    required_tools = {
        "research_start_topic",
        "research_web",
        "research_save_note",
        "research_recall",
        "research_summary",
        "research_status",
    }
    failures += emit("registry_has_research_tools", required_tools.issubset(tools), missing=sorted(required_tools - tools))

    # The fast commands build their store from DEFAULT_RESEARCH_DB, so point it at a
    # temp file: these cases used to write a "test commands" topic into the user's DB.
    import backend.eva.research.store as research_store_module

    original_default = research_store_module.DEFAULT_RESEARCH_DB
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as fast_tmp:
        research_store_module.DEFAULT_RESEARCH_DB = Path(fast_tmp) / "research_knowledge.sqlite3"
        try:
            command = maybe_handle_fast_command("research status", registry)
            failures += emit(
                "fast_command_research_status",
                command is not None and "Research status" in command[0] and "Topics: 0" in command[0] and "API_KEY" not in command[0],
                response=command,
            )

            command = maybe_handle_fast_command("start research topic test commands", registry)
            failures += emit("fast_command_start_topic", command is not None and "test commands" in command[0].lower(), response=command)

            command = maybe_handle_fast_command("save research note test commands: NIM uses one key and many model IDs.", registry)
            failures += emit("fast_command_save_note", command is not None and "saved" in command[0].lower(), response=command)

            command = maybe_handle_fast_command("what do we know about test commands", registry)
            failures += emit("fast_command_recall_topic", command is not None and "test commands" in command[0].lower(), response=command)
        finally:
            research_store_module.DEFAULT_RESEARCH_DB = original_default

    env_read_guard = ".env" not in (ROOT / "backend" / "eva" / "research" / "store.py").read_text(encoding="utf-8")
    failures += emit("research_store_does_not_read_env", env_read_guard)

    print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
