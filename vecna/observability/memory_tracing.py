"""In-memory tracing for memory retrieval decisions."""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class MemoryAccessEvent:
    item_id: str
    item_type: str
    reason: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    query: Optional[str] = None
    score: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class MemoryAccessTracer:
    """Record why memory items were retrieved."""

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self._events: List[MemoryAccessEvent] = []
        self._logger = logger or logging.getLogger("vecna.observability.memory_tracing")

    def record(
        self,
        item_id: str,
        item_type: str,
        reason: str,
        query: Optional[str] = None,
        score: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryAccessEvent:
        """Append and return a memory access event."""
        event = MemoryAccessEvent(
            item_id=item_id,
            item_type=item_type,
            reason=reason,
            query=query,
            score=score,
            metadata=metadata or {},
        )
        self._events.append(event)
        self._logger.debug(
            "memory_access item_id=%s item_type=%s reason=%s",
            item_id,
            item_type,
            reason,
        )
        return event

    def events(self) -> List[MemoryAccessEvent]:
        """Return a snapshot of recorded events."""
        return list(self._events)

    def clear(self) -> None:
        """Clear all recorded memory access events."""
        self._events.clear()
