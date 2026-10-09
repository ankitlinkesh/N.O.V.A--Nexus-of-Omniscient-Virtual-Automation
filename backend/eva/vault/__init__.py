"""Vault -- an encrypted store for saved personal info and credentials.

Windows DPAPI (see :mod:`eva.vault.dpapi`) ties every stored value to this
Windows user account: no passphrase, no unlock step, and the vault file is
useless if copied to another machine or account. Values are encrypted
per-entry (see :mod:`eva.vault.store`) so a form can be auto-filled without
the value ever passing through the LLM or landing on disk in plaintext.

Off by default, like the rest of NOVA's higher-privilege surfaces (compare
``eva.proactivity``). Set ``EVA_VAULT_ENABLED=1`` to turn it on.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from .store import Vault, VaultEntry
from ..core.data_paths import data_path

_ABSENT = {"", "0", "false", "no", "off"}

_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "vault"
_DEFAULT_VAULT_PATH = _DATA_DIR / "vault.json"


def vault_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Whether the vault is active (default OFF, empty == off)."""
    env = environ if environ is not None else os.environ
    return env.get("EVA_VAULT_ENABLED", "").strip().lower() not in _ABSENT


def vault_path(environ: Mapping[str, str] | None = None) -> Path:
    """The vault file path: ``EVA_VAULT_PATH`` override, else the repo default."""
    env = environ if environ is not None else os.environ
    override = env.get("EVA_VAULT_PATH", "").strip()
    return Path(override) if override else data_path(_DEFAULT_VAULT_PATH)


def open_default_vault(environ: Mapping[str, str] | None = None) -> Vault | None:
    """Open the vault at its configured path, or ``None`` when disabled or broken."""
    try:
        if not vault_enabled(environ):
            return None
        return Vault(vault_path(environ))
    except Exception:
        return None


__all__ = [
    "Vault",
    "VaultEntry",
    "vault_enabled",
    "vault_path",
    "open_default_vault",
]
