from __future__ import annotations

import ast
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

from ..workspace.config import get_workspace_root, load_workspace_config, resolve_workspace_path
from ..workspace.indexer import safe_list_files
from ..workspace.reader import safe_read_file
from ..core.data_paths import data_path


SAFE_CODE_EXTENSIONS = {".py", ".js", ".html", ".css", ".md", ".json", ".toml", ".yaml", ".yml"}
INDEX_PATH = Path(__file__).resolve().parents[1] / "data" / "code_index.json"
SCAN_ROOTS = (
    "",
    "backend/eva/api",
    "backend/eva/agent",
    "backend/eva/browser",
    "backend/eva/code",
    "backend/eva/core",
    "backend/eva/desktop",
    "backend/eva/llm",
    "backend/eva/research",
    "backend/eva/tools",
    "backend/eva/vision",
    "backend/eva/workspace",
    "frontend",
    "scripts",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _language(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return {
        ".py": "python",
        ".js": "javascript",
        ".html": "html",
        ".css": "css",
        ".md": "markdown",
        ".json": "json",
        ".toml": "toml",
        ".yaml": "yaml",
        ".yml": "yaml",
    }.get(suffix, "text")


def _score_text(text: str, terms: list[str]) -> int:
    lowered = text.lower()
    return sum(1 for term in terms if term in lowered)


def _decorator_name(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _extract_python(path: str, content: str) -> dict[str, Any]:
    symbols: list[dict[str, Any]] = []
    imports: list[str] = []
    endpoints: list[dict[str, Any]] = []
    tool_names: list[str] = []
    models: list[dict[str, Any]] = []
    try:
        tree = ast.parse(content)
    except SyntaxError:
        tree = None

    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imports.append(module)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                decorators = [_decorator_name(item) for item in node.decorator_list]
                kind = "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function"
                symbols.append({"name": node.name, "kind": kind, "line": node.lineno, "decorators": decorators})
                for deco in decorators:
                    match = re.search(r"\.(get|post|put|patch|delete)\((['\"])(.*?)\2", deco)
                    if match:
                        endpoints.append({"method": match.group(1).upper(), "path": match.group(3), "function": node.name, "line": node.lineno})
            elif isinstance(node, ast.ClassDef):
                decorators = [_decorator_name(item) for item in node.decorator_list]
                bases = [_decorator_name(item) for item in node.bases]
                symbols.append({"name": node.name, "kind": "class", "line": node.lineno, "bases": bases, "decorators": decorators})
                if "dataclass" in " ".join(decorators).lower() or any(base.endswith("BaseModel") or base == "BaseModel" for base in bases):
                    models.append({"name": node.name, "line": node.lineno, "kind": "dataclass_or_model"})

    for match in re.finditer(r"['\"]([A-Za-z0-9_]+)['\"]\s*:\s*ToolSpec\(", content):
        tool_names.append(match.group(1))
    for match in re.finditer(r"name\s*=\s*['\"]([A-Za-z0-9_]+)['\"]", content):
        if "ToolSpec" in content[max(0, match.start() - 120): match.end() + 120]:
            tool_names.append(match.group(1))

    return {
        "symbols": symbols,
        "imports": sorted(set(item for item in imports if item)),
        "endpoints": endpoints,
        "tool_names": sorted(set(tool_names)),
        "models": models,
    }


def _extract_javascript(content: str) -> dict[str, Any]:
    symbols: list[dict[str, Any]] = []
    for match in re.finditer(r"\b(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(", content):
        symbols.append({"name": match.group(1), "kind": "function", "line": content[: match.start()].count("\n") + 1})
    for match in re.finditer(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>", content):
        symbols.append({"name": match.group(1), "kind": "function", "line": content[: match.start()].count("\n") + 1})
    return {
        "symbols": symbols,
        "imports": re.findall(r"from\s+['\"]([^'\"]+)['\"]|import\s+['\"]([^'\"]+)['\"]", content),
        "endpoints": [{"url": item, "line": content[: content.find(item)].count("\n") + 1} for item in sorted(set(re.findall(r"fetch\(\s*['\"]([^'\"]+)['\"]", content)))],
        "tool_names": [],
        "dom_selectors": sorted(set(re.findall(r"querySelector(?:All)?\(\s*['\"]([^'\"]+)['\"]|getElementById\(\s*['\"]([^'\"]+)['\"]", content))),
        "event_listeners": sorted(set(re.findall(r"addEventListener\(\s*['\"]([^'\"]+)['\"]", content))),
        "voice_handlers": bool(re.search(r"speechSynthesis|SpeechRecognition|webkitSpeechRecognition|mic|voice", content, re.IGNORECASE)),
    }


def _extract_markup_or_style(content: str) -> dict[str, Any]:
    ids = sorted(set(re.findall(r"\bid=['\"]([^'\"]+)['\"]|#([A-Za-z0-9_-]+)", content)))
    classes = sorted(set(re.findall(r"\bclass=['\"]([^'\"]+)['\"]|\.([A-Za-z0-9_-]+)", content)))
    return {
        "symbols": [],
        "imports": [],
        "endpoints": [],
        "tool_names": [],
        "ids": [" ".join(item).strip() for item in ids if " ".join(item).strip()],
        "classes": [" ".join(item).strip() for item in classes if " ".join(item).strip()],
        "scripts": re.findall(r"<script[^>]+src=['\"]([^'\"]+)['\"]", content, re.IGNORECASE),
        "styles": re.findall(r"<link[^>]+href=['\"]([^'\"]+)['\"]", content, re.IGNORECASE),
    }


def _rough_summary(rel: str, extracted: dict[str, Any]) -> str:
    parts: list[str] = []
    if extracted.get("symbols"):
        names = [str(item.get("name")) for item in extracted["symbols"][:6] if isinstance(item, dict)]
        parts.append("symbols: " + ", ".join(names))
    if extracted.get("endpoints"):
        parts.append(f"{len(extracted['endpoints'])} endpoint/fetch reference(s)")
    if extracted.get("tool_names"):
        parts.append("tools: " + ", ".join(extracted["tool_names"][:8]))
    if not parts:
        parts.append(f"{_language(rel)} file")
    return "; ".join(parts)[:500]


def _extract_file(rel: str, content: str) -> dict[str, Any]:
    suffix = Path(rel).suffix.lower()
    if suffix == ".py":
        extracted = _extract_python(rel, content)
    elif suffix == ".js":
        extracted = _extract_javascript(content)
    elif suffix in {".html", ".css"}:
        extracted = _extract_markup_or_style(content)
    else:
        extracted = {"symbols": [], "imports": [], "endpoints": [], "tool_names": []}
    extracted["summary"] = _rough_summary(rel, extracted)
    return extracted


def build_code_index() -> dict[str, Any]:
    config = load_workspace_config()
    listed_files: dict[str, dict[str, Any]] = {}
    list_errors: list[str] = []
    list_skipped = 0
    for root in SCAN_ROOTS:
        listed = safe_list_files(root, limit=config.max_files_per_scan)
        if not listed.get("ok"):
            if root:
                list_errors.append(f"{root}: {listed.get('error')}")
            elif not listed_files:
                return {"ok": False, "error": listed.get("error") or "workspace list failed", "files": []}
            continue
        list_skipped += int(listed.get("skipped") or 0)
        for item in listed.get("files", []):
            if isinstance(item, dict) and item.get("path"):
                listed_files[str(item["path"])] = item

    files: list[dict[str, Any]] = []
    skipped = 0
    for item in listed_files.values():
        if not isinstance(item, dict):
            continue
        rel = str(item.get("path") or "")
        if Path(rel).suffix.lower() not in SAFE_CODE_EXTENSIONS:
            skipped += 1
            continue
        read = safe_read_file(rel, max_chars=config.max_file_bytes)
        if not read.get("ok"):
            skipped += 1
            continue
        content = str(read.get("content") or "")
        extracted = _extract_file(rel, content)
        files.append(
            {
                "path": rel,
                "language": _language(rel),
                "size": int(read.get("size") or 0),
                "modified_at": read.get("modified_at"),
                "symbols": extracted.get("symbols", []),
                "imports": extracted.get("imports", []),
                "endpoints": extracted.get("endpoints", []),
                "tool_names": extracted.get("tool_names", []),
                "models": extracted.get("models", []),
                "dom_selectors": extracted.get("dom_selectors", []),
                "event_listeners": extracted.get("event_listeners", []),
                "voice_handlers": extracted.get("voice_handlers", False),
                "ids": extracted.get("ids", []),
                "classes": extracted.get("classes", []),
                "scripts": extracted.get("scripts", []),
                "styles": extracted.get("styles", []),
                "summary": extracted.get("summary", ""),
            }
        )

    payload = {
        "ok": True,
        "root": str(config.root),
        "index_path": str(data_path(INDEX_PATH)),
        "indexed_at": _now(),
        "indexed_files": len(files),
        "skipped": skipped + list_skipped,
        "list_errors": list_errors,
        "safe_extensions": sorted(SAFE_CODE_EXTENSIONS),
        "files": files,
        "secrets_indexed": False,
    }
    index_path = data_path(INDEX_PATH)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def load_code_index(*, auto_build: bool = True) -> dict[str, Any]:
    index_path = data_path(INDEX_PATH)
    if not index_path.exists():
        return build_code_index() if auto_build else {"ok": False, "error": "Code index has not been built.", "files": []}
    try:
        return json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return build_code_index() if auto_build else {"ok": False, "error": "Code index could not be read.", "files": []}


def code_status() -> dict[str, Any]:
    index = load_code_index(auto_build=False)
    root = get_workspace_root()
    if not index.get("ok"):
        return {
            "ok": True,
            "indexed": False,
            "root": str(root),
            "index_path": str(data_path(INDEX_PATH)),
            "indexed_files": 0,
            "last_indexed_at": None,
            "safe_extensions": sorted(SAFE_CODE_EXTENSIONS),
            "secrets_indexed": False,
        }
    return {
        "ok": True,
        "indexed": True,
        "root": str(root),
        "index_path": str(data_path(INDEX_PATH)),
        "indexed_files": int(index.get("indexed_files") or len(index.get("files") or [])),
        "last_indexed_at": index.get("indexed_at"),
        "safe_extensions": index.get("safe_extensions") or sorted(SAFE_CODE_EXTENSIONS),
        "secrets_indexed": False,
    }


def search_code(query: str, limit: int = 10) -> dict[str, Any]:
    terms = [term.lower() for term in re.findall(r"[A-Za-z0-9_./-]+", query) if len(term) > 1]
    if not terms:
        return {"ok": False, "query": query, "error": "Search query is empty.", "matches": []}
    index = load_code_index()
    if not index.get("ok"):
        return {"ok": False, "query": query, "error": index.get("error") or "index unavailable", "matches": []}
    matches: list[dict[str, Any]] = []
    for file in index.get("files", []):
        if not isinstance(file, dict):
            continue
        rel = str(file.get("path") or "")
        blob = " ".join(
            [
                rel,
                str(file.get("summary") or ""),
                " ".join(str(item.get("name") or "") for item in file.get("symbols", []) if isinstance(item, dict)),
                " ".join(str(item) for item in file.get("imports", [])),
                " ".join(str(item) for item in file.get("tool_names", [])),
            ]
        )
        score = _score_text(blob, terms)
        if any(term in rel.lower() for term in terms):
            score += 4
        if score <= 0:
            continue
        matches.append(
            {
                "path": rel,
                "language": file.get("language"),
                "summary": file.get("summary"),
                "symbols": file.get("symbols", [])[:8],
                "tool_names": file.get("tool_names", [])[:8],
                "score": score,
            }
        )
    matches.sort(key=lambda item: (-int(item.get("score") or 0), str(item.get("path") or "")))
    return {"ok": True, "query": query, "matches": matches[: max(1, min(int(limit or 10), 50))], "index_files": len(index.get("files") or [])}


def safe_code_read(path: str) -> dict[str, Any]:
    rel = str(path).strip().replace("\\", "/")
    suffix = Path(rel).suffix.lower()
    if suffix not in SAFE_CODE_EXTENSIONS:
        return {"ok": False, "path": path, "error": "File type is not part of the safe code intelligence allowlist.", "refused": True}
    # resolve first to force workspace traversal checks through the shared safety layer.
    resolve_workspace_path(rel)
    return safe_read_file(rel, max_chars=80_000)
