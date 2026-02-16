"""Cron-friendly heartbeat runner for bounded autonomy ticks."""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from vecna.orchestrator.autonomy import AutonomyLoop


@dataclass
class HeartbeatConfig:
    interval_seconds: int = 900
    jitter_seconds: int = 90
    max_goals_per_tick: int = 3


class HeartbeatRunner:
    def __init__(
        self, autonomy_loop: AutonomyLoop, goal_queue: Any, config: Optional[HeartbeatConfig] = None
    ):
        self.autonomy_loop = autonomy_loop
        self.goal_queue = goal_queue
        self.config = config or HeartbeatConfig()

    async def tick(self) -> Dict[str, Any]:
        summary: Dict[str, Any] = {
            "status": "ok",
            "max_goals_per_tick": max(self.config.max_goals_per_tick, 0),
            "goals_popped": 0,
            "goals_executed": 0,
            "goals_completed": 0,
            "goals_failed": 0,
            "goals_skipped": 0,
        }
        attempted_goal_ids = set()

        for _ in range(summary["max_goals_per_tick"]):
            item = self.goal_queue.pop()
            if item is None:
                break

            summary["goals_popped"] += 1
            goal = self.autonomy_loop._extract_goal(item)
            if not goal:
                summary["goals_skipped"] += 1
                continue

            goal_id = ""
            if isinstance(item, dict):
                goal_id = str(item.get("goal_id", "")).strip()

            if goal_id and goal_id in attempted_goal_ids:
                summary["goals_skipped"] += 1
                continue

            try:
                if goal_id:
                    attempted_goal_ids.add(goal_id)
                summary["goals_executed"] += 1
                await self.autonomy_loop._run_goal(goal)
                summary["goals_completed"] += 1
                self.autonomy_loop._mark_completed(self.goal_queue, goal_id)
            except Exception as exc:
                summary["goals_failed"] += 1
                self.autonomy_loop._mark_failed(self.goal_queue, goal_id, str(exc))

        if summary["goals_popped"] == 0:
            summary["status"] = "idle"
        elif summary["goals_failed"] > 0 and summary["goals_completed"] == 0:
            summary["status"] = "error"
        elif summary["goals_failed"] > 0:
            summary["status"] = "partial"

        return summary
