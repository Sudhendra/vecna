"""Unit tests for ReWOO integration in HiveLoop."""

import asyncio

from vecna.core.types import HiveUpdate
from vecna.orchestrator.loop import HiveConfig, HiveLoop
from vecna.tools.permissions import ToolPermissionManager, ToolPolicy
from vecna.tools.registry import ToolRegistry
from vecna.tools.runtime import ToolRuntime
from vecna.tools.types import ToolResult, ToolSpec


class _DummyAdapter:
    def __init__(self, name: str = "dummy"):
        self.name = name
        self.domain = "general"
        self.weight = 1.0

    async def think(self, state, task):
        return "dummy", HiveUpdate(source_model=self.name)

    async def generate(self, prompt):
        if "strict ReWOO plan" in prompt:
            return """Plan: use echo
E1: echo[{"text":"ok"}]
Final: Use #E1
"""
        return ""


class _FakeSessionManager:
    def __init__(self):
        self.end_payload = None

    async def start_session(self, initial_query=None):
        return {
            "soul": "",
            "working": "",
            "daily_log": "",
            "relevant_memory": "",
            "session_id": "test",
        }

    def format_context(self, context):
        return ""

    async def end_session(self, payload):
        self.end_payload = payload


def _build_loop(
    enable_rewoo_planning: bool, rewoo_artifact_injection_mode: str = "final_summary"
) -> HiveLoop:
    config = HiveConfig(
        use_pg_memory=False,
        use_semantic_memory=False,
        auto_execute_tools=False,
        auto_execute_code=False,
        verbose=False,
        enable_rewoo_planning=enable_rewoo_planning,
        rewoo_force=enable_rewoo_planning,
        rewoo_artifact_injection_mode=rewoo_artifact_injection_mode,
    )
    return HiveLoop(config=config, adapters=[_DummyAdapter()])


def test_hive_loop_uses_legacy_path_when_rewoo_disabled(monkeypatch):
    loop = _build_loop(enable_rewoo_planning=False)

    async def fake_ensure_session_manager(initial_query=None):
        return None

    async def fake_run_cycle(task):
        return ["legacy-response"], [HiveUpdate(source_model="dummy")]

    monkeypatch.setattr(loop, "_ensure_session_manager", fake_ensure_session_manager)
    monkeypatch.setattr(loop, "_run_cycle", fake_run_cycle)

    response = asyncio.run(loop.think("simple task"))

    assert response == "legacy-response"


def test_hive_loop_uses_rewoo_when_enabled(monkeypatch):
    loop = _build_loop(enable_rewoo_planning=True)

    async def fake_ensure_session_manager(initial_query=None):
        return None

    async def fail_run_cycle(task):
        raise AssertionError("legacy run cycle should not be used when rewoo succeeds")

    registry = ToolRegistry()
    registry.register(
        ToolSpec(name="echo", description="echo", input_schema={"text": "string"}),
        executor=lambda args, ctx: ToolResult("echo", True, args["text"]),
    )
    loop.tool_registry = registry
    loop.tool_runtime = ToolRuntime(
        registry=registry,
        permission_manager=ToolPermissionManager(ToolPolicy()),
    )

    monkeypatch.setattr(loop, "_ensure_session_manager", fake_ensure_session_manager)
    monkeypatch.setattr(loop, "_run_cycle", fail_run_cycle)

    response = asyncio.run(loop.think("complex task"))

    assert "Task: complex task" in response
    assert "E1: ok" in response


def test_hive_loop_falls_back_to_legacy_when_rewoo_plan_is_invalid(monkeypatch):
    loop = _build_loop(enable_rewoo_planning=True)

    async def fake_ensure_session_manager(initial_query=None):
        return None

    async def fake_run_cycle(task):
        return ["legacy-fallback"], [HiveUpdate(source_model="dummy")]

    async def fake_generate(prompt):
        return "this is not a valid rewoo plan"

    monkeypatch.setattr(loop, "_ensure_session_manager", fake_ensure_session_manager)
    monkeypatch.setattr(loop, "_run_cycle", fake_run_cycle)
    monkeypatch.setattr(loop.adapters[0], "generate", fake_generate)

    response = asyncio.run(loop.think("complex task"))

    assert response == "legacy-fallback"


def test_hive_loop_falls_back_to_legacy_when_rewoo_plan_has_unknown_tool(monkeypatch):
    loop = _build_loop(enable_rewoo_planning=True)

    async def fake_ensure_session_manager(initial_query=None):
        return None

    async def fake_run_cycle(task):
        return ["legacy-fallback"], [HiveUpdate(source_model="dummy")]

    async def fake_generate(prompt):
        return """Plan: use unknown tool
E1: not_registered[{}]
Final: done
"""

    monkeypatch.setattr(loop, "_ensure_session_manager", fake_ensure_session_manager)
    monkeypatch.setattr(loop, "_run_cycle", fake_run_cycle)
    monkeypatch.setattr(loop.adapters[0], "generate", fake_generate)

    response = asyncio.run(loop.think("complex task"))

    assert response == "legacy-fallback"


def test_hive_loop_falls_back_to_legacy_when_rewoo_planner_raises_runtime_error(monkeypatch):
    loop = _build_loop(enable_rewoo_planning=True)

    async def fake_ensure_session_manager(initial_query=None):
        return None

    async def fake_run_cycle(task):
        return ["legacy-fallback"], [HiveUpdate(source_model="dummy")]

    async def boom_generate(prompt):
        raise RuntimeError("planner exploded")

    monkeypatch.setattr(loop, "_ensure_session_manager", fake_ensure_session_manager)
    monkeypatch.setattr(loop, "_run_cycle", fake_run_cycle)
    monkeypatch.setattr(loop.adapters[0], "generate", boom_generate)

    response = asyncio.run(loop.think("complex multi step task"))

    assert response == "legacy-fallback"


def test_hive_loop_rewoo_appends_execution_summary_to_session_log(monkeypatch):
    loop = _build_loop(enable_rewoo_planning=True)
    fake_session = _FakeSessionManager()
    loop._session_manager = fake_session

    registry = ToolRegistry()
    registry.register(
        ToolSpec(name="echo", description="echo", input_schema={"text": "string"}),
        executor=lambda args, ctx: ToolResult("echo", True, args["text"]),
    )
    loop.tool_registry = registry
    loop.tool_runtime = ToolRuntime(
        registry=registry,
        permission_manager=ToolPermissionManager(ToolPolicy()),
    )

    response = asyncio.run(loop.think("complex task"))

    assert "Task: complex task" in response
    assert fake_session.end_payload is not None
    assert len(fake_session.end_payload) == 3
    assert fake_session.end_payload[2]["role"] == "system"
    assert "[REWOO_EXECUTION]" in fake_session.end_payload[2]["content"]


def test_hive_loop_uses_rewoo_when_plan_missing_final(monkeypatch):
    loop = _build_loop(enable_rewoo_planning=True)

    async def fake_ensure_session_manager(initial_query=None):
        return None

    async def fail_run_cycle(task):
        raise AssertionError("legacy run cycle should not run for Final fallback")

    async def fake_generate(prompt):
        if "strict ReWOO plan" in prompt:
            return """Plan: no final provided
E1: echo[{"text":"ok"}]
"""
        return ""

    registry = ToolRegistry()
    registry.register(
        ToolSpec(name="echo", description="echo", input_schema={"text": "string"}),
        executor=lambda args, ctx: ToolResult("echo", True, args["text"]),
    )
    loop.tool_registry = registry
    loop.tool_runtime = ToolRuntime(
        registry=registry,
        permission_manager=ToolPermissionManager(ToolPolicy()),
    )

    monkeypatch.setattr(loop, "_ensure_session_manager", fake_ensure_session_manager)
    monkeypatch.setattr(loop, "_run_cycle", fail_run_cycle)
    monkeypatch.setattr(loop.adapters[0], "generate", fake_generate)

    response = asyncio.run(loop.think("complex task"))

    assert "Successful tool outputs" in response
    assert "E1: ok" in response


def test_rewoo_artifact_injection_mode_per_step_updates_memory_summary(monkeypatch):
    loop = _build_loop(enable_rewoo_planning=True, rewoo_artifact_injection_mode="per_step")

    async def fake_ensure_session_manager(initial_query=None):
        return None

    async def fail_run_cycle(task):
        raise AssertionError("legacy run cycle should not run when rewoo succeeds")

    registry = ToolRegistry()
    registry.register(
        ToolSpec(name="echo", description="echo", input_schema={"text": "string"}),
        executor=lambda args, ctx: ToolResult("echo", True, args["text"]),
    )
    loop.tool_registry = registry
    loop.tool_runtime = ToolRuntime(
        registry=registry,
        permission_manager=ToolPermissionManager(ToolPolicy()),
    )

    monkeypatch.setattr(loop, "_ensure_session_manager", fake_ensure_session_manager)
    monkeypatch.setattr(loop, "_run_cycle", fail_run_cycle)

    response = asyncio.run(loop.think("complex task"))

    assert "Task: complex task" in response
    assert "[REWOO_ARTIFACT] E1: ok" in loop.state.memory_summary
