from __future__ import annotations

import fnmatch
import shutil
from pathlib import Path
from typing import Any

from ..agent.action_model import AgentAction, AgentObservation
from ..agent.checkpoints import CheckpointStore
from ..agent.rollback import rollback_action
from ..agent.verifier import verify_action


SAFE_ROOT = Path(__file__).resolve().parents[3]

# Basenames are always denied regardless of which allowed root they sit
# under. Matched case-insensitively against the final path component.
_DENY_BASENAME_GLOBS = (".env*", "*.secret*", "*.sqlite3", "id_rsa*")


def _safe_path(path: str) -> Path:
    target = Path(path).expanduser().resolve()

    name_lower = target.name.lower()
    if any(fnmatch.fnmatch(name_lower, pattern) for pattern in _DENY_BASENAME_GLOBS):
        raise ValueError(f"File path '{target}' matches a denied filename pattern.")
    if ".git" in target.parts:
        raise ValueError(f"File path '{target}' is inside a .git directory.")

    home = Path.home().resolve()
    allowed_roots = (SAFE_ROOT.resolve(), home / "Documents", home / "Desktop", home / "Downloads")
    for root in allowed_roots:
        try:
            if target.is_relative_to(root):
                return target
        except (OSError, ValueError):
            continue
    raise ValueError(f"File path '{target}' is outside the allowed local roots.")


def file_read_text(path: str) -> dict[str, Any]:
    target = _safe_path(path)
    return {"ok": True, "path": str(target), "content": target.read_text(encoding="utf-8", errors="replace")}


def file_write_text(path: str, content: str) -> dict[str, Any]:
    target = _safe_path(path)
    action = AgentAction(
        "file.write_text",
        "DESTRUCTIVE_FILE_ACTION",
        "Write local text file",
        {"path": str(target), "content": content},
        ["DESTRUCTIVE_FILE_ACTION"],
        destructive=True,
        verification={"method": "file_contains", "path": str(target), "text": content},
        rollback={"checkpoint_type": "file_snapshot", "target": str(target)},
    )
    checkpoint = CheckpointStore().create_checkpoint(action)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    observation = AgentObservation(action.action_id, True, {"path": str(target)}, "Wrote file.")
    verification = verify_action(action, observation)
    if not verification.verified and checkpoint:
        rollback = rollback_action(action, checkpoint)
        return {"ok": False, "checkpoint": checkpoint.as_dict(), "verification": verification.as_dict(), "rollback": rollback.as_dict()}
    return {"ok": True, "path": str(target), "checkpoint": checkpoint.as_dict() if checkpoint else None, "verification": verification.as_dict()}


def file_patch_text(path: str, old: str, new: str) -> dict[str, Any]:
    target = _safe_path(path)
    current = target.read_text(encoding="utf-8", errors="replace")
    if old not in current:
        return {"ok": False, "error": "old_text_not_found"}
    return file_write_text(str(target), current.replace(old, new, 1))


def file_copy(src: str, dst: str) -> dict[str, Any]:
    source = _safe_path(src)
    dest = _safe_path(dst)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    return {"ok": True, "src": str(source), "dst": str(dest), "verified": dest.exists()}


def file_move(src: str, dst: str) -> dict[str, Any]:
    source = _safe_path(src)
    dest = _safe_path(dst)
    action = AgentAction("file.move", "DESTRUCTIVE_FILE_ACTION", "Move local file", {"path": str(source)}, ["DESTRUCTIVE_FILE_ACTION"], destructive=True, rollback={"checkpoint_type": "file_snapshot", "target": str(source)})
    checkpoint = CheckpointStore().create_checkpoint(action)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(dest))
    return {"ok": True, "src": str(source), "dst": str(dest), "checkpoint": checkpoint.as_dict() if checkpoint else None, "verified": dest.exists()}


def file_delete(path: str) -> dict[str, Any]:
    target = _safe_path(path)
    action = AgentAction("file.delete", "DESTRUCTIVE_FILE_ACTION", "Delete local file", {"path": str(target)}, ["DESTRUCTIVE_FILE_ACTION"], destructive=True, rollback={"checkpoint_type": "file_snapshot", "target": str(target)})
    checkpoint = CheckpointStore().create_checkpoint(action)
    target.unlink()
    return {"ok": True, "path": str(target), "checkpoint": checkpoint.as_dict() if checkpoint else None, "verified": not target.exists()}


def file_list_dir(path: str) -> dict[str, Any]:
    target = _safe_path(path)
    return {"ok": True, "path": str(target), "items": [item.name for item in target.iterdir()][:200]}
