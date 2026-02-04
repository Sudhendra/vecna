import asyncio

from vecna.config.schema import AgentMode
from vecna.orchestrator import loop as loop_module
from vecna.orchestrator import mode_router
from vecna.orchestrator.mode_router import resolve_loop


class DummyLoop:
    def __init__(self, name):
        self.name = name

    async def think(self, task, max_cycles=None):
        return f"{self.name}:{task}:{max_cycles}"


def test_resolve_loop_assistant():
    loop = resolve_loop(AgentMode.assistant)
    assert loop.name == "assistant"


def test_resolve_loop_explorer():
    loop = resolve_loop(AgentMode.explorer)
    assert loop.name == "explorer"


def test_run_session_delegates_to_resolve_loop(monkeypatch):
    def fake_resolve_loop(mode):
        return DummyLoop(mode.value)

    monkeypatch.setattr(mode_router, "resolve_loop", fake_resolve_loop)

    result = asyncio.run(loop_module.run_session("hi", mode=AgentMode.explorer, max_cycles=3))

    assert result == "explorer:hi:3"
