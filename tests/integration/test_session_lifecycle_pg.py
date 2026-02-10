import asyncio

import pytest

from vecna.config.schema import create_default_config
from vecna.core.types import Belief, Fact
from vecna.memory.flush import FlushResult, TaskState
from vecna.memory.mirror import MemoryMirror
from vecna.memory.session import SessionManager


class FakeFlush:
    def __init__(self, result):
        self.result = result

    async def flush_session_end(self, _conversation):
        return self.result


@pytest.mark.integration
def test_session_end_writes_working_and_memory(tmp_path, pg_memory_store):
    config = create_default_config()
    mirror = MemoryMirror(workspace_dir=tmp_path, pg_store=pg_memory_store, config=config)
    result = FlushResult(
        session_summary="summary",
        task_state=TaskState(current_task="task", next_steps="next", blockers="none"),
        new_facts=[Fact(content="fact", confidence=0.8)],
        new_beliefs=[Belief(content="belief", confidence=0.9)],
        key_decisions=["decision"],
        open_questions=["question"],
    )
    manager = SessionManager(mirror=mirror, flush_mgr=FakeFlush(result), config=config)

    asyncio.run(manager.end_session([{"role": "user", "content": "hi"}]))

    working = (tmp_path / "WORKING.md").read_text(encoding="utf-8")
    memory = (tmp_path / "MEMORY.md").read_text(encoding="utf-8")

    assert "task" in working
    assert "fact" in memory
