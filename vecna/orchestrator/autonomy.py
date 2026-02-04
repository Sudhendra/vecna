from typing import Optional, List

from vecna.adapters.base import BaseAdapter
from vecna.orchestrator.loop import HiveLoop, HiveConfig


class AutonomyLoop(HiveLoop):
    def __init__(
        self,
        config: Optional[HiveConfig] = None,
        adapters: Optional[List[BaseAdapter]] = None,
        name: str = "explorer",
    ):
        super().__init__(config=config, adapters=adapters, name=name)
