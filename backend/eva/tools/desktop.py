from __future__ import annotations

import os
import platform
import shutil
import subprocess
import urllib.parse
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .tavily_search import tavily_search_sync


@dataclass(frozen=True)
class DesktopStatus:
    os_name: str
    shell: str
    cwd: str


APP_ALIASES: dict[str, tuple[str, ...]] = {
    "calculator": ("calc.exe", "calculator"),
    "chrome": ("chrome.exe", "chrome"),
    "cmd": ("cmd.exe", "command prompt"),
    "codex": ("Codex.exe", "codex"),
    "discord": ("Discord.exe", "discord"),
    "edge": ("msedge.exe", "edge", "microsoft edge"),
    "explorer": ("explorer.exe", "file explorer"),
    "notepad": ("notepad.exe", "notepad"),
    "paint": ("mspaint.exe", "paint"),
    "powershell": ("powershell.exe", "powershell"),
    "settings": ("ms-settings:", "settings"),
    "spotify": ("Spotify.exe", "spotify"),
    "task manager": ("taskmgr.exe", "task manager"),
    "terminal": ("wt.exe", "terminal", "windows terminal"),
    "vscode": ("Code.exe", "code", "vs code", "visual studio code"),
    "whatsapp": ("WhatsApp.exe", "whatsapp"),
    "word": ("WINWORD.EXE", "word", "microsoft word"),
    "excel": ("EXCEL.EXE", "excel", "microsoft excel"),
    "powerpoint": ("POWERPNT.EXE", "powerpoint", "microsoft powerpoint"),
}

SPECIAL_FOLDERS: dict[str, Path] = {
    "desktop": Path.home() / "Desktop",
    "documents": Path.home() / "Documents",
    "downloads": Path.home() / "Downloads",
    "pictures": Path.home() / "Pictures",
    "videos": Path.home() / "Videos",
    "music": Path.home() / "Music",
    "eva": Path(__file__).resolve().parents[3],
    "eva folder": Path(__file__).resolve().parents[3],
}

DEFAULT_CLOSE_APP_ALLOWLIST: tuple[str, ...] = (
    "calculator",
    "chrome",
    "discord",
    "edge",
    "notepad",
    "spotify",
    "vscode",
    "codex",
    "terminal",
    "powershell",
    "word",
    "excel",
    "powerpoint",
)

BLOCKED_CLOSE_APP_NAMES = {
    "antimalware service executable",
    "cmd",
    "csrss",
    "defender",
    "desktop window manager",
    "dwm",
    "explorer",
    "lsass",
    "microsoft defender",
    "msmpeng",
    "registry",
    "runtimebroker",
    "services",
    "smss",
    "svchost",
    "system",
    "system idle process",
    "task manager",
    "taskhostw",
    "wininit",
    "winlogon",
}

CLOSE_APP_PROCESS_NAMES: dict[str, tuple[str, ...]] = {
    "notepad": ("notepad.exe",),
    "calculator": ("CalculatorApp.exe", "calc.exe"),
    "chrome": ("chrome.exe",),
    "edge": ("msedge.exe",),
    "spotify": ("Spotify.exe",),
    "discord": ("Discord.exe",),
    "vscode": ("Code.exe",),
    "codex": ("Codex.exe",),
    "terminal": ("WindowsTerminal.exe", "wt.exe"),
    "powershell": ("powershell.exe", "pwsh.exe"),
    "word": ("WINWORD.EXE",),
    "excel": ("EXCEL.EXE",),
    "powerpoint": ("POWERPNT.EXE",),
}


def system_status() -> DesktopStatus:
    return DesktopStatus(
        os_name=f"{platform.system()} {platform.release()}",
        shell=os.environ.get("SHELL") or os.environ.get("COMSPEC") or "unknown",
        cwd=os.getcwd(),
    )


def _start_detached(command: list[str]) -> None:
    subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False)


def _start_shell(target: str) -> None:
    if os.name == "nt":
        subprocess.Popen(["cmd.exe", "/c", "start", "", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        _start_detached([target])


def _candidate_names(app_name: str) -> list[str]:
    query = app_name.strip().lower()
    names = [query]
    for canonical, aliases in APP_ALIASES.items():
        if query == canonical or query in aliases:
            names = [canonical, *aliases]
            break
    return list(dict.fromkeys(names))


def _iter_start_menu_shortcuts() -> Iterable[Path]:
    roots = [
        Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path.home() / "Desktop",
    ]
    for root in roots:
        if not root.exists():
            continue
        yield from root.rglob("*.lnk")


def _find_shortcut(app_name: str) -> Path | None:
    # Phase 124: whole words, not substrings ("word" used to match WordPad and
    # Password Manager). An exact name beats a name that merely contains the words.
    from .app_index import _query_words, _score

    names = [_query_words(name) for name in _candidate_names(app_name)]
    best: tuple[float, Path] | None = None
    for shortcut in _iter_start_menu_shortcuts():
        score = max((_score(words, shortcut.stem) for words in names), default=0.0)
        if score > 0 and (best is None or score > best[0]):
            best = (score, shortcut)
    return best[1] if best else None


def _canonical_app(app_name: str) -> str:
    query = app_name.strip().lower()
    for canonical, aliases in APP_ALIASES.items():
        if query == canonical or query in aliases:
            return canonical
    return query


def close_app_allowlist() -> tuple[str, ...]:
    raw = os.environ.get("EVA_CLOSE_APP_ALLOWLIST", "")
    configured = [part.strip() for part in raw.split(",") if part.strip()] if raw.strip() else list(DEFAULT_CLOSE_APP_ALLOWLIST)
    allowed: list[str] = []
    for item in configured:
        key = _canonical_app(item)
        if key in BLOCKED_CLOSE_APP_NAMES:
            continue
        if key in CLOSE_APP_PROCESS_NAMES:
            allowed.append(key)
    return tuple(sorted(dict.fromkeys(allowed)))


def is_closeable(app_name: str) -> bool:
    """Whether ``close_app`` would accept this app -- a pure allowlist check with
    no side effects (Phase 82). Used to refuse an unknown or system app BEFORE
    the gate asks for confirmation, so a close that can only ever be refused is
    not parked at the gate first (the Phase 74 lesson: never ask to confirm
    something that will be rejected anyway)."""
    key = _canonical_app(app_name)
    if key in BLOCKED_CLOSE_APP_NAMES:
        return False
    if key not in set(close_app_allowlist()):
        return False
    return bool(CLOSE_APP_PROCESS_NAMES.get(key))


def close_app_refusal(app_name: str) -> str:
    """The standard refusal message for a non-closeable app."""
    supported = ", ".join(close_app_allowlist()) or "none configured"
    return f"I can close that if it is in the safe close allowlist. Supported: {supported}."


def open_app(app_name: str) -> str:
    key = _canonical_app(app_name)
    if key not in APP_ALIASES:
        # Phase 124: any installed app, by name. Raises (without launching) when the
        # name is refused, ambiguous, or not installed. Opening an app is still not
        # closing it: close_app's allowlist (is_closeable) is untouched.
        from .app_index import open_installed_app

        return open_installed_app(app_name)
    aliases = APP_ALIASES.get(key, (app_name.strip(),))

    for alias in aliases:
        if alias.startswith("ms-") or alias.endswith(":"):
            _start_shell(alias)
            return f"Opening {key}."
        resolved = shutil.which(alias)
        if resolved:
            _start_detached([resolved])
            return f"Opening {key}."

    shortcut = _find_shortcut(key)
    if shortcut is not None:
        os.startfile(shortcut)  # type: ignore[attr-defined]
        return f"Opening {shortcut.stem}."

    supported = ", ".join(sorted(APP_ALIASES))
    raise ValueError(f"Could not find {key} on this laptop. Supported apps: {supported}.")


def close_app(app_name: str) -> str:
    key = _canonical_app(app_name)
    allowed = set(close_app_allowlist())
    process_names = CLOSE_APP_PROCESS_NAMES.get(key)
    if key in BLOCKED_CLOSE_APP_NAMES or key not in allowed or not process_names:
        supported = ", ".join(close_app_allowlist()) or "none configured"
        raise ValueError(f"I can close that if it is in the safe close allowlist. Supported: {supported}.")
    for process_name in process_names:
        subprocess.run(["taskkill", "/IM", process_name, "/T", "/F"], capture_output=True, text=True, timeout=8)
    return f"Asked Windows to close {key}."


def open_folder(folder_name: str) -> str:
    key = folder_name.strip().lower()
    path = SPECIAL_FOLDERS.get(key) or Path(folder_name).expanduser()
    if not path.exists():
        raise ValueError(f"Folder not found: {folder_name}")
    os.startfile(path)  # type: ignore[attr-defined]
    return f"Opening {path}."


def open_url(url: str) -> str:
    target = url.strip()
    if not target:
        raise ValueError("URL is empty.")
    if "://" not in target:
        target = "https://" + target
    parsed = urllib.parse.urlparse(target)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Only valid http and https URLs are allowed.")
    webbrowser.open(target)
    return f"Opening {target}."


def web_search(query: str) -> dict:
    clean = query.strip()
    if not clean:
        raise ValueError("Search query is empty.")
    tavily_result = tavily_search_sync(clean)
    if tavily_result.get("ok"):
        return tavily_result

    target = "https://www.google.com/search?q=" + urllib.parse.quote_plus(clean)
    webbrowser.open(target)
    tavily_result.update(
        {
            "query": clean,
            "fallback": "browser",
            "browser_opened": True,
            "browser_url": target,
            "message": f"Tavily search failed or was unavailable, so I opened browser search for: {clean}.",
        }
    )
    return tavily_result


def system_power(action: str, confirmed: bool = False) -> str:
    key = action.strip().lower().replace(" ", "_")
    if key in {"lock", "lock_screen", "lock_laptop", "lock_pc"}:
        subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "Locking the laptop."

    guarded = {
        "sleep": (["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], "Putting the laptop to sleep."),
        "shutdown": (["shutdown.exe", "/s", "/t", "0"], "Shutting down the laptop."),
        "restart": (["shutdown.exe", "/r", "/t", "0"], "Restarting the laptop."),
        "sign_out": (["shutdown.exe", "/l"], "Signing out."),
        "log_out": (["shutdown.exe", "/l"], "Signing out."),
    }
    if key not in guarded:
        raise ValueError(f"Unsupported power action: {action}")
    if not confirmed:
        return f"I can {key.replace('_', ' ')}, but say 'confirm {key.replace('_', ' ')}' so I know it is intentional."
    command, reply = guarded[key]
    subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return reply


def media_key(action: str) -> str:
    key_map = {
        "mute": 0xAD,
        "volume_mute": 0xAD,
        "volume_up": 0xAF,
        "vol_up": 0xAF,
        "louder": 0xAF,
        "volume_down": 0xAE,
        "vol_down": 0xAE,
        "quieter": 0xAE,
        "play_pause": 0xB3,
        "pause": 0xB3,
        "play": 0xB3,
        "next": 0xB0,
        "previous": 0xB1,
    }
    key = action.strip().lower().replace(" ", "_")
    code = key_map.get(key)
    if code is None:
        raise ValueError(f"Unsupported media action: {action}")
    ps = (
        "$sig='[DllImport(\"user32.dll\")] public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);';"
        "$t=Add-Type -MemberDefinition $sig -Name Win32Keyboard -Namespace Eva -PassThru;"
        f"$t::keybd_event({code},0,0,[UIntPtr]::Zero);"
        f"$t::keybd_event({code},0,2,[UIntPtr]::Zero);"
    )
    subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=8)
    return f"Sent media command: {key.replace('_', ' ')}."

