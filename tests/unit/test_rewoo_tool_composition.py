"""Unit tests for ReWOO tool composition and input validation."""

import pytest

from vecna.orchestrator.rewoo import RewooEngine, execute_rewoo_plan, parse_rewoo_plan
from vecna.tools.permissions import ToolPermissionManager, ToolPolicy
from vecna.tools.registry import ToolRegistry
from vecna.tools.runtime import ToolRuntime
from vecna.tools.types import ToolExecutionContext, ToolResult, ToolSpec


def _build_runtime_and_registry() -> tuple[ToolRuntime, ToolRegistry]:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(name="echo", description="echo", input_schema={"text": "string"}),
        executor=lambda args, ctx: ToolResult("echo", True, args["text"]),
    )
    runtime = ToolRuntime(
        registry=registry,
        permission_manager=ToolPermissionManager(ToolPolicy()),
    )
    return runtime, registry


@pytest.mark.asyncio
async def test_rewoo_tool_composition_accepts_json_object_and_resolves_references():
    runtime, registry = _build_runtime_and_registry()
    plan = parse_rewoo_plan(
        """Plan: compose tool calls
E1: echo[{"text":"alpha"}]
E2: echo[{"text":"#E1 beta"}]
Final: Use #E2
"""
    )
    engine = RewooEngine(runtime=runtime, registry=registry)

    engine.validate_plan(plan, registry)
    execution = await execute_rewoo_plan(plan, runtime, ToolExecutionContext())

    assert execution.artifacts["E1"] == "alpha"
    assert execution.artifacts["E2"] == "alpha beta"


@pytest.mark.parametrize(
    ("raw_input", "message"),
    [
        ("not-json", "invalid JSON input for E1"),
        ('"plain-string"', "JSON input for E1 must be an object"),
    ],
)
def test_validate_plan_rejects_non_object_or_invalid_json_step_inputs(raw_input: str, message: str):
    runtime, registry = _build_runtime_and_registry()
    plan = parse_rewoo_plan(
        f"""Plan: invalid step input
E1: echo[{raw_input}]
Final: done
"""
    )
    engine = RewooEngine(runtime=runtime, registry=registry)

    with pytest.raises(ValueError, match=message):
        engine.validate_plan(plan, registry)
