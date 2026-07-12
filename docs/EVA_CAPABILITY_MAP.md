# Eva Public Capability Map

- Command system: deterministic local commands and human-readable refusals.
- Planner and agent loop: bounded planning and preview-only action models.
- Capability registry: permissions, resources, schemas, and verifier metadata.
- FileAgent: inspection and previews, plus the existing Phase 12L narrow create gate.
- Browser: public-URL read-only observation; control locked.
- Desktop: one-shot redacted observation; control locked and dry-run policy only.
- News: local/mock or safe-read-only reports; unrestricted crawling locked.
- CodingAgent: task, patch-plan, review, test-plan, risk, and handoff previews; source editing locked.
- Voice: locked/mock foundation; microphone and audio execution locked.
- Release demo: local report/status/profile only; publishing and git release actions locked.

No broad real execution, secret/config/session access, shell/cloud/MCP execution, or new write path is part of the public profile.

Phase 12L narrow approved text-file creation remains a gated file write path.

## Phase 30 release-candidate capabilities

Phase 30 Release Candidate Hardening / Commit Planning is complete after this pass. Phase 30 is report/status/planning only. The commit plan is text only.

- `rc.status`: deterministic readiness and lock status.
- `rc.manifest`: audited dirty-tree grouping snapshot.
- `rc.commit_plan`: human-readable commit candidates and checks as text only.
- `rc.hardening_report`: bounded-claim and safety findings.
- `rc.checklist`: user-reviewable release-candidate checklist.
- `rc.readiness`: safe-to-commit guidance without Git execution.
- `rc.safety_proof`: deterministic safety-boundary evidence.
- `rc.verification`: manual commands without execution.

For Phase 30, no git add/commit/tag/push was performed and no publishing/uploading was performed. No provider SDKs or package installs were added. No real LLM/API/provider calls happen. No `.env`, `.env.local`, secrets, tokens, cookies, passwords, browser sessions, or config contents are read.

Arbitrary file reads/writes and browser/desktop/shell/cloud/MCP/tool execution remain blocked. CodingAgent remains preview/report/status only. News remains local/mock or safe-read-only. Voice remains a locked/mock foundation. Phase 12L narrow approved new `.md`/`.txt` creation remains a gated write path.

Next safe step: user-approved commit execution outside Eva or a separate explicit commit-approval phase.

## Phase 33-42 roadmap capability map

Phase 33 Execution Boundary Audit is complete as a foundation after this pass. It maps Phase 33 through Phase 42 to typed report/status/catalog capabilities.

- Phase 33 `roadmap.execution_boundary_audit`: report-only execution boundary audit.
- Phase 34 `roadmap.command_catalog`: report-only command descriptor catalog.
- Phase 35 `roadmap.capability_catalog`: report-only capability descriptor catalog.
- Phase 36 `roadmap.control_truth_panels`: report-only Control Center and AI OS truth-panel plan.
- Phase 37 `roadmap.frontend_truth`: report-only frontend safe-demo truth status.
- Phase 38 `roadmap.grounded_answers`: report-only grounded answer routing status.
- Phase 39 `roadmap.voice_reliability`: report-only voice reliability status.
- Phase 40 `roadmap.verifier_dashboard`: report-only verifier metadata dashboard status.
- Phase 41 `roadmap.safe_real_pilot`: blocked until later explicit approval.
- Phase 42 `roadmap.release_candidate_v2`: report-only release-candidate v2 hardening status.

Execution boundary audit status: no new execution path is enabled. Roadmap commands classify and report existing surfaces only. Phase 12L narrow approved text-file creation remains a gated file write path.

Phase 42 does not tag, release, upload, publish, package, deploy, or push anything. Browser/desktop/shell/cloud/MCP execution remains locked. Secret/config/session reads remain blocked.
