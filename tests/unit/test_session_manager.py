from datetime import datetime
from pathlib import Path

from vecna.config.schema import create_default_config
from vecna.core.types import Belief, Fact
from vecna.memory.flush import FlushResult, TaskState
from vecna.memory.session import SessionManager


class FakePgStore:
    def __init__(self, results):
        self.results = results

    def search(self, _query, limit=5, hybrid=True):
        return self.results[:limit]


class FakeMirror:
    def __init__(self, workspace_dir: Path, pg_store=None):
        self.workspace_dir = workspace_dir
        self.pg_store = pg_store
        self.indexed = False
        self.appended = []
        self.updated = []
        self.promoted = []
        self.extracted = []

    async def index_markdown_files(self):
        self.indexed = True
        return 0

    async def append_daily_log(self, summary, timestamp):
        self.appended.append((summary, timestamp))

    async def update_working(self, task_state, next_steps, blockers):
        self.updated.append((task_state, next_steps, blockers))

    async def promote_to_memory(self, facts, beliefs):
        self.promoted.append((facts, beliefs))

    async def extract_facts_to_pg(self, facts, beliefs):
        self.extracted.append((facts, beliefs))


class FakeFlush:
    def __init__(self, result):
        self.result = result

    async def flush_session_end(self, _conversation):
        return self.result


async def test_start_session_reads_files_and_searches(tmp_path):
    (tmp_path / "memory").mkdir()
    (tmp_path / "SOUL.md").write_text("soul", encoding="utf-8")
    (tmp_path / "WORKING.md").write_text("working", encoding="utf-8")
    (tmp_path / "memory" / "2026-02-09.md").write_text("daily", encoding="utf-8")

    class SimpleItem:
        def __init__(self, content, item_type):
            self.content = content
            self.item_type = item_type

    item = SimpleItem(content="Relevant memory", item_type="fact")
    pg_store = FakePgStore([(item, 0.9)])
    mirror = FakeMirror(tmp_path, pg_store=pg_store)
    flush_mgr = FakeFlush(None)

    manager = SessionManager(mirror=mirror, flush_mgr=flush_mgr, config=create_default_config())
    context = await manager.start_session(initial_query="query")
    formatted = manager.format_context(context)

    assert mirror.indexed is True
    assert context.soul == "soul"
    assert context.working == "working"
    assert context.daily_log == "daily"
    assert "Relevant memory" in context.relevant_memory
    assert "[SOUL" in formatted
    assert "[WORKING" in formatted


async def test_end_session_routes_outputs(tmp_path):
    mirror = FakeMirror(tmp_path)
    result = FlushResult(
        session_summary="summary",
        task_state=TaskState(current_task="task", next_steps="next", blockers="none"),
        new_facts=[Fact(content="fact", confidence=0.8)],
        new_beliefs=[Belief(content="belief", confidence=0.9)],
        key_decisions=["decision"],
        open_questions=["question"],
    )
    flush_mgr = FakeFlush(result)

    manager = SessionManager(mirror=mirror, flush_mgr=flush_mgr, config=create_default_config())
    await manager.end_session([{"role": "user", "content": "hi"}])

    assert mirror.appended
    assert mirror.updated
    assert mirror.promoted
    assert mirror.extracted
