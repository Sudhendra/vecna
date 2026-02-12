"""Unit tests for ReWOO tracing spans and metadata."""

import asyncio
from typing import Any, Dict, List, Optional

from vecna.adapters.base import BaseAdapter, ModelConfig
from vecna.core.hive_state import HiveState
import vecna.orchestrator.rewoo as rewoo_module
from vecna.orchestrator.rewoo import RewooEngine, RewooEngineConfig
from vecna.tools.permissions import ToolPermissionManager, ToolPolicy
from vecna.tools.registry import ToolRegistry
from vecna.tools.runtime import ToolRuntime
from vecna.tools.types import ToolExecutionContext, ToolResult, ToolSpec


class _PlannerAdapter(BaseAdapter):
    def __init__(self):
        super().__init__(
            ModelConfig(
                name="planner",
                model_id="planner-model",
            )
        )

    async def generate(self, prompt: str) -> str:
        if "strict ReWOO plan" in prompt:
            return """Plan: collect and summarize
E1: echo[{"text":"hello"}]
Final: Use #E1
"""
        return "synthesized answer"


class _FakeSpan:
    def __init__(
        self, collector: List[Dict[str, Any]], name: str, metadata: Optional[Dict[str, Any]]
    ):
        self.collector = collector
        self.name = name
        self.initial_metadata = metadata or {}
        self.updated_metadata: Dict[str, Any] = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.collector.append(
            {
                "name": self.name,
                "initial": self.initial_metadata,
                "updated": self.updated_metadata,
            }
        )
        return False

    def set_metadata(self, metadata: Dict[str, Any]):
        self.updated_metadata.update(metadata)


def test_rewoo_emits_expected_trace_spans(monkeypatch):
    spans: List[Dict[str, Any]] = []

    def fake_trace_span(
        name: str, input: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None
    ):
        return _FakeSpan(spans, name, metadata)

    monkeypatch.setattr(rewoo_module, "trace_span", fake_trace_span)

    registry = ToolRegistry()
    registry.register(
        ToolSpec(name="echo", description="echo", input_schema={"text": "string"}),
        executor=lambda args, ctx: ToolResult("echo", True, args["text"]),
    )
    runtime = ToolRuntime(
        registry=registry,
        permission_manager=ToolPermissionManager(ToolPolicy()),
    )

    engine = RewooEngine(
        runtime=runtime,
        registry=registry,
        planner_adapter=_PlannerAdapter(),
        config=RewooEngineConfig(max_steps=8, retry_limit=1, backoff_base_seconds=0.01),
    )

    state = HiveState()
    state.ensure_identity()

    result = asyncio.run(engine.run("first gather then summarize", state, ToolExecutionContext()))

    assert result.used_rewoo is True

    names = [span["name"] for span in spans]
    assert "rewoo.plan" in names
    assert "rewoo.execute_step" in names
    assert "rewoo.synthesize" in names

    synth_spans = [span for span in spans if span["name"] == "rewoo.synthesize"]
    assert len(synth_spans) == 1
    assert "plan_steps" in synth_spans[0]["initial"]
    assert "steps_succeeded" in synth_spans[0]["initial"]
    assert "steps_failed" in synth_spans[0]["initial"]
    assert "policy_denials" in synth_spans[0]["initial"]
    assert "duration_ms" in synth_spans[0]["updated"]

    plan_spans = [span for span in spans if span["name"] == "rewoo.plan"]
    assert len(plan_spans) == 1
    assert "duration_ms" in plan_spans[0]["updated"]

    execute_spans = [span for span in spans if span["name"] == "rewoo.execute_step"]
    assert len(execute_spans) == 1
    assert "duration_ms" in execute_spans[0]["updated"]
