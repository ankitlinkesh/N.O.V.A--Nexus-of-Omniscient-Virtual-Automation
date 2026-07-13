from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

# Repo root, computed the same way other modules under backend/eva/<pkg>/ do:
# this file is backend/eva/mcp/config.py, so parents[3] is the repo root.
REPO_ROOT = Path(__file__).resolve().parents[3]

_FALSY = {"", "0", "false", "no", "off"}


@dataclass(frozen=True)
class McpServerConfig:
    name: str
    transport: str  # "stdio" or "http"
    command: str = ""
    args: tuple[str, ...] = ()
    url: str = ""
    env: dict[str, str] | None = None
    enabled: bool = True


def mcp_enabled() -> bool:
    """Fail-safe read of EVA_MCP_ENABLED. Unset or any falsy-looking value
    means disabled; the MCP subsystem must never activate implicitly."""
    raw = os.environ.get("EVA_MCP_ENABLED", "")
    return raw.strip().lower() not in _FALSY


def _config_path() -> Path:
    raw = os.environ.get("EVA_MCP_CONFIG_PATH", "config/mcp_servers.json")
    path = Path(raw)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def load_mcp_config() -> list[McpServerConfig]:
    """Load MCP server configs from the configured JSON file. Missing/empty
    file or malformed entries degrade gracefully to an empty/partial list --
    this must never raise for the "no config" default case."""
    path = _config_path()
    if not path.exists():
        return []

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError:
        return []

    if not raw_text.strip():
        return []

    try:
        data = json.loads(raw_text)
    except (ValueError, TypeError):
        return []

    if not isinstance(data, dict):
        return []

    entries = data.get("servers")
    if not isinstance(entries, list):
        return []

    servers: list[McpServerConfig] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        transport = entry.get("transport")
        if not isinstance(name, str) or not name.strip():
            continue
        if transport not in ("stdio", "http"):
            continue
        try:
            args_value = entry.get("args") or ()
            args = tuple(str(a) for a in args_value)
            env_value = entry.get("env")
            env = {str(k): str(v) for k, v in env_value.items()} if isinstance(env_value, dict) else None
            server = McpServerConfig(
                name=name,
                transport=transport,
                command=str(entry.get("command") or ""),
                args=args,
                url=str(entry.get("url") or ""),
                env=env,
                enabled=bool(entry.get("enabled", True)),
            )
        except (TypeError, ValueError, AttributeError):
            continue
        servers.append(server)

    return [s for s in servers if s.enabled]
