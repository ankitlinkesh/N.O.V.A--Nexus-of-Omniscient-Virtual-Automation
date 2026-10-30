"""eva-utils: a safe calculator and a clock as a read-only stdio MCP server (Phase 160).

Standalone -- it does not wrap a NOVA tool. The calculator parses with ``ast`` and walks the tree
against a whitelist; nothing is ever passed to eval/exec. Run: python -m backend.eva.mcp.servers.utils
"""

from __future__ import annotations

import ast
import math
import operator
from datetime import datetime, timezone as _tz
from typing import Any

from mcp.server.fastmcp import FastMCP

MAX_EXPR_LEN = 200
MAX_EXPONENT = 1000
MAX_RESULT = 1e300
MAX_INT_BITS = 4096
MAX_DEPTH = 40

_BIN = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {
    "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "log": math.log, "log10": math.log10, "exp": math.exp, "abs": abs,
    "round": round, "floor": math.floor, "ceil": math.ceil, "min": min, "max": max,
}
_CONSTS = {"pi": math.pi, "e": math.e}


class CalcError(ValueError):
    pass


def _check(value: Any) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CalcError("only numbers are allowed")
    if isinstance(value, int) and value.bit_length() > MAX_INT_BITS:
        raise CalcError("result is too large")
    if isinstance(value, float) and abs(value) > MAX_RESULT:
        raise CalcError("result is too large")
    return value


def _eval(node: ast.AST, depth: int = 0) -> Any:
    if depth > MAX_DEPTH:
        raise CalcError("expression is nested too deeply")
    if isinstance(node, ast.Expression):
        return _eval(node.body, depth + 1)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise CalcError("only numbers are allowed")
        return _check(node.value)
    if isinstance(node, ast.Name):
        if node.id in _CONSTS:
            return _CONSTS[node.id]
        raise CalcError(f"name '{node.id}' is not allowed")
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _check(_UNARY[type(node.op)](_eval(node.operand, depth + 1)))
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        left = _eval(node.left, depth + 1)
        right = _eval(node.right, depth + 1)
        if isinstance(node.op, ast.Pow):
            if abs(right) > MAX_EXPONENT:
                raise CalcError(f"exponent is too large (limit {MAX_EXPONENT})")
            if isinstance(left, int) and isinstance(right, int) and right > 0 and left not in (0, 1, -1):
                if abs(left).bit_length() * right > MAX_INT_BITS:
                    raise CalcError("result is too large")
        return _check(_BIN[type(node.op)](left, right))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCS:
            raise CalcError("only whitelisted math functions may be called")
        if node.keywords or len(node.args) > 8:
            raise CalcError("keyword or too many arguments")
        args = [_eval(a, depth + 1) for a in node.args]
        return _check(_FUNCS[node.func.id](*args))
    raise CalcError(f"{type(node).__name__} is not allowed")


def calculate_expression(expression: Any) -> dict[str, Any]:
    """Evaluate an arithmetic expression safely. Never raises; returns {ok, result} or {ok: False, error}."""
    if not isinstance(expression, str) or not expression.strip():
        return {"ok": False, "error": "expression is empty"}
    if len(expression) > MAX_EXPR_LEN:
        return {"ok": False, "error": f"expression is too long (limit {MAX_EXPR_LEN} characters)"}
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        return {"ok": True, "expression": expression.strip(), "result": _eval(tree)}
    except CalcError as exc:
        return {"ok": False, "error": str(exc)}
    except ZeroDivisionError:
        return {"ok": False, "error": "division by zero"}
    except SyntaxError:
        return {"ok": False, "error": "not a valid arithmetic expression"}
    except (ValueError, TypeError, OverflowError, RecursionError, MemoryError) as exc:
        return {"ok": False, "error": f"cannot evaluate: {type(exc).__name__}: {exc}"}


def _describe(now: datetime, zone_label: str, note: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {
        "ok": True,
        "timezone": zone_label,
        "iso": now.isoformat(timespec="seconds"),
        "date": now.date().isoformat(),
        "weekday": now.strftime("%A"),
    }
    if note:
        out["note"] = note
    return out


def current_time_info(timezone: str = "local") -> dict[str, Any]:
    """Current time in an IANA zone, "local" or "UTC". Never raises; falls back to UTC if tzdata is missing."""
    name = (str(timezone) if timezone is not None else "local").strip() or "local"
    if name.lower() == "local":
        return _describe(datetime.now().astimezone(), "local")
    try:
        from zoneinfo import ZoneInfo

        return _describe(datetime.now(ZoneInfo(name)), name)
    except Exception:  # noqa: BLE001 - unknown zone, bad key, or no tz database on this machine
        pass
    if name.upper() in ("UTC", "GMT", "Z"):
        return _describe(datetime.now(_tz.utc), "UTC", "built-in UTC (no tz database needed)")
    try:
        import tzdata  # noqa: F401

        hint = ""
    except ImportError:
        hint = " (the tzdata package is not installed, so only local and UTC are available)"
    return {"ok": False, "error": f"unknown timezone '{name}'{hint}"}


mcp = FastMCP("eva-utils")


@mcp.tool()
def calculate(expression: str) -> dict[str, Any]:
    """Evaluate an arithmetic expression: numbers, + - * / // % **, parentheses, sqrt sin cos tan log log10 exp abs round floor ceil min max, pi, e."""
    return calculate_expression(expression)


@mcp.tool()
def current_time(timezone: str = "local") -> dict[str, Any]:
    """Current time, date and weekday for an IANA timezone name such as Asia/Kolkata, or 'local' / 'UTC'."""
    return current_time_info(timezone)


if __name__ == "__main__":
    mcp.run()
