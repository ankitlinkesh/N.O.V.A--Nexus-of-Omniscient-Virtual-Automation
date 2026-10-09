from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

temp_root = Path(tempfile.mkdtemp(prefix="eva_research_memory_ranking_"))
os.environ["EVA_RESEARCH_MEMORY_DB_PATH"] = str(temp_root / "research_memory.sqlite3")
os.environ.pop("EVA_RESEARCH_MEMORY_VECTOR_ENABLED", None)


def emit(case: str, passed: bool, **payload: Any) -> int:
    print(json.dumps({"case": case, "pass": bool(passed), **payload}, indent=2, ensure_ascii=False))
    return 0 if passed else 1


def clean(text: str) -> bool:
    blocked = (
        "{'",
        "ResearchMemoryItem(",
        "ResearchSearchResult(",
        "sqlite3.Row",
        "Traceback",
        "C:\\",
        "/tmp/",
        "backend/eva/data",
        "raw vector",
        "vector_json",
    )
    return bool(str(text).strip()) and not any(marker in str(text) for marker in blocked)


from _nested import run_nested as _shared_run_nested  # noqa: E402


def run_nested(script_name: str) -> tuple[bool, str]:
    # Shared runner: UTF-8 output, one level deep, one timeout (scripts/_nested.py).
    return _shared_run_nested(script_name)


def main() -> int:
    failures = 0

    try:
        from backend.eva.core.fast_commands import maybe_handle_fast_command
        from backend.eva.research_memory.diversity import (
            compute_mmr_score,
            jaccard_similarity,
            rerank_for_diversity,
            tokenize_for_diversity,
        )
        from backend.eva.research_memory.models import ResearchMemoryItem, ResearchSearchResult
        from backend.eva.research_memory.ranking import (
            compute_combined_retrieval_score,
            compute_promotion_score,
            compute_recency_score,
            explain_ranking_factors,
            format_memory_review,
            format_promotion_candidates,
            format_ranking_status,
            format_recall_stats,
        )
        from backend.eva.research_memory.retrieval import format_retrieval_results, retrieve_research
        from backend.eva.research_memory.store import (
            add_research_item,
            get_recall_stats,
            get_top_recalled_items,
            list_research_items,
            record_research_recall,
        )
        from backend.eva.research_memory.vector_index import vector_search_status
        from backend.eva.tools.registry import ToolRegistry
    except Exception as exc:
        failures += emit("ranking_imports", False, error=str(exc))
        print(json.dumps({"overall_pass": False, "failures": failures}, indent=2))
        return 1

    failures += emit("diversity_module_imports", callable(tokenize_for_diversity))
    failures += emit("ranking_module_imports", callable(compute_recency_score))

    tokens = tokenize_for_diversity("Agent planning, planning verifier loops and memory!")
    failures += emit("tokenize_for_diversity_useful", {"agent", "planning", "verifier", "memory"}.issubset(tokens), tokens=sorted(tokens))

    similar = jaccard_similarity(tokenize_for_diversity("agent planning verifier loop"), tokenize_for_diversity("agent planning verifier loops"))
    unrelated = jaccard_similarity(tokenize_for_diversity("agent planning verifier"), tokenize_for_diversity("spotify music playback"))
    failures += emit("jaccard_similarity_expected_shape", similar > 0.55 and unrelated < 0.25, similar=similar, unrelated=unrelated)

    failures += emit("mmr_prefers_relevance_and_diversity", compute_mmr_score(10, 0.1) > compute_mmr_score(10, 0.9))

    now = datetime.now(timezone.utc)
    old = now - timedelta(days=400)
    item_recent = add_research_item(
        ResearchMemoryItem(
            id="",
            topic="Agents",
            title="Agent planning verifier loops",
            summary="Agent planning uses verifier loops, checkpoints, and local task state for safer autonomous work.",
            content_preview="Agent planning uses verifier loops, checkpoints, and local task state for safer autonomous work.",
            source_type="imported_note",
            tags=["agents", "planning"],
            created_at=now.isoformat(),
            quality_score=0.95,
            provenance="ranking_verifier",
        )
    )
    item_old = add_research_item(
        ResearchMemoryItem(
            id="",
            topic="Agents",
            title="Old agent planning note",
            summary="Agent planning uses verifier loops, checkpoints, and local task state for safer autonomous work.",
            content_preview="Agent planning uses verifier loops, checkpoints, and local task state for safer autonomous work.",
            source_type="imported_note",
            tags=["agents", "old"],
            created_at=old.isoformat(),
            quality_score=0.95,
            provenance="ranking_verifier",
        )
    )
    add_research_item(
        ResearchMemoryItem(
            id="",
            topic="Agents",
            title="Duplicate agent planning note",
            summary="Agent planning uses verifier loops, checkpoints, and local task state for safer autonomous work.",
            content_preview="Agent planning uses verifier loops, checkpoints, and local task state for safer autonomous work.",
            source_type="imported_note",
            tags=["agents", "dupe"],
            created_at=now.isoformat(),
            quality_score=0.95,
            provenance="ranking_verifier",
        )
    )
    item_short = add_research_item(
        ResearchMemoryItem(
            id="",
            topic="Tiny",
            title="Tiny",
            summary="agent",
            content_preview="agent",
            source_type="imported_note",
            tags=["tiny"],
            created_at=now.isoformat(),
            quality_score=0.2,
            quality_warnings=["very short note"],
            provenance="ranking_verifier",
        )
    )
    add_research_item(
        ResearchMemoryItem(
            id="",
            topic="Media",
            title="Spotify playback local app",
            summary="Spotify desktop playback uses bounded visible app automation and no web API.",
            content_preview="Spotify desktop playback uses bounded visible app automation and no web API.",
            source_type="imported_note",
            tags=["media"],
            created_at=now.isoformat(),
            quality_score=0.85,
            provenance="ranking_verifier",
        )
    )

    seeded = [
        ResearchSearchResult(id="a", topic="Agents", title="Agent planning verifier loops", summary="Agent planning verifier loops and checkpoints", score=10, reason="fixture"),
        ResearchSearchResult(id="b", topic="Agents", title="Agent planning verifier loop duplicate", summary="Agent planning verifier loops and checkpoints", score=9.8, reason="fixture"),
        ResearchSearchResult(id="c", topic="Media", title="Spotify playback local app", summary="Spotify desktop playback with bounded automation", score=9.2, reason="fixture"),
    ]
    diverse = rerank_for_diversity(seeded, limit=3)
    titles = [item.title for item in diverse]
    failures += emit(
        "rerank_for_diversity_deprioritizes_near_duplicates",
        titles == ["Agent planning verifier loops", "Spotify playback local app", "Agent planning verifier loop duplicate"],
        titles=titles,
    )

    failures += emit("recency_neutral_for_missing_or_invalid", compute_recency_score(None) == 0.5 and compute_recency_score("not-a-date") == 0.5)
    recent_score = compute_recency_score(now.isoformat())
    old_score = compute_recency_score(old.isoformat())
    failures += emit("recent_item_small_boost_over_old", recent_score > old_score and (recent_score - old_score) <= 0.5, recent=recent_score, old=old_score)
    stronger_relevance = compute_combined_retrieval_score(8.0, recency_score=old_score)
    weaker_recent = compute_combined_retrieval_score(3.0, recency_score=recent_score)
    failures += emit("combined_score_keeps_relevance_stronger", stronger_relevance > weaker_recent, stronger=stronger_relevance, weaker=weaker_recent)

    explanation = explain_ranking_factors(item_short, {"base_score": 1, "quality_score": 0.2, "recency_score": recent_score, "low_quality_penalty": 0.4})
    failures += emit(
        "ranking_explanation_human_readable",
        "Deprioritized because quality warnings exist." in explanation and clean(explanation),
        explanation=explanation,
    )

    record_research_recall([item_recent.id, item_old.id], "agent planning verifier")
    record_research_recall([item_recent.id], "agent planning verifier")
    stats = get_recall_stats(item_recent.id)
    failures += emit("recall_stats_table_additive_safe", stats.recall_count >= 2 and len(stats.query_hashes) == 1, stats=stats.as_dict())

    retrieved = retrieve_research("agent planning verifier", limit=3)
    selected_ids = [item.id for item in retrieved.results]
    selected_stats = [get_recall_stats(item_id).recall_count for item_id in selected_ids]
    failures += emit("retrieve_records_recall_stats_for_selected_results", bool(selected_ids) and all(count >= 1 for count in selected_stats), ids=selected_ids, counts=selected_stats)

    recall_output = format_recall_stats(limit=5)
    failures += emit(
        "recall_stats_output_human_readable_no_raw_queries",
        "Research Memory recall stats" in recall_output and "agent planning verifier" not in recall_output and clean(recall_output),
        output=recall_output,
    )
    failures += emit("top_recalled_items_available", bool(get_top_recalled_items(limit=3)))

    promotion_before = len(list_research_items(limit=50))
    promotion = format_promotion_candidates(limit=5)
    promotion_after = len(list_research_items(limit=50))
    failures += emit(
        "promotion_candidates_preview_only",
        "Preview only" in promotion and "No notes were promoted" in promotion and promotion_before == promotion_after and clean(promotion),
        output=promotion,
    )
    failures += emit("promotion_score_deterministic", compute_promotion_score(item_recent) >= compute_promotion_score(item_short))

    ranking_status = format_ranking_status()
    review = format_memory_review()
    failures += emit("ranking_status_human_readable", "lexical-first" in ranking_status.lower() and "diversity reranking" in ranking_status.lower() and clean(ranking_status), output=ranking_status)
    failures += emit("review_memory_human_readable", "Research Memory review" in review and "Suggested safe next commands" in review and clean(review), output=review)

    formatted = format_retrieval_results(retrieved)
    failures += emit(
        "retrieval_output_includes_ranking_reasons",
        "Match:" in formatted and ("Small recency boost." in formatted or "Boosted by quality score." in formatted) and clean(formatted),
        output=formatted,
    )
    failures += emit("vector_search_remains_disabled_default", not vector_search_status().enabled)

    commands = {
        "research memory ranking status": "Research Memory ranking status",
        "research memory recall stats": "Research Memory recall stats",
        "research memory promote candidates": "Research Memory promotion candidates",
        "research memory review memory": "Research Memory review",
    }
    tools = ToolRegistry()
    for command, expected in commands.items():
        result = maybe_handle_fast_command(command, tools, {})
        text = str(result[0] if result else "")
        failures += emit(f"fast_command_{command.replace(' ', '_')}", result is not None and expected in text and clean(text), output=text)

    source_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace").lower()
        for path in (ROOT / "backend" / "eva" / "research_memory").rglob("*.py")
    )
    failures += emit("no_memos_import_or_dependency", "import memos" not in source_text and "from memos" not in source_text and "sqlite-vec" not in source_text and "redis" not in source_text)
    failures += emit("no_background_or_cloud_enablement", "import watchdog" not in source_text and "background_dream" not in source_text and "cloud_embedding_client" not in source_text)

    outputs = "\n".join([recall_output, promotion, ranking_status, review, formatted])
    failures += emit("outputs_no_raw_dict_repr", "{'" not in outputs)
    failures += emit("outputs_no_dataclass_repr", "ResearchMemoryItem(" not in outputs and "ResearchSearchResult(" not in outputs)
    failures += emit("outputs_no_sqlite_row_repr", "sqlite3.Row" not in outputs)
    failures += emit("outputs_no_internal_absolute_paths", "C:\\" not in outputs and "/tmp/" not in outputs)
    failures += emit("outputs_no_raw_vectors", "raw vector" not in outputs.lower() and "vector_json" not in outputs.lower())

    nested_scripts = [
        "verify_eva_research_memory_retrieval.py",
        "verify_eva_research_memory_quality.py",
        "verify_eva_research_memory_vectors.py",
        "verify_eva_research_memory_help.py",
        "verify_eva_capabilities.py",
        "verify_eva_capability_permissions.py",
        "verify_eva_stabilization_v1.py",
    ]
    if os.environ.get("EVA_VERIFY_SKIP_NESTED") == "1":
        for script_name in nested_scripts:
            failures += emit(f"nested_{script_name}", True, skipped=True, reason="Skipped inside master verifier profile.")
    else:
        for script_name in nested_scripts:
            ok, tail = run_nested(script_name)
            failures += emit(f"nested_{script_name}", ok, tail=tail)

    print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
