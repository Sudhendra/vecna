import asyncio

import pytest

from vecna.config.schema import AgentMode
from vecna.orchestrator import loop as loop_module
from vecna.orchestrator import mode_router
from vecna.orchestrator.autonomy import AutonomyLoop
from vecna.orchestrator.loop import HiveLoop
from vecna.orchestrator.mode_router import resolve_loop


class DummyLoop:
    def __init__(self, name):
        self.name = name

    async def think(self, task, max_cycles=None):
        return f"{self.name}:{task}:{max_cycles}"


def test_resolve_loop_assistant():
    loop = resolve_loop(AgentMode.assistant)
    assert loop.name == "assistant"
    assert isinstance(loop, HiveLoop)


def test_resolve_loop_explorer():
    loop = resolve_loop(AgentMode.explorer)
    assert loop.name == "explorer"
    assert isinstance(loop, AutonomyLoop)


def test_run_session_delegates_to_resolve_loop(monkeypatch):
    def fake_resolve_loop(mode):
        return DummyLoop(mode.value)

    monkeypatch.setattr(mode_router, "resolve_loop", fake_resolve_loop)

    result = asyncio.run(loop_module.run_session("hi", mode=AgentMode.explorer, max_cycles=3))

    assert result == "explorer:hi:3"


def test_run_session_invalid_mode_raises_value_error():
    with pytest.raises(ValueError, match="Invalid agent mode"):
        asyncio.run(loop_module.run_session("hi", mode="nope"))
