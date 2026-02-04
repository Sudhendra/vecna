from vecna.tools.runtime import ToolRuntime
from vecna.tools.registry import ToolRegistry
from vecna.config.schema import ToolPolicyConfig


def test_tool_policy_denies():
    registry = ToolRegistry()
    runtime = ToolRuntime(registry, tool_policy=ToolPolicyConfig(deny=["execute_code"]))
    result = runtime.execute('TOOL_CALL: execute_code {"code": "print(1)"}')
    assert "denied" in result.lower()
