import inspect
from dataclasses import dataclass
from typing import List, Tuple

from vecna.tools.approvals import ApprovalStore
from vecna.tools.audit import ToolAuditEvent, ToolAuditLogger
from vecna.tools.parser import parse_tool_calls
from vecna.tools.permissions import RiskTier, ToolPermissionManager, assess_code_risk
from vecna.tools.registry import ToolRegistry
from vecna.tools.types import ToolExecutionContext, ToolResult


@dataclass
class RuntimeConfig:
    auto_execute_tools: bool = True


def format_tool_result(call, result: ToolResult) -> str:
    status = "success" if result.success else "error"
    body = result.output if result.success else (result.error or "unknown error")
    return (
        f'{call.raw_text}\n\n<TOOL_RESULT name="{call.tool_name}" status="{status}">\n'
        f"{body}\n</TOOL_RESULT>"
    )


class ToolRuntime:
    def __init__(
        self,
        registry: ToolRegistry,
        permission_manager: ToolPermissionManager,
        audit_logger: ToolAuditLogger | None = None,
        approval_store: ApprovalStore | None = None,
        config: RuntimeConfig | None = None,
    ) -> None:
        self.registry = registry
        self.permission_manager = permission_manager
        self.audit_logger = audit_logger or ToolAuditLogger()
        self.approval_store = approval_store or ApprovalStore()
        self.config = config or RuntimeConfig()

    async def execute_calls(
        self, text: str, context: ToolExecutionContext
    ) -> Tuple[str, List[ToolResult]]:
        if not self.config.auto_execute_tools:
            return text, []

        calls = parse_tool_calls(text)
        if not calls:
            return text, []

        results: List[ToolResult] = []
        modified = text

        for call in reversed(calls):
            try:
                registered = self.registry.get(call.tool_name)
            except KeyError:
                result = ToolResult(call.tool_name, False, "", error="unknown tool")
                decision_action = "deny"
                risk = RiskTier.LOW
            else:
                risk = (
                    assess_code_risk(call.arguments.get("code", ""))
                    if call.tool_name == "python_exec"
                    else RiskTier.LOW
                )
                decision = self.permission_manager.decide(call.tool_name, risk=risk)
                decision_action = decision.action

                if decision.action == "ask":
                    req = self.approval_store.request_approval(call.tool_name, call.arguments)
                    result = ToolResult(
                        call.tool_name,
                        False,
                        "",
                        error=f"approval required: {req.request_id}",
                    )
                elif decision.action == "deny":
                    result = ToolResult(call.tool_name, False, "", error="denied by policy")
                else:
                    try:
                        maybe_result = registered.executor(call.arguments, context)
                        result = (
                            await maybe_result
                            if inspect.isawaitable(maybe_result)
                            else maybe_result
                        )
                    except Exception as exc:
                        result = ToolResult(call.tool_name, False, "", error=str(exc))

                    if not isinstance(result, ToolResult):
                        result = ToolResult(call.tool_name, False, "", error="invalid tool result")

            self.audit_logger.log_event(
                ToolAuditEvent(
                    tool_name=call.tool_name,
                    action=decision_action,
                    risk_tier=risk.value,
                    success=result.success,
                    error=result.error or "",
                )
            )
            results.append(result)

            replacement = format_tool_result(call, result)
            modified = modified[: call.start_pos] + replacement + modified[call.end_pos :]

        return modified, list(reversed(results))
