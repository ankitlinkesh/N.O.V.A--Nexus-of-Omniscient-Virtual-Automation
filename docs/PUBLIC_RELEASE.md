# Eva Public/Community Release

Eva public/community release mode is for showing useful, safe Eva behavior without exposing private configuration, private runtime data, or risky automation.

The intended public posture is: local data/control with API-backed LLM reasoning when configured.

## Included

- Human-readable release and public status commands.
- Safe static demo scenarios.
- Public safety simulator for risky requests.
- Public setup doctor.
- Resource registry explorer helpers.
- Fake Research Memory demo notes.
- v2 dry-run and plan previews for explicit commands only.

## Intentionally Disabled

- Real WhatsApp sending.
- Real PyAutoGUI desktop execution.
- Real Playwright execution.
- MCP execution.
- File delete/write/edit workflows.
- Private browser, email, chat, cookie, token, localStorage, sessionStorage, or password reading.
- Normal chat routing through Eva v2.
- Cloud embeddings or cloud summarization for Research Memory.
- Vector search by default.

## Demo Mode

Demo mode is simulated by design. Commands like `eva demo run whatsapp-confirmation` show the expected plan, selected agent, safety decision, and final simulated result. They do not execute real tools.

## Safety Simulator

Use `eva safety test <request>` to preview how public mode treats risky requests.

Examples:

- `eva safety test read .env.local`
- `eva safety test send WhatsApp to mom saying hi`
- `eva safety test delete Downloads folder`
- `eva safety test use GitHub MCP to merge PR`

## Research Memory Demo Pack

Use `research memory import demo` to import fake sample notes into the local Research Memory runtime store. The sample pack does not include private data and is not imported automatically.

## Source-Available / Non-Commercial Placeholder

Public release licensing is not finalized in this phase. Add the final source-available or non-commercial license text before distribution.

## Do Not Commit

- API keys.
- `.env.local`.
- Runtime data.
- Personal Research Memory database files.
- Screenshots.
- Logs or traces.
- Private browser/session data.
- Local model files.
- Generated code-index caches.
- Pending action ledgers.

## Current Limitation

Public mode is a status, demo, safety, and documentation layer. It does not make risky executor phases available. Confirmed risky pending actions still do not run in this public release phase.
