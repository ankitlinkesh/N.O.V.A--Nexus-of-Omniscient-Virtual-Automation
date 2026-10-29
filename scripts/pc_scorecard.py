"""Live PC-automation scorecard: drive NOVA through its HTTP API, judge from outside.

    .venv/Scripts/python.exe scripts/pc_scorecard.py [--only id,id] [--port 8766]

Starts its own NOVA server on a scratch data root (EVA_DATA_DIR), so the chats never
reach the user's history, and with the operator's normal settings so real input works.
Every task is judged from OUTSIDE NOVA -- the Calculator display read through UI
Automation, the process list, file contents -- never from NOVA's own reply, which is
how earlier "green" results hid dead paths.

House rules kept: the only app typed into or clicked is Calculator, only labels named
in the message are clicked, no screenshot tasks (they upload the window), approvals are
given only for the scratch files this script creates, every file it creates is removed,
and a Calculator the user already had open is never touched (those tasks are skipped).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
HOME = Path.home()
DOWNLOADS = HOME / "Downloads"
DOCUMENTS = HOME / "Documents"
PREFIX = "nova_scorecard_"
CALC_PROCESSES = {"calculatorapp.exe", "calculator.exe"}


# --- outside-world probes -------------------------------------------------------

def calc_running() -> bool:
    import psutil

    return any((p.info.get("name") or "").lower() in CALC_PROCESSES for p in psutil.process_iter(["name"]))


def calc_display() -> str | None:
    """The Calculator result as text ("19"), read through UI Automation."""
    try:
        import uiautomation as auto

        window = auto.WindowControl(searchDepth=1, Name="Calculator")
        if not window.Exists(2):
            return None
        result = window.TextControl(AutomationId="CalculatorResults")
        if not result.Exists(2):
            return None
        text = result.Name or ""
        match = re.search(r"-?[\d,]+(?:\.\d+)?", text.replace("\u202f", ""))
        return match.group(0).replace(",", "") if match else None
    except Exception:
        return None


def close_calc() -> None:
    import psutil

    for proc in psutil.process_iter(["name"]):
        if (proc.info.get("name") or "").lower() in CALC_PROCESSES:
            try:
                proc.terminate()
            except Exception:
                pass
    time.sleep(1.0)


# --- NOVA client -----------------------------------------------------------------

class Nova:
    def __init__(self, port: int) -> None:
        self.base = f"http://127.0.0.1:{port}"
        self.session_id: str | None = None

    def chat(self, message: str, timeout: float = 180) -> dict:
        body = {"message": message}
        if self.session_id:
            body["session_id"] = self.session_id
        request = urllib.request.Request(
            self.base + "/api/chat",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Eva-Client": "1"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.session_id = payload.get("session_id") or self.session_id
        return payload

    def fresh(self) -> "Nova":
        self.session_id = None
        return self


def start_server(port: int, data_dir: str) -> subprocess.Popen:
    env = dict(os.environ, EVA_DATA_DIR=data_dir, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    log = open(Path(data_dir) / "server.log", "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.eva.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT,
    )
    deadline = time.time() + 90
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2)
            return proc
        except Exception:
            if proc.poll() is not None:
                raise RuntimeError("server exited; see " + str(Path(data_dir) / "server.log"))
            time.sleep(1)
    proc.terminate()
    raise RuntimeError("server did not start in 90s")


# --- tasks -------------------------------------------------------------------------

@dataclass
class Result:
    task: str
    category: str
    ok: bool
    seconds: float
    turns: int
    approvals: int
    detail: str = ""
    replies: list[str] = field(default_factory=list)


@dataclass
class Task:
    id: str
    category: str
    run: Callable[[Nova], tuple[bool, str, int, int, list[str]]]
    needs_calc_free: bool = False


_ACTION = re.compile(r"confirm(?: override)? (act_[0-9a-f]{12})")


def converse(nova: Nova, message: str, *, approve_if: Callable[[str], bool] = lambda _r: False, max_approvals: int = 2):
    """Send one message, approving follow-up prompts only when ``approve_if`` says so."""
    replies: list[str] = []
    approvals = 0
    payload = nova.chat(message)
    replies.append(payload.get("reply", ""))
    while payload.get("requires_confirmation") and approvals < max_approvals:
        reply = payload.get("reply", "")
        match = _ACTION.search(reply)
        if not match or not approve_if(reply):
            break
        phrase = "confirm override " if "confirm override" in reply else "confirm "
        approvals += 1
        payload = nova.chat(phrase + match.group(1))
        replies.append(payload.get("reply", ""))
    return payload, replies, approvals


def _calc_task(message: str, expected: str):
    def run(nova: Nova):
        close_calc()
        _payload, replies, approvals = converse(nova.fresh(), message)
        time.sleep(1.0)
        shown = calc_display()
        return shown == expected, f"display={shown!r} expected={expected!r}", len(replies), approvals, replies
    return run


def _open_calc(nova: Nova):
    close_calc()
    _payload, replies, approvals = converse(nova.fresh(), "open calculator")
    time.sleep(2.0)
    ok = calc_running() and calc_display() is not None
    return ok, f"running={calc_running()}", len(replies), approvals, replies


def _close_calc(nova: Nova):
    if not calc_running():
        converse(nova.fresh(), "open calculator")
        time.sleep(2.0)
    _payload, replies, approvals = converse(nova.fresh(), "close calculator", approve_if=lambda r: "calculator" in r.lower())
    time.sleep(1.5)
    return not calc_running(), f"still_running={calc_running()}", len(replies), approvals, replies


def _read_file_token(nova: Nova):
    token = "QZ-" + str(int(time.time()))[-6:]
    path = DOWNLOADS / f"{PREFIX}note.txt"
    path.write_text(f"Meeting notes.\nThe access code for the demo is {token}.\n", encoding="utf-8")
    _payload, replies, approvals = converse(nova.fresh(), f"read Downloads/{path.name} and tell me the access code", approve_if=lambda r: path.name in r)
    ok = token in replies[-1]
    return ok, f"token_in_reply={ok}", len(replies), approvals, replies


def _copy_file(nova: Nova):
    src = DOWNLOADS / f"{PREFIX}copy_src.txt"
    dst = DOCUMENTS / src.name
    src.write_text("copy me exactly\n", encoding="utf-8")
    if dst.exists():
        dst.unlink()
    _payload, replies, approvals = converse(
        nova.fresh(), f"copy Downloads/{src.name} to my Documents folder", approve_if=lambda r: src.name in r
    )
    time.sleep(0.5)
    ok = dst.exists() and dst.read_text(encoding="utf-8") == "copy me exactly\n" and src.exists()
    return ok, f"copied={dst.exists()}", len(replies), approvals, replies


def _file_then_calc(nova: Nova):
    path = DOWNLOADS / f"{PREFIX}number.txt"
    path.write_text("The number is 14\n", encoding="utf-8")
    close_calc()
    _payload, replies, approvals = converse(
        nova.fresh(),
        f"read Downloads/{path.name}, then open calculator and type the number from the file followed by *3= into it",
        # Approve only what we can see: the prompt must show the exact text it will type.
        approve_if=lambda r: path.name in r or "It will type exactly: `14*3=`" in r,
    )
    time.sleep(1.0)
    shown = calc_display()
    return shown == "42", f"display={shown!r} expected='42'", len(replies), approvals, replies


def _missing_app(nova: Nova):
    import psutil

    before = {p.pid for p in psutil.process_iter()}
    _payload, replies, approvals = converse(nova.fresh(), "open the app zzqxvr")
    text = replies[-1].lower()
    honest = any(w in text for w in ("couldn't", "could not", "can't", "cannot", "not find", "no app", "not installed", "don't see", "didn't find", "not recognized", "isn't recognized", "unable to find", "was not found", "is not found"))
    new = [p for p in psutil.process_iter(["name"]) if p.pid not in before and "zzqx" in (p.info.get("name") or "").lower()]
    return honest and not new, f"honest={honest}", len(replies), approvals, replies


def _system_disk(nova: Nova):
    free_gb = shutil.disk_usage("C:\\").free / 1024**3
    _payload, replies, approvals = converse(nova.fresh(), "how much free space is on my C drive?")
    numbers = [float(n) for n in re.findall(r"(\d+(?:\.\d+)?)\s*GB", replies[-1])]
    ok = any(abs(n - free_gb) <= max(1.0, free_gb * 0.1) for n in numbers)
    return ok, f"actual={free_gb:.1f}GB said={numbers}", len(replies), approvals, replies


def _sandbox_math(nova: Nova):
    _payload, replies, approvals = converse(nova.fresh(), "in your terminal, run: echo $((6*7*1000+123))")
    ok = "42123" in replies[-1]
    return ok, "42123 in reply" if ok else "missing", len(replies), approvals, replies


TASKS = [
    Task("open_calc", "launch", _open_calc, needs_calc_free=True),
    Task("calc_click_labels", "click", _calc_task('open calculator and click "Seven", "Plus", "Two", "Equals"', "9"), needs_calc_free=True),
    Task("calc_type", "type", _calc_task('open calculator and type "12+7=" into it', "19"), needs_calc_free=True),
    Task("read_file", "files", _read_file_token),
    Task("copy_file", "files+approval", _copy_file),
    Task("file_then_calc", "multi-step", _file_then_calc, needs_calc_free=True),
    Task("missing_app", "recovery", _missing_app),
    Task("disk_space", "system", _system_disk),
    Task("sandbox_math", "terminal", _sandbox_math),
    Task("close_calc", "launch", _close_calc, needs_calc_free=True),
]


def cleanup() -> None:
    for folder in (DOWNLOADS, DOCUMENTS):
        for path in folder.glob(PREFIX + "*"):
            try:
                path.unlink()
            except OSError:
                pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    chosen = [t for t in TASKS if not args.only or t.id in args.only.split(",")]

    user_had_calc = calc_running()
    data_dir = tempfile.mkdtemp(prefix="nova_scorecard_data_")
    server = start_server(args.port, data_dir)
    nova = Nova(args.port)
    results: list[Result] = []
    try:
        for task in chosen:
            if task.needs_calc_free and user_had_calc:
                results.append(Result(task.id, task.category, False, 0.0, 0, 0, "skipped: user's own Calculator is open"))
                continue
            started = time.perf_counter()
            try:
                ok, detail, turns, approvals, replies = task.run(nova)
            except Exception as exc:
                ok, detail, turns, approvals, replies = False, f"error: {type(exc).__name__}: {exc}", 0, 0, []
            results.append(Result(task.id, task.category, ok, round(time.perf_counter() - started, 1), turns, approvals, detail, [r[:400] for r in replies]))
            print(f"{'PASS' if ok else 'FAIL'} {task.id:18s} {results[-1].seconds:6.1f}s  {detail}", flush=True)
    finally:
        if not user_had_calc:
            close_calc()
        cleanup()
        server.terminate()
        try:
            server.wait(15)
        except Exception:
            server.kill()
        time.sleep(1.0)
        shutil.rmtree(data_dir, ignore_errors=True)  # the scratch chats/ledger/traces of this run

    ran = [r for r in results if not r.detail.startswith("skipped")]
    passed = sum(r.ok for r in ran)
    print(f"\nScore: {passed}/{len(ran)} tasks passed (judged outside NOVA); skipped {len(results) - len(ran)}")
    out = Path(args.out) if args.out else Path(tempfile.gettempdir()) / "nova_scorecard_results.json"
    out.write_text(json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Details: {out}")
    return 0 if passed == len(ran) else 1


if __name__ == "__main__":
    raise SystemExit(main())
