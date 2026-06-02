from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .io import import_research_note
from .store import list_research_items


@dataclass(frozen=True)
class DemoImportResult:
    imported_count: int
    skipped_count: int
    topic_count: int


def import_demo_research_pack() -> DemoImportResult:
    sample_path = _sample_path()
    payload = json.loads(sample_path.read_text(encoding="utf-8"))
    notes = payload.get("notes") if isinstance(payload, dict) else []
    existing_keys = {
        (item.topic.strip().lower(), item.title.strip().lower())
        for item in list_research_items(limit=5000)
        if item.provenance == "demo_fake_public_release_pack"
    }
    imported = 0
    skipped = 0
    topics: set[str] = set()
    for note in notes:
        if not isinstance(note, dict):
            continue
        topic = str(note.get("topic") or "Eva demo").strip()
        title = str(note.get("title") or topic).strip()
        text = str(note.get("text") or "").strip()
        tags = note.get("tags")
        key = (topic.lower(), title.lower())
        topics.add(topic)
        if key in existing_keys:
            skipped += 1
            continue
        item = import_research_note(topic=topic, title=title, text=text, tags=tags)
        from .store import add_research_item
        from .models import ResearchMemoryItem

        add_research_item(
            ResearchMemoryItem(
                id=item.id,
                topic=item.topic,
                title=item.title,
                summary=item.summary,
                content_preview=item.content_preview,
                source_type="demo_note",
                source_url=None,
                source_domain=None,
                tags=item.tags,
                created_at=item.created_at,
                updated_at=item.updated_at,
                confidence=item.confidence,
                private=False,
                redacted=item.redacted,
                provenance="demo_fake_public_release_pack",
                content_hash=item.content_hash,
                quality_score=item.quality_score,
                quality_warnings=item.quality_warnings,
            )
        )
        imported += 1
        existing_keys.add(key)
    return DemoImportResult(imported_count=imported, skipped_count=skipped, topic_count=len(topics))


def format_demo_import_result(result: DemoImportResult) -> str:
    return "\n".join(
        [
            "Imported Research Memory demo pack.",
            f"Imported notes: {result.imported_count}.",
            f"Skipped existing demo notes: {result.skipped_count}.",
            f"Demo topics covered: {result.topic_count}.",
            "Source: fake public demo notes only.",
            "Safety: local import only; no network, cloud, browser, MCP, Playwright, or PyAutoGUI action was used.",
        ]
    )


def _sample_path() -> Path:
    return Path(__file__).resolve().parents[3] / "samples" / "research_memory" / "eva_demo_notes.json"
