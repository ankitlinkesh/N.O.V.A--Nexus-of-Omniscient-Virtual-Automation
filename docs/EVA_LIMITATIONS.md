# Eva Known Limitations

- Eva is a local-first agent foundation, not an unrestricted autonomous operator.
- Phase 29 is a local report/status/demo profile and does not publish anything.
- Browser access is public-URL read-only observation only; browser control is unavailable.
- Desktop access is one-shot observation only; desktop control remains unavailable.
- News is local/mock or safe-read-only and does not crawl unrestrictedly.
- CodingAgent prepares plans and reports but cannot edit source or apply patches.
- Voice remains a locked/mock foundation without microphone or audio execution.
- Live provider calls are outside the Phase 29 public profile.
- Shell, test, package, git, cloud, MCP, and tool execution remain locked.
- Broad filesystem mutation remains blocked.
- Phase 12L narrow approved text-file creation is a gated write path.
- Production security, hosted service operation, deployment, and release publication are not claimed.

## Phase 30 limitations

Phase 30 Release Candidate Hardening / Commit Planning is complete after this pass. Phase 30 is report/status/planning only. The commit plan is text only.

- RC reports do not inspect live Git or arbitrary filesystem state through Eva.
- RC commit planning does not stage, commit, tag, push, publish, upload, or execute tools.
- For Phase 30, no git add/commit/tag/push was performed and no publishing/uploading was performed.
- No provider SDKs or package installs were added; no real LLM/API/provider calls happen.
- No `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config contents are read.
- Arbitrary file reads/writes and browser/desktop/shell/cloud/MCP execution remain blocked.
- CodingAgent remains preview/report/status only; News remains local/mock or safe-read-only; Voice remains locked/mock.
- Phase 12L narrow approved new `.md`/`.txt` creation remains a gated write path.
- Any later commit requires explicit user approval outside Eva or a separate explicit commit-approval phase.
