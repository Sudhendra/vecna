"""End-to-end CLI test for ReWOO-driven speak flow."""

import importlib

from click.testing import CliRunner

from vecna.cli.main import cli
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
        return "legacy", HiveUpdate(source_model=self.name)

    async def generate(self, prompt):
        if "strict ReWOO plan" in prompt:
            return """Plan: run two tool steps
E1: echo[{"text":"first"}]
E2: echo[{"text":"#E1 second"}]
Final: Use #E2
"""
        return ""


class _FakeHive:
    def __init__(self, loop: HiveLoop):
        self.loop = loop

    @property
    def state(self):
        return self.loop.state

    async def think(self, task: str) -> str:
        return await self.loop.think(task)


def test_cli_speak_runs_rewoo_and_surfaces_tool_artifacts(monkeypatch):
    loop = HiveLoop(
        config=HiveConfig(
            use_pg_memory=False,
            use_semantic_memory=False,
            auto_execute_tools=False,
            auto_execute_code=False,
            verbose=False,
            enable_rewoo_planning=True,
            rewoo_force=True,
        ),
        adapters=[_DummyAdapter()],
    )

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

    async def fake_ensure_session_manager(initial_query=None):
        return None

    cli_main = importlib.import_module("vecna.cli.main")
    monkeypatch.setattr(loop, "_ensure_session_manager", fake_ensure_session_manager)
    monkeypatch.setattr(cli_main, "get_hive", lambda: _FakeHive(loop))

    runner = CliRunner()
    result = runner.invoke(cli, ["--skip-boot", "speak", "first then second operation"])

    assert result.exit_code == 0
    assert "Successful tool outputs" in result.output
    assert "E2: first second" in result.output
