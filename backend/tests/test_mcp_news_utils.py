"""Phase 160: the news domain and the standalone eva-utils server (no network, no real apps)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.eva.mcp.domain_server import build_server, is_gated
from backend.eva.mcp.domains import DOMAIN_TOOLS, tool_domain
from backend.eva.mcp.servers import utils
from backend.eva.mcp.servers.utils import calculate_expression, current_time_info
from backend.eva.tools.registry import ToolRegistry

NEWS = ("rss_headlines", "weather_forecast")


def test_news_domain_lists_the_expected_read_only_tools():
    assert DOMAIN_TOOLS["news"] == NEWS


def test_news_tools_exist_and_are_not_gated():
    registry = ToolRegistry()
    for name in DOMAIN_TOOLS["news"]:
        spec = registry.get(name)
        assert spec is not None, name
        assert not is_gated(spec), name


def test_no_tool_in_two_domains():
    seen: dict[str, str] = {}
    for domain, names in DOMAIN_TOOLS.items():
        assert len(set(names)) == len(names), domain
        for name in names:
            assert name not in seen, f"{name} is in both {seen[name]} and {domain}"
            seen[name] = domain
    assert tool_domain("youtube_transcript") == "youtube"


def test_server_builds_for_news_domain():
    assert build_server("news") is not None


@pytest.mark.parametrize(
    "expr,expected",
    [
        ("1+2*3", 7),
        ("(1+2)*3", 9),
        ("7//2", 3),
        ("7%4", 3),
        ("2**10", 1024),
        ("-3 + +5", 2),
        ("10/4", 2.5),
        ("sqrt(16)", 4.0),
        ("max(1, 5, 3) + min(4, 2)", 7),
        ("floor(2.7) + ceil(2.1)", 5),
        ("round(2.567, 2)", 2.57),
        ("abs(-4)", 4),
    ],
)
def test_calculate_accepts_good_expressions(expr, expected):
    out = calculate_expression(expr)
    assert out["ok"] is True, out
    assert out["result"] == pytest.approx(expected)


def test_calculate_constants_and_functions():
    assert calculate_expression("pi")["result"] == pytest.approx(3.14159265, rel=1e-6)
    assert calculate_expression("log10(1000)")["result"] == pytest.approx(3.0)
    assert calculate_expression("exp(0) + sin(0) + cos(0)")["result"] == pytest.approx(2.0)


@pytest.mark.parametrize(
    "expr",
    [
        "__import__('os').system('echo hi')",
        "().__class__.__bases__",
        "(1).real",
        "'a'.upper()",
        "lambda: 1",
        "(lambda x: x)(1)",
        "x + 1",
        "open('f')",
        "eval('1')",
        "[1, 2]",
        "{'a': 1}",
        "1 if True else 2",
        "'abc'",
        "True",
        "1; 2",
        "x = 1",
        "sqrt(x=4)",
        "9**9**9",
        "10**1001",
        "2**5000",
        "1e308 * 10",
        "",
        "   ",
        "1/0",
        "sqrt(-1)",
        "1 +",
        "1" + "+1" * 200,
        "(" * 100 + "1" + ")" * 100,
    ],
)
def test_calculate_rejects_unsafe_or_bad_input(expr):
    out = calculate_expression(expr)
    assert out["ok"] is False, out
    assert out["error"]
    assert "result" not in out


def test_calculate_rejects_non_string():
    assert calculate_expression(None)["ok"] is False
    assert calculate_expression(5)["ok"] is False


def test_current_time_local_and_utc():
    local = current_time_info("local")
    assert local["ok"] is True
    assert local["date"] in local["iso"]
    assert local["weekday"] in {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}
    assert current_time_info()["ok"] is True
    utc = current_time_info("UTC")
    assert utc["ok"] is True
    assert utc["iso"].endswith("+00:00")


def test_current_time_named_zone_or_clear_fallback():
    out = current_time_info("Asia/Kolkata")
    if out["ok"]:
        assert out["iso"].endswith("+05:30")
    else:
        assert "tzdata" in out["error"]


def test_current_time_unknown_zone():
    out = current_time_info("Mars/Olympus_Mons")
    assert out["ok"] is False
    assert "unknown timezone" in out["error"]


def test_utils_server_registers_two_tools():
    tools = {t.name for t in __import__("asyncio").run(utils.mcp.list_tools())}
    assert tools == {"calculate", "current_time"}


def test_example_config_is_valid_and_utils_entry_disabled():
    path = Path(__file__).resolve().parents[2] / "config" / "mcp_servers.example.json"
    servers = {s["name"]: s for s in json.loads(path.read_text(encoding="utf-8"))["servers"]}
    entry = servers["eva-utils"]
    assert entry["enabled"] is False
    assert entry["args"] == ["-m", "backend.eva.mcp.servers.utils"]
