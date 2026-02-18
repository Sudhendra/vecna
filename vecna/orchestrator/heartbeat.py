"""Cron-friendly heartbeat runner for bounded autonomy ticks."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from vecna.core.types import SerializableMixin
from vecna.orchestrator.autonomy import AutonomyLoop


def _default_actions() -> "List[HeartbeatAction]":
    """Create default heartbeat actions — fresh instances each call."""
    return [
        HeartbeatAction(
            name="check_goals",
            description="Check for pending autonomous goals",
            interval_seconds=900,
        ),
        HeartbeatAction(
            name="dream",
            description="Run dream loop consolidation",
            interval_seconds=86400,
        ),
        HeartbeatAction(
            name="curiosity",
            description="Generate curiosity-driven exploration goals",
            interval_seconds=3600,
        ),
    ]


@dataclass
class HeartbeatAction(SerializableMixin):
    """A single scheduled action in the heartbeat system.

    Each action has a name, interval, and tracks when it last ran.
    Use should_run(elapsed_seconds) to check if the action is due,
    and mark_run() to record execution.
    """

    name: str
    interval_seconds: int = 60
    description: str = ""
    last_run: Optional[datetime] = field(default=None, repr=False)

    def should_run(self, elapsed_seconds: float) -> bool:
        """Return True if enough time has elapsed for this action to run.

        An action with interval_seconds <= 0 is treated as 'run as often as possible'.
        Negative elapsed_seconds never triggers (nonsensical input).
        """
        if elapsed_seconds < 0:
            return False
        if self.interval_seconds <= 0:
            return True
        return elapsed_seconds >= self.interval_seconds

    def mark_run(self) -> None:
        """Record that this action just ran."""
        self.last_run = datetime.utcnow()


@dataclass
class HeartbeatConfig:
    """Configuration for the heartbeat runner.

    actions: list of HeartbeatAction instances defining the cron schedule.
    Uses field(default_factory=...) so each config gets independent action instances.
    """

    interval_seconds: int = 900
    jitter_seconds: int = 90
    max_goals_per_tick: int = 3
    actions: List[HeartbeatAction] = field(default_factory=_default_actions)


class HeartbeatRunner:
    def __init__(
        self,
        autonomy_loop: AutonomyLoop,
        goal_queue: Any,
        config: Optional[HeartbeatConfig] = None,
    ):
        self.autonomy_loop = autonomy_loop
        self.goal_queue = goal_queue
        self.config = config or HeartbeatConfig()

    def get_due_actions(self) -> List[HeartbeatAction]:
        """Return actions that are due to run based on their last_run and interval."""
        due: List[HeartbeatAction] = []
        now = datetime.utcnow()
        for action in self.config.actions:
            if action.last_run is None:
                due.append(action)
            else:
                elapsed = (now - action.last_run).total_seconds()
                if action.should_run(elapsed_seconds=elapsed):
                    due.append(action)
        return due

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
        attempted_goal_ids: set[str] = set()

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
