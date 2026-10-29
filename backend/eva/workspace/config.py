from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EXCLUDE_DIRS = ".git,.venv,venv,__pycache__,node_modules,backend/eva/data,data"
DEFAULT_EXCLUDE_FILES = ".env,*.key,*.pem,*.sqlite3,*.log,llm_usage_state.json,vision_usage_state.json"
# Secret files are refused whatever EVA_WORKSPACE_EXCLUDE_FILES says. The default
# used to name only ".env", so .env.local (the file that holds the API keys) and
# every .env.* backup were listable, searchable and readable by workspace tools.
_ALWAYS_EXCLUDED_FILES = (".env", ".env.*", "*.key", "*.pem")
_SECRET_FILE_EXCEPTIONS = {".env.example"}


@dataclass(frozen=True)
class WorkspaceConfig:
    root: Path
    enabled: bool
    max_file_bytes: int
    max_files_per_scan: int
    exclude_dirs: tuple[str, ...]
    exclude_files: tuple[str, ...]


class WorkspaceSafetyError(ValueError):
    pass


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip().replace("\\", "/") for item in value.split(",") if item.strip())


def load_workspace_config() -> WorkspaceConfig:
    raw_root = os.environ.get("EVA_WORKSPACE_ROOT", str(PROJECT_ROOT)).strip() or str(PROJECT_ROOT)
    root = Path(raw_root).expanduser().resolve()
    if not root.exists():
        root = PROJECT_ROOT.resolve()
    return WorkspaceConfig(
        root=root,
        enabled=_env_bool("EVA_WORKSPACE_ENABLED", True),
        max_file_bytes=max(1024, _env_int("EVA_WORKSPACE_MAX_FILE_BYTES", 200_000)),
        max_files_per_scan=max(10, _env_int("EVA_WORKSPACE_MAX_FILES_PER_SCAN", 300)),
        exclude_dirs=_split_csv(os.environ.get("EVA_WORKSPACE_EXCLUDE_DIRS", DEFAULT_EXCLUDE_DIRS)),
        exclude_files=_split_csv(os.environ.get("EVA_WORKSPACE_EXCLUDE_FILES", DEFAULT_EXCLUDE_FILES)),
    )


def get_workspace_root() -> Path:
    return load_workspace_config().root


def workspace_status() -> dict[str, object]:
    config = load_workspace_config()
    return {
        "ok": True,
        "enabled": config.enabled,
        "root": str(config.root),
        "max_file_bytes": config.max_file_bytes,
        "max_files_per_scan": config.max_files_per_scan,
        "exclude_dirs": list(config.exclude_dirs),
        "exclude_files": list(config.exclude_files),
        "secrets_visible": False,
    }


def normalize_relative_path(relative_path: str | None) -> str:
    raw = (relative_path or "").strip().strip('"').strip("'").replace("\\", "/")
    while raw.startswith("./"):
        raw = raw[2:]
    return raw.strip("/")


def resolve_workspace_path(relative_path: str | None = "") -> Path:
    config = load_workspace_config()
    root = config.root.resolve()
    rel = normalize_relative_path(relative_path)
    target = (root / rel).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise WorkspaceSafetyError("Path escapes the Eva workspace.") from exc
    return target


def relative_to_root(path: Path, config: WorkspaceConfig | None = None) -> str:
    # ``config`` lets a directory walk load (and resolve) the config once rather
    # than twice per file, which made listing the repo take ~6s.
    config = config or load_workspace_config()
    # Lexical fast path: a path from walking the root, or one resolve_workspace_path
    # already resolved, is under the root as written. Resolving it again cost 1.7s of
    # a 4.6s search (11k calls). Anything else (a "..", a path outside) still resolves;
    # a symlinked file is still resolved and contained when it is read.
    if path.is_absolute() and ".." not in path.parts:
        try:
            return path.relative_to(config.root).as_posix()
        except ValueError:
            pass
    return path.resolve().relative_to(config.root).as_posix()


def _matches_dir_pattern(rel: str, pattern: str) -> bool:
    normalized = rel.strip("/")
    pattern = pattern.strip("/")
    return normalized == pattern or normalized.startswith(pattern + "/") or fnmatch(normalized, pattern)


def is_excluded_dir(path: Path, config: WorkspaceConfig | None = None) -> bool:
    config = config or load_workspace_config()
    rel = relative_to_root(path, config)
    parts = rel.split("/")
    for pattern in config.exclude_dirs:
        if any(part == pattern for part in parts) or _matches_dir_pattern(rel, pattern):
            return True
    return False


def is_excluded_file(path: Path, config: WorkspaceConfig | None = None) -> bool:
    config = config or load_workspace_config()
    rel = relative_to_root(path, config)
    name = path.name
    lowered = name.lower()
    if lowered not in _SECRET_FILE_EXCEPTIONS and any(fnmatch(lowered, pattern) for pattern in _ALWAYS_EXCLUDED_FILES):
        return True
    if any(_matches_dir_pattern(rel, pattern) for pattern in config.exclude_dirs):
        return True
    return any(fnmatch(name, pattern) or fnmatch(rel, pattern) for pattern in config.exclude_files)


def assert_workspace_enabled() -> WorkspaceConfig:
    config = load_workspace_config()
    if not config.enabled:
        raise WorkspaceSafetyError("Workspace skills are disabled.")
    return config


MAX_RANGED_READ_BYTES = 20_000_000


def assert_safe_file(path: Path, *, allow_large: bool = False) -> None:
    config = assert_workspace_enabled()
    if not path.exists():
        raise WorkspaceSafetyError("File does not exist.")
    if not path.is_file():
        raise WorkspaceSafetyError("Path is not a file.")
    if is_excluded_file(path):
        raise WorkspaceSafetyError("File is blocked by Eva workspace safety rules.")
    # A file over the normal cap can still be read in line-range windows (`allow_large`),
    # up to a hard ceiling; every other check above (secrets, excluded files) still applies.
    limit = MAX_RANGED_READ_BYTES if allow_large else config.max_file_bytes
    if path.stat().st_size > limit:
        raise WorkspaceSafetyError("File is too large for safe reading.")
