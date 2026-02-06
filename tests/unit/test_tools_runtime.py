import pytest

from vecna.tools.approvals import ApprovalStore
from vecna.tools.permissions import RiskTier, ToolPermissionManager, ToolPolicy
from vecna.tools.registry import ToolRegistry
from vecna.tools.runtime import ToolRuntime
from vecna.tools.types import ToolExecutionContext, ToolResult, ToolSpec


@pytest.mark.asyncio
async def test_runtime_executes_allowed_tool():
    registry = ToolRegistry()
    spec = ToolSpec(name="echo", description="echo", input_schema={"text": "string"})
    registry.register(spec, executor=lambda args, ctx: ToolResult("echo", True, args["text"]))
    runtime = ToolRuntime(registry=registry, permission_manager=ToolPermissionManager(ToolPolicy()))

    text = '<TOOL_CALL>{"name":"echo","args":{"text":"hi"}}</TOOL_CALL>'
    modified, results = await runtime.execute_calls(text, ToolExecutionContext())
    assert results[0].output == "hi"
    assert "<TOOL_RESULT" in modified


@pytest.mark.asyncio
async def test_runtime_denies_tool():
    registry = ToolRegistry()
    spec = ToolSpec(name="echo", description="echo", input_schema={"text": "string"})
    registry.register(spec, executor=lambda args, ctx: ToolResult("echo", True, args["text"]))
    policy = ToolPolicy(risk_actions={})
    runtime = ToolRuntime(registry=registry, permission_manager=ToolPermissionManager(policy))

    text = '<TOOL_CALL>{"name":"echo","args":{"text":"hi"}}</TOOL_CALL>'
    modified, results = await runtime.execute_calls(text, ToolExecutionContext())
    assert results[0].success is False
    assert "<TOOL_RESULT" in modified


@pytest.mark.asyncio
async def test_runtime_preserves_tool_result_order():
    registry = ToolRegistry()
    spec = ToolSpec(name="echo", description="echo", input_schema={"text": "string"})
    registry.register(spec, executor=lambda args, ctx: ToolResult("echo", True, args["text"]))
    runtime = ToolRuntime(registry=registry, permission_manager=ToolPermissionManager(ToolPolicy()))

    text = (
        '<TOOL_CALL>{"name":"echo","args":{"text":"first"}}</TOOL_CALL>'
        " and "
        '<TOOL_CALL>{"name":"echo","args":{"text":"second"}}</TOOL_CALL>'
    )
    modified, results = await runtime.execute_calls(text, ToolExecutionContext())
    assert [result.output for result in results] == ["first", "second"]
    assert modified.index("first") < modified.index("second")
    assert "<TOOL_RESULT" in modified


@pytest.mark.asyncio
async def test_runtime_handles_unknown_tool():
    registry = ToolRegistry()
    runtime = ToolRuntime(registry=registry, permission_manager=ToolPermissionManager(ToolPolicy()))

    text = '<TOOL_CALL>{"name":"unknown","args":{}}</TOOL_CALL>'
    modified, results = await runtime.execute_calls(text, ToolExecutionContext())
    assert results[0].success is False
    assert results[0].error == "unknown tool"
    assert "<TOOL_RESULT" in modified


@pytest.mark.asyncio
async def test_runtime_handles_executor_exception():
    registry = ToolRegistry()
    spec = ToolSpec(name="boom", description="boom", input_schema={})

    def executor(args, ctx):
        raise RuntimeError("boom")

    registry.register(spec, executor=executor)
    runtime = ToolRuntime(registry=registry, permission_manager=ToolPermissionManager(ToolPolicy()))

    text = '<TOOL_CALL>{"name":"boom","args":{}}</TOOL_CALL>'
    modified, results = await runtime.execute_calls(text, ToolExecutionContext())
    assert results[0].success is False
    assert results[0].error == "boom"
    assert "<TOOL_RESULT" in modified


@pytest.mark.asyncio
async def test_runtime_normalizes_non_tool_result():
    registry = ToolRegistry()
    spec = ToolSpec(name="bad", description="bad", input_schema={})
    registry.register(spec, executor=lambda args, ctx: "not a tool result")
    runtime = ToolRuntime(registry=registry, permission_manager=ToolPermissionManager(ToolPolicy()))

    text = '<TOOL_CALL>{"name":"bad","args":{}}</TOOL_CALL>'
    modified, results = await runtime.execute_calls(text, ToolExecutionContext())
    assert results[0].success is False
    assert results[0].error == "invalid tool result"
    assert "<TOOL_RESULT" in modified


@pytest.mark.asyncio
async def test_runtime_requires_approval_for_low_risk_when_policy_asks(tmp_path):
    registry = ToolRegistry()
    spec = ToolSpec(name="echo", description="echo", input_schema={"text": "string"})
    registry.register(spec, executor=lambda args, ctx: ToolResult("echo", True, args["text"]))
    policy = ToolPolicy(risk_actions={RiskTier.LOW: "ask"})
    store = ApprovalStore(path=tmp_path / "approvals.jsonl")
    runtime = ToolRuntime(
        registry=registry,
        permission_manager=ToolPermissionManager(policy),
        approval_store=store,
    )

    text = '<TOOL_CALL>{"name":"echo","args":{"text":"hi"}}</TOOL_CALL>'
    modified, results = await runtime.execute_calls(text, ToolExecutionContext())

    assert results[0].success is False
    assert results[0].error.startswith("approval required:")
    assert "<TOOL_RESULT" in modified
    pending = store.get_pending()
    assert len(pending) == 1
    assert pending[0].tool_name == "echo"
