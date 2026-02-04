from vecna.tools.permissions import ToolPolicy


class ToolRuntime:
    def __init__(self, registry, tool_policy=None, audit=None) -> None:
        self.registry = registry
        self.tool_policy = ToolPolicy(tool_policy) if tool_policy else None
        self.audit = audit

    def execute(self, tool_call: str) -> str:
        if not tool_call or not tool_call.startswith("TOOL_CALL:"):
            return "Invalid tool call"
        call_body = tool_call[len("TOOL_CALL:") :].lstrip()
        tool_name = call_body.split(maxsplit=1)[0] if call_body else ""
        if not tool_name:
            return "Invalid tool call"
        if self.tool_policy and self.tool_policy.is_denied(tool_name):
            if self.audit:
                self.audit.record(tool_name, success=False)
            return f"Tool {tool_name} denied by policy"
        if self.tool_policy and self.tool_policy.is_ask(tool_name):
            if self.audit:
                self.audit.record(tool_name, success=False)
            return f"Tool {tool_name} requires approval"
        return "Tool execution not implemented"
