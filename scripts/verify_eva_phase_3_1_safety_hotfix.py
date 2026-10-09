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


def emit(case: str, passed: bool, **payload: Any) -> int:
    ok = bool(passed)
    print(json.dumps({"case": case, "pass": ok, **payload}, indent=2, ensure_ascii=False))
    return 0 if ok else 1


def _fast(command: str) -> str:
    from backend.eva.core.fast_commands import maybe_handle_fast_command
    from backend.eva.tools.registry import ToolRegistry

    handled = maybe_handle_fast_command(command, ToolRegistry(), {})
    return handled[0] if handled else ""


def _capability_reply(message: str, session: dict[str, Any] | None = None) -> tuple[dict[str, Any], str, str]:
    from backend.eva.api import routes
    from backend.eva.core.intent_router import classify_capability_intent

    context = session if session is not None else {}
    classification = classify_capability_intent(message, context)
    handled = routes._handle_capability_route(message, classification, context, None, "verify")
    reply, source = handled if handled else ("", "")
    return classification, reply, source


def _clean(text: str) -> bool:
    return "{'" not in text and "EvaResource(" not in text and "EvaRuntimeState(" not in text


def main() -> int:
    failures = 0
    os.environ.setdefault("EVA_PENDING_ACTION_LEDGER_PATH", str(Path(tempfile.mkdtemp(prefix="eva_pending_")) / "pending_actions.jsonl"))

    from backend.eva.resources.registry import evaluate_resource_by_id, get_resource
    from backend.eva.resources.status import format_resource_detail

    github = format_resource_detail("github-mcp-server")
    playwright = format_resource_detail("playwright-mcp")
    official = format_resource_detail("official-mcp-servers-registry")
    docker = format_resource_detail("docker-mcp-registry")
    awesome = format_resource_detail("awesome-mcp-servers")
    chrome = format_resource_detail("eva-chrome-execution-skills")

    failures += emit("github_detail_no_allowed_now_yes", "Allowed now: yes" not in github, text=github)
    failures += emit("github_detail_executable_now_no", "Executable now: no" in github, text=github)
    failures += emit(
        "github_mcp_experimental_default_disabled",
        (get_resource("github-mcp-server") or None) is not None
        and get_resource("github-mcp-server").status == "experimental"
        and not get_resource("github-mcp-server").default_enabled,
        decision=evaluate_resource_by_id("github-mcp-server").as_dict(),
    )
    failures += emit("playwright_mcp_executable_now_no", "Executable now: no" in playwright, text=playwright)
    failures += emit(
        "reference_only_mcp_executable_now_no",
        all("Executable now: no" in text and "Registry status: reference_only" in text for text in (official, docker, awesome)),
        official=official,
        docker=docker,
        awesome=awesome,
    )
    failures += emit("internal_chrome_resource_executable", "Executable now: yes" in chrome and "Cataloged: yes" in chrome, text=chrome)
    failures += emit("resource_detail_clean", all(_clean(text) for text in (github, playwright, official, docker, awesome, chrome)))

    session: dict[str, Any] = {}
    first_classification, first_reply, first_source = _capability_reply("send WhatsApp to mom saying hi", session)
    first_lower = first_reply.lower()
    failures += emit(
        "normal_whatsapp_send_not_sent",
        first_classification.get("capability") == "message_workflow"
        and "sent" not in first_lower.replace("not send", "")
        and ("confirmation" in first_lower or "draft" in first_lower or "will not send" in first_lower),
        classification=first_classification,
        reply=first_reply,
        source=first_source,
    )

    web_classification, web_reply, web_source = _capability_reply("open whatsapp web on chrome and send hi to kuttyy", {})
    web_lower = web_reply.lower()
    failures += emit(
        "whatsapp_web_open_and_send_routes_message_workflow",
        web_classification.get("capability") == "message_workflow"
        and web_classification.get("suggested_route") == "whatsapp_message_prepare"
        and web_classification.get("recipient") == "kuttyy"
        and web_classification.get("message") == "hi"
        and web_classification.get("requested_web") is True
        and "did not send" in web_lower
        and "confirmation" in web_lower
        and "manually" not in web_lower,
        classification=web_classification,
        reply=web_reply,
        source=web_source,
    )

    follow_classification, follow_reply, follow_source = _capability_reply("open and send the message", session)
    follow_lower = follow_reply.lower()
    failures += emit(
        "open_and_send_followup_does_not_send",
        follow_classification.get("capability") == "message_workflow"
        and ("did not send" in follow_lower or "sending requires" in follow_lower)
        and "sent it" not in follow_lower,
        classification=follow_classification,
        reply=follow_reply,
        source=follow_source,
    )

    empty_session: dict[str, Any] = {}
    send_it_classification, send_it_reply, send_it_source = _capability_reply("send it", empty_session)
    send_it_lower = send_it_reply.lower()
    failures += emit(
        "send_it_without_action_id_refuses",
        send_it_classification.get("capability") == "message_workflow"
        and "specific pending action id" in send_it_lower
        and "did not send" in send_it_lower,
        classification=send_it_classification,
        reply=send_it_reply,
        source=send_it_source,
    )
    failures += emit(
        "external_send_intent_requires_confirmation",
        first_classification.get("requires_confirmation") is True
        or "confirmation" in first_lower
        or "will not send" in first_lower,
        classification=first_classification,
        reply=first_reply,
    )

    v2_send = _fast("eva v2 execute send WhatsApp to mom saying hi")
    v2_follow = _fast("eva v2 execute open and send the message")
    v2_dry = _fast("eva v2 dry run send WhatsApp to mom saying hi")
    failures += emit(
        "v2_execute_whatsapp_pending_confirmation",
        "Eva v2 execution requires confirmation" in v2_send and "Pending action:" in v2_send and "No real action was executed." in v2_send,
        response=v2_send,
    )
    failures += emit("v2_execute_open_and_send_refused", "Eva v2 execution refused" in v2_follow and "No real action was executed." in v2_follow, response=v2_follow)
    failures += emit("v2_dry_run_whatsapp_confirmation", "Confirmation required" in v2_dry and "No real action was executed" in v2_dry, response=v2_dry)

    failures += emit("resources_status_still_works", "Eva resource registry status" in _fast("resources status"))
    failures += emit("mcp_status_still_works", "MCP policy status" in _fast("mcp status"))
    failures += emit("resource_detail_still_works", "github-mcp-server" in _fast("resource detail github-mcp-server"))
    open_chatgpt = _capability_reply("open ChatGPT on Chrome", {})[0]
    failures += emit("open_chatgpt_route_unchanged", open_chatgpt.get("suggested_route") == "chrome_open_web_app", classification=open_chatgpt)

    source_paths = [
        ROOT / "backend" / "eva" / "resources",
        ROOT / "backend" / "eva" / "core" / "intent_router.py",
        ROOT / "backend" / "eva" / "api" / "routes.py",
        ROOT / "backend" / "eva" / "runtime",
    ]
    source_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace").lower()
        for root in source_paths
        for path in ([root] if root.is_file() else root.rglob("*.py"))
    )
    failures += emit("no_env_local_read", "open('.env.local" not in source_text and 'open(".env.local' not in source_text)
    from _source_guard import TOAST_EXCEPTION, no_package_install, no_shell

    # Real imports/calls only. The runtime's single shell use is the reviewed Phase 126
    # toast, exempted by name with its reason, so any other subprocess still fails.
    install = no_package_install(source_paths)[0]
    shell, allowed = no_shell(source_paths, allow=TOAST_EXCEPTION)
    failures += emit("no_package_install_attempt", not install and not shell, found=[str(f) for f in install + shell], allowed=allowed)
    failures += emit("no_mcp_execution", "run_mcp" not in source_text and "mcp.execute" not in source_text)
    failures += emit("no_playwright_pyautogui_execution", "playwright_driver.open_url" not in source_text and "pyautogui_driver.click" not in source_text)

    print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
