import json

from vecna.memory.flush import FlushManager


class DummyAdapter:
    def __init__(self, response: str):
        self.response = response

    async def generate(self, _prompt: str) -> str:
        return self.response


class DummyMirror:
    def __init__(self):
        self.promoted = []
        self.facts_to_pg = []

    async def promote_to_memory(self, facts, beliefs):
        self.promoted.append((facts, beliefs))

    async def extract_facts_to_pg(self, facts, beliefs):
        self.facts_to_pg.append((facts, beliefs))


def test_should_flush_triggers_at_threshold():
    manager = FlushManager(adapter=None, mirror=DummyMirror(), config=None, token_threshold=10)
    assert manager.should_flush(10) is True
    assert manager.should_flush(9) is False


async def test_flush_session_end_parses_structured_json():
    payload = {
        "session_summary": "Summary",
        "task_state": {
            "current_task": "Task",
            "next_steps": "Next",
            "blockers": "None",
        },
        "new_facts": [{"content": "Fact", "confidence": 0.9}],
        "new_beliefs": [{"content": "Belief", "confidence": 0.8}],
        "key_decisions": ["Decision"],
        "open_questions": ["Question"],
    }
    adapter = DummyAdapter(json.dumps(payload))
    mirror = DummyMirror()
    manager = FlushManager(adapter=adapter, mirror=mirror, config=None, token_threshold=10)

    result = await manager.flush_session_end([{"role": "user", "content": "hi"}])

    assert result.session_summary == "Summary"
    assert result.task_state.current_task == "Task"
    assert len(result.new_facts) == 1
    assert len(result.new_beliefs) == 1
    assert result.key_decisions == ["Decision"]
    assert result.open_questions == ["Question"]


async def test_flush_session_end_fallbacks_to_extractive():
    mirror = DummyMirror()
    manager = FlushManager(adapter=None, mirror=mirror, config=None, token_threshold=10)

    result = await manager.flush_session_end([{"role": "user", "content": "hello"}])

    assert result.session_summary
    assert isinstance(result.new_facts, list)


async def test_flush_mid_session_compresses_older_messages():
    payload = {
        "session_summary": "Compressed summary",
        "task_state": {"current_task": "", "next_steps": "", "blockers": ""},
        "new_facts": [],
        "new_beliefs": [],
        "key_decisions": [],
        "open_questions": [],
    }
    adapter = DummyAdapter(json.dumps(payload))
    mirror = DummyMirror()
    manager = FlushManager(adapter=adapter, mirror=mirror, config=None, token_threshold=10)
    conversation = [
        {"role": "user", "content": "msg1"},
        {"role": "assistant", "content": "msg2"},
        {"role": "user", "content": "msg3"},
        {"role": "assistant", "content": "msg4"},
        {"role": "user", "content": "msg5"},
    ]

    result = await manager.flush_mid_session(conversation)

    assert result.session_summary == "Compressed summary"
    assert len(conversation) == 3
    assert conversation[0]["role"] == "system"
    assert conversation[0]["content"].startswith("[Session context compressed:")
    assert conversation[-2]["content"] == "msg4"
    assert conversation[-1]["content"] == "msg5"


async def test_flush_mid_session_skips_when_too_short():
    mirror = DummyMirror()
    manager = FlushManager(adapter=None, mirror=mirror, config=None, token_threshold=10)
    conversation = [
        {"role": "user", "content": "msg1"},
        {"role": "assistant", "content": "msg2"},
    ]

    result = await manager.flush_mid_session(conversation)

    assert result.session_summary == ""
    assert conversation[0]["content"] == "msg1"
    assert conversation[1]["content"] == "msg2"
