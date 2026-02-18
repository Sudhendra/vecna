"""Unit tests for cron-friendly heartbeat ticks."""

from typing import Any, Dict, List, Optional

import pytest

from vecna.orchestrator.autonomy import AutonomyLoop
from vecna.orchestrator.heartbeat import HeartbeatConfig, HeartbeatRunner


class _MemoryQueue:
    def __init__(self, items: List[Dict[str, Any]]):
        self._items = list(items)
        self.mark_completed_calls: List[str] = []
        self.mark_failed_calls: List[tuple[str, str]] = []

    def pop(self) -> Optional[Dict[str, Any]]:
        if not self._items:
            return None
        return self._items.pop(0)

    def mark_completed(self, goal_id: str) -> None:
        self.mark_completed_calls.append(goal_id)

    def mark_failed(self, goal_id: str, error: str) -> None:
        self.mark_failed_calls.append((goal_id, error))


@pytest.mark.asyncio
async def test_heartbeat_tick_reads_queue_and_executes_at_most_n_goals(monkeypatch):
    queue = _MemoryQueue(
        items=[
            {"goal_id": "g1", "goal": "first"},
            {"goal_id": "g2", "content": "second"},
            {"goal_id": "g3", "goal": "third"},
        ]
    )
    loop = AutonomyLoop()
    runner = HeartbeatRunner(
        autonomy_loop=loop,
        goal_queue=queue,
        config=HeartbeatConfig(max_goals_per_tick=2),
    )

    executed: List[str] = []

    async def fake_run_goal(goal: str, max_cycles=None) -> str:
        executed.append(goal)
        return f"done:{goal}"

    monkeypatch.setattr(loop, "run_goal", fake_run_goal)

    summary = await runner.tick()

    assert summary["status"] == "ok"
    assert summary["goals_popped"] == 2
    assert summary["goals_executed"] == 2
    assert summary["goals_completed"] == 2
    assert summary["goals_failed"] == 0
    assert executed == ["first", "second"]
    assert queue.mark_completed_calls == ["g1", "g2"]
    assert queue.mark_failed_calls == []


@pytest.mark.asyncio
async def test_heartbeat_tick_returns_idle_status_when_queue_empty():
    queue = _MemoryQueue(items=[])
    loop = AutonomyLoop()
    runner = HeartbeatRunner(
        autonomy_loop=loop,
        goal_queue=queue,
        config=HeartbeatConfig(max_goals_per_tick=3),
    )

    summary = await runner.tick()

    assert summary["status"] == "idle"
    assert summary["goals_popped"] == 0
    assert summary["goals_executed"] == 0
    assert summary["goals_completed"] == 0
    assert summary["goals_failed"] == 0


@pytest.mark.asyncio
async def test_heartbeat_tick_does_not_reprocess_same_goal_id_within_tick(monkeypatch):
    queue = _MemoryQueue(
        items=[
            {"goal_id": "g1", "goal": "flaky"},
            {"goal_id": "g1", "goal": "flaky"},
        ]
    )
    loop = AutonomyLoop()
    runner = HeartbeatRunner(
        autonomy_loop=loop,
        goal_queue=queue,
        config=HeartbeatConfig(max_goals_per_tick=3),
    )

    async def fail_run_goal(goal: str, max_cycles=None) -> str:
        raise RuntimeError("boom")

    monkeypatch.setattr(loop, "run_goal", fail_run_goal)

    summary = await runner.tick()

    assert summary["status"] == "error"
    assert summary["goals_popped"] == 2
    assert summary["goals_executed"] == 1
    assert summary["goals_failed"] == 1
    assert summary["goals_skipped"] == 1
    assert queue.mark_failed_calls == [("g1", "boom")]
