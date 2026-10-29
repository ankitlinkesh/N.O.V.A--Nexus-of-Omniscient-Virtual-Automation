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


def _command_text(command: str) -> str:
    from backend.eva.core.fast_commands import maybe_handle_fast_command
    from backend.eva.tools.registry import ToolRegistry

    handled = maybe_handle_fast_command(command, ToolRegistry(), {})
    return handled[0] if handled else ""


def _execute_text(request: str) -> str:
    from backend.eva.runtime.graph import run_eva_v2_execute

    return run_eva_v2_execute(request).final_response


def main() -> int:
    failures = 0
    temp_root = Path(tempfile.mkdtemp(prefix="eva_code_index_v2_"))
    os.environ["EVA_CODE_INDEX_DATA_DIR"] = str(temp_root / "code_index")
    os.environ.setdefault("EVA_PENDING_ACTION_LEDGER_PATH", str(temp_root / "pending_actions.jsonl"))

    try:
        from backend.eva.code_index.search import search_code, search_symbols, summarize_file
        from backend.eva.code_index.status import code_index_status, refresh_code_index, workspace_summary
        from backend.eva.resources.registry import get_resource
        from backend.eva.runtime.execution_policy import CODE_READONLY_ACTIONS
    except Exception as exc:
        failures += emit("modules_import", False, error=str(exc))
        print(json.dumps({"overall_pass": False, "failures": failures}, indent=2))
        return 1

    failures += emit(
        "modules_import",
        callable(refresh_code_index)
        and callable(code_index_status)
        and callable(search_code)
        and callable(search_symbols)
        and callable(summarize_file)
        and callable(workspace_summary),
    )

    refresh = refresh_code_index()
    failures += emit(
        "refresh_builds_local_metadata_index",
        refresh.get("ok") is True
        and int(refresh.get("indexed_files") or 0) > 20
        and Path(str(refresh.get("data_dir") or "")).resolve().is_relative_to(temp_root.resolve())  # resolve: TEMP may be an 8.3 short path
        and refresh.get("secrets_indexed") is False,
        result=refresh,
    )

    status = code_index_status()
    failures += emit(
        "status_reports_safe_cache",
        status.get("ok") is True
        and status.get("indexed") is True
        and int(status.get("indexed_files") or 0) == int(refresh.get("indexed_files") or 0)
        and status.get("cache_scope") == "local_metadata_only"
        and status.get("stores_full_file_contents") is False,
        status=status,
    )

    index_files = list((temp_root / "code_index").glob("*.json"))
    combined_cache = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in index_files)
    failures += emit(
        "cache_has_no_full_source_or_secrets",
        "BEGIN PRIVATE KEY" not in combined_cache
        and ".env.local" not in combined_cache
        and "raw_content" not in combined_cache
        and "full_content" not in combined_cache
        and "def main() -> int:" not in combined_cache,
        cache_files=[path.name for path in index_files],
    )

    search = search_code("permission gate", limit=6)
    failures += emit(
        "code_search_uses_metadata_index",
        search.get("ok") is True
        and search.get("query") == "permission gate"
        and isinstance(search.get("matches"), list)
        and "content" not in json.dumps(search, ensure_ascii=False).lower(),
        result=search,
    )

    symbols = search_symbols("CodeAgent", limit=6)
    failures += emit(
        "symbol_search_finds_python_symbols",
        symbols.get("ok") is True
        and any(str(item.get("name")) == "CodeAgent" for item in symbols.get("matches") or [] if isinstance(item, dict)),
        result=symbols,
    )

    summary = summarize_file("backend/eva/agents/code_agent.py")
    failures += emit(
        "file_summary_is_summary_only",
        summary.get("ok") is True
        and summary.get("path") == "backend/eva/agents/code_agent.py"
        and "CodeAgent" in " ".join(summary.get("symbols") or [])
        and "from __future__" not in str(summary)
        and "full_content" not in str(summary).lower(),
        result=summary,
    )

    refused = summarize_file(".env.local")
    failures += emit(
        "env_local_refused",
        refused.get("ok") is False
        and refused.get("refused") is True,
        result=refused,
    )

    workspace = workspace_summary()
    failures += emit(
        "workspace_summary_mentions_safety_and_major_areas",
        workspace.get("ok") is True
        and "backend/eva/runtime" in "\n".join(workspace.get("major_areas") or [])
        and "No secrets" in str(workspace.get("safety") or ""),
        result=workspace,
    )

    resource = get_resource("eva-code-index")
    failures += emit(
        "resource_registry_has_code_index",
        resource is not None
        and resource.local_only is True
        and resource.can_read_files is True
        and resource.can_write_files is False
        and resource.default_enabled is True,
        resource=resource.as_dict() if resource else None,
    )

    failures += emit(
        "execution_policy_allowlists_file_summary",
        "code.summarize_file" in CODE_READONLY_ACTIONS,
        actions=sorted(CODE_READONLY_ACTIONS),
    )

    fast_cases = {
        "code index status": "Code index v2 status",
        "code index refresh": "Code index v2 refreshed",
        "code search permission gate": "Code index v2 matches",
        "symbol search CodeAgent": "Code index v2 symbols",
        "workspace summary": "Workspace summary",
        "code file summary backend/eva/agents/code_agent.py": "backend/eva/agents/code_agent.py",
    }
    for command, expected in fast_cases.items():
        text = _command_text(command)
        failures += emit(
            f"fast_command_{command.replace(' ', '_')}",
            expected in text and "{'" not in text and "Traceback" not in text and "from __future__" not in text,
            response=text,
        )

    v2_search = _execute_text("search code for PermissionGate")
    failures += emit(
        "v2_code_search_delegates_to_code_index",
        "Eva v2 execution result" in v2_search
        and "Code index v2 matches" in v2_search
        and "Executed through v2 read-only delegate." in v2_search
        and ".env.local" not in v2_search,
        response=v2_search,
    )

    v2_summary = _execute_text("summarize backend/eva/agents/code_agent.py")
    failures += emit(
        "v2_file_summary_delegates_readonly",
        "Eva v2 execution result" in v2_summary
        and "backend/eva/agents/code_agent.py" in v2_summary
        and "summary-only" in v2_summary.lower()
        and "from __future__" not in v2_summary,
        response=v2_summary,
    )

    source_roots = [
        ROOT / "backend" / "eva" / "code_index",
        ROOT / "backend" / "eva" / "runtime" / "read_only_delegates.py",
        ROOT / "backend" / "eva" / "agents" / "code_agent.py",
    ]
    source_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace").lower()
        for root in source_roots
        if root.exists()
        for path in ([root] if root.is_file() else root.rglob("*.py"))
    )
    failures += emit("no_env_local_open", "open('.env.local" not in source_text and 'open(\".env.local' not in source_text)
    failures += emit("no_shell_execution_added", "subprocess" not in source_text and "os.system" not in source_text and "shell=true" not in source_text)
    failures += emit("no_new_dependency_execution", "pip install" not in source_text and "playwright" not in source_text and "pyautogui" not in source_text)

    print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
