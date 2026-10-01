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


_HOME_FOLDERS = ("Documents", "Desktop", "Downloads")


def _anchor_home_folder(raw: Path) -> Path:
    """Phase 118: live, the planner asked for "Downloads" and it resolved
    against the server's working directory (this repo), not the user's folder.
    A relative path that starts with one of the user's own folders means that
    folder; anything else is left alone.
    """
    if raw.is_absolute() or not raw.parts:
        return raw
    for name in _HOME_FOLDERS:
        if raw.parts[0].lower() == name.lower():
            return Path.home().joinpath(name, *raw.parts[1:])
    return raw


def _safe_path(path: str) -> Path:
    target = _anchor_home_folder(Path(path).expanduser()).resolve()

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
    names = [item.name for item in target.iterdir()]
    return {"ok": True, "path": str(target), "items": names[:200], "total": len(names)}


# --------------------------------------------------------------------------- Phase 128
# Reading a user's own file. The path goes through the SAME `_safe_path` as every
# other file tool (allowed roots, Phase 118 bare-folder anchoring, deny basenames,
# .git refusal). Nothing here is trusted: the CONTENT of a file is untrusted data
# (a downloaded file can say "ignore your instructions"), and the tool says so in
# its result; the agent runner taints the task on it (threat_defense/taint.py).

READ_MAX_CHARS = 20_000
# Bytes read from disk. Four bytes per char is the UTF-8 worst case, so a file far
# larger than the cap is never loaded whole.
_READ_MAX_BYTES = READ_MAX_CHARS * 4
_SNIFF_BYTES = 8192

# Read-only extras: a file that is *meant* to hold a secret is not something to
# paste into a model prompt, wherever it sits under an allowed root.
_READ_DENY_BASENAME_GLOBS = ("*.pem", "*.key", "*.pfx", "*.p12", "*.ppk", "*.kdbx", "*credentials*", "*token*.json", "*.keystore")


def _refuse(error: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "error": error, "message": message, **extra}


def _extract_pdf(target: Path) -> str:
    """PDF text via pypdf, only if it is already installed. NOT a dependency."""
    from pypdf import PdfReader  # type: ignore[import-not-found]  # ImportError -> caller refuses

    reader = PdfReader(str(target))
    parts: list[str] = []
    total = 0
    for page in reader.pages:
        parts.append(page.extract_text() or "")
        total += len(parts[-1])
        if total > READ_MAX_CHARS * 2:
            break
    return "\n".join(parts)


def _extract_docx(target: Path) -> str:
    """DOCX text via python-docx, only if it is already installed."""
    import docx  # type: ignore[import-not-found]  # ImportError -> caller refuses

    return "\n".join(paragraph.text for paragraph in docx.Document(str(target)).paragraphs)


def _decode_text(raw: bytes, byte_cut: bool = False) -> str | None:
    """Decode a text file's bytes, or None when they are binary."""
    sample = raw[:_SNIFF_BYTES]
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return raw.decode("utf-16")
        except UnicodeError:
            return None
    if b"\x00" in sample:
        return None
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            # A multi-byte character cut by the read cap is not corruption; a file
            # that was read whole and still fails is not this encoding.
            text = None
            for trim in (1, 2, 3) if byte_cut else ():
                try:
                    text = raw[:-trim].decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            if text is None:
                continue
        controls = sum(1 for ch in text[:_SNIFF_BYTES] if ord(ch) < 32 and ch not in "\t\n\r\f")
        if controls > max(8, len(text[:_SNIFF_BYTES]) // 20):
            return None
        return text
    return None


def read_path_refusal(path: str) -> dict[str, Any] | None:
    """Why this path can never be read, or None. Pure path logic (no disk access).

    The registry calls this BEFORE the permission gate (the Phase 113 rule): a path
    outside the allowed roots, a denied basename or a .git path cannot be read no
    matter who approves, so asking for approval first would be asking someone to
    approve an action that cannot happen.
    """
    try:
        target = _safe_path(path)
    except ValueError as exc:
        return _refuse("path_not_allowed", f"I can't read that: {exc}")
    name_lower = target.name.lower()
    if any(fnmatch.fnmatch(name_lower, pattern) for pattern in _READ_DENY_BASENAME_GLOBS):
        return _refuse("denied_filename", f"I won't read {target.name}: it looks like a key or credentials file.")
    return None


def file_read_text(path: str) -> dict[str, Any]:
    """Read a user file as text, bounded. Refuses binary, directories, secrets."""
    refusal = read_path_refusal(path)
    if refusal is not None:
        return refusal
    target = _safe_path(path)
    if not target.exists():
        return _refuse("not_found", f"I couldn't find {target.name} at {target}. Check the name and folder.", path=str(target))
    if target.is_dir():
        return _refuse("is_directory", f"{target} is a folder, not a file. I can list its contents instead.", path=str(target))

    size = target.stat().st_size
    suffix = target.suffix.lower()
    with target.open("rb") as handle:
        raw = handle.read(_READ_MAX_BYTES + 1)
    byte_cut = len(raw) > _READ_MAX_BYTES
    raw = raw[:_READ_MAX_BYTES]

    fmt = "text"
    text: str | None
    if suffix == ".pdf" or raw.startswith(b"%PDF"):
        fmt = "pdf"
        try:
            text = _extract_pdf(target)
        except ImportError:
            return _refuse(
                "unsupported_format",
                f"I can't read PDFs yet: no PDF text extractor is installed on this machine, so I did not read {target.name}.",
                path=str(target),
            )
        except Exception as exc:
            return _refuse("read_failed", f"I couldn't extract text from {target.name}: {type(exc).__name__}.", path=str(target))
        byte_cut = False
    elif suffix == ".docx":
        fmt = "docx"
        try:
            text = _extract_docx(target)
        except ImportError:
            return _refuse(
                "unsupported_format",
                f"I can't read Word documents yet: no DOCX reader is installed on this machine, so I did not read {target.name}.",
                path=str(target),
            )
        except Exception as exc:
            return _refuse("read_failed", f"I couldn't extract text from {target.name}: {type(exc).__name__}.", path=str(target))
        byte_cut = False
    else:
        text = _decode_text(raw, byte_cut)
        if text is None:
            return _refuse("binary_file", f"{target.name} is a binary file, not text, so I did not read it.", path=str(target), size_bytes=size)

    text = text.replace(chr(13)+chr(10), chr(10)).replace(chr(13), chr(10))
    total_chars = len(text)
    truncated = byte_cut or total_chars > READ_MAX_CHARS
    shown = text[:READ_MAX_CHARS]
    result: dict[str, Any] = {
        "ok": True,
        "path": str(target),
        "name": target.name,
        "format": fmt,
        "text": shown,
        "chars": len(shown),
        "total_chars": None if byte_cut else total_chars,
        "size_bytes": size,
        "truncated": truncated,
        # The content is data from outside NOVA's trust boundary (Phase 128).
        "untrusted": True,
    }
    if truncated:
        result["message"] = f"Showing the first {len(shown)} characters of {target.name} ({size} bytes); the rest was not read."
    return result
