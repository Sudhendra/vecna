"""ReWOO planning, execution, and synthesis primitives."""

import asyncio
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from vecna.adapters.base import BaseAdapter
from vecna.core.hive_state import HiveState
from vecna.observability.langfuse import trace_span
from vecna.tools.registry import ToolRegistry
from vecna.tools.router import ToolRouter
from vecna.tools.runtime import ToolRuntime
from vecna.tools.types import ToolExecutionContext, ToolResult


logger = logging.getLogger("vecna.orchestrator.rewoo")

_PLAN_LINE_PATTERN = re.compile(r"^Plan:\s*(?P<goal>.+)$")
_STEP_LINE_PATTERN = re.compile(r"^(?P<step_id>E\d+):\s*(?P<tool>\w+)\[(?P<input>.*)\]$")
_FINAL_LINE_PATTERN = re.compile(r"^Final:\s*(?P<template>.+)$")
_REFERENCE_PATTERN = re.compile(r"#(?P<step_id>E\d+)")
_DEFAULT_FINAL_TEMPLATE = "Use available successful tool outputs to answer the task."


@dataclass
class RewooPlanStep:
    """A single executable ReWOO plan step."""

    step_id: str
    tool_name: str
    raw_input: str
    depends_on: List[str] = field(default_factory=list)
    retry_limit: Optional[int] = None
    timeout_seconds: Optional[float] = None


@dataclass
class RewooPlan:
    """A parsed ReWOO plan with execution steps and final template."""

    goal: str
    steps: List[RewooPlanStep]
    final_prompt_template: str


@dataclass
class RewooStepResult:
    """Execution outcome for a single ReWOO step."""

    step_id: str
    status: str
    rendered_input: str
    attempts: int
    tool_result: Optional[ToolResult] = None
    error: Optional[str] = None
    status_history: List[str] = field(default_factory=list)
    started_at: Optional[str] = None
    ended_at: Optional[str] = None


@dataclass
class RewooExecution:
    """Execution artifacts for a full ReWOO plan run."""

    execution_id: str
    plan: RewooPlan
    results: List[RewooStepResult]
    artifacts: Dict[str, str]
    started_at: str
    ended_at: Optional[str] = None
    steps_succeeded: int = 0
    steps_failed: int = 0
    policy_denials: int = 0


@dataclass
class RewooExecutionResult:
    """Top-level result for a ReWOO run invocation."""

    answer: str
    execution: Optional[RewooExecution]
    used_rewoo: bool
    fallback_reason: Optional[str] = None


@dataclass
class RewooEngineConfig:
    """Configuration knobs for ReWOO engine behavior."""

    max_steps: int = 8
    retry_limit: int = 1
    backoff_base_seconds: float = 0.25
    max_artifact_chars: int = 4000
    policy_denied_behavior: str = "fail_step"
    artifact_injection_mode: str = "final_summary"


class RewooEngine:
    """Model-driven ReWOO planner/executor/synthesizer."""

    def __init__(
        self,
        runtime: ToolRuntime,
        registry: ToolRegistry,
        router: Optional[ToolRouter] = None,
        planner_adapter: Optional[BaseAdapter] = None,
        synthesizer_adapter: Optional[BaseAdapter] = None,
        config: Optional[RewooEngineConfig] = None,
    ) -> None:
        self.runtime = runtime
        self.registry = registry
        self.router = router or ToolRouter()
        self.planner_adapter = planner_adapter
        self.synthesizer_adapter = synthesizer_adapter
        self.config = config or RewooEngineConfig()

    async def create_plan(self, task: str, state: HiveState) -> RewooPlan:
        """Generate and validate a ReWOO plan for the task."""
        started_perf = time.perf_counter()
        with trace_span("rewoo.plan", metadata={"task_chars": len(task)}) as span:
            plan_text = await self._generate_plan_text(task, state)
            final_template_fallback = False
            try:
                plan = parse_rewoo_plan(plan_text)
            except ValueError as exc:
                if not _is_final_template_error(str(exc)):
                    raise
                plan = _parse_plan_with_default_final(plan_text)
                final_template_fallback = True

            self.validate_plan(plan, self.registry)

            if len(plan.steps) > self.config.max_steps:
                raise ValueError(
                    f"ReWOO plan exceeds max steps ({len(plan.steps)} > {self.config.max_steps})"
                )

            span.set_metadata(
                {
                    "plan_steps": len(plan.steps),
                    "final_template_fallback": final_template_fallback,
                    "duration_ms": round((time.perf_counter() - started_perf) * 1000, 2),
                }
            )
            return plan

    def validate_plan(self, plan: RewooPlan, registry: ToolRegistry) -> None:
        """Validate plan tool names against registered tools."""
        available_tools = {spec.name for spec in registry.list_tools()}
        unknown = sorted(
            {step.tool_name for step in plan.steps if step.tool_name not in available_tools}
        )
        if unknown:
            raise ValueError(f"Unknown tools in plan: {', '.join(unknown)}")

        for step in plan.steps:
            _validate_step_input_json(step)

    def render_step_input(self, raw_input: str, artifacts: Dict[str, str]) -> str:
        """Render a step input template by replacing `#E*` artifacts."""
        return render_step_input(raw_input, artifacts)

    async def execute_plan(self, plan: RewooPlan, context: ToolExecutionContext) -> RewooExecution:
        """Execute a validated ReWOO plan through ToolRuntime."""
        return await execute_rewoo_plan(
            plan,
            self.runtime,
            context,
            retry_limit=self.config.retry_limit,
            backoff_base_seconds=self.config.backoff_base_seconds,
            max_artifact_chars=self.config.max_artifact_chars,
            policy_denied_behavior=self.config.policy_denied_behavior,
        )

    async def synthesize_answer(self, task: str, execution: RewooExecution) -> str:
        """Synthesize a final answer from execution artifacts."""
        started_perf = time.perf_counter()
        with trace_span(
            "rewoo.synthesize",
            metadata={
                "plan_steps": len(execution.plan.steps),
                "steps_succeeded": execution.steps_succeeded,
                "steps_failed": execution.steps_failed,
                "policy_denials": execution.policy_denials,
            },
        ) as span:
            synthesis_adapter = self.synthesizer_adapter or self.planner_adapter
            if synthesis_adapter is not None:
                prompt = self._build_synthesis_prompt(task, execution)
                try:
                    response = await synthesis_adapter.generate(prompt)
                except Exception as exc:
                    logger.warning("ReWOO synthesis adapter call failed: %s", exc)
                else:
                    main = _extract_main_response(response)
                    if main:
                        span.set_metadata(
                            {"duration_ms": round((time.perf_counter() - started_perf) * 1000, 2)}
                        )
                        return main

            synthesized = synthesize_rewoo_answer(task, execution)
            span.set_metadata(
                {"duration_ms": round((time.perf_counter() - started_perf) * 1000, 2)}
            )
            return synthesized

    async def run(
        self, task: str, state: HiveState, context: ToolExecutionContext
    ) -> RewooExecutionResult:
        """Run full plan -> execute -> synthesize flow with fallback semantics."""
        try:
            plan = await self.create_plan(task, state)
            execution = await self.execute_plan(plan, context)
            answer = await self.synthesize_answer(task, execution)
            return RewooExecutionResult(answer=answer, execution=execution, used_rewoo=True)
        except Exception as exc:
            logger.warning("ReWOO run failed, falling back to legacy path: %s", exc)
            return RewooExecutionResult(
                answer="",
                execution=None,
                used_rewoo=False,
                fallback_reason=str(exc),
            )

    async def _generate_plan_text(self, task: str, state: HiveState) -> str:
        """Generate raw plan text from adapter, with deterministic fallback."""
        if self.planner_adapter is None:
            return self._fallback_plan_text(task)

        tool_specs = self.registry.list_tools()
        ranked_specs = self.router.rank_specs_for_query(tool_specs, task)
        tool_names = [spec.name for spec in ranked_specs]
        prompt = self._build_planner_prompt(task, state, tool_names)

        response = await self.planner_adapter.generate(prompt)
        return self._extract_plan_block(response)

    def _build_planner_prompt(self, task: str, state: HiveState, tool_names: List[str]) -> str:
        """Build strict planner prompt for model-driven ReWOO generation."""
        available = ", ".join(tool_names)
        return (
            "You are writing a strict ReWOO plan.\n"
            "Return ONLY lines in this format:\n"
            "Plan: <goal summary>\n"
            "E1: <tool_name>[<input>]\n"
            "E2: <tool_name>[<input with #E1 refs if needed>]\n"
            "...\n"
            "Final: <template that may reference #E*>\n"
            "Rules:\n"
            "- Use only listed tools.\n"
            "- Keep steps contiguous E1..En.\n"
            "- References must point to prior steps only.\n"
            '- <input> must be valid JSON object (e.g. {"query":"topic"}).\n'
            "- #E1 must appear only inside JSON string values, never as raw JSON tokens.\n"
            f"Available tools: {available}\n"
            f"Task: {task}\n"
            f"State memory excerpt: {state.memory_summary[:1000]}"
        )

    def _build_synthesis_prompt(self, task: str, execution: RewooExecution) -> str:
        """Build synthesis prompt from plan artifacts and failures."""
        artifact_lines = [
            f"{step_id}: {value}" for step_id, value in sorted(execution.artifacts.items())
        ]
        failures = [
            f"{result.step_id}: {result.error or 'tool execution failed'}"
            for result in execution.results
            if result.status == "failed"
        ]
        artifact_block = "\n".join(artifact_lines) if artifact_lines else "(none)"
        failure_block = "\n".join(failures) if failures else "(none)"

        return (
            "Synthesize a concise answer for the user.\n"
            f"Task: {task}\n"
            f"Final template: {execution.plan.final_prompt_template}\n"
            "Successful artifacts:\n"
            f"{artifact_block}\n"
            "Failed steps:\n"
            f"{failure_block}"
        )

    def _extract_plan_block(self, response: str) -> str:
        """Extract only ReWOO plan lines from model response."""
        lines: List[str] = []
        for raw_line in response.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if _PLAN_LINE_PATTERN.match(line) or _STEP_LINE_PATTERN.match(line):
                lines.append(line)
                continue
            if _FINAL_LINE_PATTERN.match(line):
                lines.append(line)

        if not lines:
            raise ValueError("Planner did not return any valid ReWOO lines")

        return "\n".join(lines)

    def _fallback_plan_text(self, task: str) -> str:
        """Build deterministic fallback plan when no planner adapter exists."""
        tool_names = [tool.name for tool in self.registry.list_tools()]
        if not tool_names:
            raise ValueError("No tools registered for ReWOO planning")

        tool_name = "memory_search" if "memory_search" in tool_names else tool_names[0]
        if tool_name == "memory_search":
            step_input = json.dumps({"query": task, "max_results": 3, "min_score": 0.3})
        else:
            step_input = json.dumps({})

        return f"Plan: execute tool-assisted task\nE1: {tool_name}[{step_input}]\nFinal: Use #E1"


def parse_rewoo_plan(plan: str) -> RewooPlan:
    """Parse a ReWOO plan text into a typed plan model."""
    goal = ""
    final_prompt_template = ""
    steps: List[RewooPlanStep] = []

    for raw_line in plan.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        plan_match = _PLAN_LINE_PATTERN.match(line)
        if plan_match:
            goal = plan_match.group("goal").strip()
            continue

        step_match = _STEP_LINE_PATTERN.match(line)
        if step_match:
            raw_input = step_match.group("input")
            steps.append(
                RewooPlanStep(
                    step_id=step_match.group("step_id"),
                    tool_name=step_match.group("tool"),
                    raw_input=raw_input,
                    depends_on=_extract_references(raw_input),
                )
            )
            continue

        final_match = _FINAL_LINE_PATTERN.match(line)
        if final_match:
            final_prompt_template = final_match.group("template").strip()
            continue

        raise ValueError(f"Invalid ReWOO line: {line}")

    if not goal:
        raise ValueError("Missing Plan line")
    if not steps:
        raise ValueError("ReWOO plan must include at least one step")
    if not final_prompt_template:
        raise ValueError("Missing Final line")

    _validate_step_order(steps)
    _validate_step_references(steps)
    _validate_final_references(final_prompt_template, steps)
    return RewooPlan(goal=goal, steps=steps, final_prompt_template=final_prompt_template)


def _parse_plan_with_default_final(plan: str) -> RewooPlan:
    """Parse plan while falling back to a deterministic final template."""
    goal = ""
    steps: List[RewooPlanStep] = []

    for raw_line in plan.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        plan_match = _PLAN_LINE_PATTERN.match(line)
        if plan_match:
            goal = plan_match.group("goal").strip()
            continue

        step_match = _STEP_LINE_PATTERN.match(line)
        if step_match:
            raw_input = step_match.group("input")
            steps.append(
                RewooPlanStep(
                    step_id=step_match.group("step_id"),
                    tool_name=step_match.group("tool"),
                    raw_input=raw_input,
                    depends_on=_extract_references(raw_input),
                )
            )
            continue

        final_match = _FINAL_LINE_PATTERN.match(line)
        if final_match:
            continue

        raise ValueError(f"Invalid ReWOO line: {line}")

    if not goal:
        raise ValueError("Missing Plan line")
    if not steps:
        raise ValueError("ReWOO plan must include at least one step")

    _validate_step_order(steps)
    _validate_step_references(steps)
    return RewooPlan(goal=goal, steps=steps, final_prompt_template=_DEFAULT_FINAL_TEMPLATE)


def _validate_step_order(steps: List[RewooPlanStep]) -> None:
    """Ensure ReWOO steps are contiguous and monotonic E1..En."""
    expected = 1
    for step in steps:
        current = int(step.step_id[1:])
        if current != expected:
            raise ValueError(f"Invalid step order: expected E{expected}, got {step.step_id}")
        expected += 1


def _validate_step_references(steps: List[RewooPlanStep]) -> None:
    """Reject references to future or missing steps in raw input."""
    seen_ids = set()
    for step in steps:
        for referenced in step.depends_on:
            if referenced not in seen_ids:
                raise ValueError(
                    f"Invalid forward reference in {step.step_id}: {referenced} was not executed yet"
                )
        seen_ids.add(step.step_id)


def _validate_step_input_json(step: RewooPlanStep) -> None:
    """Ensure each step input is valid JSON and represented as an object."""
    try:
        parsed_input = json.loads(step.raw_input)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON input for {step.step_id}: {exc.msg}") from exc

    if not isinstance(parsed_input, dict):
        raise ValueError(f"JSON input for {step.step_id} must be an object")


def _validate_final_references(final_template: str, steps: List[RewooPlanStep]) -> None:
    """Ensure final template only references existing steps."""
    valid = {step.step_id for step in steps}
    for match in _REFERENCE_PATTERN.finditer(final_template):
        referenced = match.group("step_id")
        if referenced not in valid:
            raise ValueError(f"Final template references unknown step: {referenced}")


def _extract_references(text: str) -> List[str]:
    """Extract unique `#E*` references preserving encounter order."""
    refs: List[str] = []
    for match in _REFERENCE_PATTERN.finditer(text):
        ref = match.group("step_id")
        if ref not in refs:
            refs.append(ref)
    return refs


def render_step_input(raw_input: str, artifacts: Dict[str, str]) -> str:
    """Render a step input template by replacing `#E*` artifact references."""

    def _replace(match: re.Match[str]) -> str:
        step_id = match.group("step_id")
        if step_id not in artifacts:
            raise ValueError(f"Unknown ReWOO artifact reference: #{step_id}")
        return artifacts[step_id]

    return _REFERENCE_PATTERN.sub(_replace, raw_input)


async def execute_rewoo_plan(
    plan: RewooPlan,
    runtime: ToolRuntime,
    context: ToolExecutionContext,
    retry_limit: int = 0,
    backoff_base_seconds: float = 0.25,
    max_artifact_chars: Optional[int] = None,
    policy_denied_behavior: str = "fail_step",
) -> RewooExecution:
    """Execute ReWOO plan steps through ToolRuntime and collect artifacts."""
    execution = RewooExecution(
        execution_id=str(uuid.uuid4()),
        plan=plan,
        results=[],
        artifacts={},
        started_at=_utc_now_iso(),
    )
    consecutive_failures = 0
    circuit_open = False
    skip_reason = "skipped due to consecutive failures"

    for step in plan.steps:
        if circuit_open:
            now = _utc_now_iso()
            execution.results.append(
                RewooStepResult(
                    step_id=step.step_id,
                    status="skipped",
                    rendered_input=step.raw_input,
                    attempts=0,
                    error=skip_reason,
                    status_history=["pending", "skipped"],
                    started_at=now,
                    ended_at=now,
                )
            )
            continue

        with trace_span(
            "rewoo.execute_step",
            metadata={"step_id": step.step_id, "tool_name": step.tool_name},
        ) as step_span:
            step_started_perf = time.perf_counter()
            step_started = _utc_now_iso()
            try:
                rendered_input = render_step_input(step.raw_input, execution.artifacts)
            except ValueError as exc:
                step_ended = _utc_now_iso()
                execution.results.append(
                    RewooStepResult(
                        step_id=step.step_id,
                        status="failed",
                        rendered_input=step.raw_input,
                        attempts=1,
                        error=str(exc),
                        status_history=["pending", "running", "failed"],
                        started_at=step_started,
                        ended_at=step_ended,
                    )
                )
                step_span.set_metadata(
                    {
                        "status": "failed",
                        "attempts": 1,
                        "error": str(exc),
                        "policy_denied": False,
                        "duration_ms": round((time.perf_counter() - step_started_perf) * 1000, 2),
                    }
                )
                consecutive_failures = 2
                circuit_open = True
                continue

            attempts = 0
            tool_result: Optional[ToolResult] = None
            effective_retry_limit = (
                step.retry_limit if step.retry_limit is not None else retry_limit
            )

            while attempts <= effective_retry_limit:
                attempts += 1
                call_text = _build_tool_call_text(step.tool_name, rendered_input)
                _, tool_results = await runtime.execute_calls(call_text, context)
                tool_result = (
                    tool_results[0]
                    if tool_results
                    else ToolResult(step.tool_name, False, "", "no result")
                )

                if tool_result.success:
                    break

                if _is_non_retryable_error(tool_result.error):
                    break

                if attempts <= effective_retry_limit:
                    await asyncio.sleep(backoff_base_seconds * attempts)

            step_ended = _utc_now_iso()
            policy_denied = _is_policy_denial(tool_result.error if tool_result else None)
            if tool_result and tool_result.success:
                artifact_output = tool_result.output
                if max_artifact_chars is not None:
                    artifact_output, tool_result = _truncate_artifact(
                        artifact_output,
                        tool_result,
                        max_chars=max_artifact_chars,
                    )
                execution.artifacts[step.step_id] = artifact_output
                execution.results.append(
                    RewooStepResult(
                        step_id=step.step_id,
                        status="succeeded",
                        rendered_input=rendered_input,
                        attempts=attempts,
                        tool_result=tool_result,
                        status_history=["pending", "running", "succeeded"],
                        started_at=step_started,
                        ended_at=step_ended,
                    )
                )
                step_span.set_metadata(
                    {
                        "status": "succeeded",
                        "attempts": attempts,
                        "policy_denied": False,
                        "duration_ms": round((time.perf_counter() - step_started_perf) * 1000, 2),
                    }
                )
                consecutive_failures = 0
                continue

            error = (tool_result.error if tool_result else None) or "tool execution failed"
            execution.results.append(
                RewooStepResult(
                    step_id=step.step_id,
                    status="failed",
                    rendered_input=rendered_input,
                    attempts=attempts,
                    tool_result=tool_result,
                    error=error,
                    status_history=["pending", "running", "failed"],
                    started_at=step_started,
                    ended_at=step_ended,
                )
            )
            if policy_denied:
                execution.policy_denials += 1
                if policy_denied_behavior == "abort_plan":
                    circuit_open = True
                    skip_reason = "skipped due to policy denial"
            step_span.set_metadata(
                {
                    "status": "failed",
                    "attempts": attempts,
                    "error": error,
                    "policy_denied": policy_denied,
                    "duration_ms": round((time.perf_counter() - step_started_perf) * 1000, 2),
                }
            )
            consecutive_failures += 1
            if consecutive_failures >= 2:
                circuit_open = True

    execution.ended_at = _utc_now_iso()
    execution.steps_succeeded = len(
        [result for result in execution.results if result.status == "succeeded"]
    )
    execution.steps_failed = len(
        [result for result in execution.results if result.status == "failed"]
    )
    return execution


def _build_tool_call_text(tool_name: str, rendered_input: str) -> str:
    """Build an explicit TOOL_CALL wrapper from rendered step input."""
    args = _parse_step_args(rendered_input)
    payload = {"name": tool_name, "args": args}
    return f"<TOOL_CALL>{json.dumps(payload)}</TOOL_CALL>"


def _parse_step_args(rendered_input: str) -> Dict[str, Any]:
    """Parse step input as JSON object, or wrap as generic input argument."""
    try:
        parsed = json.loads(rendered_input)
    except json.JSONDecodeError:
        return {"input": rendered_input}

    if isinstance(parsed, dict):
        return parsed
    return {"input": rendered_input}


def _is_final_template_error(error_text: str) -> bool:
    """Return True if parse error is specifically about Final template handling."""
    return error_text.startswith("Missing Final line") or error_text.startswith(
        "Final template references unknown step"
    )


def _truncate_artifact(
    artifact_output: str,
    tool_result: ToolResult,
    max_chars: int,
) -> Tuple[str, ToolResult]:
    """Cap artifact output length and preserve full output in metadata when truncated."""
    if len(artifact_output) <= max_chars:
        return artifact_output, tool_result

    overflow = len(artifact_output) - max_chars
    truncated = f"{artifact_output[:max_chars]}...[truncated {overflow} chars]"
    metadata = dict(tool_result.metadata)
    metadata["artifact_truncated"] = True
    metadata["artifact_overflow_chars"] = overflow
    metadata["full_output"] = artifact_output
    updated_result = ToolResult(
        tool_name=tool_result.tool_name,
        success=tool_result.success,
        output=tool_result.output,
        error=tool_result.error,
        metadata=metadata,
    )
    return truncated, updated_result


def _is_non_retryable_error(error: Optional[str]) -> bool:
    """Return True when retrying will not change the outcome."""
    if not error:
        return False
    return (
        error == "denied by policy"
        or error.startswith("approval required:")
        or error == "unknown tool"
    )


def _is_policy_denial(error: Optional[str]) -> bool:
    """Return True if tool error is policy-related."""
    if not error:
        return False
    return error == "denied by policy" or error.startswith("approval required:")


def synthesize_rewoo_answer(task: str, execution: RewooExecution) -> str:
    """Synthesize a deterministic final answer from ReWOO execution artifacts."""
    successes = [result for result in execution.results if result.status == "succeeded"]
    failures = [result for result in execution.results if result.status == "failed"]

    final_template = execution.plan.final_prompt_template
    try:
        rendered_final = render_step_input(final_template, execution.artifacts)
    except ValueError:
        rendered_final = final_template

    if not successes:
        if not failures:
            return "Unable to complete the task with successful tool steps. No steps were executed."
        failure_lines = [
            f"{result.step_id} failed: {result.error or 'tool execution failed'}"
            for result in failures
        ]
        return (
            "Unable to complete the task with successful tool steps. "
            f"Observed failures: {'; '.join(failure_lines)}"
        )

    artifact_lines = [
        f"{result.step_id}: {execution.artifacts.get(result.step_id, '')}" for result in successes
    ]
    failure_lines = [
        f"{result.step_id} failed: {result.error or 'tool execution failed'}" for result in failures
    ]

    sections: List[str] = [
        f"Task: {task}",
        f"Final answer template: {rendered_final}",
        "Successful tool outputs:",
        *artifact_lines,
    ]
    if failure_lines:
        sections.extend(["Failed steps:", *failure_lines])
    return "\n".join(sections)


def _extract_main_response(response: str) -> str:
    """Extract textual answer from model response with optional update block."""
    return response.split("<HIVE_UPDATE>")[0].strip()


def _utc_now_iso() -> str:
    """Return UTC timestamp as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()
