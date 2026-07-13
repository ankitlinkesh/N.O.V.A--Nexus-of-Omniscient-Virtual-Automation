from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from ..core.config import ModelSettings
from ..llm.router import attempts_as_dicts, complete_with_fallback
from ..llm.tool_schema import to_openai_tools
from ..tools.registry import ToolRegistry

DecisionType = Literal["answer", "tool_calls", "confirmation_required", "done"]
PlannerMode = Literal["single_turn", "agent_step"]


def _native_function_calling_enabled() -> bool:
    raw = os.environ.get("EVA_NATIVE_FUNCTION_CALLING")
    if raw is None:
        return False
    return raw.strip().lower() not in {"", "0", "false", "no", "off"}


@dataclass(frozen=True)
class PlannedToolCall:
    tool: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlannerDecision:
    type: DecisionType
    reason: str
    tool_calls: list[PlannedToolCall]
    final_response: str
    requires_confirmation: bool = False
    action: str | None = None
    continue_after_tools: bool = True


class PlannerError(RuntimeError):
    pass


class ToolCallPlanner:
    def __init__(self, settings: ModelSettings, registry: ToolRegistry) -> None:
        self.settings = settings
        self.registry = registry
        self.last_llm_attempts: list[dict] = []

    async def plan(
        self,
        message: str,
        history: list[dict[str, str]] | None = None,
        *,
        mode: PlannerMode = "single_turn",
        task_context: dict[str, Any] | None = None,
    ) -> PlannerDecision:
        forced = self._forced_decision(message)
        if forced is not None:
            return forced
        if _native_function_calling_enabled():
            native = await self._native_plan(message, history or [], mode=mode, task_context=task_context or {})
            if native is not None:
                return native
            # else: fall through to the existing JSON-prompt path
        prompt = self._prompt(message, history or [], mode=mode, task_context=task_context or {})
        routed = await complete_with_fallback(
            [{"role": "system", "content": "Return strict JSON only for Eva planner decisions."}, {"role": "user", "content": prompt}],
            self.settings,
            purpose="planner",
            temperature=0.1,
            max_tokens=800,
        )
        self.last_llm_attempts = attempts_as_dicts(routed.attempts)
        if routed.response.ok:
            try:
                data = self._parse_json(routed.response.text)
                return self._validate(data, mode=mode)
            except PlannerError:
                fallback = self._local_agent_step_decision(message, task_context or {}) if mode == "agent_step" else self._local_tool_decision(message)
                if fallback is not None:
                    return fallback
                raise
        fallback = self._local_agent_step_decision(message, task_context or {}) if mode == "agent_step" else self._local_tool_decision(message)
        if fallback is not None:
            return fallback
        raise PlannerError("I could not plan that safely. Try a simpler command.")

    async def _native_plan(
        self,
        message: str,
        history: list[dict[str, str]],
        *,
        mode: PlannerMode,
        task_context: dict[str, Any],
    ) -> PlannerDecision | None:
        try:
            specs = self.registry.planner_specs()
            tools = to_openai_tools(specs)
            valid_names = {s["name"] for s in specs}

            system_prompt = (
                "You are Eva's action planner. If the user wants an action performed, "
                "call the single most appropriate tool. If it is a question you can answer "
                "directly, reply in plain text without calling a tool."
            )
            messages = [{"role": "system", "content": system_prompt}] + list(history or []) + [
                {"role": "user", "content": message}
            ]

            routed = await complete_with_fallback(
                messages,
                self.settings,
                purpose="planner",
                temperature=0.1,
                max_tokens=800,
                tools=tools,
            )
            self.last_llm_attempts = attempts_as_dicts(routed.attempts)

            if not routed.response.ok:
                return None

            if routed.response.tool_calls:
                calls: list[PlannedToolCall] = []
                for entry in routed.response.tool_calls:
                    fn = entry.get("function") or {}
                    name = fn.get("name")
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                    if name in valid_names:
                        calls.append(PlannedToolCall(tool=name, args=args if isinstance(args, dict) else {}))
                if calls:
                    return PlannerDecision(
                        type="tool_calls",
                        reason="native function-calling",
                        tool_calls=calls,
                        final_response="",
                    )
                return None

            if routed.response.text:
                return PlannerDecision(
                    type="answer",
                    reason="native function-calling",
                    tool_calls=[],
                    final_response=routed.response.text.strip(),
                )

            return None
        except Exception:
            return None

    def _forced_decision(self, message: str) -> PlannerDecision | None:
        text = " ".join(message.lower().strip().split())
        power_actions = {
            "shutdown": ("shutdown", "shut down", "turn off"),
            "restart": ("restart", "reboot"),
            "sleep": ("sleep",),
            "sign_out": ("sign out", "log out", "logout"),
        }
        for action, phrases in power_actions.items():
            if any(phrase in text for phrase in phrases):
                return PlannerDecision(
                    type="confirmation_required",
                    reason=f"{action} requires explicit confirmation.",
                    tool_calls=[],
                    final_response=f"This will {action.replace('_', ' ')} your laptop. Confirm?",
                    requires_confirmation=True,
                    action=action,
                    continue_after_tools=False,
                )

        if self._explicit_screen_request(text):
            raw_capture_only = any(word in text for word in ("screenshot", "capture screen", "take a screenshot")) and not any(
                word in text for word in ("what", "tell", "analyze", "analyse", "check", "inspect", "error", "open")
            )
            tool_name = "capture_screen" if raw_capture_only else "analyze_screen"
            args = {} if raw_capture_only else {"question": message.strip()[:800]}
            return PlannerDecision(
                type="tool_calls",
                reason="User explicitly requested one-time screen analysis." if tool_name == "analyze_screen" else "User explicitly requested one-time screen capture.",
                tool_calls=[PlannedToolCall(tool=tool_name, args=args)],
                final_response="",
            )

        return None

    def _local_tool_decision(self, message: str) -> PlannerDecision | None:
        text = " ".join(message.lower().strip().split())
        app_aliases = self._app_aliases()
        for prefix in ("open ", "launch ", "start "):
            if text.startswith(prefix):
                target = text.removeprefix(prefix).strip()
                if target in app_aliases:
                    return PlannerDecision(
                        type="tool_calls",
                        reason="Local fallback mapped a known app request.",
                        tool_calls=[PlannedToolCall(tool="open_app", args={"app": app_aliases[target]})],
                        final_response="",
                    )
                folder = target.removesuffix(" folder").strip()
                if folder in self._known_folders():
                    return PlannerDecision(
                        type="tool_calls",
                        reason="Local fallback mapped a known folder request.",
                        tool_calls=[PlannedToolCall(tool="open_folder", args={"folder": folder})],
                        final_response="",
                    )

        for prefix in ("search web for ", "web search ", "search for ", "google ", "look up "):
            if text.startswith(prefix):
                query = message.strip()[len(prefix):].strip()
                if query:
                    return PlannerDecision(
                        type="tool_calls",
                        reason="Local fallback mapped a web search request.",
                        tool_calls=[PlannedToolCall(tool="web_search", args={"query": query})],
                        final_response="",
                    )

        if self._looks_like_workspace_goal(text):
            if self._looks_like_code_goal(text):
                if text in {"project map", "code project map"} or any(marker in text for marker in ("summarize architecture", "explain feature", "implemented", "provider", "agent", "runner", "router", "browser", "nim")):
                    return PlannerDecision(
                        type="tool_calls",
                        reason="Local fallback mapped a safe code intelligence feature lookup.",
                        tool_calls=[PlannedToolCall(tool="code_explain_feature", args={"feature": self._workspace_search_query(message)})],
                        final_response="",
                    )
                return PlannerDecision(
                    type="tool_calls",
                    reason="Local fallback mapped a safe code search request.",
                    tool_calls=[PlannedToolCall(tool="code_search", args={"query": self._workspace_search_query(message), "limit": 10})],
                    final_response="",
                )
            if text in {"project structure", "inspect eva project", "summarize project", "summarize eva project", "explain the architecture"}:
                return PlannerDecision(
                    type="tool_calls",
                    reason="Local fallback mapped a workspace project summary request.",
                    tool_calls=[PlannedToolCall(tool="workspace_project_summary", args={})],
                    final_response="",
                )
            query = self._workspace_search_query(message)
            return PlannerDecision(
                type="tool_calls",
                reason="Local fallback mapped a safe workspace search request.",
                tool_calls=[PlannedToolCall(tool="workspace_search", args={"query": query, "limit": 10})],
                final_response="",
            )

        if text in {"mute", "volume up", "volume down", "play", "pause", "next song", "previous song"}:
            action_map = {
                "mute": "mute",
                "volume up": "volume_up",
                "volume down": "volume_down",
                "play": "play_pause",
                "pause": "play_pause",
                "next song": "next",
                "previous song": "previous",
            }
            return PlannerDecision(
                type="tool_calls",
                reason="Local fallback mapped a media control request.",
                tool_calls=[PlannedToolCall(tool="media_control", args={"action": action_map[text]})],
                final_response="",
            )

        if text in {"lock", "lock laptop", "lock screen", "lock pc"}:
            return PlannerDecision(
                type="tool_calls",
                reason="Local fallback mapped a lock request.",
                tool_calls=[PlannedToolCall(tool="lock_laptop", args={})],
                final_response="",
            )

        return None

    def _local_agent_step_decision(self, message: str, task_context: dict[str, Any]) -> PlannerDecision | None:
        goal = self._clean_agent_goal(message)
        text = " ".join(goal.lower().split())
        observations = [str(item) for item in task_context.get("observations") or []]
        observed_blob = "\n".join(observations).lower()
        app_aliases = self._app_aliases()

        if any(word in text for word in ("hello", "hi ", "say hello")) and not observations:
            return PlannerDecision(
                type="done",
                reason="Simple greeting goal can be answered directly.",
                tool_calls=[],
                final_response="Yo, I'm here. What are we doing?",
                continue_after_tools=False,
            )

        for prefix in ("open ", "launch ", "start "):
            if text.startswith(prefix):
                target = text.removeprefix(prefix).split(" and ", 1)[0].strip()
                if target in app_aliases and "open_app" not in observed_blob:
                    return PlannerDecision(
                        type="tool_calls",
                        reason="Need to open a known app.",
                        tool_calls=[PlannedToolCall(tool="open_app", args={"app": app_aliases[target]})],
                        final_response="",
                    )
                folder = target.removesuffix(" folder").strip()
                if folder in self._known_folders() and "open_folder" not in observed_blob:
                    return PlannerDecision(
                        type="tool_calls",
                        reason="Need to open a known folder.",
                        tool_calls=[PlannedToolCall(tool="open_folder", args={"folder": folder})],
                        final_response="",
                    )

        if self._explicit_screen_request(text):
            if "analyze_screen" not in observed_blob and "capture_screen" not in observed_blob:
                return PlannerDecision(
                    type="tool_calls",
                    reason="Need to analyze the explicitly requested screen once.",
                    tool_calls=[PlannedToolCall(tool="analyze_screen", args={"question": goal[:800]})],
                    final_response="",
                )
            return PlannerDecision(
                type="done",
                reason="Screen analysis observation is available.",
                tool_calls=[],
                final_response=self._final_from_observations(observations),
                continue_after_tools=False,
            )

        if self._looks_like_workspace_goal(text):
            if self._looks_like_code_goal(text):
                has_code_observation = "code_" in observed_blob or "patch plan" in observed_blob
                if has_code_observation:
                    return PlannerDecision(
                        type="done",
                        reason="Code intelligence observation is available.",
                        tool_calls=[],
                        final_response=self._final_from_observations(observations),
                        continue_after_tools=False,
                    )
                if text.startswith(("plan change", "make a patch plan", "patch plan")):
                    return PlannerDecision(
                        type="tool_calls",
                        reason="Need a read-only code change plan.",
                        tool_calls=[PlannedToolCall(tool="code_plan_change", args={"goal": goal})],
                        final_response="",
                    )
                if "traceback" in text or "debug this" in text or "error" in text:
                    return PlannerDecision(
                        type="tool_calls",
                        reason="Need safe traceback/code debugging.",
                        tool_calls=[PlannedToolCall(tool="code_debug_traceback", args={"traceback": goal})],
                        final_response="",
                    )
                if any(marker in text for marker in ("project map", "architecture", "where is", "implemented", "explain feature", "provider", "agent", "runner", "router", "browser", "nim", "research knowledge")):
                    return PlannerDecision(
                        type="tool_calls",
                        reason="Need code feature explanation.",
                        tool_calls=[PlannedToolCall(tool="code_explain_feature", args={"feature": self._workspace_search_query(goal)})],
                        final_response="",
                    )
                return PlannerDecision(
                    type="tool_calls",
                    reason="Need safe code search.",
                    tool_calls=[PlannedToolCall(tool="code_search", args={"query": self._workspace_search_query(goal), "limit": 10})],
                    final_response="",
                )
            has_workspace_observation = "workspace_" in observed_blob
            if has_workspace_observation:
                return PlannerDecision(
                    type="done",
                    reason="Workspace observation is available.",
                    tool_calls=[],
                    final_response=self._final_from_observations(observations),
                    continue_after_tools=False,
                )
            read_target = self._read_file_target(goal)
            if read_target:
                return PlannerDecision(
                    type="tool_calls",
                    reason="Need to read a safe workspace file.",
                    tool_calls=[PlannedToolCall(tool="workspace_read_file", args={"path": read_target})],
                    final_response="",
                )
            if any(marker in text for marker in ("project structure", "summarize project", "summarize backend", "backend architecture", "explain the architecture", "inspect eva project", "what should we build next")):
                return PlannerDecision(
                    type="tool_calls",
                    reason="Need a safe project-level workspace summary.",
                    tool_calls=[PlannedToolCall(tool="workspace_project_summary", args={})],
                    final_response="",
                )
            return PlannerDecision(
                type="tool_calls",
                reason="Need to search the Eva workspace safely.",
                tool_calls=[PlannedToolCall(tool="workspace_search", args={"query": self._workspace_search_query(goal), "limit": 10})],
                final_response="",
            )

        if self._looks_like_research_goal(text):
            topic = self._research_topic(goal)
            has_research_observation = "research_" in observed_blob or "saved local matches" in observed_blob
            has_fresh_sources = "research_web saved" in observed_blob or "fresh sources" in observed_blob
            if not has_research_observation:
                return PlannerDecision(
                    type="tool_calls",
                    reason="Need to check saved local research knowledge first.",
                    tool_calls=[PlannedToolCall(tool="research_recall", args={"topic": topic, "query": self._research_query(goal), "limit": 5})],
                    final_response="",
                )
            if not has_fresh_sources and ("found 0 saved" in observed_blob or "latest" in text or "current" in text or "research" in text):
                return PlannerDecision(
                    type="tool_calls",
                    reason="Need fresh sources and local research persistence.",
                    tool_calls=[PlannedToolCall(tool="research_web", args={"topic": topic, "query": self._research_query(goal), "max_results": 5})],
                    final_response="",
                )
            return PlannerDecision(
                type="done",
                reason="Research observation is available.",
                tool_calls=[],
                final_response=self._final_from_observations(observations),
                continue_after_tools=False,
            )

        if self._looks_like_web_goal(text):
            query = self._search_query(goal)
            has_web_observation = any(
                marker in observed_blob
                for marker in (
                    "web_search observed",
                    "web_search opened browser fallback",
                    "here are the top results",
                    "want me to open one of these",
                    "i opened a browser search",
                )
            )
            if not has_web_observation:
                return PlannerDecision(
                    type="tool_calls",
                    reason="Need current web results.",
                    tool_calls=[PlannedToolCall(tool="web_search", args={"query": query})],
                    final_response="",
                )
            return PlannerDecision(
                type="done",
                reason="Web search observation is available.",
                tool_calls=[],
                final_response=self._final_from_observations(observations),
                continue_after_tools=False,
            )

        if observations:
            return PlannerDecision(
                type="done",
                reason="Observed tool result is enough to finish.",
                tool_calls=[],
                final_response=self._final_from_observations(observations),
                continue_after_tools=False,
            )

        return PlannerDecision(
            type="answer",
            reason="Goal does not need a tool or is outside safe tools.",
            tool_calls=[],
            final_response="I can help with that, but I need a more specific safe action or research question.",
            continue_after_tools=False,
        )

    def _prompt(self, message: str, history: list[dict[str, str]], *, mode: PlannerMode, task_context: dict[str, Any]) -> str:
        if mode == "agent_step":
            return self._agent_step_prompt(message, history, task_context)
        return self._single_turn_prompt(message, history)

    def _single_turn_prompt(self, message: str, history: list[dict[str, str]]) -> str:
        recent = [
            {"role": item.get("role"), "content": item.get("content", "")[:500]}
            for item in history[-4:]
            if item.get("role") in {"user", "assistant"}
        ]
        return f"""
You are Eva's tool-calling planner. Return strict JSON only. No markdown.

User message:
{message}

Recent chat context:
{json.dumps(recent, ensure_ascii=False)}

Available tool registry:
{json.dumps(self.registry.planner_specs(), ensure_ascii=False)}

Required JSON shape:
{{
  "type": "answer" | "tool_calls" | "confirmation_required",
  "reason": "short internal explanation",
  "tool_calls": [
    {{"tool": "tool_name", "args": {{}}}}
  ],
  "final_response": "natural language response to user if no tool is needed"
}}

Rules:
- If no tool is needed, use type "answer" and put the user-facing response in final_response.
- If tools are needed, use type "tool_calls".
- Maximum 3 tool calls.
- Never call tools outside the registry.
- Never invent tool names.
- Use open_app for known apps such as chrome, spotify, vscode, codex, settings, notepad.
- Use open_folder for known folders such as downloads, documents, desktop, eva folder.
- Use web_search for web searches; use open_url for explicit URLs.
- Use browser_status/browser_current_page for browser state questions such as "what page am I on" or "what website is open".
- Use browser_search for browser-heavy search workflows where the user wants Chrome/browser context. Use browser_open_url for safe explicit URLs when browser verification matters.
- Use browser_summarize_page, browser_extract_links, or browser_save_page_to_research only when the user explicitly asks to summarize/read/extract links/save the current page. Do not read private, login, payment, account, cookie, token, or password content.
- Use media_control for volume, mute, play/pause, next, previous.
- Use lock_laptop for lock requests.
- For shutdown, restart, sleep, sign out, or log out, do not call a tool unless the user explicitly confirms in this same message. If not confirmed, use type "confirmation_required" and final_response should ask for confirmation.
- Use analyze_screen when the user asks Eva to understand, check, inspect, analyze, or identify an error on the screen. Use capture_screen only for a raw screenshot/capture request.
- Use window_active/window_list for active or open window questions. Use window_focus/window_minimize/window_maximize for explicit window-management requests. Use desktop_observe for a bounded desktop state snapshot. Keep include_screen=false unless the user explicitly asks to inspect the screen.
- Use code_search, code_find_symbol, code_project_map, code_explain_feature, code_debug_traceback, or code_plan_change for codebase/symbol/implementation/debugging/patch-plan questions. These tools are read-only and do not edit files.
- Use workspace_search, workspace_read_file, workspace_list_files, workspace_summarize_file, or workspace_project_summary for generic safe file inspection. Workspace tools are read-only.
- Use research_start_topic, research_recall, research_web, research_save_note, or research_summary for local research knowledge commands and long-term topic knowledge.
- No arbitrary shell commands. No camera. No always-on screen watching.
""".strip()

    def _agent_step_prompt(self, message: str, history: list[dict[str, str]], task_context: dict[str, Any]) -> str:
        recent = [
            {"role": item.get("role"), "content": item.get("content", "")[:500]}
            for item in history[-4:]
            if item.get("role") in {"user", "assistant"}
        ]
        compact_context = {
            "goal": task_context.get("goal") or message,
            "plan": task_context.get("plan") or [],
            "observations": (task_context.get("observations") or [])[-6:],
            "reflections": (task_context.get("reflections") or [])[-4:],
            "steps": (task_context.get("steps") or [])[-6:],
            "limits": task_context.get("limits") or {},
        }
        return f"""
You are Eva's bounded agent-step planner. Return strict JSON only. No markdown. Do not reveal hidden chain-of-thought.

User goal:
{message}

Recent chat context:
{json.dumps(recent, ensure_ascii=False)}

Current task state:
{json.dumps(compact_context, ensure_ascii=False)}

Available safe tool registry:
{json.dumps(self.registry.planner_specs(), ensure_ascii=False)}

Required JSON shape:
{{
  "type": "tool_calls" | "answer" | "confirmation_required" | "done",
  "reason": "short visible-safe summary",
  "tool_calls": [
    {{"tool": "tool_name", "args": {{}}}}
  ],
  "final_response": "only if answering or done",
  "continue_after_tools": true
}}

Rules:
- Plan only the next bounded step toward the goal.
- Prefer 1 tool call. Maximum 2 tool calls in one step.
- Never call tools outside the registry. Never invent tool names.
- Do not repeat the same web_search query already present in observations.
- Use web_search for research/current web information.
- Use browser_search for browser-heavy search tasks, browser_current_page for current page questions, browser_summarize_page for explicit current-page summaries, browser_extract_links for explicit link extraction, and browser_save_page_to_research when the user asks to save the current page into research.
- Browser tools must not access cookies, tokens, password fields, payment/account pages, or private page content. If browser reading is blocked, ask for a safe URL or pasted visible text.
- Use research_recall first, then research_web for research knowledge-base goals where the user wants to save, remember, build knowledge, make Eva a superbrain, or research a topic over time.
- Use open_app/open_folder/open_url only for explicit desktop/navigation goals.
- Use analyze_screen when the user explicitly asks to inspect/look/check/analyze the screen or identify a visible error. Use capture_screen only for raw screenshot capture.
- Use window_active/window_list for active or open window questions. Use window_focus/window_minimize/window_maximize for explicit window-management steps. Use verify_last_action after desktop actions when the task depends on knowing whether an action succeeded.
- Use code tools for Eva codebase questions. Prefer code_explain_feature for "where is X implemented", code_project_map for architecture/project map, code_find_symbol for symbol lookup, code_debug_traceback for pasted errors, and code_plan_change for requested patch plans.
- Use workspace tools for generic safe file reads/listing. Use workspace_read_file only when a relative file path is explicit.
- For shutdown, restart, sleep, sign out, or log out, return confirmation_required and do not call a power tool.
- If observations are enough, return type "done" with a concise final_response.
- No arbitrary shell commands. No camera. No hidden screen watching.
""".strip()

    def _parse_json(self, raw: str) -> dict[str, Any]:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
            raise PlannerError(f"Planner returned invalid JSON: {raw[:240]}") from exc

    def _validate(self, data: dict[str, Any], *, mode: PlannerMode) -> PlannerDecision:
        decision_type = data.get("type")
        allowed_types = {"answer", "tool_calls", "confirmation_required"} if mode == "single_turn" else {"answer", "tool_calls", "confirmation_required", "done"}
        if decision_type not in allowed_types:
            raise PlannerError(f"Unsupported planner type: {decision_type}")

        calls = []
        raw_calls = data.get("tool_calls") or []
        if not isinstance(raw_calls, list):
            raise PlannerError("tool_calls must be a list.")
        max_calls = 3 if mode == "single_turn" else 2
        if len(raw_calls) > max_calls:
            raise PlannerError(f"Planner requested more than {max_calls} tool calls.")

        for item in raw_calls:
            if not isinstance(item, dict):
                raise PlannerError("Each tool call must be an object.")
            name = str(item.get("tool", "")).strip()
            args = item.get("args") or {}
            if not isinstance(args, dict):
                raise PlannerError(f"Tool args for {name} must be an object.")
            if self.registry.get(name) is None:
                raise PlannerError(f"Planner requested unknown tool: {name}")
            calls.append(PlannedToolCall(tool=name, args=args))

        final_response = str(data.get("final_response") or "").strip()
        reason = str(data.get("reason") or "").strip()[:260]
        continue_after_tools = bool(data.get("continue_after_tools", True))

        if decision_type in {"answer", "done"} and not final_response:
            raise PlannerError("Planner answer is missing final_response.")
        if decision_type == "tool_calls" and not calls:
            raise PlannerError("Planner selected tool_calls without tool calls.")
        if decision_type == "confirmation_required":
            action = self._extract_action(data, final_response)
            return PlannerDecision(
                type="confirmation_required",
                reason=reason,
                tool_calls=[],
                final_response=final_response or f"This requires confirmation before I can {action}.",
                requires_confirmation=True,
                action=action,
                continue_after_tools=False,
            )

        return PlannerDecision(
            type=decision_type,  # type: ignore[arg-type]
            reason=reason,
            tool_calls=calls,
            final_response=final_response,
            continue_after_tools=continue_after_tools,
        )

    def _extract_action(self, data: dict[str, Any], fallback_text: str) -> str:
        action = str(data.get("action") or "").strip().lower().replace(" ", "_")
        if action:
            return action
        text = fallback_text.lower()
        candidates = {
            "shutdown": ("shutdown", "shut down", "turn off"),
            "restart": ("restart", "reboot"),
            "sleep": ("sleep",),
            "sign_out": ("sign out", "log out", "logout"),
        }
        for normalized, phrases in candidates.items():
            if any(phrase in text for phrase in phrases):
                return normalized
        return "dangerous_action"


    def _explicit_screen_request(self, text: str) -> bool:
        screen_verbs = ("look at", "check", "inspect", "analyze", "analyse", "capture", "see", "view", "identify", "show")
        screen_words = ("screen", "display", "what is open", "what's open", "error")
        return any(verb in text for verb in screen_verbs) and any(word in text for word in screen_words)
    def _app_aliases(self) -> dict[str, str]:
        return {
            "chrome": "chrome",
            "google chrome": "chrome",
            "spotify": "spotify",
            "vscode": "vscode",
            "vs code": "vscode",
            "visual studio code": "vscode",
            "codex": "codex",
            "settings": "settings",
            "notepad": "notepad",
            "calculator": "calculator",
            "edge": "edge",
            "terminal": "terminal",
            "powershell": "powershell",
        }

    def _known_folders(self) -> set[str]:
        return {"downloads", "documents", "desktop", "pictures", "videos", "music", "eva", "eva folder"}

    def _clean_agent_goal(self, message: str) -> str:
        clean = message.strip()
        lowered = clean.lower()
        if lowered.startswith("agent mode:"):
            return clean.split(":", 1)[1].strip() or clean
        if lowered.startswith("eva, handle this"):
            return clean.split("this", 1)[-1].strip(" :") or clean
        return clean

    def _looks_like_web_goal(self, text: str) -> bool:
        return any(word in text for word in ("research", "find", "summarize", "search", "compare", "latest", "best", "github", "repos", "rate limits"))

    def _looks_like_research_goal(self, text: str) -> bool:
        return any(
            marker in text
            for marker in (
                "research ",
                "knowledge base",
                "saved research",
                "local research",
                "find and remember",
                "remember best",
                "make eva a superbrain",
                "what do we know about",
                "nvidia nim",
            )
        )

    def _looks_like_workspace_goal(self, text: str) -> bool:
        return any(
            marker in text
            for marker in (
                "eva project",
                "workspace",
                "project structure",
                "backend architecture",
                "summarize backend",
                "agent runner",
                "llm router",
                "web_search",
                "tavily",
                "implemented",
                "read file",
                "where is",
                "where are",
                "what changed in eva",
                "debug this error in eva",
                "what should we build next",
            )
        )

    def _looks_like_code_goal(self, text: str) -> bool:
        return any(
            marker in text
            for marker in (
                "code",
                "symbol",
                "traceback",
                "patch plan",
                "plan change",
                "implemented",
                "where is",
                "explain feature",
                "debug this",
                "fix this error",
                "nim provider",
                "browser agent",
                "desktop agent",
                "research knowledge",
                "agent runner",
                "llm router",
                "find dead code",
                "todo",
            )
        )

    def _read_file_target(self, goal: str) -> str | None:
        match = re.search(r"\b(?:read|show|inspect)\s+file\s+(.+)$", goal, flags=re.IGNORECASE)
        if not match:
            return None
        return match.group(1).strip(" .\"'")

    def _workspace_search_query(self, goal: str) -> str:
        clean = self._clean_agent_goal(goal)
        lowered = clean.lower()
        for prefix in ("where is ", "where are ", "find file ", "find where ", "search project for ", "search workspace for "):
            if lowered.startswith(prefix):
                return clean[len(prefix):].strip(" ?:") or clean
        return clean

    def _search_query(self, goal: str) -> str:
        clean = self._clean_agent_goal(goal)
        lowered = clean.lower()
        for marker in ("search web for", "search for", "look up", "google", "search"):
            if marker in lowered:
                index = lowered.index(marker) + len(marker)
                return clean[index:].strip(" :") or clean
        replacements = (
            "find and summarize",
            "research",
            "compare",
            "figure out",
            "plan this",
            "do this task",
            "step by step",
            "summarize",
            "find",
        )
        query = clean
        for item in replacements:
            query = re.sub(rf"\b{re.escape(item)}\b", "", query, flags=re.IGNORECASE)
        query = " ".join(query.strip(" :").split())
        return query or clean

    def _research_topic(self, goal: str) -> str:
        clean = self._clean_agent_goal(goal).strip()
        lowered = clean.lower()
        if lowered.startswith("research "):
            return clean[len("research "):].split(":", 1)[0].strip() or clean
        if "about " in lowered:
            return clean[lowered.rindex("about ") + len("about "):].strip(" .?:") or clean
        if " on " in lowered:
            return clean[lowered.rindex(" on ") + len(" on "):].strip(" .?:") or clean
        return self._search_query(clean)[:160] or clean[:160]

    def _research_query(self, goal: str) -> str:
        clean = self._clean_agent_goal(goal).strip()
        if ":" in clean and clean.lower().startswith("research "):
            return clean.split(":", 1)[1].strip() or clean
        return self._search_query(clean)

    def _final_from_observations(self, observations: list[str]) -> str:
        if not observations:
            return "I finished the task."
        latest = observations[-1].strip()
        if latest.lower().startswith(("here are the top results", "i opened a browser search", "research_")):
            return latest
        return "I finished the task. " + " ".join(observations[-3:])
