from .freshness import freshness_policy_text
from .mock_feeds import build_mock_dashboard
from .news_policy import BOUNDARIES, news_policy_text
from .source_policy import source_policy_text
from .status import get_news_dashboard_status
from .topic_model import topic_model_text
def _out(title: str, body: str) -> str: return "\n".join((title, body, "", *BOUNDARIES))
def format_news_status() -> str:
    s=get_news_dashboard_status(); return _out("News / Web Intelligence status", f"Backend: {s.backend_mode}; a live public-RSS view is available with `eva news live`\nReadiness: {s.readiness}\nBuilt in Phase 27; live feeds added in Phase 155.")
def format_news_policy() -> str: return _out("News policy", news_policy_text()+"\n"+source_policy_text())
def format_news_dashboard(topic: str="world events") -> str:
    d=build_mock_dashboard(topic); body=f"Topic: {d.topic}\nSources: {len(d.source_cards)}\nEvents: {len(d.event_cards)}\nFreshness: {', '.join(d.freshness_labels)}\nUncertainty: {d.uncertainty_notes[0]}"; return _out("News / Web Intelligence Dashboard", body)
def format_news_topics() -> str: return _out("News topics", topic_model_text())
def format_news_sources() -> str:
    d=build_mock_dashboard(); return _out("News sources and reliability", "\n".join(f"- {s.source_title}: {s.reliability_note}; {s.citation_metadata}" for s in d.source_cards))
def format_news_freshness() -> str: return _out("News freshness", freshness_policy_text())
def format_news_safety_report() -> str: return _out("News safety report", "Public URLs only. Crawler, authentication, sessions, browser control, tools, and background monitoring are blocked.")
def format_news_readiness() -> str: return _out("News readiness", "Phase 27 is complete as a deterministic dashboard/report/status foundation.\nNext phase: Phase 28 Coding Specialist / CodingAgent.")
