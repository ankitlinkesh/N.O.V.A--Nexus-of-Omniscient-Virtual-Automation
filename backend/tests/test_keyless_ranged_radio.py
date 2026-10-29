"""Keyless search fallback, ranged reads of big workspace files, Ethernet-aware Wi-Fi status."""

import backend.eva.tools.keyless_search as keyless
import backend.eva.tools.system_settings as ss
import backend.eva.tools.tavily_search as tavily
from backend.eva.workspace import config as wcfg
from backend.eva.workspace import reader


# --- keyless web search -------------------------------------------------------------------

def _fake_ddgs(monkeypatch, rows=None, error=None):
    class FakeDDGS:
        def __init__(self, *a, **k):
            pass

        def text(self, query, max_results=5):
            if error:
                raise error
            return rows

    import sys, types
    module = types.ModuleType("ddgs")
    module.DDGS = FakeDDGS
    monkeypatch.setitem(sys.modules, "ddgs", module)


def test_keyless_search_normalizes_to_tavily_shape(monkeypatch):
    _fake_ddgs(monkeypatch, rows=[{"title": "T", "href": "https://a.b/c", "body": "snippet"}])
    result = keyless.keyless_search_sync("python", 3)
    assert result["ok"] and result["provider"] == "duckduckgo"
    assert result["results"] == [{"title": "T", "url": "https://a.b/c", "content": "snippet", "score": 0.0}]


def test_keyless_failure_is_reported_not_faked(monkeypatch):
    _fake_ddgs(monkeypatch, error=RuntimeError("rate limited"))
    result = keyless.keyless_search_sync("python")
    assert result["ok"] is False and result["error"].startswith("keyless_search_failed")
    _fake_ddgs(monkeypatch, rows=[])
    assert keyless.keyless_search_sync("python")["error"] == "no_results"


def test_tavily_falls_back_to_keyless_only_without_a_key(monkeypatch):
    _fake_ddgs(monkeypatch, rows=[{"title": "T", "href": "https://a.b", "body": "b"}])
    monkeypatch.setenv("EVA_KEYLESS_SEARCH", "on")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    assert tavily.tavily_search_sync("q")["provider"] == "duckduckgo"
    monkeypatch.setenv("EVA_KEYLESS_SEARCH", "off")
    assert tavily.tavily_search_sync("q")["error"] == "missing_api_key"


def test_empty_query_never_reaches_keyless(monkeypatch):
    monkeypatch.setenv("EVA_KEYLESS_SEARCH", "on")
    _fake_ddgs(monkeypatch, error=AssertionError("searched"))
    assert tavily.tavily_search_sync("   ")["error"] == "empty_query"


# --- ranged reads -------------------------------------------------------------------------

def test_big_file_is_read_in_windows(tmp_path, monkeypatch):
    big = tmp_path / "big.txt"
    big.write_bytes("".join(f"line {i}\n" for i in range(1, 2001)).encode("utf-8"))
    monkeypatch.setattr(reader, "resolve_workspace_path", lambda p: big)
    monkeypatch.setattr(reader, "relative_to_root", lambda p: "big.txt")
    monkeypatch.setattr(wcfg, "assert_workspace_enabled", lambda: type("C", (), {"max_file_bytes": 1024})())
    monkeypatch.setattr(wcfg, "is_excluded_file", lambda p: False)
    first = reader.safe_read_file("big.txt", max_chars=500)
    assert first["ok"] and first["truncated"] and first["start_line"] == 1
    second = reader.safe_read_file("big.txt", max_chars=500, start_line=first["next_start_line"])
    assert second["ok"] and second["content"].startswith(f"line {first['next_start_line']}\n")
    assert second["start_line"] == first["next_start_line"]
    last = reader.safe_read_file("big.txt", max_chars=500, start_line=1990)
    assert last["truncated"] is False and last["next_start_line"] is None and last["content"].rstrip().endswith("line 2000")


def test_ranged_reading_still_refuses_past_the_hard_ceiling(tmp_path, monkeypatch):
    f = tmp_path / "huge.txt"
    f.write_text("x" * 100, encoding="utf-8")
    monkeypatch.setattr(wcfg, "assert_workspace_enabled", lambda: type("C", (), {"max_file_bytes": 10})())
    monkeypatch.setattr(wcfg, "is_excluded_file", lambda p: False)
    monkeypatch.setattr(wcfg, "MAX_RANGED_READ_BYTES", 50)
    try:
        wcfg.assert_safe_file(f, allow_large=True)
    except wcfg.WorkspaceSafetyError as exc:
        assert "too large" in str(exc)
    else:
        raise AssertionError("not refused")


# --- Ethernet-aware Wi-Fi status ----------------------------------------------------------

def test_wifi_off_on_ethernet_is_explained(monkeypatch):
    monkeypatch.setattr(ss, "_radio_states", lambda kind: (["off"], {}))
    monkeypatch.setattr(ss, "_wired_connection", lambda: True)
    result = ss.radio_status("wifi")
    assert result["state"] == "off" and result["network"] == "ethernet" and "Ethernet" in result["message"]


def test_wifi_off_without_ethernet_is_plain(monkeypatch):
    monkeypatch.setattr(ss, "_radio_states", lambda kind: (["off"], {}))
    monkeypatch.setattr(ss, "_wired_connection", lambda: False)
    assert ss.radio_status("wifi")["message"] == "Wi-Fi is off."


def test_bluetooth_off_never_mentions_ethernet(monkeypatch):
    monkeypatch.setattr(ss, "_radio_states", lambda kind: (["off"], {}))
    monkeypatch.setattr(ss, "_wired_connection", lambda: True)
    assert "Ethernet" not in ss.radio_status("bluetooth")["message"]
