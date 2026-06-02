from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SafetySimulation:
    request: str
    decision: str
    reason: str
    likely_permission: str
    public_mode_result: str
    safer_alternative: str

    def as_text(self) -> str:
        return "\n".join(
            [
                "Eva public safety simulator",
                "",
                "Demo mode: no real action executed.",
                f"Request: {self.request}",
                f"Safety result: {self.decision}",
                f"Reason: {self.reason}",
                f"Likely permission decision: {self.likely_permission}",
                f"Public mode result: {self.public_mode_result}",
                f"Safer alternative: {self.safer_alternative}",
            ]
        )


def simulate_public_safety(request: str) -> SafetySimulation:
    text = str(request or "").strip()
    lowered = text.lower()
    if ".env.local" in lowered or "api key" in lowered or "token" in lowered or "password" in lowered:
        return SafetySimulation(
            request=text,
            decision="hard_block",
            reason=".env.local, API keys, tokens, and passwords are secret material.",
            likely_permission="not overrideable",
            public_mode_result="Blocked.",
            safer_alternative="Use `eva doctor public` or `eva public checklist` to inspect release readiness without reading secrets.",
        )
    if "github" in lowered and "mcp" in lowered and any(word in lowered for word in ("merge", "write", "delete", "commit", "push")):
        return SafetySimulation(
            request=text,
            decision="public_refuse",
            reason="MCP execution and repo write actions are disabled by default.",
            likely_permission="would require confirmation or override in a later gated executor",
            public_mode_result="Refused in public mode.",
            safer_alternative="Use `resource detail github-mcp-server` or `resources experimental` to inspect policy.",
        )
    if "whatsapp" in lowered or "send message" in lowered or "send " in lowered:
        return SafetySimulation(
            request=text,
            decision="ask_confirmation",
            reason="External messages require explicit confirmation, and public mode does not perform real sends.",
            likely_permission="confirmation required",
            public_mode_result="Public mode shows a pending-action demo and refuses real sending.",
            safer_alternative="Use `eva demo run whatsapp-confirmation`.",
        )
    if "delete" in lowered or "remove downloads" in lowered or "erase" in lowered:
        return SafetySimulation(
            request=text,
            decision="ask_override",
            reason="Destructive file actions require override and checkpoint planning.",
            likely_permission="override required",
            public_mode_result="Refused in public mode.",
            safer_alternative="Use `eva safety test delete Downloads folder` to preview the gate.",
        )
    if "playwright" in lowered or "pyautogui" in lowered or "click" in lowered:
        return SafetySimulation(
            request=text,
            decision="public_refuse",
            reason="Browser/desktop automation execution is disabled in public demo mode.",
            likely_permission="confirmation or override may be required in private builds",
            public_mode_result="Refused in public mode.",
            safer_alternative="Use demo scenarios or v2 dry-run previews.",
        )
    return SafetySimulation(
        request=text,
        decision="allow_read_only_demo",
        reason="No risky operation was detected in this simulator.",
        likely_permission="allow for status/demo/dry-run only",
        public_mode_result="Allowed as a simulated or read-only response.",
        safer_alternative="Use `eva demo scenarios` to see safe examples.",
    )
