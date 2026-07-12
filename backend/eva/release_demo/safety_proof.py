from __future__ import annotations


SAFETY_PROOF = (
    "Execution gates remain locked or preview-only.",
    "Public demo commands return deterministic local text.",
    "Secrets, configuration values, sessions, and private runtime dumps are excluded.",
    "Browser control, desktop control, shell, cloud, MCP, and unrestricted crawling remain unavailable.",
    "CodingAgent cannot edit source or apply patches.",
    "Publishing, uploading, packaging, and git release operations are unavailable.",
    "Phase 12L remains a gated file-write boundary.",
)


def safety_proof_text() -> str:
    return "\n".join(
        (
            "Eva public demo safety proof",
            *[f"- {item}" for item in SAFETY_PROOF],
            "- For the exact, code-derived execution boundary (which tools run, which need confirmation), run `eva capability truth`.",
        )
    )
