"""Shared source checks for verifiers: find real imports and calls, not words.

Older verifiers proved "no subprocess / no network / no pip install" with substring
scans over lower-cased source. Those fail on prose ("no verifier subprocesses"),
help text ("`pip install uiautomation`"), comments ("ordinary requests.") and
unrelated names ("ai_os.system_map"), so the scripts went red and were left out of
the suite, which meant the invariant was checked by nothing. These helpers parse
the source and report only code that could actually do the forbidden thing.

Exceptions are explicit: ``allow`` maps a repo-relative path to the reason it may
do so, and every exception is reported back so a verifier can show it.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]

SHELL_MODULES = ("subprocess",)
SHELL_CALLS = ("os.system", "os.popen", "os.spawnl", "os.spawnv", "os.execv", "os.execl", "pty.spawn")
NETWORK_MODULES = ("requests", "httpx", "urllib.request", "urllib3", "aiohttp", "http.client")
BROWSER_DRIVER_MODULES = ("playwright", "pyautogui", "selenium")
_PROCESS_RUNNERS = {"run", "call", "check_call", "check_output", "Popen", "system", "popen", "create_subprocess_exec", "create_subprocess_shell"}
_JS_RUNNERS = {"evaluate", "evaluate_handle", "execute_script", "add_init_script", "run_js"}


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    what: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.what}"


def python_files(paths: Iterable[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        path = Path(path)
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(path.rglob("*.py")))
    return files


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _dotted(node: ast.AST) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def _strings(node: ast.AST) -> list[str]:
    return [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _matches(module: str, wanted: Iterable[str]) -> bool:
    return any(module == name or module.startswith(name + ".") for name in wanted)


def _scan_file(path: Path, *, modules: tuple[str, ...], calls: tuple[str, ...], pip: bool, env_local: bool, js_secrets: bool) -> list[Finding]:
    rel = _rel(path)
    tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="replace"), filename=str(path))
    wanted_modules = modules + (("pip",) if pip else ())
    found: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _matches(alias.name, wanted_modules):
                    found.append(Finding(rel, node.lineno, f"imports {alias.name}"))
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            if _matches(node.module, wanted_modules):
                found.append(Finding(rel, node.lineno, f"imports from {node.module}"))
            for alias in node.names:
                full = f"{node.module}.{alias.name}"
                if full in calls:
                    found.append(Finding(rel, node.lineno, f"imports {full}"))
        elif isinstance(node, ast.Call):
            name = _dotted(node.func)
            if name and name in calls:
                found.append(Finding(rel, node.lineno, f"calls {name}"))
            short = name.rsplit(".", 1)[-1] if name else ""
            args = list(node.args) + [kw.value for kw in node.keywords]
            text = " ".join(s for arg in args for s in _strings(arg)).lower()
            if pip and short in _PROCESS_RUNNERS and "pip" in text and "install" in text:
                found.append(Finding(rel, node.lineno, f"runs a package install via {name}"))
            if env_local and short == "open" and ".env.local" in text:
                found.append(Finding(rel, node.lineno, "opens .env.local"))
            if js_secrets and short in _JS_RUNNERS and ("document.cookie" in text or "localstorage" in text):
                found.append(Finding(rel, node.lineno, f"reads browser secrets via {name}"))
    return found


def scan(
    paths: Iterable[Path],
    *,
    modules: Iterable[str] = (),
    calls: Iterable[str] = (),
    pip: bool = False,
    env_local: bool = False,
    js_secrets: bool = False,
    allow: Mapping[str, str] | None = None,
) -> tuple[list[Finding], list[str]]:
    """Return (violations, allowed_notes). ``allow`` exempts whole files by repo path."""
    allow = dict(allow or {})
    violations: list[Finding] = []
    notes: list[str] = []
    for path in python_files(paths):
        found = _scan_file(path, modules=tuple(modules), calls=tuple(calls), pip=pip, env_local=env_local, js_secrets=js_secrets)
        rel = _rel(path)
        if found and rel in allow:
            notes.append(f"{rel}: allowed ({allow[rel]})")
            continue
        violations.extend(found)
    return violations, notes


def no_shell(paths: Iterable[Path], allow: Mapping[str, str] | None = None) -> tuple[list[Finding], list[str]]:
    return scan(paths, modules=SHELL_MODULES, calls=SHELL_CALLS, allow=allow)


def no_package_install(paths: Iterable[Path], allow: Mapping[str, str] | None = None) -> tuple[list[Finding], list[str]]:
    return scan(paths, pip=True, allow=allow)


def no_network(paths: Iterable[Path], allow: Mapping[str, str] | None = None) -> tuple[list[Finding], list[str]]:
    return scan(paths, modules=NETWORK_MODULES, allow=allow)


def no_browser_drivers(paths: Iterable[Path], allow: Mapping[str, str] | None = None) -> tuple[list[Finding], list[str]]:
    return scan(paths, modules=BROWSER_DRIVER_MODULES, allow=allow)


def no_env_local_read(paths: Iterable[Path]) -> tuple[list[Finding], list[str]]:
    return scan(paths, env_local=True)


def no_browser_secret_reads(paths: Iterable[Path]) -> tuple[list[Finding], list[str]]:
    return scan(paths, js_secrets=True)


# The one reviewed shell use in the runtime tree.
TOAST_EXCEPTION = {
    "backend/eva/runtime/toast.py": "Phase 126 toast: constant PowerShell script, title/body passed as env vars, never spliced",
}
