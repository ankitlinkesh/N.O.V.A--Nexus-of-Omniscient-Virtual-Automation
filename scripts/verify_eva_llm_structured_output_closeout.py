from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DOCS = (
    ROOT / "docs" / "EVA_CURRENT_STATE.md",
    ROOT / "docs" / "EVA_CAPABILITIES.md",
    ROOT / "docs" / "EVA_AGENT_FRAMEWORK.md",
    ROOT / "docs" / "EVA_THREAT_MODEL.md",
    ROOT / "docs" / "EVA_VERIFICATION.md",
)
PHASE15C_VERIFIERS = {
    "verify_eva_llm_structured_output_core.py",
    "verify_eva_llm_structured_output_commands.py",
    "verify_eva_llm_structured_output_wiring.py",
}


def assert_true(condition: object, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    from scripts import verify_eva_all

    texts = {path.name: path.read_text(encoding="utf-8") for path in DOCS}
    for name, text in texts.items():
        assert_true("Phase 15C" in text, f"Phase 15C missing from {name}")

    combined = "\n".join(texts.values()).lower()
    for phrase in (
        "phase 15c structured output validation hardening is complete",
        "mock/local only",
        "live llm/api calls remain locked",
        "no provider sdks are used",
        "no `.env`, `.env.local`, secrets, tokens, cookies, passwords, or browser sessions are read",
        "invalid llm output cannot execute tools",
        "repair does not execute or rewrite user intent",
        "hallucinated capabilities are flagged/rejected",
        "secret-like and private-path-like outputs are flagged",
        "browser/desktop execution remains locked",
        "phase 12l narrow approved new `.md`/`.txt` creation remains a gated write path",
        "next phase is 15d llm router red-team/failure tests",
    ):
        assert_true(phrase in combined, f"Phase 15C closeout documentation missing: {phrase}")

    assert_true(PHASE15C_VERIFIERS <= set(verify_eva_all.FULL_VERIFIERS), "Phase 15C verifiers missing from full profile")
    assert_true(PHASE15C_VERIFIERS <= set(verify_eva_all.QUICK_VERIFIERS), "Phase 15C verifiers missing from quick profile")
    assert_true("verify_eva_llm_structured_output_closeout.py" in verify_eva_all.FULL_VERIFIERS, "closeout verifier missing from full profile")

    print("PASS: Phase 15C documentation and master verifier proof are complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
