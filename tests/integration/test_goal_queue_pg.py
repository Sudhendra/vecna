"""Integration tests for PostgreSQL-backed goal queue."""

import uuid

import pytest

from vecna.orchestrator.pg_goal_queue import PgGoalQueue


def _reset_goal_queue_table(postgres_db):
    with postgres_db.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS autonomy_goals;")
        cur.execute(
            """
            CREATE TABLE autonomy_goals (
                goal_id UUID PRIMARY KEY,
                content TEXT NOT NULL,
                content_hash VARCHAR(64) NOT NULL UNIQUE,
                priority INTEGER NOT NULL DEFAULT 5,
                status VARCHAR(24) NOT NULL DEFAULT 'pending',
                retry_count INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                scheduled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                completed_at TIMESTAMPTZ,
                CHECK (priority >= 0),
                CHECK (retry_count >= 0),
                CHECK (max_retries >= 0),
                CHECK (status IN ('pending', 'in_progress', 'completed', 'failed'))
            );
            """
        )
        cur.execute(
            """
            CREATE INDEX autonomy_goals_status_scheduled_idx
            ON autonomy_goals (status, scheduled_at ASC, priority DESC);
            """
        )
        cur.execute(
            """
            CREATE INDEX autonomy_goals_created_at_idx
            ON autonomy_goals (created_at DESC);
            """
        )
    postgres_db.commit()


@pytest.mark.integration
def test_pg_goal_queue_push_pop_dedup_and_retry(postgres_available, postgres_db):
    if not postgres_available:
        pytest.skip("PostgreSQL not available")

    _reset_goal_queue_table(postgres_db)

    queue = PgGoalQueue(connection_string="postgresql://unused")
    queue._conn = postgres_db

    unique_content = f"Investigate trace {uuid.uuid4()}"
    duplicate_id = queue.push(
        unique_content, priority=7, max_retries=1, metadata={"source": "integration"}
    )
    duplicate_id_2 = queue.push(unique_content, priority=3, max_retries=5)

    assert duplicate_id_2 == duplicate_id

    first = queue.pop()
    assert first is not None
    assert first["goal_id"] == duplicate_id
    assert first["goal"] == unique_content

    retry_result = queue.mark_failed(duplicate_id, "temporary network issue")
    assert retry_result is not None
    assert retry_result["status"] == "pending"

    second = queue.pop()
    assert second is not None
    assert second["goal_id"] == duplicate_id

    terminal_result = queue.mark_failed(duplicate_id, "second failure")
    assert terminal_result is not None
    assert terminal_result["status"] == "failed"

    assert queue.pop() is None


@pytest.mark.integration
def test_pg_goal_queue_mark_completed(postgres_available, postgres_db):
    if not postgres_available:
        pytest.skip("PostgreSQL not available")

    _reset_goal_queue_table(postgres_db)

    queue = PgGoalQueue(connection_string="postgresql://unused")
    queue._conn = postgres_db

    goal_id = queue.push(f"Complete objective {uuid.uuid4()}", priority=9)
    item = queue.pop()
    assert item is not None
    assert item["goal_id"] == goal_id

    queue.mark_completed(goal_id)

    with postgres_db.cursor() as cur:
        cur.execute(
            "SELECT status, completed_at FROM autonomy_goals WHERE goal_id = %s", (goal_id,)
        )
        status, completed_at = cur.fetchone()

    assert status == "completed"
    assert completed_at is not None
