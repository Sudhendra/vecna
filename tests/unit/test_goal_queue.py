import asyncio
from typing import Any, List, Optional

import pytest

from vecna.orchestrator.autonomy import AutonomyLoop
from vecna.orchestrator.goal_queue import GoalQueue
from vecna.orchestrator.pg_goal_queue import PgGoalQueue


def test_goal_queue_push_pop(tmp_path):
    q = GoalQueue(path=tmp_path / "queue.jsonl")
    q.push({"goal": "explore tool usage"})
    item = q.pop()
    assert item is not None
    assert item["goal"] == "explore tool usage"


def test_autonomy_loop_consumes_goal_queue(tmp_path, monkeypatch):
    q = GoalQueue(path=tmp_path / "queue.jsonl")
    q.push({"goal": "first"})
    q.push({"goal": "second"})

    loop = AutonomyLoop()
    calls = []

    async def fake_think(task, max_cycles=None):
        calls.append((task, max_cycles))
        return f"done:{task}"

    monkeypatch.setattr(loop, "think", fake_think)

    results = asyncio.run(loop.run(q, max_cycles=2))

    assert results == ["done:first", "done:second"]
    assert calls == [("first", 2), ("second", 2)]


def test_autonomy_loop_skips_empty_items(tmp_path, monkeypatch):
    q = GoalQueue(path=tmp_path / "queue.jsonl")
    q.push({})
    q.push({"goal": "ok"})

    loop = AutonomyLoop()
    calls = []

    async def fake_think(task, max_cycles=None):
        calls.append((task, max_cycles))
        return f"done:{task}"

    monkeypatch.setattr(loop, "think", fake_think)

    results = asyncio.run(loop.run(q, max_cycles=1))

    assert results == ["done:ok"]
    assert calls == [("ok", 1)]


class _FakeCursor:
    def __init__(self, conn):
        self._conn = conn
        self._fetchone: Optional[Any] = None

    def execute(self, query: str, params: Optional[tuple] = None):
        self._conn.executed.append((query, params))
        index = len(self._conn.executed) - 1
        self._fetchone = (
            self._conn.fetchone_results[index] if index < len(self._conn.fetchone_results) else None
        )

    def fetchone(self):
        return self._fetchone

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeConnection:
    def __init__(self, fetchone_results: Optional[List[Any]] = None):
        self.fetchone_results = fetchone_results or []
        self.executed: List[Any] = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0

    def cursor(self, *args, **kwargs):
        return _FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _queue_with_fake_conn(fake_conn: _FakeConnection) -> PgGoalQueue:
    queue = PgGoalQueue(connection_string="postgresql://test")
    queue._conn = fake_conn
    return queue


def test_pg_goal_queue_push_returns_inserted_id():
    fake_conn = _FakeConnection(fetchone_results=[{"goal_id": "id-1"}])
    queue = _queue_with_fake_conn(fake_conn)

    goal_id = queue.push(
        "investigate anomaly", priority=8, max_retries=2, metadata={"source": "unit"}
    )

    assert goal_id == "id-1"
    assert fake_conn.commits == 1
    assert "ON CONFLICT (content_hash) DO NOTHING" in fake_conn.executed[0][0]


def test_pg_goal_queue_push_returns_existing_id_on_dedup():
    fake_conn = _FakeConnection(fetchone_results=[None, {"goal_id": "existing-id"}])
    queue = _queue_with_fake_conn(fake_conn)

    goal_id = queue.push("deduplicate me")

    assert goal_id == "existing-id"
    assert len(fake_conn.executed) == 2
    assert fake_conn.commits == 1


def test_pg_goal_queue_pop_returns_priority_item():
    fake_conn = _FakeConnection(
        fetchone_results=[
            {
                "goal_id": "id-2",
                "content": "highest",
                "priority": 10,
                "status": "in_progress",
                "retry_count": 0,
                "max_retries": 1,
                "metadata": {"source": "test"},
            }
        ]
    )
    queue = _queue_with_fake_conn(fake_conn)

    item = queue.pop()

    assert item is not None
    assert item["goal"] == "highest"
    assert item["goal_id"] == "id-2"
    assert fake_conn.commits == 1
    assert "FOR UPDATE SKIP LOCKED" in fake_conn.executed[0][0]


def test_pg_goal_queue_pop_returns_none_when_empty():
    fake_conn = _FakeConnection(fetchone_results=[None])
    queue = _queue_with_fake_conn(fake_conn)

    assert queue.pop() is None
    assert fake_conn.commits == 1


def test_pg_goal_queue_mark_completed():
    fake_conn = _FakeConnection(fetchone_results=[{"goal_id": "id-3"}])
    queue = _queue_with_fake_conn(fake_conn)

    queue.mark_completed("id-3")

    assert fake_conn.commits == 1
    query, params = fake_conn.executed[0]
    assert "status = 'completed'" in query
    assert params == ("id-3",)


def test_pg_goal_queue_mark_failed_with_retries_remaining():
    fake_conn = _FakeConnection(
        fetchone_results=[{"goal_id": "id-4", "status": "pending", "retry_count": 1}]
    )
    queue = _queue_with_fake_conn(fake_conn)

    result = queue.mark_failed("id-4", "transient")

    assert result is not None
    assert result["status"] == "pending"
    assert result["retry_count"] == 1
    assert fake_conn.commits == 1


def test_pg_goal_queue_mark_failed_terminal_failure():
    fake_conn = _FakeConnection(
        fetchone_results=[{"goal_id": "id-5", "status": "failed", "retry_count": 2}]
    )
    queue = _queue_with_fake_conn(fake_conn)

    result = queue.mark_failed("id-5", "permanent")

    assert result is not None
    assert result["status"] == "failed"
    assert fake_conn.commits == 1


def test_pg_goal_queue_mark_completed_missing_goal_id_raises():
    fake_conn = _FakeConnection(fetchone_results=[None])
    queue = _queue_with_fake_conn(fake_conn)

    with pytest.raises(KeyError, match="missing-id"):
        queue.mark_completed("missing-id")

    assert fake_conn.rollbacks == 0


def test_pg_goal_queue_mark_failed_missing_goal_id_raises():
    fake_conn = _FakeConnection(fetchone_results=[None])
    queue = _queue_with_fake_conn(fake_conn)

    with pytest.raises(KeyError, match="missing-id"):
        queue.mark_failed("missing-id", "error")

    assert fake_conn.rollbacks == 0
