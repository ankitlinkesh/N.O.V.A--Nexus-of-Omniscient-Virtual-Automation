"""Phase 124: open ANY installed app by name, not just the ~20 in APP_ALIASES.

Resolution order for a name that is not an alias: Start Menu shortcuts, then
installed Store/UWP apps (``Get-StartApps``). The two sources are merged into one
bounded, cached index.

Three rules this module exists to keep:

* **Whole words, never substrings.** The old shortcut search used
  ``name in stem or stem in name``: "word" matched "WordPad" and "Password
  Manager", "obs" matched "Jobs". A candidate matches only when every query word
  appears as a whole word in its name; an exact name always wins.
* **Decline rather than guess** (the Phase 59 grounding idea). Two candidates
  that match about equally produce a question, not a launch.
* **A denylist, because opening is not harmless for every installed thing.**
  Shells, consoles, admin consoles, installers/uninstallers and anything whose
  shortcut targets a script are never launched through this generic path.

Nothing here launches by itself except ``launch_entry``; the index builders and
the target reader are separate functions so tests can fake every lookup layer.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

INDEX_TTL_SECONDS = 300.0
FAILED_INDEX_TTL_SECONDS = 30.0
_START_APPS_TIMEOUT = 20.0
_TARGETS_TIMEOUT = 20.0
_MAX_SHORTCUTS = 4000
_MAX_START_APPS = 3000
_MAX_TARGET_LOOKUPS = 12
# Candidates scoring at least this fraction of the best are "about equal" (a ratio,
# not a difference: "VLC media player" 0.33 vs "... skinned" 0.25 is a clear winner,
# "Release Notes" vs "Sticky Notes" 0.5 vs 0.5 is a tie).
AMBIGUITY_RATIO = 0.8

_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


@dataclass(frozen=True)
class AppEntry:
    name: str
    kind: str  # "lnk" | "uwp"
    ref: str  # shortcut path, or the AppID for a UWP app
    target: str = ""


@dataclass
class AppResolution:
    status: str  # found | ambiguous | denied | none
    entry: AppEntry | None = None
    candidates: list[AppEntry] = field(default_factory=list)
    reason: str = ""

    @property
    def names(self) -> list[str]:
        return [c.name for c in self.candidates]


# --- denylist ---------------------------------------------------------------

_DENY_PHRASES = (
    "command prompt", "windows terminal", "windows powershell", "registry editor",
    "group policy", "task scheduler", "disk management", "computer management",
    "control panel", "administrative tools", "windows tools", "local security policy",
    "component services", "event viewer", "device manager", "windows subsystem",
    "developer command prompt", "developer powershell",
)
_DENY_WORDS = frozenset({
    "cmd", "powershell", "pwsh", "wt", "wsl", "bash", "regedit", "gpedit", "mmc",
    "taskschd", "diskmgmt", "compmgmt", "secpol", "eventvwr", "devmgmt", "services",
})
_INSTALLER_WORDS = frozenset({"setup", "installer", "uninstaller", "uninstall", "install", "installation"})
_DENY_EXES = frozenset({
    "cmd.exe", "powershell.exe", "powershell_ise.exe", "pwsh.exe", "wt.exe",
    "windowsterminal.exe", "wsl.exe", "wslhost.exe", "bash.exe", "regedit.exe",
    "mmc.exe", "control.exe", "conhost.exe", "msiexec.exe", "rundll32.exe",
    "mshta.exe", "wscript.exe", "cscript.exe", "regedt32.exe", "taskschd.msc",
    "services.msc", "diskmgmt.msc", "compmgmt.msc", "gpedit.msc", "secpol.msc",
    "eventvwr.msc", "devmgmt.msc", "eventvwr.exe", "msconfig.exe",
})
_DENY_SCRIPT_EXTS = (".bat", ".cmd", ".ps1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh", ".msc", ".msi")


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def denied_reason(name: str, target: str = "") -> str:
    """Why this name/target must not be opened through the generic launcher ('' if fine)."""
    words = _words(name)
    joined = " ".join(words)
    if any(phrase in joined for phrase in _DENY_PHRASES):
        return "it is a shell or system administration tool"
    if any(w in _INSTALLER_WORDS or "uninstall" in w for w in words):
        return "it is an installer or uninstaller"
    if any(w in _DENY_WORDS for w in words):
        return "it is a shell or system administration tool"
    raw = (target or "").strip().strip('"')
    if raw:
        base = re.split(r"[\\/]", raw)[-1].lower()
        if base.endswith(_DENY_SCRIPT_EXTS):
            return "its shortcut runs a script"
        if base in _DENY_EXES:
            return "it is a shell or system administration tool"
        if base.startswith("unins") or "uninstall" in base or "setup" in base or "installer" in base:
            return "it is an installer or uninstaller"
    return ""


def _entry_denied_reason(entry: AppEntry) -> str:
    reason = denied_reason(entry.name, entry.target)
    if reason:
        return reason
    if entry.kind == "uwp":
        # Path-style AppIDs ({GUID}\WindowsPowerShell\v1.0\powershell.exe) name the exe.
        return denied_reason("", entry.ref) or ("it is a shell or system administration tool" if "windowsterminal" in entry.ref.lower() else "")
    return ""


# --- index sources (each separately patchable in tests) ----------------------

def _iter_shortcuts() -> Iterable[Path]:
    from .desktop import _iter_start_menu_shortcuts

    return _iter_start_menu_shortcuts()


def _ps(script: str, stdin_text: str | None, timeout: float) -> str:
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
         "[Console]::OutputEncoding=[Text.Encoding]::UTF8;[Console]::InputEncoding=[Text.Encoding]::UTF8;" + script],
        input=stdin_text, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, creationflags=_NO_WINDOW,
    )
    return completed.stdout or ""


def _read_start_apps() -> list[tuple[str, str]]:
    """(Name, AppID) pairs from Get-StartApps. Empty on any failure or timeout."""
    try:
        out = _ps("Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress", None, _START_APPS_TIMEOUT)
        data = json.loads(out) if out.strip() else []
    except Exception:
        return []
    if isinstance(data, dict):
        data = [data]
    pairs: list[tuple[str, str]] = []
    for item in data if isinstance(data, list) else []:
        if isinstance(item, dict) and item.get("Name") and item.get("AppID"):
            pairs.append((str(item["Name"]), str(item["AppID"])))
        if len(pairs) >= _MAX_START_APPS:
            break
    return pairs


def _shortcut_targets(paths: list[str]) -> dict[str, str]:
    """TargetPath of each .lnk, read in ONE bounded PowerShell call. {} on failure."""
    if not paths:
        return {}
    script = (
        "$sh=New-Object -ComObject WScript.Shell;"
        "$p=@([Console]::In.ReadToEnd()|ConvertFrom-Json);"
        "$r=@(foreach($x in $p){[pscustomobject]@{p=$x;t=[string]$sh.CreateShortcut($x).TargetPath}});"
        "ConvertTo-Json -Compress -InputObject $r"
    )
    try:
        out = _ps(script, json.dumps(paths[:_MAX_TARGET_LOOKUPS]), _TARGETS_TIMEOUT)
        data = json.loads(out) if out.strip() else []
    except Exception:
        return {}
    if isinstance(data, dict):
        data = [data]
    return {str(i["p"]): str(i.get("t") or "") for i in data if isinstance(i, dict) and i.get("p")}


def _build_index() -> list[AppEntry]:
    entries: list[AppEntry] = []
    try:
        for count, path in enumerate(_iter_shortcuts()):
            if count >= _MAX_SHORTCUTS:
                break
            entries.append(AppEntry(name=path.stem, kind="lnk", ref=str(path)))
    except Exception:
        pass
    for name, appid in _read_start_apps():
        entries.append(AppEntry(name=name, kind="uwp", ref=appid))
    return entries


_cache_lock = threading.Lock()
_cache: dict[str, object] = {"at": 0.0, "ttl": 0.0, "entries": []}


def app_index(*, force: bool = False) -> list[AppEntry]:
    now = time.monotonic()
    with _cache_lock:
        if not force and _cache["entries"] is not None and now - float(_cache["at"]) < float(_cache["ttl"]):
            return list(_cache["entries"])  # type: ignore[arg-type]
    entries = _build_index()
    with _cache_lock:
        _cache.update(at=time.monotonic(), ttl=INDEX_TTL_SECONDS if entries else FAILED_INDEX_TTL_SECONDS, entries=entries)
    return list(entries)


def invalidate_app_index() -> None:
    with _cache_lock:
        _cache.update(at=0.0, ttl=0.0, entries=[])


# --- matching ---------------------------------------------------------------

def _query_words(query: str) -> list[str]:
    words = _words(query)
    while len(words) > 1 and words[0] in {"the", "my"}:
        words = words[1:]
    while len(words) > 1 and words[-1] in {"app", "application", "program"}:
        words = words[:-1]
    return words


def _score(qwords: list[str], name: str) -> float:
    """1.0 for an exact name; len(q)/len(name) when every query word is a whole word
    of the name; 0 otherwise. Never a substring test."""
    nwords = _words(name)
    if not qwords or not nwords:
        return 0.0
    if nwords == qwords:
        return 1.0
    if set(qwords) <= set(nwords):
        return len(qwords) / len(nwords)
    return 0.0


def _matches(query: str, entries: list[AppEntry]) -> list[tuple[float, AppEntry]]:
    qwords = _query_words(query)
    scored = [(s, e) for e in entries for s in (_score(qwords, e.name),) if s > 0]
    # Same name from both sources (Discord.lnk and a StartApps "Discord"): keep one,
    # preferring the shortcut.
    best: dict[tuple[str, ...], tuple[float, AppEntry]] = {}
    for s, e in scored:
        key = tuple(_words(e.name))
        cur = best.get(key)
        if cur is None or (cur[1].kind == "uwp" and e.kind == "lnk"):
            best[key] = (s, e)
    return sorted(best.values(), key=lambda item: (-item[0], item[1].name.lower()))


def resolve_installed_app(query: str, *, entries: list[AppEntry] | None = None) -> AppResolution:
    clean = (query or "").strip()
    if not _words(clean):
        return AppResolution("none", reason="empty")
    reason = denied_reason(clean)
    if reason:
        return AppResolution("denied", reason=reason)
    index = entries if entries is not None else app_index()
    matched = _matches(clean, index)
    if not matched:
        return AppResolution("none")

    # Read shortcut targets for the (few) name matches only, then apply the denylist.
    lnk_paths = [e.ref for _, e in matched if e.kind == "lnk"]
    targets = _shortcut_targets(lnk_paths) if lnk_paths else {}
    allowed: list[tuple[float, AppEntry]] = []
    first_denial = ""
    for s, e in matched:
        e = AppEntry(e.name, e.kind, e.ref, targets.get(e.ref, ""))
        why = _entry_denied_reason(e)
        if why:
            first_denial = first_denial or why
            continue
        allowed.append((s, e))
    if not allowed:
        return AppResolution("denied", candidates=[e for _, e in matched], reason=first_denial)

    top_score = allowed[0][0]
    close = [e for s, e in allowed if s >= top_score * AMBIGUITY_RATIO]
    if top_score < 1.0 and len(close) > 1:
        return AppResolution("ambiguous", candidates=close[:6])
    return AppResolution("found", entry=allowed[0][1], candidates=[allowed[0][1]])


# --- launching + verification hints -----------------------------------------

_resolved_names: dict[str, list[str]] = {}


def _remember(query: str, entry: AppEntry) -> None:
    """Window titles are not the typed name ("Visual Studio Code" vs "vscode"), so
    the verifier needs the resolved display name and exe to look for."""
    hints = [entry.name]
    base = re.split(r"[\\/]", entry.target.strip('"'))[-1] if entry.target else ""
    if base.lower().endswith(".exe") and len(base) > 4:
        hints.append(base[:-4])
    _resolved_names[" ".join(_words(query))] = hints


def resolved_window_queries(query: str) -> list[str]:
    return list(_resolved_names.get(" ".join(_words(query)), []))


def _launch_shortcut(path: str) -> None:
    os.startfile(path)  # type: ignore[attr-defined]


def _launch_uwp(appid: str) -> None:
    subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{appid}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def launch_entry(entry: AppEntry) -> None:
    if entry.kind == "lnk":
        _launch_shortcut(entry.ref)
    else:
        _launch_uwp(entry.ref)


def open_installed_app(query: str) -> str:
    """Resolve and launch an installed app. Raises ValueError (message is user-facing)
    when it is refused, ambiguous or not installed -- never launches in those cases."""
    res = resolve_installed_app(query)
    if res.status == "denied":
        raise ValueError(
            f"I won't open {query.strip()} through the generic app launcher: {res.reason}. "
            "That is a shell, admin or installer tool; start it yourself if you really mean it."
        )
    if res.status == "ambiguous":
        raise ValueError(f"I found several: {', '.join(res.names)}. Which one do you want?")
    if res.status == "none" or res.entry is None:
        raise ValueError(f"I couldn't find an installed app called {query.strip()} on this laptop.")
    _remember(query, res.entry)
    launch_entry(res.entry)
    return f"Opening {res.entry.name}."
