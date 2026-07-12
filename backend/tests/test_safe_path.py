"""Executable spec for backend/eva/tools/safe_file_tools.py's _safe_path().

Current implementation:

    def _safe_path(path: str) -> Path:
        target = Path(path).expanduser().resolve()
        home = Path.home().resolve()
        root = SAFE_ROOT.resolve()
        if not (str(target).startswith(str(root)) or str(target).startswith(str(home))):
            raise ValueError("File path is outside the allowed local roots.")
        return target

Two bugs this locks in a fix for:
  1. String-prefix comparison instead of Path.is_relative_to -- a sibling
     directory whose name merely starts with the home dir's name (e.g.
     C:\\Users\\HP-evil\\...) passes the `str(target).startswith(str(home))`
     check even though it is not inside home at all.
  2. The entire home directory is allowed, not just
     Documents/Desktop/Downloads under it -- so things like ~/.ssh/id_rsa or
     ~/AppData/Local/... are currently readable/writable/deletable by file
     tools.

Target design: allowed roots are SAFE_ROOT (project root) and
Path.home()/"Documents", /"Desktop", /"Downloads", checked with
Path.is_relative_to. Denied regardless of root: any path with a `.git` path
component, or a basename matching .env* / *.secret* / *.sqlite3 / id_rsa*.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.eva.tools.safe_file_tools import SAFE_ROOT, _safe_path


def test_sibling_prefix_of_home_is_rejected():
    home = Path.home().resolve()
    evil = Path(str(home) + "-evil") / "x.txt"
    with pytest.raises(ValueError):
        _safe_path(str(evil))


def test_ssh_private_key_under_home_is_rejected():
    target = Path.home() / ".ssh" / "id_rsa"
    with pytest.raises(ValueError):
        _safe_path(str(target))


def test_appdata_local_under_home_is_rejected():
    target = Path.home() / "AppData" / "Local" / "x.txt"
    with pytest.raises(ValueError):
        _safe_path(str(target))


def test_dotenv_in_project_root_is_rejected():
    target = SAFE_ROOT / ".env"
    with pytest.raises(ValueError):
        _safe_path(str(target))


def test_git_directory_segment_is_rejected():
    target = SAFE_ROOT / ".git" / "config"
    with pytest.raises(ValueError):
        _safe_path(str(target))


def test_secret_like_basename_is_rejected():
    target = SAFE_ROOT / "notes.secret.txt"
    with pytest.raises(ValueError):
        _safe_path(str(target))


def test_sqlite3_db_basename_is_rejected():
    target = SAFE_ROOT / "data" / "eva.sqlite3"
    with pytest.raises(ValueError):
        _safe_path(str(target))


def test_id_rsa_basename_is_rejected_even_outside_ssh_dir():
    target = SAFE_ROOT / "id_rsa_backup"
    with pytest.raises(ValueError):
        _safe_path(str(target))


def test_project_docs_path_is_allowed():
    target = SAFE_ROOT / "docs" / "x.md"
    resolved = _safe_path(str(target))
    assert resolved == target.resolve()


def test_home_documents_path_is_allowed():
    target = Path.home() / "Documents" / "x.txt"
    resolved = _safe_path(str(target))
    assert resolved == target.resolve()
