"""Pin each MCP tool's description, so a server cannot change a tool after you have trusted it.

An MCP server tells the model what each tool is for in free text, and that text is read by the
model as if it were instructions ("tool poisoning"). A server can also look harmless when first
trusted and later swap a tool's description for a hostile one (a "rug pull"). Pinning a server's
NAME (``trust.py``) does not stop either, because the name stays the same.

This records a SHA-256 fingerprint of each tool's name, description and input schema the first
time it is seen (trust on first use) and then, on every later load:

  * unchanged        -> the tool is registered as before;
  * changed          -> the tool is NOT registered, and the change is reported, until you
                        re-approve it (``repin``) or delete its entry;
  * new but suspect  -> a tool whose description carries invisible characters or injection
                        markers is quarantined at first sight, and is never pinned.

It only ever REMOVES tools from what is offered; it cannot add one or loosen the gate (every MCP
tool is still confirm-class). Off with ``EVA_MCP_PIN_TOOLS=0``; the pin file is ``mcp_tool_pins.json``
in the data root (``EVA_MCP_PINS_PATH`` overrides it).
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from ..core.data_paths import data_path
from ..security.visible_text import reveal


def pinning_enabled() -> bool:
    return os.environ.get("EVA_MCP_PIN_TOOLS", "1").strip().lower() not in {"0", "false", "no", "off"}


def pins_path() -> Path:
    override = os.environ.get("EVA_MCP_PINS_PATH", "").strip()
    return Path(override) if override else data_path(Path("mcp_tool_pins.json"))


def fingerprint(tool: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"name": tool.get("name"), "description": tool.get("description") or "", "input_schema": tool.get("input_schema")},
        sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load() -> dict[str, dict[str, str]]:
    try:
        data = json.loads(pins_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(pins: dict[str, dict[str, str]]) -> None:
    path = pins_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pins, indent=2, sort_keys=True), encoding="utf-8")


def _suspicious(description: str) -> str:
    """Why a tool description should not be trusted at first sight, or ""."""
    _, hidden = reveal(description)
    if hidden:
        return f"its description contains {hidden} invisible or unusual character(s)"
    try:
        from ..threat_defense.taint import assess

        verdict = assess(description, "mcp_result")
        if verdict.injection_detected and str(verdict.severity).lower() in {"high", "critical"}:
            return "its description looks like instructions to the model (" + ", ".join(verdict.categories[:3]) + ")"
    except Exception:
        return ""
    return ""


def review(server: str, tool: dict[str, Any]) -> tuple[str, str]:
    """(status, reason): status is ``ok``, ``new`` (pinned now), ``changed`` or ``quarantined``.

    ``ok`` and ``new`` may be registered; ``changed`` and ``quarantined`` must not be.
    """
    if not pinning_enabled():
        return "ok", ""
    key = f"{server}.{tool.get('name')}"
    digest = fingerprint(tool)
    pins = _load()
    known = pins.get(key)
    if known is None:
        why = _suspicious(str(tool.get("description") or ""))
        if why:
            return "quarantined", why
        pins[key] = {"sha256": digest}
        _save(pins)
        return "new", "pinned on first use"
    if known.get("sha256") == digest:
        return "ok", ""
    return "changed", "its description or schema changed since you first trusted it"


def repin(server: str, tool: dict[str, Any]) -> str:
    """Accept the tool's CURRENT definition as the trusted one. Returns the new digest."""
    pins = _load()
    digest = fingerprint(tool)
    pins[f"{server}.{tool.get('name')}"] = {"sha256": digest}
    _save(pins)
    return digest
