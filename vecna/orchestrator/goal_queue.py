"""File-backed FIFO goal queue used by current autonomy tests."""

import json
from pathlib import Path
from typing import Optional, Dict, Any


class GoalQueue:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def push(self, item: Dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(item) + "\n")

    def pop(self) -> Optional[Dict[str, Any]]:
        if not self.path.exists():
            return None

        with self.path.open("r", encoding="utf-8") as handle:
            lines = handle.readlines()

        if not lines:
            return None

        first = lines[0].rstrip("\n")
        remaining = lines[1:]

        with self.path.open("w", encoding="utf-8") as handle:
            handle.writelines(remaining)

        return json.loads(first)


FileGoalQueue = GoalQueue
