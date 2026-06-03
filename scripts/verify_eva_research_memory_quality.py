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
    temp_root = Path(tempfile.mkdtemp(prefix="eva_research_memory_quality_"))
    os.environ["EVA_RESEARCH_MEMORY_DB_PATH"] = str(temp_root / "research_memory.sqlite3")
    os.environ.setdefault("EVA_PENDING_ACTION_LEDGER_PATH", str(temp_root / "pending_actions.jsonl"))

    from backend.eva.research_memory.io import export_research_memory
    from backend.eva.research_memory.store import get_research_item, search_research_items

    failures = 0

    old_save = _reply("save research note LangGraph: Graph agents can route tasks through nodes")
    old_import = _reply("research memory import note topic LangGraph title Old import text old import still works")
    failures += emit("existing_save_import_without_tags_still_work", "Saved research note locally" in old_save and "Imported research note locally" in old_import, save=old_save, imported=old_import)

    tagged_import = _reply("research memory import note topic LangGraph title Tagged Note tags Agents, Graph, agents text LangGraph tag filtering works")
    tagged = search_research_items("tag filtering", limit=5)[0]
    failures += emit(
        "import_with_tags_saves_normalized_tags",
        "Imported research note locally" in tagged_import and tagged.tags == ["agents", "graph"],
        reply=tagged_import,
        item=tagged.as_dict(),
    )

    tagged_save = _reply("research memory save topic LangGraph tags Planner,Agents note Planner tags are searchable")
    saved = search_research_items("Planner tags", limit=5)[0]
    failures += emit(
        "save_with_tags_saves_normalized_tags",
        "Saved research note locally" in tagged_save and "planner" in saved.tags and "agents" in saved.tags,
        reply=tagged_save,
        item=saved.as_dict(),
    )

    tags = _reply("research memory tags")
    failures += emit("tags_command_shows_counts", "agents:" in tags.lower() and "graph:" in tags.lower() and _clean(tags), reply=tags)

    topic_search = _reply("research memory search tag filtering topic LangGraph")
    tag_search = _reply("research memory search tag filtering tag agents")
    source_search = _reply("research memory search tag filtering source imported_note")
    failures += emit("search_by_topic_works", "Tagged Note" in topic_search and "Topic: LangGraph" in topic_search and _clean(topic_search), reply=topic_search)
    failures += emit("search_by_tag_works", "Tagged Note" in tag_search and "agents" in tag_search.lower() and _clean(tag_search), reply=tag_search)
    failures += emit("search_by_source_type_works", "Tagged Note" in source_search and "Type: imported_note" in source_search and _clean(source_search), reply=source_search)

    dup_a = _reply("research memory import note topic Dupes title Same tags dup text duplicate content for hashing")
    dup_b = _reply("research memory import note topic Dupes title Same tags dup text duplicate content for hashing")
    near = _reply("research memory import note topic Dupes title Similar tags dup text duplicate content for hashing plus tiny variation")
    failures += emit("duplicate_fixture_created", all("Imported research note locally" in text for text in (dup_a, dup_b, near)), replies=[dup_a, dup_b, near])

    duplicates = _reply("research memory duplicates")
    failures += emit("exact_duplicate_detection_works", "Exact duplicate" in duplicates and "Same" in duplicates and _clean(duplicates), reply=duplicates)
    failures += emit("near_duplicate_preview_works_or_graceful", ("Near duplicate" in duplicates or "near-duplicate preview is exact-only" in duplicates.lower()) and _clean(duplicates), reply=duplicates)

    short = _reply("research memory import note topic Quality title Tiny text ok")
    url_only = _reply("research memory import note topic Quality title URL text https://example.com https://example.org")
    quality = _reply("research memory quality")
    failures += emit("quality_flags_very_short_notes", "very short" in quality.lower() and _clean(quality), reply=quality, short=short)
    failures += emit("quality_flags_duplicate_like_notes", "duplicate" in quality.lower() and _clean(quality), reply=quality)
    failures += emit("quality_flags_url_only_notes", "mostly urls" in quality.lower() and _clean(quality), reply=quality, url_only=url_only)

    before_count = len(search_research_items("duplicate content", limit=20))
    merge_preview = _reply("research memory merge duplicates preview")
    after_count = len(search_research_items("duplicate content", limit=20))
    failures += emit("merge_duplicates_preview_does_not_delete", before_count == after_count and "preview" in merge_preview.lower() and _clean(merge_preview), reply=merge_preview)

    secret = _reply("research memory save topic Security tags secret note OPENAI_API_KEY=sk-test12345678901234567890 password: hunter2")
    secret_search = _reply("research memory search Security tag secret")
    failures += emit(
        "secret_text_redacted_before_hashing_and_output",
        "redacted" in secret.lower() and "sk-test" not in secret_search and "hunter2" not in secret_search and _clean(secret_search),
        reply=secret,
        search=secret_search,
    )

    export = export_research_memory()
    failures += emit("export_still_works_after_schema_change", export.item_count >= 1 and export.filename.endswith(".json"), export=export.__dict__)

    delete_target = search_research_items("old import still works", limit=5)[0]
    delete_reply = _reply(f"research memory delete item {delete_target.id}")
    failures += emit("delete_exact_item_still_works", "Deleted research memory item" in delete_reply and get_research_item(delete_target.id) is None, reply=delete_reply)

    clear_reply = _reply("research memory clear topic Quality confirm")
    failures += emit("clear_topic_confirm_still_works", "Cleared research memory topic Quality" in clear_reply and _clean(clear_reply), reply=clear_reply)

    combined = "\n".join([old_save, old_import, tagged_import, tagged_save, tags, topic_search, tag_search, source_search, duplicates, quality, merge_preview, secret, secret_search, delete_reply, clear_reply])
    failures += emit("outputs_clean_no_raw_reprs_or_paths", _clean(combined))

    print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
