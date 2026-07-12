# Eva Phase 30 Dirty Tree Manifest

Phase 30 Release Candidate Hardening / Commit Planning is complete after this pass.

The audited baseline was clean on `main` at `4f364d2`, matching `origin/main`. The Phase 30 patch intentionally creates an uncommitted review tree.

Phase 30 is report/status/planning only. The commit plan is text only.

## Changed-area groups

- Core routing and command integration.
- Capability registry, resource mappings, and report-only tool schemas.
- Planner, Control Center, AI OS, and team-review status.
- Existing release, safety, limitation, verification, and current-state docs.
- Master verifier registration.

## New-area groups

- `backend/eva/release_candidate/`: deterministic RC models and reports.
- Dedicated Phase 30 RC overview, commit plan, manifest, checklist, and hardening docs.
- `scripts/verify_eva_release_candidate_hardening.py`: focused Phase 30 verifier.

This manifest is an audited snapshot. Eva does not run Git, inspect arbitrary filesystem content, or expose private paths.

## Phase 30 boundary

For Phase 30, no git add/commit/tag/push was performed and no publishing/uploading was performed. No provider SDKs or package installs were added. No real LLM/API/provider calls happen.

No `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config contents are read. Arbitrary file reads/writes are blocked. Browser/desktop/shell/cloud/MCP execution and tool execution remain locked.

CodingAgent remains preview/report/status only. News remains local/mock or safe-read-only. Voice remains a locked/mock foundation. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated write path.

Next safe step: user-approved commit execution outside Eva or a separate explicit commit-approval phase.
