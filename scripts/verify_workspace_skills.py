from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.eva.core.config import load_local_env
from backend.eva.core.fast_commands import maybe_handle_fast_command
from backend.eva.tools.registry import ToolRegistry
from backend.eva.workspace import safe_read_file, search_workspace, summarize_workspace, workspace_status


def emit(case: str, passed: bool, **payload: object) -> int:
    print(json.dumps({"case": case, "pass": passed, **payload}, indent=2, ensure_ascii=False))
    return 0 if passed else 1


def main() -> int:
    load_local_env(ROOT / ".env")
    tools = ToolRegistry()
    failures = 0

    status = workspace_status()
    failures += emit(
        "workspace_status",
        bool(status.get("enabled")) and ".env" in ",".join(status.get("exclude_files", [])),
        root=status.get("root"),
        enabled=status.get("enabled"),
        exclude_dirs=status.get("exclude_dirs"),
        exclude_files=status.get("exclude_files"),
    )

    structure_reply = maybe_handle_fast_command("project structure", tools)
    structure_text = structure_reply[0] if structure_reply else ""
    failures += emit(
        "project_structure",
        all(marker in structure_text for marker in ("backend/eva/agent", "frontend", "scripts")) and ".venv" not in structure_text and ".git" not in structure_text,
        source=structure_reply[1] if structure_reply else None,
        preview=structure_text[:800],
    )

    agent_search = search_workspace("agent runner", limit=10)
    agent_paths = [str(item.get("path")) for item in agent_search.get("matches", []) if isinstance(item, dict)]
    failures += emit(
        "search_agent_runner",
        any(path.endswith("backend/eva/agent/runner.py") for path in agent_paths),
        matches=agent_search.get("matches", [])[:5],
    )

    tavily_search = search_workspace("tavily", limit=10)
    tavily_paths = [str(item.get("path")) for item in tavily_search.get("matches", []) if isinstance(item, dict)]
    failures += emit(
        "search_tavily",
        any("tavily" in path.lower() for path in tavily_paths),
        matches=tavily_search.get("matches", [])[:5],
    )

    safe_read = safe_read_file("backend/eva/agent/runner.py", max_chars=200_000)
    failures += emit(
        "read_safe_file",
        bool(safe_read.get("ok")) and "run_agentic_task" in str(safe_read.get("content") or ""),
        path=safe_read.get("path"),
        line_count=safe_read.get("line_count"),
    )

    env_read = safe_read_file(".env")
    failures += emit(
        "read_forbidden_env",
        not env_read.get("ok") and bool(env_read.get("refused")),
        error=env_read.get("error"),
    )

    # The rule, not the file: these must be excluded whether or not they exist here,
    # and whatever EVA_WORKSPACE_EXCLUDE_FILES says. Only ".env" used to be blocked,
    # so .env.local (the API keys) and every .env.* backup were readable.
    from backend.eva.workspace.config import is_excluded_file, resolve_workspace_path

    original_excludes = os.environ.get("EVA_WORKSPACE_EXCLUDE_FILES")
    os.environ["EVA_WORKSPACE_EXCLUDE_FILES"] = "*.log"
    try:
        secret_names = [".env.local", ".ENV.LOCAL", ".env.local.bak-phase121", ".env.bak-20260901-072033", "deploy.pem", "id.key"]
        readable = [name for name in secret_names if not is_excluded_file(resolve_workspace_path(name))]
        example_blocked = is_excluded_file(resolve_workspace_path(".env.example"))
    finally:
        if original_excludes is None:
            os.environ.pop("EVA_WORKSPACE_EXCLUDE_FILES", None)
        else:
            os.environ["EVA_WORKSPACE_EXCLUDE_FILES"] = original_excludes
    failures += emit("secret_env_files_always_refused", not readable and not example_blocked, readable=readable, example_blocked=example_blocked)

    traversal = safe_read_file("../../.env")
    failures += emit(
        "path_traversal_refused",
        not traversal.get("ok") and bool(traversal.get("refused")),
        error=traversal.get("error"),
    )

    project_summary = summarize_workspace()
    folders = [str(item.get("folder")) for item in project_summary.get("sections", []) if isinstance(item, dict)]
    failures += emit(
        "summarize_project",
        bool(project_summary.get("ok")) and "backend/eva/llm" in folders and "backend/eva/tools" in folders,
        folders=folders,
    )

    print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
