from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def emit(case: str, passed: bool, **payload: object) -> int:
    print(json.dumps({"case": case, "pass": passed, **payload}, indent=2, ensure_ascii=True))
    return 0 if passed else 1


def main() -> int:
    from backend.eva.core.capabilities import get_capability
    from backend.eva.tools.registry import ToolRegistry

    failures = 0
    registry = ToolRegistry()
    specs = registry.list_tools()
    by_name = {item["name"]: item for item in specs}

    failures += emit(
        "public_specs_include_tool_intelligence_metadata",
        all("category" in item and "risk" in item and "verification_strategy" in item and "failure_recovery" in item for item in specs),
    )
    capability = get_capability("media_music_control")
    failures += emit(
        "media_music_capability_declared",
        # The capability now names the desktop-verified Spotify tools; what matters is
        # that every tool it names is real and it covers play, search and media keys.
        capability is not None
        and all(tool in by_name for tool in capability.related_tools)
        and any(tool.startswith("spotify_play") for tool in capability.related_tools)
        and any(tool.startswith("spotify_search") for tool in capability.related_tools)
        and "media_control" in capability.related_tools,
        capability=capability.__dict__ if capability else None,
    )
    failures += emit(
        "spotify_tools_visible_to_planner",
        all(name in {item["name"] for item in registry.planner_specs()} for name in ("spotify_search", "spotify_play_query", "spotify_pause", "spotify_next", "spotify_previous")),
    )
    failures += emit(
        "dangerous_tools_not_safe_by_default",
        by_name["guarded_power_action"]["safe_by_default"] is False
        and by_name["system_power"]["risk"] == "high",
    )

    print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
