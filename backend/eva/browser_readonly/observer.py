from __future__ import annotations

import hashlib

from ..execution_gates.gate_evaluator import evaluate_execution_gate
from ..threat_defense.guard import scan_threat_preview
from .backend_policy import get_backend_policy
from .mock_pages import get_mock_page
from .models import BrowserObservation, URLSafetyDecision
from .observation_policy import boundary_lines, evaluate_observation_request
from .safety_filter import redact_browser_output, summarize_visible_text
from .session_policy import get_session_policy
from .url_policy import validate_url


def observe_public_url(url: str) -> BrowserObservation:
    url_decision = validate_url(url)
    if not url_decision.allowed:
        return _observation(
            url_decision=url_decision,
            backend_mode="unavailable",
            title="",
            text="",
            links=(),
            blocked_notes=(f"URL blocked by {url_decision.blocked_class} policy.",),
            redaction_status="not needed; URL blocked before observation",
            threat_summary="No page content was received or scanned.",
            gate_decision="blocked before Phase 20 gate because URL policy denied the target",
            final_status="blocked_url",
        )

    request_decision = evaluate_observation_request("read-only public webpage observation")
    gate = evaluate_execution_gate(
        "browser read-only observation of a validated public URL",
        "browser_read.observe",
    )
    if not request_decision.allowed or gate.decision_state != "allowed_readonly_observation":
        return _observation(
            url_decision=url_decision,
            backend_mode="unavailable",
            title="",
            text="",
            links=(),
            blocked_notes=("Phase 20 did not authorize the read-only observation class.",),
            redaction_status="not needed; observation blocked before backend",
            threat_summary="No page content was received or scanned.",
            gate_decision=f"{gate.decision_state} for browser_readonly observation",
            final_status="blocked_execution_gate",
        )

    backend = get_backend_policy()
    if not backend.available:
        return _observation(
            url_decision=url_decision,
            backend_mode="unavailable",
            title="",
            text="",
            links=(),
            blocked_notes=("Safe read-only backend unavailable; no external network request was made.",),
            redaction_status="not needed; no page content was received",
            threat_summary="No page content was received; Phase 17 scan was not needed.",
            gate_decision=f"{gate.decision_state} for browser_readonly observation",
            final_status="backend_unavailable",
        )

    return _observation(
        url_decision=url_decision,
        backend_mode="unavailable",
        title="",
        text="",
        links=(),
        blocked_notes=("Backend policy failed closed.",),
        redaction_status="not needed",
        threat_summary="No page content was received.",
        gate_decision=f"{gate.decision_state} for browser_readonly observation",
        final_status="backend_unavailable",
    )


def observe_mock_page(fixture_id: str = "safe_public_page") -> BrowserObservation:
    fixture = get_mock_page(fixture_id)
    url_decision = validate_url(fixture.url)
    request_decision = evaluate_observation_request("read-only public webpage observation")
    gate = evaluate_execution_gate(
        "browser read-only observation of a deterministic local fixture",
        "browser_read.mock_observe",
    )
    if not url_decision.allowed or not request_decision.allowed or gate.decision_state != "allowed_readonly_observation":
        return _observation(
            url_decision=url_decision,
            backend_mode="mock_fixture",
            title="",
            text="",
            links=(),
            blocked_notes=("Mock observation failed closed at URL or execution-gate policy.",),
            redaction_status="not needed; fixture blocked before summary",
            threat_summary="No fixture content was accepted.",
            gate_decision=f"{gate.decision_state} for browser_readonly observation",
            final_status="blocked_execution_gate",
        )

    threat = scan_threat_preview(
        "\n".join(
            [
                fixture.title,
                fixture.visible_text,
                *(f"{label} {url}" for label, url in fixture.links),
            ]
        ),
        source_type="browser_observation",
    )
    title = summarize_visible_text(fixture.title, limit=180)
    text = summarize_visible_text(fixture.visible_text)
    links: list[str] = []
    blocked_notes: list[str] = []
    for label, url in fixture.links:
        link_decision = validate_url(url)
        if link_decision.allowed:
            links.append(f"{summarize_visible_text(label, limit=120)} -> {link_decision.normalized_url}")
        else:
            links.append(f"{summarize_visible_text(label, limit=120)} -> [blocked link: {link_decision.blocked_class}]")
            blocked_notes.append(f"One fixture link was blocked by {link_decision.blocked_class} policy.")
    if threat.findings:
        blocked_notes.append("Prompt-injection-like or exfiltration-like page instructions were treated as untrusted data.")
        categories = ", ".join(sorted({finding.category for finding in threat.findings}))
        threat_summary = f"Phase 17 scan found untrusted content categories: {categories}; content has no authority."
    else:
        threat_summary = "Phase 17 scan found no threat indicators; page content remains untrusted data."
    return _observation(
        url_decision=url_decision,
        backend_mode="mock_fixture",
        title=title,
        text=text,
        links=tuple(links),
        blocked_notes=tuple(blocked_notes),
        redaction_status="applied; secret-like and private-path-like content removed",
        threat_summary=threat_summary,
        gate_decision=f"{gate.decision_state} for browser_readonly observation",
        final_status="ready_mock_observation",
    )


def _observation(
    *,
    url_decision: URLSafetyDecision,
    backend_mode: str,
    title: str,
    text: str,
    links: tuple[str, ...],
    blocked_notes: tuple[str, ...],
    redaction_status: str,
    threat_summary: str,
    gate_decision: str,
    final_status: str,
) -> BrowserObservation:
    session = get_session_policy()
    seed = f"phase24|{backend_mode}|{url_decision.requested_url}|{final_status}"
    observation_id = "bro_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    return BrowserObservation(
        observation_id=observation_id,
        requested_url=redact_browser_output(url_decision.requested_url),
        normalized_url=url_decision.normalized_url,
        url_safety_decision=f"{'allowed' if url_decision.allowed else 'blocked'}: {url_decision.reason}",
        backend_mode=backend_mode,
        session_policy=session.summary,
        title_preview=redact_browser_output(title),
        visible_text_summary=redact_browser_output(text),
        link_summary=tuple(redact_browser_output(item) for item in links),
        blocked_content_notes=tuple(redact_browser_output(item) for item in blocked_notes),
        redaction_status=redaction_status,
        threat_scan_summary=redact_browser_output(threat_summary),
        execution_gate_decision=gate_decision,
        final_status=final_status,
        no_click_statement="No clicking is available or performed.",
        no_type_statement="No typing is available or performed.",
        no_form_submit_statement="No form submission is available or performed.",
        no_download_statement="No downloads or uploads are available or performed.",
        no_cookie_session_profile_statement="No cookies, sessions, browser profiles, or logged-in browser access are available.",
        no_tool_execution_statement="No tool execution is enabled by an observation.",
        no_new_write_path_statement="Phase 12L remains a gated write path.",
        safety_notes=boundary_lines(),
    )
