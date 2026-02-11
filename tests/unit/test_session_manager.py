from datetime import date
from pathlib import Path

from vecna.config.schema import create_default_config
from vecna.core.types import Belief, Fact
from vecna.memory.flush import FlushResult, TaskState
from vecna.memory.session import SessionManager


class FakePgStore:
    def __init__(self, results):
        self.results = results
        self.last_search_kwargs = {}
        self.recorded_sessions = []

    def search(
        self,
        _query,
        top_k=5,
        hybrid=True,
        vector_weight=0.7,
        text_weight=0.3,
    ):
        self.last_search_kwargs = {
            "top_k": top_k,
            "hybrid": hybrid,
            "vector_weight": vector_weight,
            "text_weight": text_weight,
        }
        return self.results[:top_k]

    def record_session(self, session_id, started_at, ended_at, summary, tokens_used):
        self.recorded_sessions.append(
            {
                "session_id": session_id,
                "started_at": started_at,
                "ended_at": ended_at,
                "summary": summary,
                "tokens_used": tokens_used,
            }
        )
        return True


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

    async def promote_to_memory(self, facts, beliefs, key_decisions=None, open_questions=None):
        self.promoted.append((facts, beliefs, key_decisions, open_questions))

    async def extract_facts_to_pg(self, facts, beliefs):
        self.extracted.append((facts, beliefs))


class FakeFlush:
    def __init__(self, result):
        self.result = result
        self.should_flush_result = False
        self.mid_result = result

    async def flush_session_end(self, _conversation):
        return self.result

    def should_flush(self, _conversation_tokens):
        return self.should_flush_result

    async def flush_mid_session(self, _conversation):
        return self.mid_result


async def test_start_session_reads_files_and_searches(tmp_path):
    (tmp_path / "memory").mkdir()
    (tmp_path / "SOUL.md").write_text("soul", encoding="utf-8")
    (tmp_path / "WORKING.md").write_text("working", encoding="utf-8")
    (tmp_path / "memory" / f"{date.today().isoformat()}.md").write_text("daily", encoding="utf-8")

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


async def test_start_session_uses_configured_search_weights(tmp_path):
    (tmp_path / "memory").mkdir()
    (tmp_path / "SOUL.md").write_text("soul", encoding="utf-8")
    (tmp_path / "WORKING.md").write_text("working", encoding="utf-8")
    (tmp_path / "memory" / f"{date.today().isoformat()}.md").write_text("daily", encoding="utf-8")

    class SimpleItem:
        def __init__(self, content, item_type):
            self.content = content
            self.item_type = item_type

    cfg = create_default_config()
    cfg.memory.vector_weight = 0.55
    cfg.memory.text_weight = 0.45

    pg_store = FakePgStore([(SimpleItem(content="Relevant memory", item_type="fact"), 0.9)])
    mirror = FakeMirror(tmp_path, pg_store=pg_store)
    flush_mgr = FakeFlush(None)
    manager = SessionManager(mirror=mirror, flush_mgr=flush_mgr, config=cfg)

    await manager.start_session(initial_query="query")

    assert pg_store.last_search_kwargs["vector_weight"] == 0.55
    assert pg_store.last_search_kwargs["text_weight"] == 0.45


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
    promoted_facts, promoted_beliefs, key_decisions, open_questions = mirror.promoted[0]
    assert promoted_facts
    assert promoted_beliefs
    assert key_decisions == ["decision"]
    assert open_questions == ["question"]


async def test_maybe_flush_mid_session_routes_summary_and_facts(tmp_path):
    mirror = FakeMirror(tmp_path)
    result = FlushResult(
        session_summary="mid-summary",
        task_state=TaskState(current_task="task", next_steps="next", blockers="none"),
        new_facts=[Fact(content="fact", confidence=0.6)],
        new_beliefs=[Belief(content="belief", confidence=0.7)],
        key_decisions=[],
        open_questions=[],
    )
    flush_mgr = FakeFlush(result)
    flush_mgr.should_flush_result = True
    manager = SessionManager(mirror=mirror, flush_mgr=flush_mgr, config=create_default_config())

    conversation = [
        {"role": "user", "content": "one"},
        {"role": "assistant", "content": "two"},
        {"role": "user", "content": "three"},
    ]

    mid_result = await manager.maybe_flush_mid_session(conversation)

    assert mid_result is not None
    assert mirror.appended
    assert mirror.extracted


async def test_end_session_records_session_when_pg_store_available(tmp_path):
    pg_store = FakePgStore([])
    mirror = FakeMirror(tmp_path, pg_store=pg_store)
    result = FlushResult(
        session_summary="summary",
        task_state=TaskState(current_task="task", next_steps="next", blockers="none"),
        new_facts=[],
        new_beliefs=[],
        key_decisions=[],
        open_questions=[],
        tokens_used=123,
    )
    manager = SessionManager(
        mirror=mirror, flush_mgr=FakeFlush(result), config=create_default_config()
    )

    await manager.start_session(initial_query=None)
    await manager.end_session([{"role": "user", "content": "hi"}])

    assert pg_store.recorded_sessions
    assert pg_store.recorded_sessions[0]["summary"] == "summary"
    assert pg_store.recorded_sessions[0]["tokens_used"] == 123
