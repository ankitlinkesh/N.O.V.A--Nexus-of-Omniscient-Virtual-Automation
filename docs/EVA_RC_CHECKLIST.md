# Eva Release-Candidate Checklist

Phase 30 Release Candidate Hardening / Commit Planning is complete after this pass.

Phase 30 is report/status/planning only. The commit plan is text only.

- [x] Dirty tree grouped by milestone and module.
- [x] Public claims checked against browser, desktop, shell, provider, crawler, voice, and source-edit locks.
- [x] Phase 12L documented as a gated write path.
- [x] Commit plan remains text-only and non-executing.
- [x] Control Center, AI OS, capabilities, planner, and team review aligned.
- [x] Public docs checked for user-specific private paths.
- [x] Ignored environment filenames noted without reading contents.
- [x] Focused, quick, full, compile, diff, and status checks included.
- [ ] User reviews the complete diff and explicitly authorizes any later commit.

## Phase 30 boundary

For Phase 30, no git add/commit/tag/push was performed and no publishing/uploading was performed. No provider SDKs or package installs were added. No real LLM/API/provider calls happen.

No `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config contents are read. Arbitrary file reads/writes are blocked. Browser/desktop/shell/cloud/MCP execution and tool execution remain locked.

CodingAgent remains preview/report/status only. News remains local/mock or safe-read-only. Voice remains a locked/mock foundation. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated write path.

Next safe step: user-approved commit execution outside Eva or a separate explicit commit-approval phase.
