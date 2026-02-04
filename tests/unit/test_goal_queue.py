import asyncio

from vecna.orchestrator.autonomy import AutonomyLoop
from vecna.orchestrator.goal_queue import GoalQueue


def test_goal_queue_push_pop(tmp_path):
    q = GoalQueue(path=tmp_path / "queue.jsonl")
    q.push({"goal": "explore tool usage"})
    item = q.pop()
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
