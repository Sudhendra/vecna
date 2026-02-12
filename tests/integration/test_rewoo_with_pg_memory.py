"""Integration tests for ReWOO with PostgreSQL-backed memory retrieval."""

import asyncio
import uuid

from vecna.adapters.base import BaseAdapter, ModelConfig
from vecna.core.hive_state import HiveState
from vecna.memory.pg_store import MemoryItem
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
            return """Plan: retrieve memory from PG
E1: pg_lookup[{"query":"vecna hybrid memory"}]
Final: Use #E1
"""
        return prompt


def test_rewoo_with_pg_memory_surfaces_retrieved_context(pg_memory_store):
    unique_suffix = str(uuid.uuid4())
    content = f"vecna hybrid memory fact {unique_suffix}"
    item_id = pg_memory_store.add_item(
        MemoryItem(
            content=content,
            item_type="fact",
            confidence=0.9,
            domain="test",
            source_model="test",
        )
    )

    def pg_lookup(args, ctx):
        item = pg_memory_store.get_item(item_id)
        if item is None:
            return ToolResult("pg_lookup", False, "", error="no results")
        return ToolResult("pg_lookup", True, item.content)

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="pg_lookup", description="Lookup PG memory", input_schema={"query": "string"}
        ),
        executor=pg_lookup,
    )
    runtime = ToolRuntime(
        registry=registry,
        permission_manager=ToolPermissionManager(ToolPolicy()),
    )

    state = HiveState()
    state.ensure_identity()
    engine = RewooEngine(
        runtime=runtime,
        registry=registry,
        planner_adapter=_PlannerAdapter(),
        config=RewooEngineConfig(max_steps=4, retry_limit=1, backoff_base_seconds=0.01),
    )

    result = asyncio.run(engine.run("find vecna hybrid memory", state, ToolExecutionContext()))

    assert result.used_rewoo is True
    assert result.execution is not None
    assert result.execution.artifacts["E1"] == content
    assert unique_suffix in result.answer
