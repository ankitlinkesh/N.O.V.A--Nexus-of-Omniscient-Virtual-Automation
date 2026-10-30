# NOVA to-do

Open work, newest first. Move an item to the README phase table when it ships.

## Context engineering

NOVA's small local model (Qwen3-VL-4B) is confused by too many tools. A narrowed tool menu already exists
(`backend/eva/agent/tool_menu.py`: keyword GROUPS, a small always-on CORE, capped at 24 tools,
`EVA_TOOL_MENU_LIMIT`). What is missing is measurement and tuning, not the mechanism.

- Measure it with the eval harness: how often the right tool is on the menu, and how often the model picks it.
- Known gaps to check: the GROUPS list is keyword-only, so typos ("youtbe"), phrasings without a keyword and
  "play ... on youtube" (matches both the spotify and youtube groups) can show the wrong menu.
- The Phase 160 MCP domains (`backend/eva/mcp/domains.py`) could become a second grouping source so the two
  lists cannot drift apart.
- Every extra server or tool added makes this more important.

## Evaluation

We have verifiers but nothing that measures how often the model picks the right tool or invents a result.
Build an eval harness that replays real chat failures and scores tool choice and honesty, without sending
anything or touching the real apps (stubbed tools).

- Seed it from the failures in `data/eva.sqlite3`: "yes confirm", "say hi to kutty on whatsapp",
  "open youbte and play music", "do it again", "is that action complete".
- Use it to measure whether changes work, e.g. the YouTube planner rule and the MCP routing.
- Track: right tool chosen, a send claimed that never happened, loops on a repeated action.

## Ideas from CowAgent

Borrowed ideas, not code: CowAgent is a full competing agent and has no confirm-before-send gate.

- **Scheduler tool:** timed tasks ("remind me at 6", "check news every morning"). NOVA has no scheduler.
  It would be gated like anything else.
- **Memory tiers:** context, daily and core memory with a nightly summary pass. It would help with things
  like "do it again" having no memory of the last request.
- **Skills as manifests:** reusable multi-tool workflows (for example "morning briefing" = news + weather +
  calendar) that route as one unit. That also means fewer tools in front of the model.
- **Telegram channel:** talk to NOVA from a phone with the same confirm flow. It is a real security
  surface, so it needs an allowlist of the owner's account.
- **`mcp.json` hot reload:** a nicer way to manage the MCP servers added in Phase 160.
