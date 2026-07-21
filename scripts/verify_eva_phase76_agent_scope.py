"""Standalone verifier for Phase 76 (UI agent-scope selector).

The request behind this was "multi-agent so it goes faster", and that is not
what shipped, because it would not be true here: every agent is an LLM loop
drawing on one rationed budget (20/min, 300/day) and there is one cursor and one
foreground window, so concurrent sub-tasks split a quota rather than multiplying
throughput. What the machinery genuinely offers is CONTAINMENT, so the control
is labelled and built as that -- a scope selector, not a speed setting.

What this verifies:

  1. A SCOPE CAN ONLY NARROW. Every role is a strict subset of full access,
     which is the entire reason `agent_scope` is safe to accept over HTTP
     without authentication: the field can hand capability away, never take it.
     If a role ever granted something the unrestricted default lacked, this
     field would become an escalation channel for any unauthenticated caller.
  2. EVERY ROLE ACTUALLY RESTRICTS SOMETHING. A role that denied nothing would
     read as containment in the UI and provide none.
  3. AN UNKNOWN SCOPE IS REJECTED, NEVER IGNORED. Silently dropping it would
     leave someone who asked for containment running with full access while
     believing otherwise -- worse than refusing outright.
  4. IT IS ENFORCED END TO END, through the real HTTP route, and the refusal is
     attributable to the scope rather than to something that would have refused
     anyway.
  5. IT DOES NOT LEAK between requests.
  6. THE UI CONTROL IS WIRED. A selector that never sends the field would look
     exactly like containment and deliver none -- the "reachable from nowhere"
     failure (49b, app.focus) in its user-interface form.

Fully offline: no model call, no real action; the only command exercised is
refused before it runs.
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def check(value: object, message: str) -> None:
    if not value:
        raise AssertionError(message)


def main() -> int:
    from fastapi.testclient import TestClient

    from eva.agents.role_policy import ROLE_POLICIES, known_roles
    from eva.main import app
    from eva.tools.registry import ToolRegistry

    HEADERS = {"X-Eva-Client": "1"}
    client = TestClient(app)
    all_tools = set(ToolRegistry()._tools)

    # ------------------------------------------------------------------ 1/2
    for name, policy in ROLE_POLICIES.items():
        granted = policy.green | policy.orange
        check(
            granted <= all_tools,
            f"role `{name}` grants tools that are not registered: {sorted(granted - all_tools)}",
        )
        check(granted < all_tools, f"role `{name}` restricts nothing; the scope would be decorative")

    # ------------------------------------------------------------------ 3
    rejected = client.post(
        "/api/chat/stream",
        json={"message": "hi", "agent_scope": "desktop-please"},
        headers=HEADERS,
    )
    check(rejected.status_code == 400, f"an unknown scope was not rejected (status {rejected.status_code})")
    check("Unknown agent scope" in str(rejected.json().get("detail")), "the rejection does not name the problem")

    # The UI's default option is value="" -- it must read as full access, not
    # as an unknown role.
    empty = client.post("/api/chat/stream", json={"message": "roles", "agent_scope": ""}, headers=HEADERS)
    check(empty.status_code == 200, "an empty scope was rejected instead of meaning full access")

    for role in known_roles():
        accepted = client.post(
            "/api/chat/stream",
            json={"message": "roles", "agent_scope": role},
            headers=HEADERS,
        )
        check(accepted.status_code == 200, f"known scope `{role}` was rejected")

    # ------------------------------------------------------------------ 4
    scoped = client.post(
        "/api/chat/stream",
        json={"message": "$ git status", "agent_scope": "research"},
        headers=HEADERS,
    )
    check(scoped.status_code == 200, "a scoped request failed outright")
    check("may not call" in scoped.text, "a RED tool was not refused under a research scope")

    unscoped = client.post("/api/chat/stream", json={"message": "$ git status"}, headers=HEADERS)
    check(
        "may not call" not in unscoped.text,
        "the same request is role-refused WITHOUT a scope -- the refusal above is not attributable to the scope",
    )

    # ------------------------------------------------------------------ 5
    after = client.post("/api/chat/stream", json={"message": "$ git status"}, headers=HEADERS)
    check("may not call" not in after.text, "a scope leaked into a later, unscoped request")

    # ------------------------------------------------------------------ 6
    markup = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    check('id="scopeSelect"' in markup, "the scope selector is missing from the UI")
    check("agent_scope:" in script, "the UI never SENDS agent_scope; the control would be decorative")
    check("currentAgentScope" in script, "the UI does not read the selected scope")
    for role in known_roles():
        check(f'value="{role}"' in markup, f"the UI offers no option for role `{role}`")
    # Honest labelling: the control must not be sold as a speed setting.
    check("not speed" in markup.lower(), "the UI does not say this is containment rather than speed")

    # ------------------------------------------------------------------ 7
    import verify_eva_all

    name = "verify_eva_phase76_agent_scope.py"
    check(name in verify_eva_all.FULL_VERIFIERS, "full profile missing the Phase 76 verifier")
    check(name in verify_eva_all.QUICK_VERIFIERS, "quick profile missing the Phase 76 verifier")
    check(name in verify_eva_all.VERIFIER_DESCRIPTORS, "master descriptor missing the Phase 76 verifier")

    print(
        "PASS: Phase 76 agent-scope selector. The request was 'multi-agent so it goes faster'; that would not be true "
        "here -- every agent is an LLM loop drawing on one 20/min, 300/day budget, and there is one cursor and one "
        "foreground window -- so what shipped is the thing the machinery actually offers, labelled honestly as "
        "containment rather than speed. A request may be confined to a role's tool surface from the UI. It is safe to "
        "accept that field over HTTP without authentication for one specific reason, asserted structurally rather "
        "than assumed: every role is a strict SUBSET of full access, so the field can hand capability away and never "
        "take it -- and every role really does restrict something, so the control is not decorative. An unrecognised "
        "scope is REJECTED rather than ignored, because silently dropping it would leave a user who asked for "
        "containment running unrestricted while believing otherwise. Enforcement is verified end to end through the "
        "real HTTP route, with the same request proven NOT refused without the scope so the refusal is attributable "
        "to it, and the scope is proven not to leak into a later request. The UI control is proven to actually send "
        "the field, since a selector that never sent it would look exactly like containment and deliver none."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
