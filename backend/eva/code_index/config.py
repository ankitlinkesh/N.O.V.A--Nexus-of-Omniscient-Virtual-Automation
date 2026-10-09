from __future__ import annotations

import os
from fnmatch import fnmatch
from pathlib import Path
from ..core.data_paths import data_path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "code_index"

SAFE_EXTENSIONS = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".toml",
    ".ts",
    ".txt",
    ".yaml",
    ".yml",
}

SKIP_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".next",
    "dist",
    "build",
    "coverage",
    "logs",
    "screenshots",
    "checkpoints",
    "models",
    "bin",
}

SKIP_PATH_PREFIXES = {
    "backend/eva/data",
    "backend/data/checkpoints",
    "data",
    "frontend/assets",
}

SKIP_FILE_PATTERNS = {
    ".env",
    ".env.*",
    "*.env",
    "*.local",
    "*.sqlite3",
    "*.db",
    "*.log",
    "*.pem",
    "*.key",
    "*.pfx",
    "*.p12",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.webp",
    "*.mp4",
    "*.mov",
    "*.zip",
}

SENSITIVE_NAME_MARKERS = (
    "secret",
    "token",
    "credential",
    "password",
    "cookie",
    "session",
)


def project_root() -> Path:
    raw = os.environ.get("EVA_CODE_INDEX_ROOT") or os.environ.get("EVA_WORKSPACE_ROOT")
    if raw:
        candidate = Path(raw).expanduser().resolve()
        if candidate.exists():
            return candidate
    return PROJECT_ROOT.resolve()


def data_dir() -> Path:
    raw = os.environ.get("EVA_CODE_INDEX_DATA_DIR")
    return Path(raw).expanduser().resolve() if raw else data_path(DEFAULT_DATA_DIR).resolve()


def index_path() -> Path:
    return data_dir() / "index.json"


def relative_path(path: Path, root: Path | None = None) -> str:
    base = (root or project_root()).resolve()
    return path.resolve().relative_to(base).as_posix()


def normalize_relative_path(path: str | None) -> str:
    value = str(path or "").strip().strip('"').strip("'").replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value.strip("/")


def resolve_safe_path(path: str | None) -> tuple[bool, Path | None, str]:
    root = project_root()
    rel = normalize_relative_path(path)
    target = (root / rel).resolve()
    try:
        resolved_rel = relative_path(target, root)
    except ValueError:
        return False, None, "Path escapes the Eva workspace."
    if is_skipped_path(resolved_rel, target):
        return False, None, "Path is blocked by Eva code-index safety rules."
    return True, target, ""


def is_skipped_path(rel: str, path: Path) -> bool:
    normalized = rel.strip("/").replace("\\", "/")
    parts = set(normalized.split("/"))
    name = path.name.lower()
    if any(part in SKIP_DIR_NAMES for part in parts):
        return True
    if any(normalized == prefix or normalized.startswith(prefix + "/") for prefix in SKIP_PATH_PREFIXES):
        return True
    if path.is_file() and is_skipped_file_name(name, normalized):
        return True
    return False


def is_skipped_file_name(name: str, rel: str) -> bool:
    lowered = name.lower()
    if lowered.startswith(".env"):
        return True
    if any(marker in lowered for marker in SENSITIVE_NAME_MARKERS):
        return True
    return any(fnmatch(lowered, pattern) or fnmatch(rel.lower(), pattern) for pattern in SKIP_FILE_PATTERNS)
