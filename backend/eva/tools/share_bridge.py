"""Phase 134: a file bridge between the user's folders and NOVA's sandbox box.

The box sees exactly one Windows folder, ``D:\\nova-share`` (``/mnt/share`` inside).
These two tools are the ONLY way a user file gets into it and a box-made file gets
out. Both are confirm-class (see ``ActionType.SANDBOX_TRANSFER``):

* ``share.to_box`` -- the box has internet, so putting a file there could exfiltrate
  it. The source is validated with the SAME rules as ``file.read_text``
  (``_safe_path`` roots + deny globs + the key/credential read-deny list).
* ``share.from_box`` -- box-made content lands in the user's folders, so the result
  is marked untrusted and the name may not escape the share.

Both work on the HOST with plain file copies. Nothing here goes through
``sandbox_run`` or ``wsl.exe``. Neither ever overwrites: a taken name becomes
``name (2).ext``, ``name (3).ext`` ...  The share path is a module constant so
tests can point it at a tmp dir.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from ..shell.sandbox_terminal import SHARE_GUEST_PATH, SHARE_HOST_PATH
from .safe_file_tools import _HOME_FOLDERS, _safe_path, read_path_refusal

SHARE_ROOT = SHARE_HOST_PATH  # tests monkeypatch this; never hard-code D:\nova-share below
MAX_BYTES = 100 * 1024 * 1024
_MAX_COLLISIONS = 1000


def _refuse(error: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "error": error, "message": message, **extra}


def _share_root() -> Path:
    root = Path(SHARE_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _inside(path: Path, root: Path) -> bool:
    try:
        return path.is_relative_to(root)
    except (OSError, ValueError):
        return False


def _numbered(name: str, n: int) -> str:
    if n <= 1:
        return name
    p = Path(name)
    return f"{p.stem} ({n}){p.suffix}"


def _copy_no_overwrite(src: Path, folder: Path, name: str) -> Path | None:
    """Copy `src` into `folder` under the first free name. 'xb' (O_EXCL) cannot
    overwrite and cannot write through a pre-planted symlink. None if no name is free."""
    for n in range(1, _MAX_COLLISIONS + 1):
        dest = folder / _numbered(name, n)
        try:
            with src.open("rb") as reader, dest.open("xb") as writer:
                shutil.copyfileobj(reader, writer)
        except FileExistsError:
            continue
        shutil.copystat(src, dest, follow_symlinks=False)
        return dest
    return None


def share_to_box(path: str) -> dict[str, Any]:
    """Copy one user file into the share; return its in-box path."""
    refusal = read_path_refusal(str(path or ""))
    if refusal is not None:
        return refusal
    source = _safe_path(str(path))
    if not source.exists():
        return _refuse("not_found", f"I couldn't find {source.name} at {source}.", path=str(source))
    if not source.is_file():
        return _refuse("not_a_file", f"{source} is a folder, not a file. I only copy single files.", path=str(source))
    size = source.stat().st_size
    if size > MAX_BYTES:
        return _refuse("too_large", f"{source.name} is {size // (1024 * 1024)} MB; the limit is {MAX_BYTES // (1024 * 1024)} MB.", path=str(source))

    root = _share_root()
    dest = _copy_no_overwrite(source, root, source.name)
    if dest is None:
        return _refuse("no_free_name", f"Too many copies of {source.name} already in the share.")
    if not _inside(dest.resolve(), root):  # belt and braces: never leave a copy outside the share
        try:
            dest.unlink()
        except OSError:
            pass
        return _refuse("outside_share", "The copy would land outside the sandbox share, so I removed it.")
    return {
        "ok": True,
        "name": dest.name,
        "src": str(source),
        "box_path": f"{SHARE_GUEST_PATH}/{dest.name}",
        "bytes": size,
        "verified": dest.exists(),
    }


def _plain_relative(name: str) -> str | None:
    """The name as a safe relative path, or None (absolute, drive, `..`, empty)."""
    text = str(name or "").strip().replace("\\", "/")
    if text.startswith(SHARE_GUEST_PATH + "/"):
        text = text[len(SHARE_GUEST_PATH) + 1:]
    if not text or text.startswith("/") or ":" in text:
        return None
    parts = [p for p in text.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        return None
    return "/".join(parts)


def share_from_box(name: str, folder: str = "Downloads") -> dict[str, Any]:
    """Copy one file from the share into Documents/Desktop/Downloads."""
    rel = _plain_relative(name)
    if rel is None:
        return _refuse("bad_name", "Give me a plain file name inside the sandbox share (no '..', no absolute paths).")
    wanted = str(folder or "Downloads").strip()
    home_folder = next((f for f in _HOME_FOLDERS if f.lower() == wanted.lower()), None)
    if home_folder is None:
        return _refuse("bad_folder", "The destination must be Documents, Desktop or Downloads.")

    root = _share_root()
    candidate = (root / rel).resolve()
    if not _inside(candidate, root) or candidate == root:
        return _refuse("outside_share", f"{name} is not inside the sandbox share.")
    if not candidate.exists():
        return _refuse("not_found", f"I couldn't find {rel} in the sandbox share.")
    if not candidate.is_file():
        return _refuse("not_a_file", f"{rel} is a folder, not a file. I only copy single files.")
    size = candidate.stat().st_size
    if size > MAX_BYTES:
        return _refuse("too_large", f"{candidate.name} is {size // (1024 * 1024)} MB; the limit is {MAX_BYTES // (1024 * 1024)} MB.")

    try:
        folder_path = _safe_path(str(Path.home() / home_folder))
        _safe_path(str(folder_path / candidate.name))  # deny globs on the final name
    except ValueError as exc:
        return _refuse("path_not_allowed", f"I can't put that there: {exc}")
    folder_path.mkdir(parents=True, exist_ok=True)
    dest = _copy_no_overwrite(candidate, folder_path, candidate.name)
    if dest is None:
        return _refuse("no_free_name", f"Too many copies of {candidate.name} already in {home_folder}.")
    return {
        "ok": True,
        "name": dest.name,
        "dst": str(dest),
        "folder": home_folder,
        "bytes": size,
        "untrusted": True,
        "verified": dest.exists(),
    }
