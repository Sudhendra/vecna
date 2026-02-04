from vecna.tools.permissions import ToolPolicy


class ToolRuntime:
    def __init__(self, registry, tool_policy=None) -> None:
        self.registry = registry
        self.tool_policy = ToolPolicy(tool_policy) if tool_policy else None

    def execute(self, tool_call: str) -> str:
        tool_name = tool_call.split()[1] if tool_call else ""
        if self.tool_policy and self.tool_policy.is_denied(tool_name):
            return f"Tool {tool_name} denied by policy"
        return "Tool execution not implemented"
