"""Tests for autonomy loop kill switch and retry behavior."""

import asyncio
from typing import Any, Dict, List, Optional

import pytest

from vecna.orchestrator.autonomy import AutonomyLoop, BackoffConfig
from vecna.orchestrator.kill_switch import KillSwitch


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
async def test_autonomy_loop_stops_when_kill_switch_active(tmp_path):
    queue = _MemoryQueue(items=[{"goal": "first"}, {"goal": "second"}])
    switch = KillSwitch(state_dir=tmp_path)
    switch.kill("maintenance")

    loop = AutonomyLoop(kill_switch=switch)
    calls: List[str] = []

    async def fake_think(task, max_cycles=None):
        calls.append(task)
        return f"done:{task}"

    loop.think = fake_think

    results = await loop.run(queue)

    assert results == []
    assert calls == []


def test_backoff_compute_behavior():
    backoff = BackoffConfig(base_seconds=0.5, max_seconds=3.0, multiplier=2.0)

    assert backoff.delay_for_attempt(0) == 0.5
    assert backoff.delay_for_attempt(1) == 1.0
    assert backoff.delay_for_attempt(2) == 2.0
    assert backoff.delay_for_attempt(3) == 3.0
    assert backoff.delay_for_attempt(5) == 3.0


@pytest.mark.asyncio
async def test_autonomy_loop_processes_queue_formats_and_handles_failures(monkeypatch):
    queue = _MemoryQueue(
        items=[
            {"goal_id": "g1", "goal": "first"},
            {"goal_id": "g2", "content": "from-pg", "max_retries": 2},
        ]
    )
    loop = AutonomyLoop(backoff=BackoffConfig(base_seconds=0.25, max_seconds=1.0, multiplier=2.0))

    calls: List[str] = []
    attempt_count = {"from-pg": 0}

    async def fake_think(task, max_cycles=None):
        calls.append(task)
        if task == "from-pg":
            attempt_count["from-pg"] += 1
            if attempt_count["from-pg"] < 3:
                raise RuntimeError(f"transient-{attempt_count['from-pg']}")
        return f"done:{task}"

    sleep_delays: List[float] = []

    async def fake_sleep(delay: float) -> None:
        sleep_delays.append(delay)

    loop.think = fake_think
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    results = await loop.run(queue, max_cycles=2)

    assert results == ["done:first", "done:from-pg"]
    assert calls == ["first", "from-pg", "from-pg", "from-pg"]
    assert queue.mark_completed_calls == ["g1", "g2"]
    assert queue.mark_failed_calls == []
    assert sleep_delays == [0.25, 0.5]


@pytest.mark.asyncio
async def test_autonomy_loop_marks_failed_once_when_retry_budget_exhausted(monkeypatch):
    queue = _MemoryQueue(items=[{"goal_id": "g1", "goal": "flaky", "max_retries": 2}])
    loop = AutonomyLoop(backoff=BackoffConfig(base_seconds=0.25, max_seconds=1.0, multiplier=2.0))

    calls: List[str] = []

    async def fake_think(task, max_cycles=None):
        calls.append(task)
        raise RuntimeError(f"transient-{len(calls)}")

    sleep_delays: List[float] = []

    async def fake_sleep(delay: float) -> None:
        sleep_delays.append(delay)

    loop.think = fake_think
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    results = await loop.run(queue)

    assert results == []
    assert calls == ["flaky", "flaky", "flaky"]
    assert queue.mark_completed_calls == []
    assert queue.mark_failed_calls == [("g1", "transient-3")]
    assert sleep_delays == [0.25, 0.5]


@pytest.mark.asyncio
async def test_autonomy_loop_stops_retries_when_kill_switch_activates(monkeypatch, tmp_path):
    queue = _MemoryQueue(items=[{"goal_id": "g1", "goal": "flaky", "max_retries": 3}])
    switch = KillSwitch(state_dir=tmp_path)
    loop = AutonomyLoop(
        backoff=BackoffConfig(base_seconds=0.25, max_seconds=1.0, multiplier=2.0),
        kill_switch=switch,
    )

    calls: List[str] = []

    async def fake_think(task, max_cycles=None):
        calls.append(task)
        switch.kill("operator stop")
        raise RuntimeError("transient")

    sleep_delays: List[float] = []

    async def fake_sleep(delay: float) -> None:
        sleep_delays.append(delay)

    loop.think = fake_think
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    results = await loop.run(queue)

    assert results == []
    assert calls == ["flaky"]
    assert queue.mark_completed_calls == []
    assert queue.mark_failed_calls == [("g1", "transient")]
    assert sleep_delays == []
