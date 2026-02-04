from vecna.config.schema import AgentMode
from vecna.orchestrator.mode_router import resolve_loop


class DummyLoop:
    def __init__(self, name):
        self.name = name


def test_resolve_loop_assistant():
    loop = resolve_loop(AgentMode.assistant)
    assert loop.name == "assistant"


def test_resolve_loop_explorer():
    loop = resolve_loop(AgentMode.explorer)
    assert loop.name == "explorer"
