from vecna.tools.permissions import ToolPolicy


class ToolRuntime:
    def __init__(self, registry, tool_policy=None) -> None:
        self.registry = registry
        self.tool_policy = ToolPolicy(tool_policy) if tool_policy else None

    def execute(self, tool_call: str) -> str:
        parts = tool_call.split() if tool_call else []
        if len(parts) < 2:
            return "Invalid tool call"
        tool_name = parts[1]
        if self.tool_policy and self.tool_policy.is_denied(tool_name):
            return f"Tool {tool_name} denied by policy"
        if self.tool_policy and self.tool_policy.is_ask(tool_name):
            return f"Tool {tool_name} requires approval"
        return "Tool execution not implemented"
