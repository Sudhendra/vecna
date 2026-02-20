"""Tests for cron-based autonomous operation — HeartbeatAction and HeartbeatConfig."""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from vecna.orchestrator.heartbeat import HeartbeatAction, HeartbeatConfig, HeartbeatRunner


class TestHeartbeatActions:
    """Tests for HeartbeatAction scheduling logic."""

    def test_check_goals_action_should_run_when_elapsed_exceeds_interval(self):
        action = HeartbeatAction(
            name="check_goals",
            description="Check for pending autonomous goals",
            interval_seconds=900,
        )
        assert action.should_run(elapsed_seconds=1000) is True

    def test_check_goals_action_should_not_run_when_elapsed_below_interval(self):
        action = HeartbeatAction(
            name="check_goals",
            description="Check for pending autonomous goals",
            interval_seconds=900,
        )
        assert action.should_run(elapsed_seconds=100) is False

    def test_dream_action_daily_interval_not_ready(self):
        action = HeartbeatAction(
            name="dream",
            description="Run dream loop consolidation",
            interval_seconds=86400,
        )
        assert action.should_run(elapsed_seconds=3600) is False

    def test_dream_action_daily_interval_ready(self):
        action = HeartbeatAction(
            name="dream",
            description="Run dream loop consolidation",
            interval_seconds=86400,
        )
        assert action.should_run(elapsed_seconds=90000) is True

    def test_action_records_last_run_with_timestamp(self):
        action = HeartbeatAction(name="test", interval_seconds=60)
        assert action.last_run is None
        before = datetime.utcnow()
        action.mark_run()
        after = datetime.utcnow()
        assert action.last_run is not None
        assert before <= action.last_run <= after

    def test_should_run_at_exact_boundary(self):
        """Elapsed exactly equals interval should trigger."""
        action = HeartbeatAction(name="boundary", interval_seconds=300)
        assert action.should_run(elapsed_seconds=300) is True

    def test_should_not_run_at_zero_elapsed(self):
        action = HeartbeatAction(name="zero", interval_seconds=60)
        assert action.should_run(elapsed_seconds=0) is False

    def test_action_has_description_field(self):
        action = HeartbeatAction(
            name="test_desc",
            description="A descriptive action",
            interval_seconds=120,
        )
        assert action.description == "A descriptive action"

    def test_action_default_description_is_empty(self):
        action = HeartbeatAction(name="minimal", interval_seconds=60)
        assert action.description == ""

    def test_action_serializes_to_dict(self):
        """HeartbeatAction should support to_dict (SerializableMixin)."""
        action = HeartbeatAction(
            name="serialize_test",
            description="Testing serialization",
            interval_seconds=600,
        )
        d = action.to_dict()
        assert d["name"] == "serialize_test"
        assert d["description"] == "Testing serialization"
        assert d["interval_seconds"] == 600
        assert d["last_run"] is None

    def test_action_serializes_last_run_as_iso(self):
        action = HeartbeatAction(name="ts", interval_seconds=60)
        action.mark_run()
        d = action.to_dict()
        # last_run should be an ISO string, not a datetime object
        assert isinstance(d["last_run"], str)
        # Should be parseable back to datetime
        parsed = datetime.fromisoformat(d["last_run"])
        assert parsed.isoformat() == d["last_run"]
        assert d["last_run"] == action.last_run.isoformat()


class TestHeartbeatActionEdgeCases:
    """Error and edge-case tests (Amendment 10)."""

    def test_negative_elapsed_seconds_does_not_run(self):
        action = HeartbeatAction(name="neg", interval_seconds=60)
        assert action.should_run(elapsed_seconds=-10) is False

    def test_negative_interval_always_runs(self):
        """An action with interval_seconds <= 0 should always run (run as often as possible)."""
        action = HeartbeatAction(name="eager", interval_seconds=0)
        assert action.should_run(elapsed_seconds=0) is True
        action2 = HeartbeatAction(name="negative_interval", interval_seconds=-1)
        assert action2.should_run(elapsed_seconds=0) is True

    def test_very_large_elapsed_runs(self):
        action = HeartbeatAction(name="stale", interval_seconds=60)
        assert action.should_run(elapsed_seconds=999_999_999) is True

    def test_mark_run_updates_timestamp_each_call(self):
        action = HeartbeatAction(name="multi", interval_seconds=60)
        action.mark_run()
        first_run = action.last_run
        # Small sleep to ensure timestamp differs
        time.sleep(0.01)
        action.mark_run()
        second_run = action.last_run
        assert second_run is not None
        assert first_run is not None
        assert second_run >= first_run

    def test_float_elapsed_seconds(self):
        """should_run should handle float elapsed values."""
        action = HeartbeatAction(name="float_test", interval_seconds=10)
        assert action.should_run(elapsed_seconds=10.5) is True
        assert action.should_run(elapsed_seconds=9.9) is False


class TestHeartbeatConfig:
    """Tests for HeartbeatConfig default action system."""

    def test_default_actions_include_required_names(self):
        config = HeartbeatConfig()
        action_names = [a.name for a in config.actions]
        assert "check_goals" in action_names
        assert "dream" in action_names
        assert "curiosity" in action_names

    def test_default_check_goals_interval(self):
        config = HeartbeatConfig()
        check_goals = next(a for a in config.actions if a.name == "check_goals")
        assert check_goals.interval_seconds == 900

    def test_default_dream_interval(self):
        config = HeartbeatConfig()
        dream = next(a for a in config.actions if a.name == "dream")
        assert dream.interval_seconds == 86400

    def test_default_curiosity_interval(self):
        config = HeartbeatConfig()
        curiosity = next(a for a in config.actions if a.name == "curiosity")
        # Curiosity should have an interval between check_goals and dream
        assert 0 < curiosity.interval_seconds < 86400

    def test_config_preserves_existing_fields(self):
        """HeartbeatConfig should still have interval_seconds, jitter_seconds,
        max_goals_per_tick."""
        config = HeartbeatConfig()
        assert config.interval_seconds == 900
        assert config.jitter_seconds == 90
        assert config.max_goals_per_tick == 3

    def test_custom_actions_override_defaults(self):
        custom_action = HeartbeatAction(name="custom", interval_seconds=42)
        config = HeartbeatConfig(actions=[custom_action])
        assert len(config.actions) == 1
        assert config.actions[0].name == "custom"
        assert config.actions[0].interval_seconds == 42


class TestHeartbeatConfigEdgeCases:
    """Edge cases for HeartbeatConfig (Amendment 10)."""

    def test_empty_actions_list(self):
        config = HeartbeatConfig(actions=[])
        assert config.actions == []

    def test_actions_are_independent_instances(self):
        """Each HeartbeatConfig should have its own action instances, not shared mutable state."""
        config1 = HeartbeatConfig()
        config2 = HeartbeatConfig()
        config1.actions[0].mark_run()
        # config2 actions should be unaffected
        assert config2.actions[0].last_run is None


# ---------------------------------------------------------------------------
# Stub goal queue for HeartbeatRunner tests (Amendment 11: public interface)
# ---------------------------------------------------------------------------


class StubGoalQueue:
    """Minimal stub matching GoalQueue's public interface (push/pop)."""

    def __init__(self, items: Optional[List[Dict[str, Any]]] = None):
        self._items: List[Dict[str, Any]] = list(items) if items else []
        self.completed: List[str] = []
        self.failed: List[tuple] = []

    def push(self, item: Dict[str, Any]) -> None:
        self._items.append(item)

    def pop(self) -> Optional[Dict[str, Any]]:
        if not self._items:
            return None
        return self._items.pop(0)

    def mark_completed(self, goal_id: str) -> None:
        self.completed.append(goal_id)

    def mark_failed(self, goal_id: str, error: str) -> None:
        self.failed.append((goal_id, error))


# ---------------------------------------------------------------------------
# Stub autonomy loop for HeartbeatRunner tests (Amendment 11: public interface)
# ---------------------------------------------------------------------------


class StubAutonomyLoop:
    """Stub that exposes the public goal-processing API expected by HeartbeatRunner.

    HeartbeatRunner calls extract_goal(), run_goal(), mark_goal_completed(),
    and mark_goal_failed() — all public methods added in this task.
    """

    def __init__(
        self,
        run_result: str = "done",
        run_error: Optional[Exception] = None,
    ):
        self.run_result = run_result
        self.run_error = run_error
        self.executed_goals: List[str] = []

    def extract_goal(self, item: Any) -> str:
        """Public facade for goal extraction from a queue item."""
        if not isinstance(item, dict):
            return ""
        goal = item.get("goal")
        if isinstance(goal, str) and goal.strip():
            return goal
        content = item.get("content")
        if isinstance(content, str) and content.strip():
            return content
        return ""

    async def run_goal(self, goal: str) -> str:
        """Public facade for goal execution."""
        if self.run_error is not None:
            raise self.run_error
        self.executed_goals.append(goal)
        return self.run_result

    def mark_goal_completed(self, goal_queue: Any, goal_id: str) -> None:
        """Public facade for marking a goal completed."""
        if not goal_id:
            return
        marker = getattr(goal_queue, "mark_completed", None)
        if callable(marker):
            marker(goal_id)

    def mark_goal_failed(self, goal_queue: Any, goal_id: str, error: str) -> None:
        """Public facade for marking a goal failed."""
        if not goal_id:
            return
        marker = getattr(goal_queue, "mark_failed", None)
        if callable(marker):
            marker(goal_id, error)


class TestHeartbeatRunnerDueActions:
    """Tests for HeartbeatRunner.get_due_actions() scheduling integration."""

    def _make_runner(
        self,
        config: Optional[HeartbeatConfig] = None,
    ) -> HeartbeatRunner:
        """Create a HeartbeatRunner with stub dependencies via constructor."""
        stub_loop = StubAutonomyLoop()
        stub_queue = StubGoalQueue()
        return HeartbeatRunner(
            autonomy_loop=stub_loop,
            goal_queue=stub_queue,
            config=config,
        )

    def test_get_due_actions_returns_all_when_never_run(self):
        """Actions that have never run should all be due."""
        config = HeartbeatConfig()
        runner = self._make_runner(config=config)
        due = runner.get_due_actions()
        assert len(due) == len(config.actions)
        due_names = [a.name for a in due]
        assert "check_goals" in due_names
        assert "dream" in due_names
        assert "curiosity" in due_names

    def test_get_due_actions_excludes_recently_run(self):
        """An action that just ran should not be due again immediately."""
        action = HeartbeatAction(name="recent", interval_seconds=3600)
        action.mark_run()
        config = HeartbeatConfig(actions=[action])
        runner = self._make_runner(config=config)
        due = runner.get_due_actions()
        assert len(due) == 0

    def test_get_due_actions_includes_overdue(self):
        """An action whose last_run is older than its interval should be due."""
        action = HeartbeatAction(name="overdue", interval_seconds=60)
        action.last_run = datetime.utcnow() - timedelta(seconds=120)
        config = HeartbeatConfig(actions=[action])
        runner = self._make_runner(config=config)
        due = runner.get_due_actions()
        assert len(due) == 1
        assert due[0].name == "overdue"


class TestHeartbeatRunnerTick:
    """Tests for HeartbeatRunner.tick() — the wake-check-act-sleep cycle."""

    def _make_runner(
        self,
        stub_loop: Optional[StubAutonomyLoop] = None,
        stub_queue: Optional[StubGoalQueue] = None,
        config: Optional[HeartbeatConfig] = None,
    ) -> HeartbeatRunner:
        loop = stub_loop or StubAutonomyLoop()
        queue = stub_queue or StubGoalQueue()
        return HeartbeatRunner(autonomy_loop=loop, goal_queue=queue, config=config)

    async def test_tick_idle_when_queue_empty(self):
        """tick() returns idle status when no goals are queued."""
        runner = self._make_runner()
        summary = await runner.tick()
        assert summary["status"] == "idle"
        assert summary["goals_popped"] == 0
        assert summary["goals_executed"] == 0

    async def test_tick_processes_single_goal(self):
        """tick() processes a goal and marks it completed."""
        queue = StubGoalQueue([{"goal_id": "g1", "goal": "test goal"}])
        loop = StubAutonomyLoop(run_result="completed")
        runner = self._make_runner(stub_loop=loop, stub_queue=queue)
        summary = await runner.tick()
        assert summary["status"] == "ok"
        assert summary["goals_popped"] == 1
        assert summary["goals_executed"] == 1
        assert summary["goals_completed"] == 1
        assert summary["goals_failed"] == 0
        assert "test goal" in loop.executed_goals
        assert "g1" in queue.completed

    async def test_tick_handles_goal_execution_failure(self):
        """tick() catches goal execution errors and marks goal as failed."""
        queue = StubGoalQueue([{"goal_id": "g2", "goal": "fail goal"}])
        loop = StubAutonomyLoop(run_error=RuntimeError("model timeout"))
        runner = self._make_runner(stub_loop=loop, stub_queue=queue)
        summary = await runner.tick()
        assert summary["status"] == "error"
        assert summary["goals_failed"] == 1
        assert summary["goals_completed"] == 0
        assert len(queue.failed) == 1
        assert queue.failed[0][0] == "g2"
        assert "model timeout" in queue.failed[0][1]

    async def test_tick_skips_empty_goal_content(self):
        """tick() skips items where goal content is empty."""
        queue = StubGoalQueue([{"goal_id": "g3", "goal": ""}])
        runner = self._make_runner(stub_queue=queue)
        summary = await runner.tick()
        assert summary["goals_popped"] == 1
        assert summary["goals_skipped"] == 1
        assert summary["goals_executed"] == 0

    async def test_tick_respects_max_goals_per_tick(self):
        """tick() stops after processing max_goals_per_tick items."""
        items = [{"goal_id": f"g{i}", "goal": f"goal {i}"} for i in range(10)]
        queue = StubGoalQueue(items)
        config = HeartbeatConfig(max_goals_per_tick=2)
        runner = self._make_runner(stub_queue=queue, config=config)
        summary = await runner.tick()
        assert summary["goals_popped"] == 2
        assert summary["max_goals_per_tick"] == 2

    async def test_tick_skips_duplicate_goal_ids(self):
        """tick() skips goals with the same goal_id already attempted in this tick."""
        items = [
            {"goal_id": "dup", "goal": "goal A"},
            {"goal_id": "dup", "goal": "goal B"},
        ]
        queue = StubGoalQueue(items)
        config = HeartbeatConfig(max_goals_per_tick=5)
        runner = self._make_runner(stub_queue=queue, config=config)
        summary = await runner.tick()
        assert summary["goals_executed"] == 1
        assert summary["goals_skipped"] == 1

    async def test_tick_partial_status_on_mixed_results(self):
        """tick() returns 'partial' when some goals succeed and some fail."""
        # We need a loop that fails on specific goals
        call_count = 0

        class AlternatingLoop(StubAutonomyLoop):
            async def run_goal(self, goal: str) -> str:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return "ok"
                raise RuntimeError("second goal fails")

        items = [
            {"goal_id": "ok1", "goal": "good goal"},
            {"goal_id": "bad1", "goal": "bad goal"},
        ]
        queue = StubGoalQueue(items)
        config = HeartbeatConfig(max_goals_per_tick=5)
        loop = AlternatingLoop()
        runner = self._make_runner(stub_loop=loop, stub_queue=queue, config=config)
        summary = await runner.tick()
        assert summary["status"] == "partial"
        assert summary["goals_completed"] == 1
        assert summary["goals_failed"] == 1

    async def test_tick_with_non_dict_queue_item(self):
        """tick() handles queue items that are not dicts (edge case)."""

        # StubGoalQueue only returns dicts, but the actual GoalQueue could
        # theoretically return malformed items. Test via a custom queue.
        class BadQueue:
            def __init__(self):
                self._items = ["not a dict", None]
                self._idx = 0

            def pop(self) -> Any:
                if self._idx >= len(self._items):
                    return None
                item = self._items[self._idx]
                self._idx += 1
                return item

        queue = BadQueue()
        config = HeartbeatConfig(max_goals_per_tick=5)
        loop = StubAutonomyLoop()
        runner = HeartbeatRunner(autonomy_loop=loop, goal_queue=queue, config=config)
        summary = await runner.tick()
        # "not a dict" should be popped but skipped; None terminates
        assert summary["goals_popped"] == 1
        assert summary["goals_skipped"] == 1

    async def test_tick_max_goals_zero_processes_nothing(self):
        """tick() with max_goals_per_tick=0 should process no goals."""
        items = [{"goal_id": "g1", "goal": "ignored"}]
        queue = StubGoalQueue(items)
        config = HeartbeatConfig(max_goals_per_tick=0)
        runner = self._make_runner(stub_queue=queue, config=config)
        summary = await runner.tick()
        assert summary["status"] == "idle"
        assert summary["goals_popped"] == 0


class TestHeartbeatRunnerTickEdgeCases:
    """Error and edge-case tests for tick() (Amendment 10)."""

    async def test_tick_negative_max_goals_treated_as_zero(self):
        """Negative max_goals_per_tick should be clamped to 0."""
        items = [{"goal_id": "g1", "goal": "goal"}]
        queue = StubGoalQueue(items)
        config = HeartbeatConfig(max_goals_per_tick=-1)
        loop = StubAutonomyLoop()
        runner = HeartbeatRunner(autonomy_loop=loop, goal_queue=queue, config=config)
        summary = await runner.tick()
        assert summary["max_goals_per_tick"] == 0
        assert summary["goals_popped"] == 0

    async def test_tick_handles_keyboard_interrupt_propagation(self):
        """KeyboardInterrupt during goal execution should propagate, not be swallowed."""

        class InterruptLoop(StubAutonomyLoop):
            async def run_goal(self, goal: str) -> str:
                raise KeyboardInterrupt("user abort")

        items = [{"goal_id": "g1", "goal": "will interrupt"}]
        queue = StubGoalQueue(items)
        loop = InterruptLoop()
        runner = HeartbeatRunner(autonomy_loop=loop, goal_queue=queue)
        try:
            await runner.tick()
            assert False, "KeyboardInterrupt should have propagated"
        except KeyboardInterrupt:
            pass  # Expected


class TestHeartbeatRunnerConcurrency:
    """Concurrency stress tests for HeartbeatRunner (Amendment 12)."""

    async def test_concurrent_get_due_actions_no_data_loss(self):
        """50+ concurrent calls to get_due_actions() should all return consistent results."""
        config = HeartbeatConfig()
        loop = StubAutonomyLoop()
        queue = StubGoalQueue()
        runner = HeartbeatRunner(autonomy_loop=loop, goal_queue=queue, config=config)

        async def call_due():
            return runner.get_due_actions()

        tasks = [asyncio.create_task(call_due()) for _ in range(50)]
        results = await asyncio.gather(*tasks)

        # All 50 calls should return the same 4 default actions (never-run = always due)
        for result in results:
            assert len(result) == 4
            names = {a.name for a in result}
            assert names == {"check_goals", "dream", "curiosity", "thoughtfulness"}

    async def test_concurrent_mark_run_no_lost_updates(self):
        """50+ concurrent mark_run() calls on the same action should all record timestamps."""
        action = HeartbeatAction(name="concurrent_mark", interval_seconds=60)

        async def mark_it():
            action.mark_run()

        tasks = [asyncio.create_task(mark_it()) for _ in range(50)]
        await asyncio.gather(*tasks)

        # last_run should be set (last writer wins, but should not be None)
        assert action.last_run is not None
        # Should be a recent timestamp
        assert (datetime.utcnow() - action.last_run).total_seconds() < 5

    async def test_concurrent_ticks_independent_summaries(self):
        """Multiple concurrent tick() calls each produce independent summary dicts."""
        items = [{"goal_id": f"g{i}", "goal": f"goal {i}"} for i in range(60)]
        queue = StubGoalQueue(items)
        config = HeartbeatConfig(max_goals_per_tick=1)
        loop = StubAutonomyLoop(run_result="ok")
        runner = HeartbeatRunner(autonomy_loop=loop, goal_queue=queue, config=config)

        tasks = [asyncio.create_task(runner.tick()) for _ in range(50)]
        summaries = await asyncio.gather(*tasks)

        # Each tick processes at most 1 goal
        total_popped = sum(s["goals_popped"] for s in summaries)
        total_executed = sum(s["goals_executed"] for s in summaries)
        total_completed = sum(s["goals_completed"] for s in summaries)

        # We queued 60 items, 50 concurrent ticks with max 1 each → at most 50 popped
        assert total_popped <= 60
        assert total_executed <= total_popped
        assert total_completed <= total_executed
        # At least some should have been processed
        assert total_popped > 0
