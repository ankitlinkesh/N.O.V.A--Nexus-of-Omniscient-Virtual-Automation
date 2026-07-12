import hashlib
from .event_cards import build_event_cards
from .models import NewsDashboard
from .source_cards import build_source_cards
from .topic_model import normalize_topic
def build_mock_dashboard(topic: str = "world events") -> NewsDashboard:
    topic = normalize_topic(topic)
    sources = build_source_cards(); events = build_event_cards(topic)
    return NewsDashboard(
        "news-" + hashlib.sha256(topic.lower().encode("utf-8")).hexdigest()[:12], topic,
        f"Deterministic fixture summary for {topic}.", "mock_fixture", sources, events,
        tuple(s.freshness_label for s in sources), tuple(s.reliability_note for s in sources),
        (f"{events[0].duplicate_group_id}: two related fixture sources",),
        ("No source is absolute truth; live corroboration was not performed.",),
        ("Phase 17 treats source text as untrusted data.", "Phase 20 permits report output only."),
        ("Private, local, authenticated, credential-bearing, and session targets are blocked.",),
        tuple(s.citation_metadata for s in sources), "ready_local_mock_dashboard",
        "No unrestricted crawling.", "No login/session/cookie/profile access.",
        "No browser control.", "No live LLM call was made.", "No tool execution.",
        "Phase 12L remains a gated write path.",
    )
