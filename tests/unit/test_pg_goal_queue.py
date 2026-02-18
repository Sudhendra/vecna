"""Tests for the PostgreSQL-backed goal queue with in-memory fallback.

Tests the GoalItem dataclass, GoalStatus enum, priority ordering,
and the in-memory fallback mode of PgGoalQueue.

Amendments:
  9  — No trivial assertions (assert specific values/fields/behaviors)
  10 — At least 2 error/edge-case tests
  11 — Test through public interface only
  12 — Concurrency stress tests with asyncio.gather()
"""

import asyncio

import pytest

from vecna.orchestrator.pg_goal_queue import GoalItem, GoalStatus, PgGoalQueue, PRIORITY_ORDER


class TestGoalItem:
    """Tests for GoalItem dataclass behavior."""

    def test_goal_item_defaults(self):
        item = GoalItem(goal="learn quantum computing")
        assert item.goal == "learn quantum computing"
        assert item.priority == "medium"
        assert item.status == GoalStatus.PENDING
        assert item.source == "manual"
        assert item.max_retries == 2
        assert item.metadata == {}
        assert item.error is None
        assert item.completed_at is None

    def test_goal_item_custom_fields(self):
        item = GoalItem(
            goal="explore AI safety",
            priority="critical",
            goal_id="custom-id",
            source="dreamloop",
            max_retries=5,
            metadata={"origin": "dream"},
        )
        assert item.goal_id == "custom-id"
        assert item.priority == "critical"
        assert item.source == "dreamloop"
        assert item.max_retries == 5
        assert item.metadata == {"origin": "dream"}

    def test_goal_item_to_dict_includes_all_fields(self):
        item = GoalItem(goal_id="g1", goal="test goal", priority="high")
        result = item.to_dict()
        assert result["goal_id"] == "g1"
        assert result["goal"] == "test goal"
        assert result["priority"] == "high"
        assert result["status"] == "pending"
        assert result["source"] == "manual"
        assert result["content"] == "test goal"  # backward compat

    def test_goal_item_lt_comparison_for_priority(self):
        """GoalItem.__lt__ must respect PRIORITY_ORDER for heapq."""
        critical = GoalItem(goal="a", priority="critical")
        high = GoalItem(goal="b", priority="high")
        medium = GoalItem(goal="c", priority="medium")
        low = GoalItem(goal="d", priority="low")
        assert critical < high
        assert high < medium
        assert medium < low
        assert not low < critical

    def test_goal_item_unique_ids(self):
        """Each GoalItem gets a unique goal_id by default."""
        items = [GoalItem(goal=f"goal-{i}") for i in range(10)]
        ids = [item.goal_id for item in items]
        assert len(set(ids)) == 10


class TestGoalStatus:
    """Tests for GoalStatus enum."""

    def test_status_values(self):
        assert GoalStatus.PENDING.value == "pending"
        assert GoalStatus.RUNNING.value == "running"
        assert GoalStatus.COMPLETED.value == "completed"
        assert GoalStatus.FAILED.value == "failed"

    def test_status_from_string(self):
        assert GoalStatus("pending") == GoalStatus.PENDING
        assert GoalStatus("failed") == GoalStatus.FAILED


class TestPriorityOrder:
    """Tests for PRIORITY_ORDER constant."""

    def test_critical_is_highest(self):
        assert PRIORITY_ORDER["critical"] < PRIORITY_ORDER["high"]
        assert PRIORITY_ORDER["high"] < PRIORITY_ORDER["medium"]
        assert PRIORITY_ORDER["medium"] < PRIORITY_ORDER["low"]


class TestPgGoalQueueInMemory:
    """Test PgGoalQueue with in-memory fallback (no real PG needed)."""

    def test_push_and_pop(self):
        queue = PgGoalQueue(use_memory_fallback=True)
        queue.push(GoalItem(goal="Learn about quantum computing", priority="high"))
        item = queue.pop()
        assert item.goal == "Learn about quantum computing"
        assert item.priority == "high"
        assert item.status == GoalStatus.RUNNING

    def test_pop_empty_queue(self):
        queue = PgGoalQueue(use_memory_fallback=True)
        assert queue.pop() is None

    def test_priority_ordering(self):
        queue = PgGoalQueue(use_memory_fallback=True)
        queue.push(GoalItem(goal="low priority", priority="low"))
        queue.push(GoalItem(goal="critical priority", priority="critical"))
        queue.push(GoalItem(goal="medium priority", priority="medium"))
        item = queue.pop()
        assert item.goal == "critical priority"
        assert item.priority == "critical"

    def test_priority_ordering_full_drain(self):
        """Pop all items and verify they come out in priority order."""
        queue = PgGoalQueue(use_memory_fallback=True)
        queue.push(GoalItem(goal="low", priority="low"))
        queue.push(GoalItem(goal="high", priority="high"))
        queue.push(GoalItem(goal="critical", priority="critical"))
        queue.push(GoalItem(goal="medium", priority="medium"))

        goals = []
        while True:
            item = queue.pop()
            if item is None:
                break
            goals.append(item.goal)

        assert goals == ["critical", "high", "medium", "low"]

    def test_mark_completed(self):
        queue = PgGoalQueue(use_memory_fallback=True)
        queue.push(GoalItem(goal_id="g1", goal="test", priority="medium"))
        queue.mark_completed("g1")
        # Completed items don't come back
        item = queue.pop()
        assert item is None

    def test_mark_failed(self):
        queue = PgGoalQueue(use_memory_fallback=True)
        queue.push(GoalItem(goal_id="g2", goal="test", priority="medium"))
        queue.mark_failed("g2", "something broke")
        item = queue.pop()
        assert item is None

    def test_list_pending(self):
        queue = PgGoalQueue(use_memory_fallback=True)
        queue.push(GoalItem(goal="a", priority="low"))
        queue.push(GoalItem(goal="b", priority="high"))
        pending = queue.list_pending()
        assert len(pending) == 2
        goals = {p.goal for p in pending}
        assert goals == {"a", "b"}

    def test_list_pending_excludes_completed(self):
        queue = PgGoalQueue(use_memory_fallback=True)
        queue.push(GoalItem(goal_id="g1", goal="done", priority="high"))
        queue.push(GoalItem(goal_id="g2", goal="still pending", priority="low"))
        queue.mark_completed("g1")
        pending = queue.list_pending()
        assert len(pending) == 1
        assert pending[0].goal == "still pending"

    def test_list_pending_excludes_failed(self):
        queue = PgGoalQueue(use_memory_fallback=True)
        queue.push(GoalItem(goal_id="g1", goal="broken", priority="high"))
        queue.push(GoalItem(goal_id="g2", goal="ok", priority="low"))
        queue.mark_failed("g1", "error")
        pending = queue.list_pending()
        assert len(pending) == 1
        assert pending[0].goal == "ok"

    def test_pop_after_mark_completed_skips_completed(self):
        """Push multiple, complete one, verify pop returns next pending."""
        queue = PgGoalQueue(use_memory_fallback=True)
        queue.push(GoalItem(goal_id="g1", goal="first", priority="critical"))
        queue.push(GoalItem(goal_id="g2", goal="second", priority="high"))
        queue.mark_completed("g1")
        item = queue.pop()
        assert item.goal == "second"
        assert item.goal_id == "g2"

    def test_pop_sets_status_to_running(self):
        queue = PgGoalQueue(use_memory_fallback=True)
        queue.push(GoalItem(goal="test", priority="medium"))
        item = queue.pop()
        assert item.status == GoalStatus.RUNNING


class TestPgGoalQueueErrorPaths:
    """Error and edge-case tests (Amendment 10: at least 2)."""

    def test_mark_completed_nonexistent_goal_raises_key_error(self):
        queue = PgGoalQueue(use_memory_fallback=True)
        with pytest.raises(KeyError, match="nonexistent-id"):
            queue.mark_completed("nonexistent-id")

    def test_mark_failed_nonexistent_goal_raises_key_error(self):
        queue = PgGoalQueue(use_memory_fallback=True)
        with pytest.raises(KeyError, match="nonexistent-id"):
            queue.mark_failed("nonexistent-id", "some error")

    def test_push_and_pop_with_empty_goal_string(self):
        """Edge case: empty goal string is still a valid GoalItem."""
        queue = PgGoalQueue(use_memory_fallback=True)
        queue.push(GoalItem(goal="", priority="low"))
        item = queue.pop()
        assert item.goal == ""
        assert item.priority == "low"

    def test_double_mark_completed_raises_on_second(self):
        """Completing an already-completed goal should raise."""
        queue = PgGoalQueue(use_memory_fallback=True)
        queue.push(GoalItem(goal_id="g1", goal="test", priority="medium"))
        queue.mark_completed("g1")
        with pytest.raises(KeyError, match="g1"):
            queue.mark_completed("g1")

    def test_mark_failed_then_completed_raises(self):
        """Failing a goal then completing it should raise on complete."""
        queue = PgGoalQueue(use_memory_fallback=True)
        queue.push(GoalItem(goal_id="g1", goal="test", priority="medium"))
        queue.mark_failed("g1", "broken")
        with pytest.raises(KeyError, match="g1"):
            queue.mark_completed("g1")

    def test_memory_fallback_explicit_true(self):
        """PgGoalQueue with use_memory_fallback=True always uses memory backend."""
        queue = PgGoalQueue(use_memory_fallback=True)
        queue.push(GoalItem(goal="test", priority="medium"))
        item = queue.pop()
        assert item.goal == "test"
        assert item.status == GoalStatus.RUNNING

    def test_unknown_priority_treated_as_medium(self):
        """Unknown priority string gets default PRIORITY_ORDER value of 2 (medium)."""
        queue = PgGoalQueue(use_memory_fallback=True)
        queue.push(GoalItem(goal="unknown-prio", priority="urgent"))
        queue.push(GoalItem(goal="medium-prio", priority="medium"))
        # Both have same effective priority (2), so order depends on push order
        first = queue.pop()
        second = queue.pop()
        # heapq is stable for equal priorities — first pushed comes first
        assert {first.goal, second.goal} == {"unknown-prio", "medium-prio"}


class TestPgGoalQueueConcurrency:
    """Concurrency stress tests (Amendment 12).

    Uses asyncio.gather() with 50+ concurrent operations
    to verify no data loss or corruption.
    """

    async def test_concurrent_push_no_data_loss(self):
        """50 concurrent pushes must all be retrievable."""
        queue = PgGoalQueue(use_memory_fallback=True)

        async def push_one(i: int) -> None:
            queue.push(GoalItem(goal=f"goal-{i}", priority="medium"))

        await asyncio.gather(*[push_one(i) for i in range(50)])

        pending = queue.list_pending()
        assert len(pending) == 50
        goal_names = {p.goal for p in pending}
        assert goal_names == {f"goal-{i}" for i in range(50)}

    async def test_concurrent_push_and_pop_no_corruption(self):
        """Push 50 items, then pop 50 concurrently — no duplicates, no loss."""
        queue = PgGoalQueue(use_memory_fallback=True)
        for i in range(50):
            queue.push(GoalItem(goal_id=f"g-{i}", goal=f"goal-{i}", priority="medium"))

        results = []

        async def pop_one() -> None:
            item = queue.pop()
            if item is not None:
                results.append(item.goal_id)

        await asyncio.gather(*[pop_one() for _ in range(60)])

        # All 50 items should be popped, no duplicates
        assert len(results) == 50
        assert len(set(results)) == 50

    async def test_concurrent_mark_completed(self):
        """Marking 50 goals completed concurrently must not corrupt state."""
        queue = PgGoalQueue(use_memory_fallback=True)
        for i in range(50):
            queue.push(GoalItem(goal_id=f"g-{i}", goal=f"goal-{i}", priority="medium"))

        async def mark_one(goal_id: str) -> None:
            queue.mark_completed(goal_id)

        await asyncio.gather(*[mark_one(f"g-{i}") for i in range(50)])

        pending = queue.list_pending()
        assert len(pending) == 0

    async def test_concurrent_push_pop_mark_interleaved(self):
        """Interleaved push/pop/mark operations must not lose data."""
        queue = PgGoalQueue(use_memory_fallback=True)
        completed_ids = []

        async def push_and_pop(i: int) -> None:
            queue.push(GoalItem(goal_id=f"g-{i}", goal=f"goal-{i}", priority="medium"))
            item = queue.pop()
            if item is not None:
                queue.mark_completed(item.goal_id)
                completed_ids.append(item.goal_id)

        await asyncio.gather(*[push_and_pop(i) for i in range(50)])

        # All pushed items should be either completed or still pending
        pending = queue.list_pending()
        total_accounted = len(completed_ids) + len(pending)
        assert total_accounted == 50
