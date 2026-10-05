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

    wsl.exe -d nova -u nova --cd /home/nova/workspace --exec bash -c "<WRAPPER>"

``wsl -- bash -c CMD`` re-parses CMD through the login shell and ate ``$var``
expansions, and Windows argument quoting mangles embedded double quotes, so the
command always travels as base64 (UTF-8 first) and the wrapper has no double quotes.

The wrapper (``_wrapper``), all inside the box:
- decodes the command into a temp FILE and runs ``bash -l FILE </dev/null``. Phase 131:
  piping the script into ``bash -l`` made it bash's stdin, so ``head -1`` or ``read``
  ate the script's next line and that line never ran (measured live).
- enforces the time limit with coreutils ``timeout`` (SIGTERM, SIGKILL 5s later):
  killing only the Windows-side wsl.exe client left the command running.
- keeps only the last ``_CAP_BYTES`` of each stream (``tail -c``) so ``yes`` cannot
  stream gigabytes into NOVA's process; ``pipefail`` keeps the command's exit code.
- prints ``_TIMEOUT_MARK`` on stderr only when ``timeout`` really fired (exit 124/137
  AND the limit elapsed), so a command that itself exits 124 is not called a timeout.

Every OS touch sits behind ``_default_runner`` so tests inject a fake and never need
a real WSL (conftest fails any test that reaches the real one).
"""

from __future__ import annotations

import base64
import os
import re
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
HOST_BACKSTOP_S = 30  # host-side wait beyond the in-box limit (covers a WSL cold start)
_CAP_BYTES = 32000  # per stream, kept inside the box; MAX_OUTPUT_CHARS trims after decoding
_TIMEOUT_MARK = "__NOVA_SANDBOX_TIMEOUT__"
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

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
    """UTF-8, except wsl.exe's OWN messages, which are UTF-16LE when it ignores
    WSL_UTF8 (a NUL in the bytes gives that away; a Linux program almost never
    prints NULs)."""
    if data is None:
        return ""
    if isinstance(data, str):
        return data.replace("\x00", "").replace("\ufeff", "")
    raw = bytes(data)
    if raw.startswith(b"\xff\xfe") or b"\x00" in raw:
        return raw.decode("utf-16-le", errors="replace").replace("\ufeff", "")
    return raw.decode("utf-8", errors="replace")


_decode_listing = _decode  # ``wsl --list`` is UTF-16LE on some builds


def _tail(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text, False
    return text[-MAX_OUTPUT_CHARS:], True


def clamp_timeout(timeout_s: Any) -> int:
    try:
        value = int(timeout_s)
    except (TypeError, ValueError, OverflowError):  # OverflowError: JSON Infinity
        value = DEFAULT_TIMEOUT_S
    return max(MIN_TIMEOUT_S, min(value, MAX_TIMEOUT_S))


def _wrapper(encoded: str, seconds: int) -> str:
    """The in-box script (see the module docstring). No double quotes on purpose."""
    s = clamp_timeout(seconds)
    return (
        "f=$(mktemp); e=$(mktemp); trap 'rm -f $f $e' EXIT; "
        f"echo {encoded} | base64 -d > $f; "
        "set -o pipefail; s=$SECONDS; "
        f"timeout -k {KILL_GRACE_S} {s} bash -l $f </dev/null 2> >(tail -c {_CAP_BYTES} > $e) | tail -c {_CAP_BYTES}; "
        "rc=$?; wait; cat $e >&2; "
        f"if [ $rc -eq 124 -o $rc -eq 137 ] && [ $((SECONDS-s)) -ge {s} ]; then echo {_TIMEOUT_MARK} >&2; fi; "
        "exit $rc"
    )


def build_argv(command: str, seconds: int = DEFAULT_TIMEOUT_S) -> list[str]:
    """The exact argv. The command is base64 so no quoting layer can touch it; the
    wrapper runs it from a file with stdin closed, bounded in time and output."""
    encoded = base64.b64encode(command.encode("utf-8")).decode("ascii")
    return [
        _WSL,
        "-d", DISTRO,
        "-u", SANDBOX_USER,
        "--cd", SANDBOX_CWD,
        "--exec", "bash", "-c",
        _wrapper(encoded, seconds),
    ]


def decode_command(argv: list[str]) -> str | None:
    """Inverse of build_argv's encoding (tests and the verifier use it)."""
    match = re.search(r"echo ([A-Za-z0-9+/=]+) \| base64 -d > \$f", argv[-1] if argv else "")
    return base64.b64decode(match.group(1)).decode("utf-8") if match else None


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

    raw_out = getattr(completed, "stdout", None) or b""
    raw_err = getattr(completed, "stderr", None) or b""
    out, cut_out = _tail(_decode(raw_out))
    err, cut_err = _tail(_decode(raw_err))
    # The box keeps only the last _CAP_BYTES of a stream, so a full one was cut there.
    cut_out = cut_out or len(raw_out) >= _CAP_BYTES
    cut_err = cut_err or len(raw_err) >= _CAP_BYTES
    timed_out = _TIMEOUT_MARK in err
    err = err.replace(_TIMEOUT_MARK + "\n", "").replace(_TIMEOUT_MARK, "")
    code = getattr(completed, "returncode", None)
    if timed_out:
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
        lines.append("Ran in my sandbox (not on your PC): it timed out, so I stopped it.")
    else:
        lines.append(f"Ran in my sandbox (not on your PC), exit code {result.get('exit_code')}:")
    body = str(result.get("stdout") or "")
    err = str(result.get("stderr") or "")
    if err:
        body = (body + ("\n" if body and not body.endswith("\n") else "") + "[stderr]\n" + err)
    # Terminal colour codes and carriage-return progress bars are noise in a chat reply.
    body = _ANSI.sub("", body).replace("\r\n", "\n")
    body = "\n".join(line.rsplit("\r", 1)[-1] for line in body.split("\n")).rstrip("\n")
    # A fence longer than any backtick run in the output, so `cat README.md` can't close it.
    longest = max((len(run) for run in re.findall(r"`+", body)), default=0)
    fence = "`" * max(3, longest + 1)
    lines.append(f"{fence}\n" + (body if body else "(no output)") + f"\n{fence}")
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
