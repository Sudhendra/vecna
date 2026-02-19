"""
Background Observer — passive integration event intake.

Ingests events from integrations (webhooks, polling) and converts them
to substrate-compatible observations. Events are classified, filtered
for relevance, rate-limited, and then converted to Facts or Goals.

Event flow:
    Integration → BackgroundObserver.ingest() → classify + filter
        → If relevant: create MemoryItem (source_type="observation")
        → If notable: create GoalItem (e.g., "Review PR #123")
        → If user-related: update HumanModel (future)
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from vecna.core.types import SerializableMixin

logger = logging.getLogger("vecna.integrations.observer")

if TYPE_CHECKING:
    from vecna.memory.pg_store import PgMemoryStore
    from vecna.orchestrator.pg_goal_queue import PgGoalQueue


# -- Source-to-category mapping --
_SOURCE_CATEGORIES: Dict[str, str] = {
    "github": "code_activity",
    "gitlab": "code_activity",
    "bitbucket": "code_activity",
    "slack": "communication",
    "discord": "communication",
    "imessage": "communication",
    "whatsapp": "communication",
    "email": "communication",
    "gmail": "communication",
    "google_calendar": "calendar",
    "calendar": "calendar",
    "outlook_calendar": "calendar",
}

# -- Event types that should generate goals (actionable) --
_NOTABLE_EVENT_TYPES = frozenset(
    {
        "pr_review_requested",
        "issue_assigned",
        "pr_changes_requested",
        "mention",
        "direct_message",
        "meeting_starting",
        "deadline_approaching",
        "task_assigned",
    }
)

# -- Event types with higher base relevance --
_HIGH_RELEVANCE_EVENTS = frozenset(
    {
        "pr_merged",
        "pr_review_requested",
        "pr_opened",
        "issue_assigned",
        "push",
        "mention",
        "direct_message",
        "event_reminder",
        "meeting_starting",
        "deadline_approaching",
    }
)


@dataclass
class IntegrationEvent(SerializableMixin):
    """A raw event from any integration source."""

    source: str = ""
    event_type: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class EventClassification:
    """Classification result for an integration event."""

    category: str = "system"  # code_activity, communication, calendar, system
    relevance: float = 0.0  # 0.0-1.0 relevance score
    is_notable: bool = False  # Should generate a goal?
    is_user_related: bool = False  # Should update HumanModel?


@dataclass
class ObserverConfig(SerializableMixin):
    """Configuration for the BackgroundObserver."""

    relevance_threshold: float = 0.3
    max_events_per_hour: int = 100
    privacy_tier: str = "local_only"


@dataclass
class ObserverResult(SerializableMixin):
    """Result of processing a single integration event."""

    facts_created: int = 0
    goals_created: int = 0
    skipped: bool = False
    rate_limited: bool = False
    classification: Optional[EventClassification] = None


class BackgroundObserver:
    """
    Passive observer that ingests integration events into the substrate.

    Classifies events by type, filters for relevance, enforces rate limits,
    and creates Facts/Goals as appropriate.
    """

    def __init__(
        self,
        pg_store: Optional["PgMemoryStore"] = None,
        goal_queue: Optional["PgGoalQueue"] = None,
        config: Optional[ObserverConfig] = None,
    ):
        self.pg_store = pg_store
        self.goal_queue = goal_queue
        self.config = config or ObserverConfig()

        # Rate limiting state
        self._event_timestamps: List[float] = []
        self._hour_window: float = 3600.0  # seconds

    @property
    def events_this_hour(self) -> int:
        """Count events within the current hour window."""
        now = time.monotonic()
        self._event_timestamps = [t for t in self._event_timestamps if now - t < self._hour_window]
        return len(self._event_timestamps)

    def _is_rate_limited(self) -> bool:
        """Check if we've exceeded the events-per-hour limit."""
        return self.events_this_hour >= self.config.max_events_per_hour

    def _record_event_timestamp(self) -> None:
        """Record a new event for rate limiting."""
        self._event_timestamps.append(time.monotonic())

    def classify(self, event: IntegrationEvent) -> EventClassification:
        """Classify an integration event by category and relevance."""
        source_lower = event.source.lower()
        event_type_lower = event.event_type.lower()

        # Determine category from source
        category = _SOURCE_CATEGORIES.get(source_lower, "system")

        # Calculate relevance score
        relevance = 0.1  # base relevance
        if event_type_lower in _HIGH_RELEVANCE_EVENTS:
            relevance = 0.7
        elif category in ("code_activity", "communication"):
            relevance = 0.4
        elif category == "calendar":
            relevance = 0.5

        # Boost if payload contains user-targeting fields
        payload = event.payload or {}
        if any(
            key in payload
            for key in (
                "requested_reviewer",
                "assignee",
                "mentioned_user",
                "recipient",
            )
        ):
            relevance = min(1.0, relevance + 0.2)

        is_notable = event_type_lower in _NOTABLE_EVENT_TYPES
        is_user_related = any(
            key in payload for key in ("user", "author", "sender", "requested_reviewer")
        )

        return EventClassification(
            category=category,
            relevance=relevance,
            is_notable=is_notable,
            is_user_related=is_user_related,
        )

    def ingest(self, event: IntegrationEvent) -> ObserverResult:
        """
        Ingest a single integration event.

        Returns ObserverResult describing what actions were taken.
        """
        result = ObserverResult()

        # Rate limiting check
        if self._is_rate_limited():
            logger.warning(
                "Rate limited: %d events this hour (max %d)",
                self.events_this_hour,
                self.config.max_events_per_hour,
            )
            result.rate_limited = True
            return result

        self._record_event_timestamp()

        # Classify the event
        classification = self.classify(event)
        result.classification = classification

        # Check relevance threshold
        if classification.relevance < self.config.relevance_threshold:
            logger.debug(
                "Skipping low-relevance event: %s/%s (relevance=%.2f)",
                event.source,
                event.event_type,
                classification.relevance,
            )
            result.skipped = True
            return result

        # Record the raw event in memory store
        if self.pg_store:
            self._record_memory_event(event, classification)

        # Create a Fact (observation) for relevant events
        if self.pg_store:
            fact_created = self._create_observation_fact(event, classification)
            if fact_created:
                result.facts_created += 1

        # Create a Goal for notable events
        if classification.is_notable and self.goal_queue:
            goal_created = self._create_goal(event, classification)
            if goal_created:
                result.goals_created += 1

        logger.info(
            "Ingested %s/%s: category=%s, relevance=%.2f, facts=%d, goals=%d",
            event.source,
            event.event_type,
            classification.category,
            classification.relevance,
            result.facts_created,
            result.goals_created,
        )

        return result

    def _record_memory_event(
        self, event: IntegrationEvent, classification: EventClassification
    ) -> None:
        """Record the raw event as a MemoryEvent."""
        try:
            from vecna.memory.pg_store import MemoryEvent

            mem_event = MemoryEvent(
                event_type=f"integration_{classification.category}",
                payload={
                    "source": event.source,
                    "event_type": event.event_type,
                    "category": classification.category,
                    "relevance": classification.relevance,
                    **(event.payload or {}),
                },
            )
            self.pg_store.add_event(mem_event)  # type: ignore[union-attr]
        except (RuntimeError, ConnectionError, OSError, ValueError) as e:
            logger.error("Failed to record memory event: %s", e)

    def _create_observation_fact(
        self, event: IntegrationEvent, classification: EventClassification
    ) -> bool:
        """Create a MemoryItem (observation) from the event."""
        try:
            from vecna.memory.pg_store import MemoryItem

            # Build human-readable content from the event
            payload = event.payload or {}
            title = payload.get("title", payload.get("text", event.event_type))
            content = f"[{event.source}] {event.event_type}: {title}"

            item = MemoryItem(
                content=content,
                item_type="observation",
                confidence=classification.relevance,
                domain=classification.category,
                metadata={
                    "source": event.source,
                    "event_type": event.event_type,
                    "privacy_tier": self.config.privacy_tier,
                    "category": classification.category,
                    "raw_payload": event.payload,
                },
            )
            result = self.pg_store.add_item(item)  # type: ignore[union-attr]
            return result is not None
        except (RuntimeError, ConnectionError, OSError, ValueError) as e:
            logger.error("Failed to create observation fact: %s", e)
            return False

    def _create_goal(self, event: IntegrationEvent, classification: EventClassification) -> bool:
        """Create a GoalItem for notable events."""
        try:
            from vecna.orchestrator.pg_goal_queue import GoalItem

            payload = event.payload or {}
            title = payload.get("title", event.event_type)

            goal_text = f"[{event.source}] {event.event_type}: {title}"
            if "pr_number" in payload:
                goal_text = f"Review PR #{payload['pr_number']}: {title}"
            elif "issue_number" in payload:
                goal_text = f"Address issue #{payload['issue_number']}: {title}"

            goal_item = GoalItem(
                goal=goal_text,
                priority="high" if classification.relevance >= 0.7 else "medium",
                source="observer",
                metadata={
                    "integration_source": event.source,
                    "event_type": event.event_type,
                    "origin": "background_observer",
                },
            )
            self.goal_queue.push(goal_item)  # type: ignore[union-attr]
            return True
        except (RuntimeError, ConnectionError, OSError, ValueError) as e:
            logger.error("Failed to create goal: %s", e)
            return False
