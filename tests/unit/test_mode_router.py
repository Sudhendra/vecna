import asyncio

import pytest

from vecna.config.schema import AgentMode
from vecna.core.types import IdentityEvent
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


def test_run_session_invalid_mode_type_raises_type_error():
    with pytest.raises(TypeError, match="Invalid agent mode type"):
        asyncio.run(loop_module.run_session("hi", mode=123))  # type: ignore[arg-type]


class LegacyIdentityEvent:
    def __init__(self, trigger):
        self.trigger = trigger


def test_get_identity_event_type_prefers_event_type_alias():
    event = IdentityEvent(trigger="periodic")

    assert loop_module._get_identity_event_type(event) == "periodic"


def test_get_identity_event_type_falls_back_to_trigger_for_legacy_events():
    event = LegacyIdentityEvent(trigger="periodic")

    assert loop_module._get_identity_event_type(event) == "periodic"
