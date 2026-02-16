import pytest

from vecna.tools.approvals import ApprovalStore
from vecna.tools.permissions import RiskTier, ToolPermissionManager, ToolPolicy
from vecna.tools.quotas import QuotaConfig, ToolQuotaManager
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
    assert results[0].error is not None
    assert results[0].error.startswith("approval required:")
    assert "<TOOL_RESULT" in modified
    pending = store.get_pending()
    assert len(pending) == 1
    assert pending[0].tool_name == "echo"


@pytest.mark.asyncio
async def test_runtime_uses_tool_specific_risk_for_http_request(tmp_path):
    registry = ToolRegistry()
    spec = ToolSpec(name="http_request", description="http", input_schema={"method": "string"})
    registry.register(spec, executor=lambda args, ctx: ToolResult("http_request", True, "ok"))
    policy = ToolPolicy(risk_actions={RiskTier.LOW: "allow", RiskTier.MEDIUM: "ask"})
    store = ApprovalStore(path=tmp_path / "approvals.jsonl")
    runtime = ToolRuntime(
        registry=registry,
        permission_manager=ToolPermissionManager(policy),
        approval_store=store,
    )

    text = '<TOOL_CALL>{"name":"http_request","args":{"method":"POST"}}</TOOL_CALL>'
    modified, results = await runtime.execute_calls(text, ToolExecutionContext())

    assert results[0].success is False
    assert results[0].error is not None
    assert results[0].error.startswith("approval required:")
    assert "<TOOL_RESULT" in modified
    pending = store.get_pending()
    assert len(pending) == 1
    assert pending[0].tool_name == "http_request"


@pytest.mark.asyncio
async def test_runtime_handles_malformed_http_request_args_without_crashing():
    registry = ToolRegistry()
    spec = ToolSpec(name="http_request", description="http", input_schema={"method": "string"})
    registry.register(spec, executor=lambda args, ctx: ToolResult("http_request", True, "ok"))
    policy = ToolPolicy(risk_actions={RiskTier.MEDIUM: "allow"})
    runtime = ToolRuntime(registry=registry, permission_manager=ToolPermissionManager(policy))

    text = '<TOOL_CALL>{"name":"http_request","args":"bad-args"}</TOOL_CALL>'
    modified, results = await runtime.execute_calls(text, ToolExecutionContext())

    assert results[0].success is True
    assert results[0].output == "ok"
    assert "<TOOL_RESULT" in modified


def test_tool_execution_context_defaults_allowed_fs_roots():
    context = ToolExecutionContext()
    assert context.allowed_fs_roots == []


@pytest.mark.asyncio
async def test_runtime_returns_quota_exceeded_error_when_limit_hit():
    registry = ToolRegistry()
    spec = ToolSpec(name="echo", description="echo", input_schema={"text": "string"})
    registry.register(spec, executor=lambda args, ctx: ToolResult("echo", True, args["text"]))
    quota_manager = ToolQuotaManager(QuotaConfig(per_session=1, per_tool=0))
    runtime = ToolRuntime(
        registry=registry,
        permission_manager=ToolPermissionManager(ToolPolicy()),
        quota_manager=quota_manager,
    )
    context = ToolExecutionContext(session_id="session-1")

    first_text = '<TOOL_CALL>{"name":"echo","args":{"text":"one"}}</TOOL_CALL>'
    _, first_results = await runtime.execute_calls(first_text, context)
    assert first_results[0].success is True

    second_text = '<TOOL_CALL>{"name":"echo","args":{"text":"two"}}</TOOL_CALL>'
    _, second_results = await runtime.execute_calls(second_text, context)
    assert second_results[0].success is False
    assert second_results[0].error == "quota exceeded"
