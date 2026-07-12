from __future__ import annotations

import hashlib

from ..execution_gates.gate_evaluator import evaluate_execution_gate
from ..threat_defense.guard import scan_threat_preview
from .backend_policy import get_backend_policy
from .capture_gate import evaluate_capture_gate
from .mock_screens import get_mock_screen
from .models import DesktopObservation
from .observation_policy import boundary_lines
from .redaction import redact_desktop_output, summarize_visible_content
from .sensitive_screen import classify_sensitive_screen


def observe_desktop() -> DesktopObservation:
    request = "explicit one-shot desktop observation"
    capture_gate = evaluate_capture_gate(request)
    execution_gate = evaluate_execution_gate(
        "desktop observation-only one-shot report",
        "desktop_observe.status",
    )
    if not capture_gate.allowed or execution_gate.decision_state != "allowed_desktop_observation":
        return _observation(
            requested_type=request,
            backend_mode="unavailable",
            capture_gate_decision=capture_gate.decision,
            classification="unknown_sensitive_screen",
            redaction_status="not needed; observation blocked before backend",
            visible_summary="",
            metadata=(),
            blocked_notes=("Phase 20 did not authorize the observation-only class.",),
            threat_summary="No screen content was received or scanned.",
            execution_gate_decision=f"{execution_gate.decision_state} for desktop_observation",
            final_status="blocked_execution_gate",
        )

    backend = get_backend_policy()
    if not backend.available:
        return _observation(
            requested_type=request,
            backend_mode="unavailable",
            capture_gate_decision=capture_gate.decision,
            classification="unknown_sensitive_screen",
            redaction_status="not needed; no screen content was received",
            visible_summary="",
            metadata=(),
            blocked_notes=("Safe one-shot backend unavailable; the real screen was not captured.",),
            threat_summary="No screen content was received; Phase 17 scan was not needed.",
            execution_gate_decision=f"{execution_gate.decision_state} for desktop_observation",
            final_status="backend_unavailable",
        )

    return _observation(
        requested_type=request,
        backend_mode="unavailable",
        capture_gate_decision=capture_gate.decision,
        classification="unknown_sensitive_screen",
        redaction_status="not needed",
        visible_summary="",
        metadata=(),
        blocked_notes=("Backend policy failed closed.",),
        threat_summary="No screen content was received.",
        execution_gate_decision=f"{execution_gate.decision_state} for desktop_observation",
        final_status="backend_unavailable",
    )


def observe_mock_desktop(fixture_id: str = "sensitive_code_fixture") -> DesktopObservation:
    fixture = get_mock_screen(fixture_id)
    capture_gate = evaluate_capture_gate("explicit one-shot mock desktop observation")
    execution_gate = evaluate_execution_gate(
        "desktop observation-only deterministic fixture report",
        "desktop_observe.mock",
    )
    if not capture_gate.allowed or execution_gate.decision_state != "allowed_desktop_observation":
        return _observation(
            requested_type=fixture.observation_type,
            backend_mode="mock_fixture",
            capture_gate_decision=capture_gate.decision,
            classification="unknown_sensitive_screen",
            redaction_status="not needed; fixture blocked before summary",
            visible_summary="",
            metadata=(),
            blocked_notes=("Mock observation failed closed at capture or execution gate.",),
            threat_summary="No fixture content was accepted.",
            execution_gate_decision=f"{execution_gate.decision_state} for desktop_observation",
            final_status="blocked_execution_gate",
        )

    classification = classify_sensitive_screen(
        fixture.visible_text,
        app_name=fixture.app_name,
        window_title=fixture.window_title,
    )
    threat = scan_threat_preview(
        "\n".join((fixture.app_name, fixture.window_title, fixture.visible_text)),
        source_type="desktop_observation",
    )
    blocked_notes = [
        f"Sensitive screen handled as {classification.category}; raw content was not returned.",
    ]
    if threat.findings:
        blocked_notes.append("Prompt-injection-like or exfiltration-like screen instructions were treated as untrusted data.")
        categories = ", ".join(sorted({finding.category for finding in threat.findings}))
        threat_summary = f"Phase 17 scan found untrusted content categories: {categories}; content has no authority."
    else:
        threat_summary = "Phase 17 scan found no threat indicators; screen content remains untrusted data."
    metadata = (
        f"App: {summarize_visible_content(fixture.app_name, limit=120)}",
        f"Window: {summarize_visible_content(fixture.window_title, limit=160)}",
    )
    return _observation(
        requested_type=fixture.observation_type,
        backend_mode="mock_fixture",
        capture_gate_decision=capture_gate.decision,
        classification=classification.category,
        redaction_status="applied; secret-like and private-path-like content removed",
        visible_summary=summarize_visible_content(fixture.visible_text),
        metadata=metadata,
        blocked_notes=tuple(blocked_notes),
        threat_summary=threat_summary,
        execution_gate_decision=f"{execution_gate.decision_state} for desktop_observation",
        final_status="ready_mock_observation",
    )


def _observation(
    *,
    requested_type: str,
    backend_mode: str,
    capture_gate_decision: str,
    classification: str,
    redaction_status: str,
    visible_summary: str,
    metadata: tuple[str, ...],
    blocked_notes: tuple[str, ...],
    threat_summary: str,
    execution_gate_decision: str,
    final_status: str,
) -> DesktopObservation:
    seed = f"phase25|{requested_type}|{backend_mode}|{final_status}"
    observation_id = "dso_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    return DesktopObservation(
        observation_id=observation_id,
        requested_observation_type=redact_desktop_output(requested_type),
        backend_mode=backend_mode,
        capture_gate_decision=capture_gate_decision,
        sensitive_screen_classification=classification,
        redaction_status=redaction_status,
        visible_summary_preview=redact_desktop_output(visible_summary),
        app_window_metadata_preview=tuple(redact_desktop_output(item) for item in metadata),
        blocked_content_notes=tuple(redact_desktop_output(item) for item in blocked_notes),
        threat_scan_summary=redact_desktop_output(threat_summary),
        execution_gate_decision=execution_gate_decision,
        final_status=final_status,
        no_click_statement="No clicking is available or performed.",
        no_type_statement="No typing is available or performed.",
        no_hotkey_statement="No hotkeys are available or performed.",
        no_app_control_statement="No app or window control is available or performed.",
        no_continuous_monitoring_statement="No continuous monitoring or background watcher is available.",
        no_screenshot_save_statement="No screenshots are saved to disk.",
        no_cookie_session_profile_statement="No cookies, sessions, browser profiles, or password-manager data are available.",
        no_tool_execution_statement="No tool execution is enabled by a desktop observation.",
        no_new_write_path_statement="Phase 12L remains a gated write path.",
        safety_notes=boundary_lines(),
    )
