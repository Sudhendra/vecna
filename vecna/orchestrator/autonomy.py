"""Autonomy loop with bounded retries, backoff, and kill-switch support."""

import asyncio
from dataclasses import dataclass
from typing import Any, List, Optional

from vecna.adapters.base import BaseAdapter
from vecna.orchestrator.goal_queue import GoalQueue
from vecna.orchestrator.kill_switch import KillSwitch, KillSwitchActiveError
from vecna.orchestrator.loop import HiveLoop, HiveConfig


@dataclass
class BackoffConfig:
    base_seconds: float = 2.0
    max_seconds: float = 120.0
    multiplier: float = 2.0

    def delay_for_attempt(self, attempt: int) -> float:
        if attempt < 0:
            return self.base_seconds
        delay = self.base_seconds * (self.multiplier**attempt)
        return min(delay, self.max_seconds)


class AutonomyLoop(HiveLoop):
    def __init__(
        self,
        config: Optional[HiveConfig] = None,
        adapters: Optional[List[BaseAdapter]] = None,
        name: str = "explorer",
        backoff: Optional[BackoffConfig] = None,
        kill_switch: Optional[KillSwitch] = None,
    ):
        super().__init__(config=config, adapters=adapters, name=name)
        self.backoff = backoff or BackoffConfig()
        self.kill_switch = kill_switch

    async def run(
        self,
        goal_queue: GoalQueue,
        max_cycles: Optional[int] = None,
    ) -> List[str]:
        results: List[str] = []
        while True:
            if self._kill_switch_is_active():
                break

            item = goal_queue.pop()
            if item is None:
                break

            goal = self._extract_goal(item)
            if not goal:
                continue

            goal_id = str(item.get("goal_id", "")).strip()
            max_retries = self._extract_max_retries(item)
            attempt = 0
            stop_requested = False

            while True:
                if self._kill_switch_is_active():
                    stop_requested = True
                    break

                try:
                    result = await self._run_goal(goal, max_cycles=max_cycles)
                    results.append(result)
                    self._mark_completed(goal_queue, goal_id)
                    break
                except Exception as exc:
                    self._mark_failed(goal_queue, goal_id, str(exc))
                    if attempt >= max_retries:
                        break
                    if self._kill_switch_is_active():
                        stop_requested = True
                        break
                    await asyncio.sleep(self.backoff.delay_for_attempt(attempt))
                    attempt += 1

            if stop_requested:
                break

        return results

    async def _run_goal(self, goal: str, max_cycles: Optional[int] = None) -> str:
        """Execute one queued goal, preferring ReWOO when enabled."""
        return await self.think(goal, max_cycles=max_cycles)

    def _extract_goal(self, item: Any) -> str:
        if not isinstance(item, dict):
            return ""

        goal_value = item.get("goal")
        if isinstance(goal_value, str) and goal_value.strip():
            return goal_value

        content_value = item.get("content")
        if isinstance(content_value, str) and content_value.strip():
            return content_value

        return ""

    def _kill_switch_is_active(self) -> bool:
        if self.kill_switch is None:
            return False
        try:
            self.kill_switch.check_or_raise()
        except KillSwitchActiveError:
            return True
        return False

    def _extract_max_retries(self, item: Any) -> int:
        if not isinstance(item, dict):
            return 0
        value = item.get("max_retries", 0)
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return 0
        return max(parsed, 0)

    def _mark_completed(self, goal_queue: GoalQueue, goal_id: str) -> None:
        if not goal_id:
            return
        marker = getattr(goal_queue, "mark_completed", None)
        if callable(marker):
            marker(goal_id)

    def _mark_failed(self, goal_queue: GoalQueue, goal_id: str, error: str) -> None:
        if not goal_id:
            return
        marker = getattr(goal_queue, "mark_failed", None)
        if callable(marker):
            marker(goal_id, error)
