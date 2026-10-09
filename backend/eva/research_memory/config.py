from __future__ import annotations

import os
from pathlib import Path
from ..core.data_paths import data_path


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RESEARCH_MEMORY_DATA_DIR = ROOT / "backend" / "eva" / "data" / "research_memory"


def _data_dir() -> Path:
    override = os.environ.get("EVA_RESEARCH_MEMORY_DIR", "").strip()
    if override:
        return Path(override)
    db_override = os.environ.get("EVA_RESEARCH_MEMORY_DB_PATH", "").strip()
    if db_override:
        return Path(db_override).parent
    return data_path(DEFAULT_RESEARCH_MEMORY_DATA_DIR)


def _db_path() -> Path:
    override = os.environ.get("EVA_RESEARCH_MEMORY_DB_PATH", "").strip()
    if override:
        return Path(override)
    return _data_dir() / "research_memory.sqlite3"


RESEARCH_MEMORY_DATA_DIR = _data_dir()
RESEARCH_MEMORY_DB_PATH = _db_path()

MAX_NOTE_LENGTH = 5000
MAX_SUMMARY_LENGTH = 1500
MAX_SOURCE_TITLE_LENGTH = 300
MAX_URL_LENGTH = 1000
MAX_TAGS = 8

BLOCKED_PRIVATE_PATTERNS = (
    ".env",
    "api_key",
    "apikey",
    "bearer ",
    "cookie",
    "localstorage",
    "sessionstorage",
    "password",
    "private key",
    "logged in",
    "gmail",
    "email inbox",
    "whatsapp chat",
    "token",
)
