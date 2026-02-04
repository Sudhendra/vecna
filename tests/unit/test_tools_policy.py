from vecna.tools.runtime import ToolRuntime
from vecna.tools.registry import ToolRegistry
from vecna.tools.audit import ToolAudit
from vecna.tools.router import ToolRouter
from vecna.config.schema import ToolPolicyConfig


def test_tool_policy_denies():
    registry = ToolRegistry()
    runtime = ToolRuntime(registry, tool_policy=ToolPolicyConfig(deny=["execute_code"]))
    result = runtime.execute('TOOL_CALL: execute_code {"code": "print(1)"}')
    assert "denied" in result.lower()


def test_tool_policy_malformed_call_returns_error_string():
    registry = ToolRegistry()
    runtime = ToolRuntime(registry, tool_policy=ToolPolicyConfig())
    result = runtime.execute("TOOL_CALL:")
    assert "invalid" in result.lower()


def test_tool_policy_ask_requires_approval():
    registry = ToolRegistry()
    runtime = ToolRuntime(registry, tool_policy=ToolPolicyConfig(ask=["execute_code"]))
    result = runtime.execute('TOOL_CALL: execute_code {"code": "print(1)"}')
    assert "approval" in result.lower()


def test_tool_policy_allows_tool_execution_not_implemented():
    registry = ToolRegistry()
    runtime = ToolRuntime(registry, tool_policy=ToolPolicyConfig())
    result = runtime.execute('TOOL_CALL: execute_code {"code": "print(1)"}')
    assert "not implemented" in result.lower()
    assert "denied" not in result.lower()


def test_tool_policy_allowlist_rejects_unknown_tool():
    registry = ToolRegistry()
    runtime = ToolRuntime(registry, tool_policy=ToolPolicyConfig(allow=["safe_tool"]))
    result = runtime.execute('TOOL_CALL: execute_code {"code": "print(1)"}')
    assert "denied" in result.lower()


def test_tool_policy_requires_tool_call_prefix():
    registry = ToolRegistry()
    runtime = ToolRuntime(registry, tool_policy=ToolPolicyConfig())
    result = runtime.execute('execute_code {"code": "print(1)"}')
    assert "invalid" in result.lower()


def test_tool_policy_denied_call_records_audit_attempt():
    router = ToolRouter()
    audit = ToolAudit(router)
    registry = ToolRegistry()
    runtime = ToolRuntime(
        registry,
        tool_policy=ToolPolicyConfig(deny=["execute_code"]),
        audit=audit,
    )
    result = runtime.execute('TOOL_CALL: execute_code {"code": "print(1)"}')
    assert "denied" in result.lower()
    assert router._stats["execute_code"]["total"] == 1
    assert router._stats["execute_code"]["success"] == 0
