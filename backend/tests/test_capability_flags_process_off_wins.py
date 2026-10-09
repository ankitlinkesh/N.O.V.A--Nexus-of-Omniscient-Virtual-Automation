"""A process that turns a capability off cannot be overruled by .env.local.

.env.local overrides the process environment on purpose (it must beat stale shell
exports), so before this nothing could force real input off from outside: the
operator's .env.local sets EVA_ENABLE_REAL_INPUT=1, EVA_V2_PYAUTOGUI_ENABLED=1, MCP,
voice ..., and every verifier in the suite ran with them on. Now an explicit "0" from
the launching process wins, in the off direction only.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_PROBE = (
    "import os, sys; from pathlib import Path; sys.path.insert(0, {root!r});"
    "from backend.eva.core.config import load_local_env;"
    "load_local_env(Path({envfile!r}), override=True);"
    "print(os.environ.get('EVA_ENABLE_REAL_INPUT'), os.environ.get('EVA_MCP_ENABLED'), os.environ.get('NVIDIA_NIM_MODEL'))"
)
_KEYS = {"EVA_ENABLE_REAL_INPUT", "EVA_MCP_ENABLED", "NVIDIA_NIM_MODEL"}


def _probe(envfile: Path, **env_overrides: str) -> list[str]:
    env = {k: v for k, v in os.environ.items() if k not in _KEYS}
    env.update(env_overrides)
    out = subprocess.run(
        [sys.executable, "-c", _PROBE.format(root=str(ROOT), envfile=str(envfile))],
        capture_output=True, text=True, env=env, timeout=60,
    )
    assert out.returncode == 0, out.stderr
    return out.stdout.split()


def _envfile(tmp_path: Path, text: str) -> Path:
    path = tmp_path / ".env.local"
    path.write_text(text, encoding="utf-8")
    return path


def test_process_off_beats_env_local(tmp_path):
    envfile = _envfile(tmp_path, "EVA_ENABLE_REAL_INPUT=1\nEVA_MCP_ENABLED=1\nNVIDIA_NIM_MODEL=from-file\n")
    real_input, mcp, model = _probe(envfile, EVA_ENABLE_REAL_INPUT="0", NVIDIA_NIM_MODEL="from-shell")
    assert real_input == "0"      # denied by the process: the file cannot turn it on
    assert mcp == "1"             # not denied: the file still wins as before
    assert model == "from-file"   # ordinary keys keep .env.local precedence


def test_without_a_denial_env_local_still_wins(tmp_path):
    envfile = _envfile(tmp_path, "EVA_ENABLE_REAL_INPUT=1\nEVA_MCP_ENABLED=1\nNVIDIA_NIM_MODEL=from-file\n")
    real_input, mcp, _ = _probe(envfile)
    assert real_input == "1" and mcp == "1"


def test_a_process_on_does_not_beat_env_local_off(tmp_path):
    envfile = _envfile(tmp_path, "EVA_ENABLE_REAL_INPUT=0\nEVA_MCP_ENABLED=0\nNVIDIA_NIM_MODEL=x\n")
    real_input, _, _ = _probe(envfile, EVA_ENABLE_REAL_INPUT="1")
    assert real_input == "0"  # only the off direction is privileged


def test_verify_all_turns_every_capability_off_for_children():
    from backend.eva.core.config import CAPABILITY_FLAGS

    source = (ROOT / "scripts" / "verify_eva_all.py").read_text(encoding="utf-8")
    assert "for flag in CAPABILITY_FLAGS:" in source and 'child_env[flag] = "0"' in source
    assert {"EVA_ENABLE_REAL_INPUT", "EVA_V2_PYAUTOGUI_ENABLED", "EVA_MCP_ENABLED"} <= set(CAPABILITY_FLAGS)


def test_conftest_clears_every_capability_flag_config_knows():
    from backend.eva.core.config import CAPABILITY_FLAGS

    tree = ast.parse((ROOT / "backend" / "tests" / "conftest.py").read_text(encoding="utf-8"))
    listed = next(
        {elt.value for elt in node.value.elts}
        for node in tree.body
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "CAPABILITY_FLAGS" for t in node.targets)
    )
    assert set(CAPABILITY_FLAGS) <= listed
