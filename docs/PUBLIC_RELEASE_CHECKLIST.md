# Eva Public Release Checklist

Use this before sharing a community build.

## Safety

- [ ] Confirm license file is present and uses PolyForm Noncommercial License 1.0.0.
- [ ] Confirm README is reviewed for public/source-available wording.
- [ ] Confirm `.env.example` uses placeholders only.
- [ ] Confirm `.env.local` is ignored and not staged.
- [ ] Confirm API keys are not committed.
- [ ] Confirm secret scan passed.
- [ ] Confirm runtime data is not committed.
- [ ] Confirm personal Research Memory database files are not committed.
- [ ] Confirm sample Research Memory notes are fake only.
- [ ] Confirm screenshots, logs, traces, and caches are not committed.
- [ ] Confirm private browser/session data is not committed.
- [ ] Confirm local model files are not committed.
- [ ] Confirm GitHub repo visibility choice has been reviewed.

## Execution Gates

- [ ] MCP execution remains disabled.
- [ ] Playwright execution remains disabled.
- [ ] PyAutoGUI execution remains disabled.
- [ ] WhatsApp automatic send remains disabled.
- [ ] File write/edit/delete workflows remain unavailable or refused.
- [ ] Normal chat is not routed through Eva v2.
- [ ] Vector search remains disabled by default.

## Demo Surface

- [ ] `eva release status` is readable.
- [ ] `eva public checklist` is readable.
- [ ] `eva demo scenarios` lists safe scenarios.
- [ ] `eva demo run whatsapp-confirmation` says no real action executed.
- [ ] `eva safety test read .env.local` hard-blocks.
- [ ] `eva doctor public` avoids network, package installs, and secret reads.
- [ ] `eva public hardening status` is readable.
- [ ] `eva public release audit` is readable.
- [ ] `research memory import demo` imports fake notes only.

## Wording

- [ ] Use: local data/control with API-backed LLM reasoning when configured.
- [ ] Do not claim Eva is entirely local-only.
- [ ] Do not claim Eva is open-source if the intended model is source-available/non-commercial.
- [ ] Confirm no commercial resale is allowed if using PolyForm Noncommercial.
- [ ] Confirm commercial use, paid redistribution, hosted commercial services, and resale require separate written permission.
- [ ] Clearly explain that public demos simulate actions and do not send, delete, post, merge, or run MCP tools.
