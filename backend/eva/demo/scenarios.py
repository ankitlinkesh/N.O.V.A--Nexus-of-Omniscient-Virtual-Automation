from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DemoScenario:
    scenario_id: str
    title: str
    fake_user_request: str
    expected_intent: str
    selected_agent: str
    safety_decision: str
    resource_decision: str
    proposed_plan: tuple[str, ...]
    final_result: str


_SCENARIOS: tuple[DemoScenario, ...] = (
    DemoScenario(
        scenario_id="open-chatgpt",
        title="Open ChatGPT safely",
        fake_user_request="open ChatGPT on Chrome",
        expected_intent="browser.open_web_app",
        selected_agent="BrowserAgent",
        safety_decision="allowed demo plan; public mode does not submit prompts",
        resource_decision="Chrome skill cataloged; no cookies or localStorage are read",
        proposed_plan=("Open Chrome to chatgpt.com", "Verify public domain if available", "Stop without typing private content"),
        final_result="Demo would report that ChatGPT is open, without submitting anything.",
    ),
    DemoScenario(
        scenario_id="research-memory",
        title="Recall local Research Memory",
        fake_user_request="research memory retrieve MCP",
        expected_intent="research_memory.retrieve",
        selected_agent="ResearchAgent",
        safety_decision="allowed read-only local retrieval",
        resource_decision="Research Memory v2 local runtime store only",
        proposed_plan=("Search saved local notes lexically", "Rank topic/tag/source matches", "Return sanitized summaries"),
        final_result="Demo would show local saved research snippets if demo notes were imported.",
    ),
    DemoScenario(
        scenario_id="whatsapp-confirmation",
        title="WhatsApp send confirmation",
        fake_user_request="send WhatsApp to mom saying hi",
        expected_intent="message.send.whatsapp",
        selected_agent="SafetyAgent",
        safety_decision="confirmation required; public mode refuses real send",
        resource_decision="WhatsApp automation is not executed in public demo mode",
        proposed_plan=("Prepare a pending action", "Show exact recipient and message", "Require explicit confirmation", "Still do not send in public mode"),
        final_result="Demo shows the confirmation gate and leaves the message unsent.",
    ),
    DemoScenario(
        scenario_id="unsafe-env-request",
        title="Secret-file refusal",
        fake_user_request="read .env.local",
        expected_intent="secret_access",
        selected_agent="SafetyAgent",
        safety_decision="hard block",
        resource_decision="No resource is allowed to read secrets",
        proposed_plan=("Detect secret-file request", "Refuse", "Suggest checking public setup docs instead"),
        final_result="Demo refuses to read secret files.",
    ),
    DemoScenario(
        scenario_id="delete-downloads-refusal",
        title="Destructive file refusal",
        fake_user_request="delete Downloads folder",
        expected_intent="destructive_file_action",
        selected_agent="SafetyAgent",
        safety_decision="override required; public mode refuses destructive execution",
        resource_decision="File delete executor is unavailable in public demo mode",
        proposed_plan=("Classify as destructive", "Explain checkpoint/override policy", "Do not delete anything"),
        final_result="Demo shows the refusal and no file operation runs.",
    ),
    DemoScenario(
        scenario_id="github-mcp-refusal",
        title="GitHub MCP write refusal",
        fake_user_request="use GitHub MCP to merge PR",
        expected_intent="mcp.repo_write",
        selected_agent="SafetyAgent",
        safety_decision="public mode refuses repo write/MCP execution",
        resource_decision="GitHub MCP is cataloged but disabled by default",
        proposed_plan=("Detect MCP write request", "Check resource policy", "Refuse execution"),
        final_result="Demo explains that MCP is cataloged only and no merge runs.",
    ),
    DemoScenario(
        scenario_id="vector-search-disabled",
        title="Vector search disabled",
        fake_user_request="research memory semantic search Eva",
        expected_intent="research_memory.vector_search",
        selected_agent="ResearchAgent",
        safety_decision="safe status path; vector search remains disabled by default",
        resource_decision="Research Memory vector interface is experimental and disabled",
        proposed_plan=("Check vector status", "Refuse vector indexing/search when disabled", "Suggest lexical retrieval"),
        final_result="Demo suggests Research Memory lexical search/retrieve instead.",
    ),
)


def list_demo_scenarios() -> list[DemoScenario]:
    return list(_SCENARIOS)


def get_demo_scenario(scenario_id: str) -> DemoScenario | None:
    wanted = str(scenario_id or "").strip().lower()
    for scenario in _SCENARIOS:
        if scenario.scenario_id == wanted:
            return scenario
    return None
