# Eva Demo Smoke Test

Phase 32 Post-Push Sync + Demo Smoke Test Hardening is complete after this pass.

The demo smoke test is report/status/checklist only. It helps a fresh operator run a safe local Eva demo after the approved checkpoint commit `e226b96` has been pushed.

Remote moved warning was handled by updating local origin to:

```text
https://github.com/ankitlinkesh/eva-community.git
```

No commit/push/tag/release was performed in Phase 32.

## Safe local demo

Run these Eva commands from chat or the local command surface:

```text
eva release status
eva release demo
eva release commands
eva release capability map
eva release safety proof
eva release readiness
eva release verification
eva release smoke test
eva release post push sync
```

To verify Eva without enabling unsafe features, run terminal verifiers manually:

```powershell
.\.venv\Scripts\python.exe -m compileall backend scripts
.\.venv\Scripts\python.exe scripts\verify_eva_post_push_demo_smoke.py
.\.venv\Scripts\python.exe scripts\verify_eva_all.py --quick --timeout 90
.\.venv\Scripts\python.exe scripts\verify_eva_all.py --full --timeout 90
git diff --check
```

## First-run checklist

- Confirm the local server can start.
- Show the public demo status before capability claims.
- Show the safety proof before any roadmap feature.
- Explain that browser, desktop, shell, cloud, MCP, and CodingAgent execution remain locked.
- Refresh verifier evidence before saying the checkout is ready.

## Boundaries

- Demo smoke test is report/status/checklist only.
- No provider SDKs or package installs.
- No real LLM/API/provider calls happen.
- No `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config contents are read.
- No secrets, tokens, cookies, passwords, browser sessions, or config contents are read.
- Browser/desktop/shell/cloud/MCP execution remains locked.
- CodingAgent remains preview/report/status only.
- Phase 12L narrow approved new `.md`/`.txt` creation remains a gated file write path.
- No new write path was added.

Blocking issues: none after the focused and master verifier sweep passes.
