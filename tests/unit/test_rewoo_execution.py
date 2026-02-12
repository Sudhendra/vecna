"""Unit tests for ReWOO execution helpers."""

import pytest

from vecna.orchestrator.rewoo import (
    execute_rewoo_plan,
    parse_rewoo_plan,
    render_step_input,
    synthesize_rewoo_answer,
)
from vecna.tools.permissions import ToolPermissionManager, ToolPolicy
from vecna.tools.registry import ToolRegistry
from vecna.tools.runtime import ToolRuntime
from vecna.tools.types import ToolExecutionContext, ToolResult, ToolSpec


def test_render_step_input_substitutes_known_artifacts():
    rendered = render_step_input(
        "Summarize #E1 with context from #E2",
        {"E1": "facts", "E2": "notes"},
    )

    assert rendered == "Summarize facts with context from notes"


def test_render_step_input_supports_repeated_references():
    rendered = render_step_input("Combine #E1 then #E1 again", {"E1": "alpha"})

    assert rendered == "Combine alpha then alpha again"


def test_render_step_input_fails_for_unknown_references():
    with pytest.raises(ValueError, match="Unknown ReWOO artifact reference"):
        render_step_input("Use #E9", {"E1": "alpha"})


def _build_runtime(policy: ToolPolicy | None = None) -> ToolRuntime:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(name="echo", description="echo", input_schema={"text": "string"}),
        executor=lambda args, ctx: ToolResult("echo", True, args["text"]),
    )
    return ToolRuntime(
        registry=registry,
        permission_manager=ToolPermissionManager(policy or ToolPolicy()),
    )


def _build_runtime_with_executors(
    executors: dict[str, object], policy: ToolPolicy | None = None
) -> ToolRuntime:
    registry = ToolRegistry()
    for tool_name, executor in executors.items():
        registry.register(
            ToolSpec(name=tool_name, description=tool_name, input_schema={"text": "string"}),
            executor=executor,
        )
    return ToolRuntime(
        registry=registry,
        permission_manager=ToolPermissionManager(policy or ToolPolicy()),
    )


@pytest.mark.asyncio
async def test_execute_rewoo_plan_runs_steps_in_order_and_tracks_statuses():
    runtime = _build_runtime()
    plan = parse_rewoo_plan(
        """Plan: run two echo steps
E1: echo[{"text":"first"}]
E2: echo[{"text":"#E1 second"}]
Final: done
"""
    )

    execution = await execute_rewoo_plan(plan, runtime, ToolExecutionContext())

    assert [step.step_id for step in execution.results] == ["E1", "E2"]
    assert [step.status for step in execution.results] == ["succeeded", "succeeded"]
    assert execution.artifacts["E1"] == "first"
    assert execution.artifacts["E2"] == "first second"


@pytest.mark.asyncio
async def test_execute_rewoo_plan_marks_failed_step_for_unknown_tool():
    runtime = _build_runtime()
    plan = parse_rewoo_plan(
        """Plan: include unknown tool
E1: unknown_tool[{}]
Final: done
"""
    )

    execution = await execute_rewoo_plan(plan, runtime, ToolExecutionContext())

    assert execution.results[0].status == "failed"
    assert execution.results[0].error == "unknown tool"


@pytest.mark.asyncio
async def test_execute_rewoo_plan_marks_failed_step_when_policy_denies():
    policy = ToolPolicy(risk_actions={})
    runtime = _build_runtime(policy=policy)
    plan = parse_rewoo_plan(
        """Plan: denied by policy
E1: echo[{"text":"blocked"}]
Final: done
"""
    )

    execution = await execute_rewoo_plan(plan, runtime, ToolExecutionContext())

    assert execution.results[0].status == "failed"
    assert execution.results[0].error == "denied by policy"


@pytest.mark.asyncio
async def test_execute_rewoo_plan_retries_runtime_error_and_succeeds():
    attempts = {"count": 0}

    def flaky_executor(args, ctx):
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise RuntimeError("boom")
        return ToolResult("flaky", True, "ok")

    runtime = _build_runtime_with_executors({"flaky": flaky_executor})
    plan = parse_rewoo_plan(
        """Plan: retry flaky tool
E1: flaky[{"text":"x"}]
Final: done
"""
    )

    execution = await execute_rewoo_plan(plan, runtime, ToolExecutionContext(), retry_limit=1)

    assert attempts["count"] == 2
    assert execution.results[0].status == "succeeded"
    assert execution.results[0].attempts == 2


@pytest.mark.asyncio
async def test_execute_rewoo_plan_does_not_retry_policy_denied():
    policy = ToolPolicy(risk_actions={})
    runtime = _build_runtime(policy=policy)
    plan = parse_rewoo_plan(
        """Plan: denied by policy
E1: echo[{"text":"blocked"}]
Final: done
"""
    )

    execution = await execute_rewoo_plan(plan, runtime, ToolExecutionContext(), retry_limit=3)

    assert execution.results[0].status == "failed"
    assert execution.results[0].attempts == 1
    assert execution.results[0].error == "denied by policy"


@pytest.mark.asyncio
async def test_execute_rewoo_plan_stops_after_two_consecutive_failures():
    calls = {"echo": 0}

    def always_fail(args, ctx):
        raise RuntimeError("fail")

    def echo(args, ctx):
        calls["echo"] += 1
        return ToolResult("echo", True, args["text"])

    runtime = _build_runtime_with_executors({"boom": always_fail, "echo": echo})
    plan = parse_rewoo_plan(
        """Plan: stop after repeated failures
E1: boom[{"text":"a"}]
E2: boom[{"text":"b"}]
E3: echo[{"text":"should-not-run"}]
Final: done
"""
    )

    execution = await execute_rewoo_plan(plan, runtime, ToolExecutionContext(), retry_limit=0)

    assert [result.step_id for result in execution.results] == ["E1", "E2", "E3"]
    assert [result.status for result in execution.results] == ["failed", "failed", "skipped"]
    assert calls["echo"] == 0


@pytest.mark.asyncio
async def test_synthesize_rewoo_answer_includes_artifacts_and_failures():
    runtime = _build_runtime_with_executors(
        {
            "echo": lambda args, ctx: ToolResult("echo", True, args["text"]),
        }
    )
    plan = parse_rewoo_plan(
        """Plan: gather + fail
E1: echo[{"text":"first"}]
E2: unknown_tool[{}]
Final: done
"""
    )

    execution = await execute_rewoo_plan(plan, runtime, ToolExecutionContext())
    answer = synthesize_rewoo_answer("help with summary", execution)

    assert "help with summary" in answer
    assert "E1: first" in answer
    assert "E2 failed: unknown tool" in answer


@pytest.mark.asyncio
async def test_synthesize_rewoo_answer_has_deterministic_fallback_when_no_successes():
    runtime = _build_runtime_with_executors(
        {"boom": lambda args, ctx: (_ for _ in ()).throw(RuntimeError("boom"))}
    )
    plan = parse_rewoo_plan(
        """Plan: only failing steps
E1: boom[{"text":"x"}]
Final: done
"""
    )

    execution = await execute_rewoo_plan(plan, runtime, ToolExecutionContext(), retry_limit=0)
    answer = synthesize_rewoo_answer("help with summary", execution)

    assert answer.startswith("Unable to complete the task with successful tool steps.")


@pytest.mark.asyncio
async def test_execute_rewoo_plan_truncates_large_artifacts():
    long_output = "x" * 32

    runtime = _build_runtime_with_executors(
        {
            "echo": lambda args, ctx: ToolResult("echo", True, long_output),
        }
    )
    plan = parse_rewoo_plan(
        """Plan: generate large output
E1: echo[{"text":"ignored"}]
Final: Use #E1
"""
    )

    execution = await execute_rewoo_plan(
        plan,
        runtime,
        ToolExecutionContext(),
        max_artifact_chars=10,
    )

    assert execution.artifacts["E1"].startswith("x" * 10)
    assert "[truncated" in execution.artifacts["E1"]
    assert execution.results[0].tool_result is not None
    assert execution.results[0].tool_result.metadata["artifact_truncated"] is True
    assert execution.results[0].tool_result.metadata["full_output"] == long_output
