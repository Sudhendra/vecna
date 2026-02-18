"""Autonomous Thoughtfulness Engine for proactive assistance.

The core differentiator — Vecna thinks about you when you're not there.
Generates follow-up messages, anticipatory assistance, and dream-based
insights that are queued for delivery at the next user interaction.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from vecna.core.hive_state import HiveState
from vecna.core.types import SerializableMixin

logger = logging.getLogger("vecna.orchestrator.thoughtfulness")

DEFAULT_MAX_DAILY = 3
DEFAULT_EXPIRY_HOURS = 48
DEFAULT_MIN_RELEVANCE = 0.3


@dataclass
class ProactiveMessage(SerializableMixin):
    """A message Vecna prepared proactively.

    Attributes:
        content: The message text.
        trigger: Origin type (follow_up, anticipation, insight, dream).
        relevance_score: How relevant to current context (0.0-1.0).
        created_at: When the message was created.
        expires_at: After this time the message won't be delivered.
    """

    content: str = ""
    trigger: str = "insight"
    relevance_score: float = 0.5
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None

    def is_expired(self) -> bool:
        """Check if this message has expired.

        Returns:
            True if expires_at is set and in the past.
        """
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary.

        Overrides SerializableMixin to handle expires_at None case explicitly.
        """
        result = super().to_dict()
        return result


class ThoughtfulnessEngine:
    """Generates proactive messages for the user.

    Runs as a heartbeat action to produce follow-ups based on
    recent conversation topics, anticipatory messages based on
    detected patterns, and packaged dream loop insights.

    Rate limited to max_daily_messages per day to avoid
    overwhelming the user.
    """

    def __init__(
        self,
        max_daily_messages: int = DEFAULT_MAX_DAILY,
        default_expiry_hours: int = DEFAULT_EXPIRY_HOURS,
        min_relevance: float = DEFAULT_MIN_RELEVANCE,
    ) -> None:
        self.max_daily_messages = max_daily_messages
        self.default_expiry_hours = default_expiry_hours
        self.min_relevance = min_relevance
        self.daily_message_count: int = 0
        self._pending: List[ProactiveMessage] = []

    def enqueue_message(self, message: ProactiveMessage) -> None:
        """Add a message to the pending queue.

        Increments the daily message count. Messages are stored
        regardless of daily limit; the limit is enforced by
        get_pending_messages() and by generate_* methods.

        Args:
            message: The proactive message to enqueue.
        """
        self._pending.append(message)
        self.daily_message_count += 1
        logger.debug(
            "Enqueued proactive message: trigger=%s relevance=%.2f",
            message.trigger,
            message.relevance_score,
        )

    def generate_follow_ups(self, state: HiveState) -> List[ProactiveMessage]:
        """Generate follow-up messages from recent state.

        Scans recent facts for topics that could benefit from
        additional context or research.

        Args:
            state: Current HiveState with accumulated facts.

        Returns:
            List of follow-up ProactiveMessages.
        """
        messages: List[ProactiveMessage] = []
        recent_facts = sorted(
            state.facts,
            key=lambda f: f.timestamp if hasattr(f, "timestamp") else datetime.min,
            reverse=True,
        )[:5]

        for fact in recent_facts:
            if self.daily_message_count >= self.max_daily_messages:
                break
            content = fact.content if hasattr(fact, "content") else str(fact)
            relevance = min(
                fact.confidence * 0.8 if hasattr(fact, "confidence") else 0.5,
                1.0,
            )
            msg = ProactiveMessage(
                content=f"Following up on: {content}",
                trigger="follow_up",
                relevance_score=relevance,
                expires_at=datetime.now() + timedelta(hours=self.default_expiry_hours),
            )
            messages.append(msg)
            self.enqueue_message(msg)

        return messages

    def generate_anticipations(self, patterns: List[Dict[str, Any]]) -> List[ProactiveMessage]:
        """Generate anticipatory messages from detected patterns.

        Args:
            patterns: List of pattern dicts with type and description.

        Returns:
            List of anticipation ProactiveMessages.
        """
        messages: List[ProactiveMessage] = []

        for pattern in patterns:
            if self.daily_message_count >= self.max_daily_messages:
                break
            description = pattern.get("description", "Detected pattern")
            msg = ProactiveMessage(
                content=f"Anticipation: {description}",
                trigger="anticipation",
                relevance_score=0.7,
                expires_at=datetime.now() + timedelta(hours=self.default_expiry_hours),
            )
            messages.append(msg)
            self.enqueue_message(msg)

        return messages

    def generate_dream_insights(self, insights: List[str]) -> List[ProactiveMessage]:
        """Package dream loop insights as proactive messages.

        Args:
            insights: List of insight strings from DreamLoop.

        Returns:
            List of dream ProactiveMessages.
        """
        messages: List[ProactiveMessage] = []

        for insight in insights:
            if self.daily_message_count >= self.max_daily_messages:
                break
            msg = ProactiveMessage(
                content=insight,
                trigger="dream",
                relevance_score=0.6,
                expires_at=datetime.now() + timedelta(hours=self.default_expiry_hours),
            )
            messages.append(msg)
            self.enqueue_message(msg)

        return messages

    def get_pending_messages(self) -> List[ProactiveMessage]:
        """Get all pending non-expired messages sorted by relevance.

        Filters expired messages and applies the daily rate limit.
        Returns at most max_daily_messages messages, sorted by
        relevance_score descending.

        Returns:
            Sorted list of pending ProactiveMessages.
        """
        valid = [m for m in self._pending if not m.is_expired()]
        valid.sort(key=lambda m: m.relevance_score, reverse=True)
        return valid[: self.max_daily_messages]

    def clear_delivered(self) -> None:
        """Clear all pending messages after delivery."""
        self._pending.clear()
        logger.debug("Cleared delivered proactive messages")

    def reset_daily_count(self) -> None:
        """Reset the daily message counter (call at midnight)."""
        self.daily_message_count = 0
        logger.debug("Daily message count reset")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize engine state."""
        return {
            "pending_messages": [m.to_dict() for m in self._pending],
            "daily_message_count": self.daily_message_count,
            "max_daily_messages": self.max_daily_messages,
        }
