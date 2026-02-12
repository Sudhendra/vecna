from typing import Optional, List

from vecna.adapters.base import BaseAdapter
from vecna.orchestrator.goal_queue import GoalQueue
from vecna.orchestrator.loop import HiveLoop, HiveConfig


class AutonomyLoop(HiveLoop):
    def __init__(
        self,
        config: Optional[HiveConfig] = None,
        adapters: Optional[List[BaseAdapter]] = None,
        name: str = "explorer",
    ):
        super().__init__(config=config, adapters=adapters, name=name)

    async def run(
        self,
        goal_queue: GoalQueue,
        max_cycles: Optional[int] = None,
    ) -> List[str]:
        results: List[str] = []
        while True:
            item = goal_queue.pop()
            if item is None:
                break
            goal = item.get("goal")
            if not goal:
                continue
            results.append(await self._run_goal(goal, max_cycles=max_cycles))
        return results

    async def _run_goal(self, goal: str, max_cycles: Optional[int] = None) -> str:
        """Execute one queued goal, preferring ReWOO when enabled."""
        return await self.think(goal, max_cycles=max_cycles)
