"""Standalone verifier for Phase 124 (open any installed app by name).

Every lookup layer and launcher is faked; nothing is started.

1. Whole-word matching: "word" is Word (not WordPad / Password Manager), "obs" is not "Jobs".
2. A Store/UWP app launches through shell:AppsFolder.
3. An ambiguous name returns a question and launches nothing.
4. Shells, admin consoles, installers and script-target shortcuts are refused.
5. An unknown name is honestly "not installed".
6. Alias apps and close_app's allowlist are unchanged.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
failures = 0


def emit(case: str, ok: bool, **extra: object) -> int:
    payload = {"case": case, "pass": bool(ok)}
    payload.update(extra)
    print(json.dumps(payload, indent=2, default=str))
    return 0 if ok else 1


def refused(fn, *args) -> str | None:
    try:
        fn(*args)
    except ValueError as exc:
        return str(exc)
    return None


try:
    from backend.eva.tools import app_index, desktop

    shortcuts = [
        r"C:\SM\Discord.lnk", r"C:\SM\Word.lnk", r"C:\SM\WordPad.lnk", r"C:\SM\Password Manager.lnk",
        r"C:\SM\Jobs.lnk", r"C:\SM\OBS Studio.lnk", r"C:\SM\Windows PowerShell.lnk",
        r"C:\SM\Registry Editor.lnk", r"C:\SM\Uninstall Foo.lnk", r"C:\SM\Deploy Tool.lnk",
        r"C:\SM\Notes Pro.lnk", r"C:\SM\Notes Lite.lnk",
    ]
    targets = {
        r"C:\SM\Windows PowerShell.lnk": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
        r"C:\SM\Registry Editor.lnk": r"C:\Windows\regedit.exe",
        r"C:\SM\Deploy Tool.lnk": r"C:\tools\deploy.bat",
        r"C:\SM\OBS Studio.lnk": r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
    }
    log: list = []
    app_index.invalidate_app_index()
    app_index._iter_shortcuts = lambda: [Path(p) for p in shortcuts]
    app_index._read_start_apps = lambda: [("Spotify Music", "SpotifyAB.SpotifyMusic_x!Spotify")]
    app_index._shortcut_targets = lambda paths: {p: targets[p] for p in paths if p in targets}
    app_index._launch_shortcut = lambda p: log.append(("lnk", p))
    app_index._launch_uwp = lambda a: log.append(("uwp", a))

    res = app_index.resolve_installed_app("discord")
    failures += emit("discord resolves to Discord.lnk", res.status == "found" and res.entry.ref.endswith("Discord.lnk"))

    res = app_index.resolve_installed_app("word")
    failures += emit("word is Word, not WordPad or Password Manager", res.status == "found" and res.entry.name == "Word", got=res.names)

    app_index.invalidate_app_index()
    failures += emit(
        "obs does not match Jobs",
        app_index.resolve_installed_app("obs").entry.name == "OBS Studio"
        and app_index._score(["obs"], "Jobs") == 0,
    )

    log.clear()
    desktop.open_app("spotify music")
    failures += emit("a UWP app launches via its AppID", log == [("uwp", "SpotifyAB.SpotifyMusic_x!Spotify")], log=log)

    log.clear()
    msg = refused(desktop.open_app, "notes")
    failures += emit("an ambiguous name asks, launches nothing", bool(msg) and "several" in msg and not log, message=msg)

    for name in ("Windows PowerShell", "Registry Editor", "Uninstall Foo", "Deploy Tool", "regedit", "services"):
        log.clear()
        msg = refused(desktop.open_app, name)
        failures += emit(f"refused: {name}", bool(msg) and "won't open" in msg and not log, message=msg)

    msg = refused(desktop.open_app, "zorblax")
    failures += emit("unknown name is honestly not installed", bool(msg) and "couldn't find an installed app" in msg, message=msg)

    failures += emit(
        "close_app allowlist is unchanged",
        not desktop.is_closeable("obs studio") and desktop.is_closeable("notepad")
        and set(desktop.close_app_allowlist()) == set(desktop.DEFAULT_CLOSE_APP_ALLOWLIST),
    )

    from backend.eva.tools.registry import ToolRegistry

    spec = ToolRegistry()._tools["open_app"]
    failures += emit("open_app keeps its gate class and drops the enum", spec.action_type == "SAFE_LOCAL_UI" and "enum" not in spec.args_schema["properties"]["app"])

    planner = (ROOT / "backend" / "eva" / "agent" / "planner.py").read_text(encoding="utf-8")
    failures += emit("both planner rule lists say any installed app", planner.count("any installed app") >= 2 and "known apps such as" not in planner)

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    failures += emit("README records Phase 124", "| 124 |" in readme)
except Exception as exc:  # pragma: no cover
    failures += emit("checks ran", False, error=f"{type(exc).__name__}: {exc}")

print(json.dumps({"overall_pass": failures == 0, "failures": failures}, indent=2))
raise SystemExit(0 if failures == 0 else 1)
