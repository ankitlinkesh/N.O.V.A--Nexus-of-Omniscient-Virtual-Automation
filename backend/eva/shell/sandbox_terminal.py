"""NOVA's own terminal: an isolated WSL2 Ubuntu box (Phase 130).

Inside the box, NOVA runs any command with no approval prompt. The box is a WSL2
distro named ``nova``: it cannot see C: or D:, cannot launch Windows programs and
has no sudo. It sees only D:\\nova-share (as /mnt/share); its workspace is
/home/nova/workspace.

THIS IS A SANDBOX AND NOTHING ELSE. Every code path here ends in ``wsl.exe -d nova``.
There is deliberately no fallback that runs a command on the Windows host: a missing
distro, a missing wsl.exe or a failed launch is reported honestly and the command is
NOT run. This is not the Phase 74 bounded runner (``bounded_runner.py``, allowlisted
host executables) and does not touch the hard-blocked ``SHELL_ACTION``.

Invocation, measured on this machine (other forms break):

    wsl.exe -d nova -u nova --cd /home/nova/workspace --exec bash -c "echo <B64> | base64 -d | timeout -k 5 <S> bash -l"

``wsl -- bash -c CMD`` re-parses CMD through the login shell and ate ``$var``
expansions, and Windows argument quoting mangles embedded double quotes, so the
command always travels as base64 (UTF-8 first).

The time limit is enforced INSIDE the box by coreutils ``timeout`` (SIGTERM, then
SIGKILL 5s later): killing only the Windows-side wsl.exe client leaves the command
running in the distro, so a runaway loop would pile up. The host-side subprocess
timeout is a backstop a little longer than that.

Every OS touch sits behind ``_default_runner`` so tests inject a fake and never need
a real WSL (conftest fails any test that reaches the real one).
"""

from __future__ import annotations

import base64
import os
import subprocess
from typing import Any, Callable

DISTRO = "nova"
SANDBOX_USER = "nova"
SANDBOX_CWD = "/home/nova/workspace"
SHARE_HOST_PATH = "D:\\nova-share"
SHARE_GUEST_PATH = "/mnt/share"

MAX_COMMAND_CHARS = 4000
MIN_TIMEOUT_S = 1
MAX_TIMEOUT_S = 300
DEFAULT_TIMEOUT_S = 60
MAX_OUTPUT_CHARS = 8000
KILL_GRACE_S = 5  # timeout -k: SIGKILL this long after SIGTERM
HOST_BACKSTOP_S = 10  # host-side wait beyond the in-box limit
_TIMEOUT_EXIT_CODES = (124, 137)  # coreutils timeout: TERM-ed / KILL-ed

_WSL = "wsl.exe"
_NOT_SET_UP = "My sandbox isn't set up yet. Run D:\\wsl\\setup_nova_box.ps1 and try again."

Runner = Callable[[list[str], float, dict[str, str]], Any]


def _default_runner(argv: list[str], timeout: float, env: dict[str, str]) -> Any:
    """The one real process launch. shell=False, argv list, always ``wsl.exe``."""
    return subprocess.run(  # noqa: S603 - shell=False, fixed executable
        argv,
        shell=False,
        capture_output=True,
        timeout=timeout,
        env=env,
        check=False,
    )


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["WSL_UTF8"] = "1"
    return env


def _decode(data: Any) -> str:
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    return bytes(data).decode("utf-8", errors="replace")


def _decode_listing(data: Any) -> str:
    """``wsl --list`` is UTF-16LE on some builds: strip NULs and BOMs, then decode."""
    if data is None:
        return ""
    if isinstance(data, str):
        return data.replace("\x00", "").replace("\ufeff", "")
    raw = bytes(data)
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        raw = raw[2:]
    return raw.replace(b"\x00", b"").decode("utf-8", errors="replace").replace("\ufeff", "")


def _tail(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text, False
    return text[-MAX_OUTPUT_CHARS:], True


def clamp_timeout(timeout_s: Any) -> int:
    try:
        value = int(timeout_s)
    except (TypeError, ValueError):
        value = DEFAULT_TIMEOUT_S
    return max(MIN_TIMEOUT_S, min(value, MAX_TIMEOUT_S))


def build_argv(command: str, seconds: int = DEFAULT_TIMEOUT_S) -> list[str]:
    """The exact argv. The command is base64 so no quoting layer can touch it; the
    time limit is enforced by ``timeout`` inside the box."""
    encoded = base64.b64encode(command.encode("utf-8")).decode("ascii")
    return [
        _WSL,
        "-d", DISTRO,
        "-u", SANDBOX_USER,
        "--cd", SANDBOX_CWD,
        "--exec", "bash", "-c",
        f"echo {encoded} | base64 -d | timeout -k {KILL_GRACE_S} {clamp_timeout(seconds)} bash -l",
    ]


def _result(ok: bool, **extra: Any) -> dict[str, Any]:
    base = {
        "ok": ok,
        "exit_code": None,
        "stdout": "",
        "stderr": "",
        "timed_out": False,
        "truncated": False,
        "cwd": SANDBOX_CWD,
        "sandbox": True,
    }
    base.update(extra)
    return base


def sandbox_status(runner: Runner | None = None) -> dict[str, Any]:
    """Is the ``nova`` distro installed? Never runs anything inside it."""
    run = runner or _default_runner
    try:
        completed = run([_WSL, "--list", "--quiet"], 15, _env())
    except FileNotFoundError:
        return {"available": False, "error": "wsl.exe is not installed. " + _NOT_SET_UP}
    except subprocess.TimeoutExpired:
        return {"available": False, "error": "wsl.exe did not answer in time. " + _NOT_SET_UP}
    except OSError as exc:
        return {"available": False, "error": f"wsl.exe could not start ({type(exc).__name__}). " + _NOT_SET_UP}
    names = [line.strip().lower() for line in _decode_listing(getattr(completed, "stdout", b"")).splitlines()]
    if DISTRO in names:
        return {"available": True, "distro": DISTRO, "cwd": SANDBOX_CWD}
    return {"available": False, "error": _NOT_SET_UP}


def run_in_sandbox(command: str, timeout_s: int = DEFAULT_TIMEOUT_S, runner: Runner | None = None) -> dict[str, Any]:
    """Run ``command`` in NOVA's sandbox. Never on the host."""
    text = command if isinstance(command, str) else str(command or "")
    if not text.strip():
        return _result(False, error="Give me a command to run in my sandbox.")
    if len(text) > MAX_COMMAND_CHARS:
        return _result(False, error=f"That command is too long ({len(text)} characters; the limit is {MAX_COMMAND_CHARS}). Put it in a script in the sandbox instead.")

    run = runner or _default_runner
    status = sandbox_status(run)
    if not status.get("available"):
        return _result(False, error=str(status.get("error") or _NOT_SET_UP))

    seconds = clamp_timeout(timeout_s)
    try:
        completed = run(build_argv(text, seconds), seconds + KILL_GRACE_S + HOST_BACKSTOP_S, _env())
    except subprocess.TimeoutExpired as exc:
        out, cut_out = _tail(_decode(getattr(exc, "stdout", None)))
        err, cut_err = _tail(_decode(getattr(exc, "stderr", None)))
        return _result(
            False,
            error=f"Timed out after {seconds}s in my sandbox.",
            stdout=out,
            stderr=err,
            timed_out=True,
            truncated=cut_out or cut_err,
        )
    except FileNotFoundError:
        return _result(False, error="wsl.exe is not installed. " + _NOT_SET_UP)
    except OSError as exc:
        return _result(False, error=f"My sandbox could not start ({type(exc).__name__}: {exc}).")

    out, cut_out = _tail(_decode(getattr(completed, "stdout", None)))
    err, cut_err = _tail(_decode(getattr(completed, "stderr", None)))
    code = getattr(completed, "returncode", None)
    if code in _TIMEOUT_EXIT_CODES:
        return _result(
            False,
            error=f"Timed out after {seconds}s in my sandbox.",
            exit_code=code,
            stdout=out,
            stderr=err,
            timed_out=True,
            truncated=cut_out or cut_err,
        )
    return _result(
        code == 0,
        exit_code=code,
        stdout=out,
        stderr=err,
        truncated=cut_out or cut_err,
    )


def format_result(command: str, result: dict[str, Any]) -> str:
    """Reply text: says it ran in NOVA's sandbox, shows exit code and output."""
    if result.get("error") and result.get("exit_code") is None and not result.get("stdout") and not result.get("stderr"):
        return str(result["error"])
    lines = []
    if result.get("timed_out"):
        lines.append(f"Ran in my sandbox (not on your PC): `{command}` timed out.")
    else:
        lines.append(f"Ran in my sandbox (not on your PC), exit code {result.get('exit_code')}:")
    body = str(result.get("stdout") or "")
    err = str(result.get("stderr") or "")
    if err:
        body = (body + ("\n" if body and not body.endswith("\n") else "") + "[stderr]\n" + err)
    body = body.rstrip("\n")
    lines.append("```\n" + (body if body else "(no output)") + "\n```")
    if result.get("truncated"):
        lines.append(f"(Output was long, so this is only the last {MAX_OUTPUT_CHARS} characters.)")
    return "\n".join(lines)


__all__ = [
    "DISTRO",
    "SANDBOX_CWD",
    "build_argv",
    "clamp_timeout",
    "format_result",
    "run_in_sandbox",
    "sandbox_status",
]
