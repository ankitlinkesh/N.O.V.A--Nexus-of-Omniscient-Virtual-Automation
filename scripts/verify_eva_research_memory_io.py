from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Intentional fake secret-pattern fixture for redaction tests. Not a real secret.


def emit(case: str, passed: bool, **payload: Any) -> int:
    print(json.dumps({"case": case, "pass": passed, **payload}, indent=2, ensure_ascii=False))
    return 0 if passed else 1


def _reply(command: str) -> str:
    from backend.eva.core.fast_commands import maybe_handle_fast_command
    from backend.eva.tools.registry import ToolRegistry

    result = maybe_handle_fast_command(command, ToolRegistry(), {})
    return str(result[0] if result else "")


def _clean(text: str) -> bool:
    return all(marker not in text for marker in ("{'", "ResearchMemoryItem(", "ResearchSearchResult(", "sqlite3.Row", "Traceback", "C:\\", "/tmp/"))


def main() -> int:
    temp_root = Path(tempfile.mkdtemp(prefix="eva_research_memory_io_"))
    os.environ["EVA_RESEARCH_MEMORY_DB_PATH"] = str(temp_root / "research_memory.sqlite3")
    os.environ.setdefault("EVA_PENDING_ACTION_LEDGER_PATH", str(temp_root / "pending_actions.jsonl"))

    from backend.eva.research_memory.store import get_research_item, list_research_items, search_research_items
    from backend.eva.runtime.graph import run_eva_v2_execute

    failures = 0

    import_reply = _reply("research memory import note topic LangGraph title Graph basics text LangGraph supports durable graph workflows")
    imported = search_research_items("durable graph workflows", limit=5)
    imported_id = imported[0].id if imported else ""
    failures += emit(
        "import_note_command_saves_note_under_topic",
        "Imported research note locally" in import_reply and bool(imported_id) and imported[0].topic == "LangGraph" and _clean(import_reply),
        reply=import_reply,
        item=imported[0].as_dict() if imported else None,
    )
    failures += emit("imported_note_is_searchable", bool(imported and "Graph basics" in imported[0].title), results=[item.as_dict() for item in imported])

    other_reply = _reply("research memory import note topic Other title Other note text unrelated local note")
    failures += emit("second_topic_note_saved", "Imported research note locally" in other_reply, reply=other_reply)

    export_all = _reply("research memory export")
    export_files = list((temp_root / "exports").glob("*.json"))
    failures += emit(
        "export_all_creates_json_under_runtime_storage",
        "Exported research memory" in export_all and bool(export_files) and all(path.parent == temp_root / "exports" for path in export_files) and _clean(export_all),
        reply=export_all,
        files=[path.name for path in export_files],
    )

    export_topic = _reply("research memory export topic LangGraph")
    topic_exports = sorted((temp_root / "exports").glob("*langgraph*.json"))
    topic_payload = json.loads(topic_exports[-1].read_text(encoding="utf-8")) if topic_exports else {}
    topics = {item.get("topic") for item in topic_payload.get("items", []) if isinstance(item, dict)}
    failures += emit(
        "export_topic_exports_only_topic",
        "Exported research memory topic LangGraph" in export_topic and topics == {"LangGraph"} and _clean(export_topic),
        reply=export_topic,
        topics=sorted(topics),
    )
    failures += emit("export_output_does_not_reveal_absolute_path", "C:\\" not in export_all + export_topic and "/tmp/" not in export_all + export_topic)

    delete_reply = _reply(f"research memory delete item {imported_id}")
    failures += emit(
        "delete_item_removes_only_that_id",
        "Deleted research memory item" in delete_reply and get_research_item(imported_id) is None and bool(search_research_items("unrelated local note", limit=5)),
        reply=delete_reply,
    )

    missing_delete = _reply("research memory delete item missing-id-123")
    failures += emit("delete_missing_item_is_friendly", "not found" in missing_delete.lower() and _clean(missing_delete), reply=missing_delete)

    clear_refused = _reply("research memory clear topic Other")
    failures += emit("clear_topic_without_confirm_refused", "confirm" in clear_refused.lower() and "did not clear" in clear_refused.lower(), reply=clear_refused)

    _reply("research memory import note topic LangGraph title Keep note text keep this topic")
    clear_confirmed = _reply("research memory clear topic Other confirm")
    failures += emit(
        "clear_topic_with_confirm_clears_only_topic",
        "Cleared research memory topic Other" in clear_confirmed
        and not list_research_items(topic="Other", limit=5)
        and bool(list_research_items(topic="LangGraph", limit=5)),
        reply=clear_confirmed,
    )

    clear_all = _reply("research memory clear all confirm")
    failures += emit("no_clear_all_command_exists", "clear all" in clear_all.lower() and "not supported" in clear_all.lower(), reply=clear_all)

    stats = _reply("research memory stats")
    failures += emit("stats_output_human_readable_path_free", "Research Memory v2 stats" in stats and "Total items:" in stats and _clean(stats), reply=stats)

    secret_reply = _reply("research memory import note topic Security title Token text OPENAI_API_KEY=sk-test12345678901234567890 password: hunter2")
    secret_search = _reply("research memory search Security")
    failures += emit(
        "secret_looking_text_redacted_on_import",
        "Imported research note locally" in secret_reply
        and "redacted" in secret_reply.lower()
        and "sk-test" not in secret_search
        and "hunter2" not in secret_search,
        reply=secret_reply,
        search=secret_search,
    )

    for command, case in (
        ("read my Gmail research emails", "private_gmail_scraping_refused"),
        ("scrape private chat for research", "private_chat_scraping_refused"),
        ("use cookies to access private page", "cookie_scraping_refused"),
        ("bypass login/paywall for research", "paywall_scraping_refused"),
    ):
        state = run_eva_v2_execute(command)
        failures += emit(case, "refused" in state.final_response.lower() and "No real action was executed" in state.final_response, response=state.final_response)

    combined = "\n".join([import_reply, export_all, export_topic, delete_reply, missing_delete, clear_refused, clear_confirmed, clear_all, stats, secret_reply, secret_search])
    failures += emit("outputs_have_no_raw_reprs", _clean(combined))

    print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
