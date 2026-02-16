"""Runtime executor for parsed tool calls and approval controls."""

import inspect
import re
import time
from dataclasses import dataclass
from typing import Dict, List, Tuple

from vecna.tools.approvals import ApprovalStore
from vecna.tools.audit import ToolAuditEvent, ToolAuditLogger
from vecna.tools.parser import parse_tool_calls
from vecna.tools.permissions import RiskTier, ToolPermissionManager, assess_tool_risk
from vecna.tools.quotas import ToolQuotaManager
from vecna.tools.registry import ToolRegistry
from vecna.tools.types import ToolExecutionContext, ToolResult


_TOOL_APPROVAL_TAG_RE = re.compile(r"<TOOL_APPROVAL\b[^>]*/>", re.IGNORECASE)
_TOOL_APPROVAL_ATTR_RE = re.compile(r'([a-zA-Z_]+)\s*=\s*"([^"]*)"')


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
        quota_manager: ToolQuotaManager | None = None,
        config: RuntimeConfig | None = None,
    ) -> None:
        self.registry = registry
        self.permission_manager = permission_manager
        self.audit_logger = audit_logger or ToolAuditLogger()
        self.approval_store = approval_store or ApprovalStore()
        self.quota_manager = quota_manager
        self.config = config or RuntimeConfig()

    async def execute_calls(
        self, text: str, context: ToolExecutionContext
    ) -> Tuple[str, List[ToolResult]]:
        text = self._process_inline_approvals(text)

        if not self.config.auto_execute_tools:
            return text, []

        calls = parse_tool_calls(text)
        if not calls:
            return text, []

        results: List[ToolResult] = []
        modified = text

        for call in reversed(calls):
            should_record_usage = False

            if (
                self.quota_manager is not None
                and context.session_id is not None
                and not self.quota_manager.can_execute(context.session_id, call.tool_name)
            ):
                result = ToolResult(call.tool_name, False, "", error="quota exceeded")
                decision_action = "deny"
                risk = RiskTier.LOW
            else:
                try:
                    registered = self.registry.get(call.tool_name)
                except KeyError:
                    result = ToolResult(call.tool_name, False, "", error="unknown tool")
                    decision_action = "deny"
                    risk = RiskTier.LOW
                else:
                    risk = assess_tool_risk(call.tool_name, call.arguments)
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
                    elif decision.action == "allow":
                        should_record_usage = True
                        start = time.perf_counter()
                        try:
                            maybe_result = registered.executor(call.arguments, context)
                            result = (
                                await maybe_result
                                if inspect.isawaitable(maybe_result)
                                else maybe_result
                            )
                        except Exception as exc:
                            result = ToolResult(call.tool_name, False, "", error=str(exc))

                        latency_ms = (time.perf_counter() - start) * 1000

                        if not isinstance(result, ToolResult):
                            result = ToolResult(
                                call.tool_name, False, "", error="invalid tool result"
                            )
                        result.metadata.setdefault("latency_ms", round(latency_ms, 3))
                    else:
                        decision_action = "deny"
                        result = ToolResult(
                            call.tool_name, False, "", error="invalid policy action"
                        )

            if (
                should_record_usage
                and self.quota_manager is not None
                and context.session_id is not None
            ):
                self.quota_manager.record(context.session_id, call.tool_name)

            self.audit_logger.log_event(
                ToolAuditEvent(
                    tool_name=call.tool_name,
                    action=decision_action,
                    risk_tier=risk.value,
                    success=result.success,
                    error=result.error or "",
                    payload={"latency_ms": result.metadata.get("latency_ms")},
                )
            )
            results.append(result)

            replacement = format_tool_result(call, result)
            modified = modified[: call.start_pos] + replacement + modified[call.end_pos :]

        return modified, list(reversed(results))

    def _process_inline_approvals(self, text: str) -> str:
        """Apply inline approval tags and replace with minimal status text."""
        modified = text
        matches = list(_TOOL_APPROVAL_TAG_RE.finditer(text))

        for match in reversed(matches):
            attrs = self._parse_approval_attrs(match.group(0))
            request_id = attrs.get("request_id")
            action = attrs.get("action", "").lower()

            if not request_id or action not in {"approve", "deny"}:
                status = "invalid"
                replacement = '<TOOL_APPROVAL_STATUS status="invalid" />'
            else:
                target_status = "approved" if action == "approve" else "denied"
                updated = self.approval_store.update_status(request_id, target_status)
                status = target_status if updated else "not_found"
                replacement = (
                    f'<TOOL_APPROVAL_STATUS request_id="{request_id}" status="{status}" />'
                )

            modified = modified[: match.start()] + replacement + modified[match.end() :]

        return modified

    def _parse_approval_attrs(self, tag: str) -> Dict[str, str]:
        """Extract attributes from a TOOL_APPROVAL tag."""
        attrs: Dict[str, str] = {}
        for key, value in _TOOL_APPROVAL_ATTR_RE.findall(tag):
            attrs[key.lower()] = value
        return attrs
