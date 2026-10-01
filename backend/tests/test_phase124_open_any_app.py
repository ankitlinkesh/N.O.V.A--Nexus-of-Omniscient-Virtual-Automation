"""Phase 124: open_app opens any installed app by name (whole-word matching,
ambiguity question, safety denylist). Every lookup layer and the launcher are faked;
nothing here starts a process."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.eva.tools import app_index, desktop

SHORTCUTS = [
    r"C:\SM\Discord.lnk",
    r"C:\SM\Word.lnk",
    r"C:\SM\WordPad.lnk",
    r"C:\SM\Password Manager.lnk",
    r"C:\SM\Jobs.lnk",
    r"C:\SM\OBS Studio.lnk",
    r"C:\SM\VLC media player.lnk",
    r"C:\SM\VLC media player - Reset preferences and cache files.lnk",
    r"C:\SM\VLC media player skinned.lnk",
    r"C:\SM\Visual Studio 2022.lnk",
    r"C:\SM\Visual Studio Installer.lnk",
    r"C:\SM\Windows PowerShell.lnk",
    r"C:\SM\Registry Editor.lnk",
    r"C:\SM\Uninstall Foo.lnk",
    r"C:\SM\Deploy Tool.lnk",
    r"C:\SM\Visual Studio Code.lnk",
    r"C:\SM\Visual Studio Build.lnk",
    r"C:\SM\Notes Pro.lnk",
    r"C:\SM\Notes Lite.lnk",
]
TARGETS = {
    r"C:\SM\Discord.lnk": r"C:\Users\x\Discord\Update.exe",
    r"C:\SM\Windows PowerShell.lnk": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
    r"C:\SM\Registry Editor.lnk": r"C:\Windows\regedit.exe",
    r"C:\SM\Deploy Tool.lnk": r"C:\tools\deploy.bat",
    r"C:\SM\OBS Studio.lnk": r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
}
START_APPS = [
    ("Calculator", "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"),
    ("Spotify Music", "SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify"),
    ("Discord", "Discord.Discord_x!App"),
    ("Windows Terminal", "Microsoft.WindowsTerminal_8wekyb3d8bbwe!App"),
]


@pytest.fixture
def launched(monkeypatch):
    log: list[tuple[str, str]] = []
    app_index.invalidate_app_index()
    monkeypatch.setattr(app_index, "_iter_shortcuts", lambda: [Path(p) for p in SHORTCUTS])
    monkeypatch.setattr(app_index, "_read_start_apps", lambda: list(START_APPS))
    monkeypatch.setattr(app_index, "_shortcut_targets", lambda paths: {p: TARGETS[p] for p in paths if p in TARGETS})
    monkeypatch.setattr(app_index, "_launch_shortcut", lambda p: log.append(("lnk", p)))
    monkeypatch.setattr(app_index, "_launch_uwp", lambda a: log.append(("uwp", a)))
    app_index._resolved_names.clear()
    yield log
    app_index.invalidate_app_index()


def test_discord_resolves_to_its_shortcut(launched):
    # (the alias path handles the typed word "discord"; this tests the index itself)
    res = app_index.resolve_installed_app("discord")
    assert res.status == "found" and res.entry.kind == "lnk" and res.entry.ref == r"C:\SM\Discord.lnk"


def test_word_means_word_not_wordpad_or_password_manager(launched):
    res = app_index.resolve_installed_app("word")
    assert res.status == "found" and res.entry.name == "Word"


def test_find_shortcut_is_whole_word(monkeypatch):
    monkeypatch.setattr(desktop, "_iter_start_menu_shortcuts", lambda: [Path(r"C:\SM\WordPad.lnk"), Path(r"C:\SM\Password Manager.lnk"), Path(r"C:\SM\Word.lnk")])
    assert desktop._find_shortcut("word") == Path(r"C:\SM\Word.lnk")
    monkeypatch.setattr(desktop, "_iter_start_menu_shortcuts", lambda: [Path(r"C:\SM\WordPad.lnk"), Path(r"C:\SM\Password Manager.lnk")])
    assert desktop._find_shortcut("word") is None


def test_obs_does_not_match_jobs(launched, monkeypatch):
    res = app_index.resolve_installed_app("obs")
    assert res.status == "found" and res.entry.name == "OBS Studio"
    monkeypatch.setattr(app_index, "_iter_shortcuts", lambda: [Path(r"C:\SM\Jobs.lnk")])
    app_index.invalidate_app_index()
    assert app_index.resolve_installed_app("obs").status == "none"


def test_open_launches_shortcut_and_remembers_window_names(launched):
    assert desktop.open_app("obs studio") == "Opening OBS Studio."
    assert launched == [("lnk", r"C:\SM\OBS Studio.lnk")]
    from backend.eva.desktop.verifier import _app_queries

    queries = _app_queries("obs studio")
    assert "OBS Studio" in queries and "obs64" in queries


def test_uwp_app_launches_via_shell_appsfolder(launched):
    assert desktop.open_app("spotify music") == "Opening Spotify Music."
    assert launched == [("uwp", "SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify")]


def test_real_uwp_launcher_command(monkeypatch):
    seen = []
    monkeypatch.setattr(app_index.subprocess, "Popen", lambda cmd, **kw: seen.append(cmd))
    app_index._launch_uwp("Pkg!App")
    assert seen == [["explorer.exe", "shell:AppsFolder" + chr(92) + "Pkg!App"]]


def test_ambiguous_name_asks_instead_of_launching(launched):
    with pytest.raises(ValueError) as err:
        desktop.open_app("notes")
    assert "several" in str(err.value) and "Notes Pro" in str(err.value) and "Notes Lite" in str(err.value)
    with pytest.raises(ValueError):
        desktop.open_app("visual studio")
    assert launched == []


def test_clear_winner_over_weak_second_is_not_over_refused(launched):
    res = app_index.resolve_installed_app("vlc")
    assert res.status == "found" and res.entry.name == "VLC media player"


def test_more_specific_name_resolves_ambiguity(launched):
    assert app_index.resolve_installed_app("notes pro").status == "found"


@pytest.mark.parametrize(
    "name",
    ["Windows PowerShell", "Registry Editor", "Uninstall Foo", "Deploy Tool", "Visual Studio Installer", "regedit", "pwsh", "wsl", "mmc", "control panel", "services"],
)
def test_denylisted_apps_are_refused(launched, name):
    with pytest.raises(ValueError) as err:
        desktop.open_app(name)
    assert "won't open" in str(err.value)
    assert launched == []


def test_script_target_is_refused_even_with_innocent_name(launched):
    res = app_index.resolve_installed_app("deploy tool")
    assert res.status == "denied" and "script" in res.reason


def test_exe_target_denied_even_with_innocent_name(launched, monkeypatch):
    monkeypatch.setattr(app_index, "_iter_shortcuts", lambda: [Path(r"C:\SM\Handy Helper.lnk")])
    monkeypatch.setattr(app_index, "_shortcut_targets", lambda paths: {p: r"C:\Windows\System32\cmd.exe" for p in paths})
    app_index.invalidate_app_index()
    assert app_index.resolve_installed_app("handy helper").status == "denied"


def test_unknown_name_is_honestly_not_installed(launched):
    with pytest.raises(ValueError) as err:
        desktop.open_app("zorblax")
    assert "couldn't find an installed app" in str(err.value)
    assert launched == []


def test_alias_apps_behave_as_before(launched, monkeypatch):
    started = []
    monkeypatch.setattr(desktop.shutil, "which", lambda a: r"C:\fake\\" + a if a == "notepad.exe" else None)
    monkeypatch.setattr(desktop, "_start_detached", lambda cmd: started.append(cmd))
    assert desktop.open_app("notepad") == "Opening notepad."
    assert started == [[r"C:\fake\\notepad.exe"]]
    shell = []
    monkeypatch.setattr(desktop, "_start_shell", lambda t: shell.append(t))
    assert desktop.open_app("Settings") == "Opening settings."
    assert shell == ["ms-settings:"]
    assert launched == []  # the generic path was never consulted


def test_index_is_cached_and_bounded(launched, monkeypatch):
    builds = []
    real = app_index._build_index
    monkeypatch.setattr(app_index, "_build_index", lambda: (builds.append(1), real())[1])
    app_index.invalidate_app_index()
    app_index.resolve_installed_app("discord")
    app_index.resolve_installed_app("obs")
    assert len(builds) == 1


def test_get_startapps_timeout_returns_empty(monkeypatch):
    def boom(*a, **k):
        raise TimeoutError("slow")

    monkeypatch.setattr(app_index, "_ps", boom)
    assert app_index._read_start_apps() == []
    assert app_index._shortcut_targets(["x.lnk"]) == {}


def test_get_startapps_json_parsing(monkeypatch):
    monkeypatch.setattr(app_index, "_ps", lambda *a, **k: '{"Name":"Solo","AppID":"Pkg!App"}')
    assert app_index._read_start_apps() == [("Solo", "Pkg!App")]


def test_close_app_allowlist_unchanged(launched):
    # Being able to open any app does not make it closeable.
    assert desktop.is_closeable("vlc") is False
    assert desktop.is_closeable("obs studio") is False
    assert desktop.is_closeable("notepad") is True
    assert set(desktop.close_app_allowlist()) == set(desktop.DEFAULT_CLOSE_APP_ALLOWLIST)


def test_open_app_schema_no_longer_pins_an_enum_and_planner_text_updated():
    from backend.eva.tools.registry import ToolRegistry

    spec = ToolRegistry()._tools["open_app"]
    assert "enum" not in spec.args_schema["properties"]["app"]
    assert spec.action_type == "SAFE_LOCAL_UI"  # same class as before
    src = (Path(desktop.__file__).resolve().parents[1] / "agent" / "planner.py").read_text(encoding="utf-8")
    assert "known apps such as" not in src
    assert src.count("any installed app") >= 2


def test_a_tainted_task_must_ask_before_opening_an_unlisted_app():
    # Review finding: open_app is allow-class, so the injection check let a
    # hostile page open ANY installed program once Phase 124 widened it.
    from backend.eva.agent.planner import PlannedToolCall
    from backend.eva.agent.runner import _opens_unlisted_app
    from backend.eva.threat_defense.authorization import authorize_action

    unlisted = PlannedToolCall(tool="open_app", args={"app": "quick assist"})
    alias = PlannedToolCall(tool="open_app", args={"app": "calculator"})
    assert _opens_unlisted_app(unlisted) and not _opens_unlisted_app(alias)
    tainted = authorize_action(tool_privileged=_opens_unlisted_app(unlisted), context_tainted=True, injection_detected=True)
    assert tainted.escalate
    clean = authorize_action(tool_privileged=_opens_unlisted_app(unlisted), context_tainted=False, injection_detected=False)
    assert not clean.escalate
