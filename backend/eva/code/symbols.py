from __future__ import annotations

from typing import Any

from .indexer import load_code_index


def find_symbol(symbol: str) -> dict[str, Any]:
    needle = " ".join(symbol.strip().split()).lower()
    if not needle:
        return {"ok": False, "symbol": symbol, "error": "Symbol query is empty.", "matches": []}
    index = load_code_index()
    if not index.get("ok"):
        return {"ok": False, "symbol": symbol, "error": index.get("error") or "index unavailable", "matches": []}
    matches: list[dict[str, Any]] = []
    for file in index.get("files", []):
        if not isinstance(file, dict):
            continue
        for entry in file.get("symbols", []):
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "")
            if needle in name.lower():
                matches.append(
                    {
                        "path": file.get("path"),
                        "name": name,
                        "kind": entry.get("kind"),
                        "line": entry.get("line"),
                        "summary": file.get("summary"),
                    }
                )
        for tool in file.get("tool_names", []):
            if needle in str(tool).lower():
                matches.append({"path": file.get("path"), "name": tool, "kind": "tool", "line": 1, "summary": file.get("summary")})
    result = {"ok": True, "symbol": symbol, "matches": matches[:25], "count": len(matches)}
    if index.get("truncated"):
        # Say so instead of letting "no matches" read as "does not exist".
        result["warning"] = "The code index stopped at its file limit, so this search may be missing files."
    return result
