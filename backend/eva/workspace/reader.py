from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .config import WorkspaceSafetyError, assert_safe_file, relative_to_root, resolve_workspace_path


def _modified_at(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def safe_read_file(path: str, *, max_chars: int = 30_000, start_line: int = 1) -> dict[str, object]:
    """Read a safe text file, or one window of a big one.

    `start_line` (1-based) picks where the window starts; the reply carries
    `next_start_line` when there is more, so a long file is read in several calls
    instead of being refused for its size.
    """
    start_line = max(1, int(start_line or 1))
    try:
        target = resolve_workspace_path(path)
        assert_safe_file(target, allow_large=True)
        raw = target.read_bytes()
    except WorkspaceSafetyError as exc:
        return {"ok": False, "path": path, "error": str(exc), "refused": True}
    except OSError as exc:
        return {"ok": False, "path": path, "error": str(exc), "refused": False}

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")

    if "\x00" in text[:2048]:
        return {"ok": False, "path": path, "error": "Binary-looking file refused.", "refused": True}

    lines = text.splitlines(keepends=True)
    if start_line == 1:
        content = text[:max_chars]
        shown = len(content.splitlines())
    else:
        content, shown = "", 0
        for line in lines[start_line - 1 :]:
            if content and len(content) + len(line) > max_chars:
                break
            content += line if content else line[:max_chars]
            shown += 1
    truncated = start_line - 1 + shown < len(lines)
    return {
        "ok": True,
        "path": relative_to_root(target),
        "size": len(raw),
        "modified_at": _modified_at(target),
        "line_count": text.count("\n") + 1 if text else 0,
        "start_line": start_line,
        "end_line": start_line - 1 + shown,
        "next_start_line": start_line + shown if truncated else None,
        "truncated": truncated,
        "content": content,
    }
