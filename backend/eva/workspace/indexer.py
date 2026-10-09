from __future__ import annotations

from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
import re

from .config import (
    WorkspaceSafetyError,
    assert_workspace_enabled,
    is_excluded_dir,
    is_excluded_file,
    load_workspace_config,
    relative_to_root,
    resolve_workspace_path,
)
from .reader import safe_read_file


TEXT_EXTENSIONS = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


def _modified_at(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def _patterns_match(rel: str, patterns: list[str] | None) -> bool:
    if not patterns:
        return True
    return any(fnmatch(rel, pattern) or pattern.lower() in rel.lower() for pattern in patterns)


def safe_list_files(
    path: str | None = "", patterns: list[str] | None = None, limit: int | None = None, *, cap: int | None = None
) -> dict[str, object]:
    try:
        config = assert_workspace_enabled()
        start = resolve_workspace_path(path or "")
        if not start.exists():
            raise WorkspaceSafetyError("Folder does not exist.")
        if start.is_file():
            start = start.parent
        if is_excluded_dir(start, config):
            raise WorkspaceSafetyError("Folder is blocked by Eva workspace safety rules.")
    except WorkspaceSafetyError as exc:
        return {"ok": False, "path": path or "", "error": str(exc), "files": []}

    # ``cap`` lets a name-only search see the whole tree; the default stays the config limit.
    ceiling = max(config.max_files_per_scan, int(cap or 0))
    max_files = min(max(1, int(limit or ceiling)), ceiling)
    files: list[dict[str, object]] = []
    skipped = 0
    for root, dirs, names in _walk_limited(start):
        dirs[:] = [name for name in dirs if not is_excluded_dir(Path(root) / name, config)]
        for name in names:
            candidate = Path(root) / name
            try:
                if is_excluded_file(candidate, config):
                    skipped += 1
                    continue
                rel = relative_to_root(candidate, config)
                if not _patterns_match(rel, patterns):
                    continue
                stat = candidate.stat()
            except (OSError, ValueError):
                skipped += 1
                continue
            if stat.st_size > config.max_file_bytes:
                skipped += 1
                continue
            files.append(
                {
                    "path": rel,
                    "size": stat.st_size,
                    "modified_at": _modified_at(candidate),
                }
            )
            if len(files) >= max_files:
                return {"ok": True, "root": str(config.root), "path": path or "", "files": files, "truncated": True, "skipped": skipped}
    files.sort(key=lambda item: str(item["path"]))
    return {"ok": True, "root": str(config.root), "path": path or "", "files": files, "truncated": False, "skipped": skipped}


def _walk_limited(start: Path):
    # Isolated helper keeps os.walk import local-looking and easy to audit.
    import os

    return os.walk(start)


_NAME_SCAN_CAP = 5000


def search_workspace(query: str, limit: int = 10) -> dict[str, object]:
    config = load_workspace_config()
    if not config.enabled:
        return {"ok": False, "query": query, "error": "Workspace skills are disabled.", "matches": []}

    normalized_query = " ".join(query.strip().split())[:200]
    if not normalized_query:
        return {"ok": False, "query": query, "error": "Search query is empty.", "matches": []}
    terms = [term.lower() for term in re.findall(r"[A-Za-z0-9_./-]+", normalized_query) if len(term) > 1]
    if not terms:
        terms = [normalized_query.lower()]

    # File NAMES are matched across the whole tree (cheap); file CONTENTS are read for
    # at most max_files_per_scan files, name matches first. Listing only the first
    # max_files_per_scan files in walk order left most of the repo (tools/, workspace/
    # ...) unsearchable, so "tavily" never found tavily_search.py.
    listed = safe_list_files("", cap=_NAME_SCAN_CAP)
    if not listed.get("ok"):
        return {"ok": False, "query": normalized_query, "error": listed.get("error") or "list failed", "matches": []}

    all_paths = [str(item.get("path") or "") for item in listed.get("files", [])]
    path_scores = {rel: sum(4 for term in terms if term in rel.lower()) for rel in all_paths}
    named = [rel for rel in all_paths if path_scores[rel]]
    named_set = set(named)
    content_paths = (named + [rel for rel in all_paths if rel not in named_set])[: config.max_files_per_scan]

    matches: list[dict[str, object]] = [{"path": rel, "line": 1, "snippet": rel, "score": path_scores[rel]} for rel in named]
    for rel in content_paths:
        path_score = path_scores[rel]
        suffix = Path(rel).suffix.lower()
        if suffix and suffix not in TEXT_EXTENSIONS:
            continue
        read = safe_read_file(rel, max_chars=min(config.max_file_bytes, 80_000))
        if not read.get("ok"):
            continue
        for line_number, line in enumerate(str(read.get("content") or "").splitlines(), start=1):
            lower = line.lower()
            line_score = sum(2 for term in terms if term in lower)
            if not line_score:
                continue
            snippet = " ".join(line.strip().split())[:240]
            matches.append({"path": rel, "line": line_number, "snippet": snippet, "score": path_score + line_score})
            if len(matches) >= max(limit * 6, limit):
                break

    matches.sort(key=lambda item: (-int(item.get("score") or 0), str(item.get("path") or ""), int(item.get("line") or 0)))
    trimmed = matches[: max(1, min(limit, 50))]
    return {
        "ok": True,
        "query": normalized_query,
        "matches": trimmed,
        "count": len(trimmed),
        "searched_files": len(all_paths),
        "content_searched_files": len(content_paths),
        "content_truncated": len(content_paths) < len(all_paths),
        "truncated": bool(listed.get("truncated")),
    }
