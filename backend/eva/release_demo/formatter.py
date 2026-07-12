from __future__ import annotations

from .capability_map import capability_map_text
from .demo_commands import demo_commands_text
from .demo_smoke import demo_smoke_text
from .demo_profile import build_demo_profile
from .known_limitations import known_limitations_text
from .post_push_sync import post_push_sync_text
from .release_readiness import VERIFICATION_COMMANDS, release_readiness_text
from .safety_proof import safety_proof_text
from .status import get_release_demo_status


BOUNDARY_LINES = (
    "No publishing was performed.",
    "No commit was made.",
    "No secrets were read or exposed.",
    "No live LLM/API/provider call was made.",
    "No browser control is enabled.",
    "No desktop control is enabled.",
    "No CodingAgent source editing is enabled.",
    "No shell/test/package/git execution is enabled.",
    "No unrestricted crawler is enabled.",
    "Phase 12L remains a gated write path.",
)


def _output(title: str, body: str) -> str:
    return "\n".join((title, body, "", *BOUNDARY_LINES))


def _bullets(items: tuple[str, ...]) -> str:
    return "\n".join(f"- {item}" for item in items)


def format_release_status() -> str:
    status = get_release_demo_status()
    body = "\n".join(
        (
            "Phase: Phase 29 Public Demo / Release.",
            f"Mode: {status.mode}.",
            f"Demo readiness: {status.readiness}.",
            f"Publishing enabled: {status.publishing_enabled}.",
            f"External upload enabled: {status.external_upload_enabled}.",
            f"Git release enabled: {status.git_release_enabled}.",
            f"Next safe step: {status.next_safe_step}.",
        )
    )
    return _output("Eva release status", body)


def format_release_demo() -> str:
    profile = build_demo_profile()
    body = "\n".join(
        (
            profile.public_facing_disclaimer,
            f"Profile ID: {profile.release_demo_id}.",
            f"Readiness: {profile.final_readiness_status}.",
            "Verified milestone summary:",
            _bullets(profile.verified_milestone_summary),
            "Demo walkthrough:",
            _bullets(profile.demo_command_list),
            f"Next safe step: {profile.next_safe_step}.",
        )
    )
    return _output("Eva public demo profile", body)


def format_release_commands() -> str:
    return _output("Eva release demo command guide", demo_commands_text())


def format_release_capability_map() -> str:
    return _output("Eva release capability map", capability_map_text())


def format_release_safety_proof() -> str:
    return _output("Eva release safety proof", safety_proof_text())


def format_release_readiness() -> str:
    return _output("Eva release readiness report", release_readiness_text())


def format_release_limitations() -> str:
    return _output("Eva release known limitations", known_limitations_text())


def format_release_verification() -> str:
    body = "\n".join(
        (
            "Run these checks manually from the repository root:",
            _bullets(VERIFICATION_COMMANDS),
            "Chat does not start these commands. Fresh terminal evidence is required before a readiness claim.",
        )
    )
    return _output("Eva release verification bundle", body)


def format_release_demo_smoke() -> str:
    return _output("Eva release demo smoke test", demo_smoke_text())


def format_release_post_push_sync() -> str:
    return _output("Eva release post-push sync status", post_push_sync_text())
