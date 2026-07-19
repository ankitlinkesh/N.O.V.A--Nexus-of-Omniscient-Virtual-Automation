from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .planner import PlannedToolCall
from ..tools.registry import ToolRegistry


@dataclass(frozen=True)
class ToolExecutionResult:
    ok: bool
    tool: str
    result: Any = None
    error: str | None = None
    requires_confirmation: bool = False
    action: str | None = None
    verification: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "ok": self.ok,
            "tool": self.tool,
            "result": self.result,
            "error": self.error,
        }
        if self.requires_confirmation:
            payload["requires_confirmation"] = True
            payload["action"] = self.action
        if self.verification is not None:
            payload["verification"] = self.verification
        return payload


class ToolExecutor:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def execute_all(self, calls: list[PlannedToolCall]) -> list[ToolExecutionResult]:
        from .policies import max_tools_per_step

        limit = max_tools_per_step()
        results: list[ToolExecutionResult] = []
        stopped_for_confirmation = False
        for call in calls[:limit]:
            result = self.execute(call)
            results.append(result)
            if result.requires_confirmation:
                stopped_for_confirmation = True
                break

        # Phase 64 (Defect 4): calls beyond `limit` used to be dropped with no
        # error, no warning, and nothing told to the model or the user -- the
        # agent would proceed believing the whole plan ran. Only report this
        # when the cap itself is why calls were skipped; a stop for
        # confirmation is already surfaced through requires_confirmation and
        # is not silent truncation.
        if not stopped_for_confirmation and len(calls) > limit:
            skipped = calls[limit:]
            skipped_tools = [call.tool for call in skipped]
            results.append(
                ToolExecutionResult(
                    ok=False,
                    tool="plan_truncated",
                    error=(
                        f"Stopped after {limit} tool call(s) this step: {len(skipped)} more were planned "
                        f"but not executed ({', '.join(skipped_tools)}). Increase EVA_MAX_TOOLS_PER_STEP or "
                        "split the request into smaller steps."
                    ),
                    result={"truncated": True, "limit": limit, "executed": len(results), "skipped_tools": skipped_tools},
                )
            )
        return results

    def execute(self, call: PlannedToolCall) -> ToolExecutionResult:
        spec = self.registry.get(call.tool)
        if spec is None:
            return ToolExecutionResult(ok=False, tool=call.tool, error="Unknown tool.")

        args = dict(call.args or {})
        validation_error = self._validate_args(spec.args_schema, args)
        if validation_error:
            return ToolExecutionResult(ok=False, tool=call.tool, error=validation_error)

        # All permission enforcement lives in ToolRegistry.run(). The gate
        # strips `confirmed` from args, so a planned call can never approve
        # itself; a gated tool comes back as a requires_confirmation dict.
        try:
            result = self.registry.run(call.tool, **args)
        except Exception as exc:
            return ToolExecutionResult(ok=False, tool=call.tool, error=str(exc))

        if isinstance(result, dict) and result.get("requires_confirmation"):
            return ToolExecutionResult(
                ok=False,
                tool=call.tool,
                result=result,
                error=result.get("message") or "This action requires confirmation.",
                requires_confirmation=True,
                action=result.get("pending_id") or call.tool,
            )
        if isinstance(result, dict) and result.get("hard_blocked"):
            return ToolExecutionResult(ok=False, tool=call.tool, result=result, error=result.get("message"))

        # Verification-first (Phase 38): the handler returned, but did the action
        # actually take effect? Independently check its declared post-condition.
        # Only an *independent* failure demotes ok to False (proof the effect did
        # not happen); self-reported/observed/unverified never fabricate success.
        verification: dict[str, Any] | None = None
        ok = True
        error: str | None = None
        try:
            from ..tools.postconditions import verify_tool_effect

            outcome = verify_tool_effect(call.tool, spec.verification_method, args, result)
            verification = outcome.as_dict()
            if outcome.independent and not outcome.verified:
                ok = False
                error = f"post-condition not met: {outcome.detail}"
        except Exception:
            verification = None

        return ToolExecutionResult(ok=ok, tool=call.tool, result=result, error=error, verification=verification)

    def _validate_args(self, schema: dict[str, Any], args: dict[str, Any]) -> str | None:
        properties = schema.get("properties", {}) or {}
        required = schema.get("required", []) or []
        additional = bool(schema.get("additionalProperties", True))

        for key in required:
            if key not in args:
                return f"Missing required argument: {key}"

        if not additional:
            unknown = sorted(set(args) - set(properties))
            if unknown:
                return f"Unknown arguments: {', '.join(unknown)}"

        for key, value in args.items():
            rules = properties.get(key)
            if not isinstance(rules, dict):
                continue
            expected_type = rules.get("type")
            if expected_type == "string" and not isinstance(value, str):
                return f"Argument {key} must be a string."
            if expected_type == "boolean" and not isinstance(value, bool):
                return f"Argument {key} must be a boolean."
            allowed = rules.get("enum")
            if allowed is not None and isinstance(value, str) and value.lower() not in {str(item).lower() for item in allowed}:
                return f"Argument {key} has unsupported value: {value}"

        return None
