from __future__ import annotations

from .models import ActionClassification


def classify_action(request: str, requested_capability: str | None = None) -> ActionClassification:
    summary = _summarize(request)
    text = f"{request or ''} {requested_capability or ''}".lower()
    capability = _capability_for(text, requested_capability)
    action_class, permission, risk, reason = _classify(text)
    return ActionClassification(
        request_summary=summary,
        action_class=action_class,
        requested_capability=capability,
        permission_class=permission,
        risk_level=risk,
        reason=reason,
    )


def action_classifier_text() -> str:
    return "\n".join(
        [
            "Controlled Execution Gates action classifier",
            "No live LLM call was made.",
            "Execution gates are local/mock policy preview only.",
            "Tools are not executed.",
            "Approval alone does not execute.",
            "Confirmation alone does not execute unless an existing implemented gate accepts it.",
            "Browser/desktop/shell/cloud/MCP/package execution remains locked.",
            "Secrets/config/session data are blocked.",
            "Phase 12L narrow real-create remains a gated write path.",
            "Classification is deterministic string-policy metadata only.",
        ]
    )


def _classify(text: str) -> tuple[str, str, str, str]:
    if any(term in text for term in ("raw worksession", "worksession/private", "private runtime dump", "runtime dump")):
        return ("forbidden_raw_runtime_dump", "blocked_sensitive_runtime", "critical", "Raw private runtime dumps are denied.")
    if any(term in text for term in ("password", "credential", "api key", "secret key", "bearer", "token", "cookie")):
        return ("forbidden_credential_access", "blocked_credential", "critical", "Credential or token access is denied.")
    if any(term in text for term in (".env", "secret", "secrets", "config secret", "browser session", "session data")):
        return ("forbidden_secret_access", "blocked_secret", "critical", "Secret, config, or session access is denied.")
    if any(term in text for term in ("imaginary", "super capability", "super_execute", "hallucinated", "unknown capability")):
        return ("unknown_or_hallucinated_action", "unknown_capability", "high", "Unknown or hallucinated capability is denied.")
    if any(term in text for term in ("run shell", "powershell", "cmd.exe", "terminal command", "execute command", "shell command")):
        return ("forbidden_shell_execution", "blocked_execution", "critical", "Shell execution remains locked.")
    if any(term in text for term in ("pip install", "npm install", "package install", "install package", "apt install")):
        return ("forbidden_package_install", "blocked_execution", "critical", "Package installation remains locked.")
    if any(term in text for term in ("cloud", "mcp", "connector")) and any(term in text for term in ("call", "execute", "run", "control")):
        return ("forbidden_cloud_or_mcp_execution", "blocked_execution", "critical", "Cloud and MCP execution remain locked.")
    if any(term in text for term in ("write arbitrary", "arbitrary source", "overwrite", "delete file", "broad write", "source file")):
        return ("forbidden_arbitrary_file_write", "blocked_file_write", "critical", "Arbitrary file writes remain blocked.")
    if any(term in text for term in ("click browser", "control chrome", "control browser", "browser control", "browser action")):
        return ("forbidden_browser_control", "blocked_execution", "high", "Browser control remains locked.")
    if any(term in text for term in ("control desktop", "type keys", "desktop control", "mouse", "keyboard")):
        return ("forbidden_desktop_control", "blocked_execution", "high", "Desktop control remains locked.")
    if "browser_read." in text:
        return (
            "browser_readonly_observation",
            "readonly_observation",
            "low",
            "Phase 24 permits observation/report output for validated public URLs only.",
        )
    if "desktop_observe." in text:
        return (
            "desktop_observation_only",
            "observation_only",
            "low",
            "Phase 25 permits explicit one-shot redacted desktop observation/report output only.",
        )
    if any(term in text for term in ("phase 12l", "approved new", "real create", "new docs note", ".md", ".txt")) and any(term in text for term in ("create", "real", "approved")):
        return ("existing_phase12l_real_create_candidate", "existing_phase12l_gate", "medium", "Existing narrow Phase 12L candidate recognized without expansion.")
    if any(term in text for term in ("read browser", "browser page", "page someday", "browser read-only", "browser readonly")):
        return ("future_browser_readonly_candidate", "future_gate_locked", "medium", "Future browser read-only candidate is locked.")
    if any(term in text for term in ("observe desktop", "desktop window", "desktop observation")):
        return ("future_desktop_observation_candidate", "future_gate_locked", "medium", "Future desktop observation candidate is locked.")
    if any(term in text for term in ("read a normal project file", "readonly file", "read-only file", "file someday")):
        return ("future_readonly_file_candidate", "future_gate_locked", "medium", "Future read-only file candidate is locked.")
    if "context" in text:
        return ("context_preview", "preview_status", "low", "Context request is preview-only.")
    if "threat" in text or "prompt injection" in text:
        return ("threat_scan_preview", "preview_status", "low", "Threat scan request is preview-only.")
    if "agent loop" in text:
        return ("agent_loop_preview", "preview_status", "low", "Agent Loop request is preview-only.")
    if "workflow" in text:
        return ("workflow_preview", "preview_status", "low", "Workflow request is preview-only.")
    if "fileagent" in text or "draft" in text:
        return ("fileagent_draft_preview", "preview_status", "low", "FileAgent draft request is preview-only.")
    if any(term in text for term in ("status", "report", "policy", "readiness", "approval", "confirmation", "rollback", "what can eva execute")):
        return ("status_or_report", "preview_status", "low", "Status or report request is preview-only.")
    if any(term in text for term in ("preview", "local", "mock")):
        return ("local_preview", "preview_status", "low", "Local preview request is preview-only.")
    return ("requires_clarification", "clarification_needed", "low", "The requested action needs clarification before gate evaluation.")


def _capability_for(text: str, requested_capability: str | None) -> str:
    if requested_capability:
        return requested_capability
    if "execution_gates" in text:
        return "execution_gates.evaluate"
    if "agent loop" in text:
        return "agent_loop.run_preview"
    if "workflow" in text:
        return "workflow_planner.preview"
    if "context" in text:
        return "context.assemble_preview"
    if "threat" in text:
        return "threat.scan_preview"
    if "fileagent" in text:
        return "file.draft_create_preview"
    if "phase 12l" in text or "real create" in text:
        return "file.real_create_new_text_file"
    return "execution_gates.evaluate"


def _summarize(request: str) -> str:
    clean = " ".join(str(request or "").split())
    if not clean:
        return "No execution-gate request supplied."
    if len(clean) <= 220:
        return clean
    return clean[:200].rstrip() + " ... [trimmed]"
