"""Tests for the BackgroundObserver — passive integration event intake."""

from datetime import datetime
from unittest.mock import MagicMock

from vecna.integrations.observer import (
    BackgroundObserver,
    ObserverConfig,
    IntegrationEvent,
    ObserverResult,
)


class TestIntegrationEvent:
    """IntegrationEvent is the raw inbound event from any integration."""

    def test_create_event(self):
        event = IntegrationEvent(
            source="github",
            event_type="pr_opened",
            payload={"pr_number": 42, "title": "Add feature X"},
        )
        assert event.source == "github"
        assert event.event_type == "pr_opened"
        assert event.payload["pr_number"] == 42

    def test_event_has_timestamp(self):
        before = datetime.now()
        event = IntegrationEvent(source="slack", event_type="message")
        after = datetime.now()
        # Amendment 9: assert timestamp is recent, not just isinstance
        assert before <= event.timestamp <= after

    def test_event_to_dict(self):
        """to_dict() from SerializableMixin (Amendment 7) serializes all fields."""
        event = IntegrationEvent(
            source="calendar",
            event_type="event_created",
            payload={"title": "Team standup"},
        )
        d = event.to_dict()
        assert d["source"] == "calendar"
        assert d["event_type"] == "event_created"
        assert d["payload"]["title"] == "Team standup"
        # timestamp is datetime -> should be serialized to ISO string
        assert isinstance(d["timestamp"], str)

    def test_event_defaults(self):
        """Default IntegrationEvent has empty source, type, and payload."""
        event = IntegrationEvent()
        assert event.source == ""
        assert event.event_type == ""
        assert event.payload == {}

    def test_event_with_rich_payload(self):
        """Events can carry arbitrarily complex payloads."""
        payload = {
            "commits": [{"sha": "abc123"}, {"sha": "def456"}],
            "branch": "main",
            "stats": {"additions": 100, "deletions": 50},
        }
        event = IntegrationEvent(source="github", event_type="push", payload=payload)
        assert len(event.payload["commits"]) == 2
        assert event.payload["stats"]["additions"] == 100


class TestEventClassification:
    """Events are classified into categories."""

    def test_classify_github_as_code_activity(self):
        observer = BackgroundObserver()
        event = IntegrationEvent(
            source="github",
            event_type="pr_opened",
            payload={"title": "Fix bug"},
        )
        classification = observer.classify(event)
        assert classification.category == "code_activity"

    def test_classify_slack_as_communication(self):
        observer = BackgroundObserver()
        event = IntegrationEvent(
            source="slack",
            event_type="message_received",
            payload={"text": "Hey team"},
        )
        classification = observer.classify(event)
        assert classification.category == "communication"

    def test_classify_calendar_as_calendar(self):
        observer = BackgroundObserver()
        event = IntegrationEvent(
            source="google_calendar",
            event_type="event_reminder",
            payload={"title": "Meeting"},
        )
        classification = observer.classify(event)
        assert classification.category == "calendar"

    def test_classify_unknown_as_system(self):
        observer = BackgroundObserver()
        event = IntegrationEvent(
            source="unknown_source",
            event_type="heartbeat",
            payload={},
        )
        classification = observer.classify(event)
        assert classification.category == "system"

    def test_classification_has_relevance_score(self):
        observer = BackgroundObserver()
        event = IntegrationEvent(
            source="github",
            event_type="pr_review_requested",
            payload={"title": "Important PR", "requested_reviewer": "user"},
        )
        classification = observer.classify(event)
        assert 0.0 <= classification.relevance <= 1.0

    def test_high_relevance_events_score_above_threshold(self):
        """pr_merged, pr_review_requested, push, etc. should score >= 0.7."""
        observer = BackgroundObserver()
        for event_type in ("pr_merged", "pr_review_requested", "push", "mention"):
            event = IntegrationEvent(source="github", event_type=event_type, payload={})
            classification = observer.classify(event)
            assert classification.relevance >= 0.7, (
                f"{event_type} should be high relevance, got {classification.relevance}"
            )

    def test_user_targeting_boosts_relevance(self):
        """Payload with requested_reviewer/assignee boosts relevance."""
        observer = BackgroundObserver()
        event = IntegrationEvent(
            source="github",
            event_type="pr_opened",
            payload={"requested_reviewer": "user"},
        )
        classification = observer.classify(event)
        # Base code_activity is 0.4, + 0.2 boost = 0.6
        assert classification.relevance >= 0.5

    def test_notable_events_flagged(self):
        """pr_review_requested, issue_assigned, etc. are notable."""
        observer = BackgroundObserver()
        event = IntegrationEvent(
            source="github",
            event_type="pr_review_requested",
            payload={"title": "Fix"},
        )
        classification = observer.classify(event)
        assert classification.is_notable is True

    def test_non_notable_events_not_flagged(self):
        """Regular push events are not notable."""
        observer = BackgroundObserver()
        event = IntegrationEvent(source="github", event_type="push", payload={})
        classification = observer.classify(event)
        assert classification.is_notable is False

    def test_classify_gitlab_as_code_activity(self):
        """gitlab source maps to code_activity (same as github)."""
        observer = BackgroundObserver()
        event = IntegrationEvent(source="gitlab", event_type="merge_request", payload={})
        classification = observer.classify(event)
        assert classification.category == "code_activity"

    def test_classify_email_as_communication(self):
        """email/gmail sources map to communication."""
        observer = BackgroundObserver()
        event = IntegrationEvent(source="email", event_type="received", payload={})
        classification = observer.classify(event)
        assert classification.category == "communication"


class TestObserverConfig:
    def test_default_config(self):
        config = ObserverConfig()
        assert config.relevance_threshold == 0.3
        assert config.max_events_per_hour == 100
        assert config.privacy_tier == "local_only"

    def test_custom_config(self):
        config = ObserverConfig(
            relevance_threshold=0.5,
            max_events_per_hour=50,
        )
        assert config.relevance_threshold == 0.5
        assert config.max_events_per_hour == 50

    def test_config_to_dict(self):
        """ObserverConfig serializes via SerializableMixin (Amendment 7)."""
        config = ObserverConfig(privacy_tier="cloud_ok")
        d = config.to_dict()
        assert d["privacy_tier"] == "cloud_ok"
        assert d["relevance_threshold"] == 0.3


class TestBackgroundObserverIngest:
    """BackgroundObserver.ingest() processes events into substrate actions."""

    def test_ingest_relevant_event_creates_fact(self):
        mock_store = MagicMock()
        mock_store.add_item.return_value = "item-001"

        observer = BackgroundObserver(pg_store=mock_store)
        event = IntegrationEvent(
            source="github",
            event_type="pr_merged",
            payload={"pr_number": 42, "title": "Ship feature X", "repo": "vecna"},
        )
        result = observer.ingest(event)
        assert result.facts_created >= 1
        assert mock_store.add_item.called

    def test_ingest_notable_event_creates_goal(self):
        mock_store = MagicMock()
        mock_store.add_item.return_value = "item-001"
        mock_queue = MagicMock()

        observer = BackgroundObserver(pg_store=mock_store, goal_queue=mock_queue)
        event = IntegrationEvent(
            source="github",
            event_type="pr_review_requested",
            payload={
                "pr_number": 99,
                "title": "Critical fix",
                "requested_reviewer": "user",
            },
        )
        result = observer.ingest(event)
        assert result.goals_created >= 1

    def test_ingest_irrelevant_event_skipped(self):
        mock_store = MagicMock()
        observer = BackgroundObserver(
            pg_store=mock_store,
            config=ObserverConfig(relevance_threshold=0.9),
        )
        event = IntegrationEvent(
            source="system",
            event_type="healthcheck",
            payload={},
        )
        result = observer.ingest(event)
        assert result.facts_created == 0
        assert result.goals_created == 0
        assert result.skipped

    def test_ingest_records_memory_event(self):
        mock_store = MagicMock()
        mock_store.add_item.return_value = "item-001"
        mock_store.add_event.return_value = "event-001"

        observer = BackgroundObserver(pg_store=mock_store)
        event = IntegrationEvent(
            source="github",
            event_type="push",
            payload={"branch": "main", "commits": 3},
        )
        observer.ingest(event)
        assert mock_store.add_event.called

    def test_ingest_without_store_skips_fact_creation(self):
        """If no pg_store is provided, no facts or events are created."""
        observer = BackgroundObserver()
        event = IntegrationEvent(
            source="github",
            event_type="pr_merged",
            payload={"title": "Ship it"},
        )
        result = observer.ingest(event)
        assert result.facts_created == 0
        assert result.goals_created == 0
        # Should not crash — just no storage

    def test_ingest_without_goal_queue_skips_goal_creation(self):
        """Notable events don't create goals if no goal_queue provided."""
        mock_store = MagicMock()
        mock_store.add_item.return_value = "item-001"
        observer = BackgroundObserver(pg_store=mock_store)
        event = IntegrationEvent(
            source="github",
            event_type="pr_review_requested",
            payload={"title": "Review me"},
        )
        result = observer.ingest(event)
        assert result.goals_created == 0
        assert result.facts_created >= 1

    def test_ingest_fact_content_contains_source_and_type(self):
        """Created MemoryItem should have human-readable content."""
        mock_store = MagicMock()
        mock_store.add_item.return_value = "item-001"
        observer = BackgroundObserver(pg_store=mock_store)
        event = IntegrationEvent(
            source="github",
            event_type="pr_merged",
            payload={"title": "Ship feature X"},
        )
        observer.ingest(event)
        # Inspect the MemoryItem passed to add_item
        call_args = mock_store.add_item.call_args
        item = call_args[0][0]
        assert "github" in item.content
        assert "pr_merged" in item.content
        assert "Ship feature X" in item.content

    def test_ingest_goal_text_for_pr(self):
        """Goal text for PR events includes PR number."""
        mock_store = MagicMock()
        mock_store.add_item.return_value = "item-001"
        mock_queue = MagicMock()
        observer = BackgroundObserver(pg_store=mock_store, goal_queue=mock_queue)
        event = IntegrationEvent(
            source="github",
            event_type="pr_review_requested",
            payload={"pr_number": 42, "title": "Critical fix"},
        )
        observer.ingest(event)
        call_args = mock_queue.push.call_args
        goal_item = call_args[0][0]
        assert "PR #42" in goal_item.goal
        assert "Critical fix" in goal_item.goal


class TestObserverRateLimiting:
    def test_rate_limit_rejects_excess_events(self):
        mock_store = MagicMock()
        mock_store.add_item.return_value = "item-001"

        observer = BackgroundObserver(
            pg_store=mock_store,
            config=ObserverConfig(max_events_per_hour=3),
        )

        results = []
        for i in range(5):
            event = IntegrationEvent(
                source="github",
                event_type="push",
                payload={"commit": i},
            )
            result = observer.ingest(event)
            results.append(result)

        # First 3 should succeed, last 2 should be rate limited
        assert not results[0].rate_limited
        assert not results[1].rate_limited
        assert not results[2].rate_limited
        assert results[3].rate_limited
        assert results[4].rate_limited

    def test_rate_limit_counter_tracks_events(self):
        observer = BackgroundObserver()
        assert observer.events_this_hour == 0

    def test_rate_limited_events_create_no_facts(self):
        """Rate-limited events should not create any facts or goals."""
        mock_store = MagicMock()
        mock_store.add_item.return_value = "item-001"

        observer = BackgroundObserver(
            pg_store=mock_store,
            config=ObserverConfig(max_events_per_hour=1),
        )
        # First event succeeds
        event1 = IntegrationEvent(source="github", event_type="push", payload={"commit": 1})
        observer.ingest(event1)

        # Second event is rate-limited
        event2 = IntegrationEvent(
            source="github", event_type="pr_merged", payload={"title": "Big PR"}
        )
        result = observer.ingest(event2)
        assert result.rate_limited
        assert result.facts_created == 0
        assert result.goals_created == 0


class TestObserverResult:
    def test_result_defaults(self):
        result = ObserverResult()
        assert result.facts_created == 0
        assert result.goals_created == 0
        assert not result.skipped
        assert not result.rate_limited

    def test_result_to_dict(self):
        result = ObserverResult(facts_created=2, goals_created=1)
        d = result.to_dict()
        assert d["facts_created"] == 2
        assert d["goals_created"] == 1
        assert d["skipped"] is False
        assert d["rate_limited"] is False


class TestObserverErrorPaths:
    """Amendment 10: Error/edge-case tests."""

    def test_ingest_handles_store_add_item_failure(self):
        """If pg_store.add_item raises, ingest should not crash."""
        mock_store = MagicMock()
        mock_store.add_item.side_effect = RuntimeError("DB connection lost")
        mock_store.add_event.return_value = "event-001"

        observer = BackgroundObserver(pg_store=mock_store)
        event = IntegrationEvent(
            source="github",
            event_type="pr_merged",
            payload={"title": "Ship it"},
        )
        result = observer.ingest(event)
        # Should gracefully handle the error, not crash
        assert result.facts_created == 0

    def test_ingest_handles_store_add_event_failure(self):
        """If pg_store.add_event raises, ingest should not crash."""
        mock_store = MagicMock()
        mock_store.add_event.side_effect = RuntimeError("Redis down")
        mock_store.add_item.return_value = "item-001"

        observer = BackgroundObserver(pg_store=mock_store)
        event = IntegrationEvent(
            source="github",
            event_type="push",
            payload={"branch": "main"},
        )
        # Should not raise
        result = observer.ingest(event)
        # Event recording failed, but fact creation may still succeed
        assert result.facts_created >= 0

    def test_ingest_handles_goal_queue_push_failure(self):
        """If goal_queue.push raises, ingest should not crash."""
        mock_store = MagicMock()
        mock_store.add_item.return_value = "item-001"
        mock_queue = MagicMock()
        mock_queue.push.side_effect = RuntimeError("Queue full")

        observer = BackgroundObserver(pg_store=mock_store, goal_queue=mock_queue)
        event = IntegrationEvent(
            source="github",
            event_type="pr_review_requested",
            payload={"title": "Critical"},
        )
        result = observer.ingest(event)
        # Fact should still be created, goal creation failed
        assert result.facts_created >= 1
        assert result.goals_created == 0

    def test_classify_with_none_payload(self):
        """Classify should handle None payload gracefully."""
        observer = BackgroundObserver()
        event = IntegrationEvent(
            source="github",
            event_type="push",
            payload=None,
        )
        classification = observer.classify(event)
        assert classification.category == "code_activity"
        assert classification.relevance >= 0.0

    def test_ingest_with_empty_event(self):
        """A completely empty event should be classified as system/low-relevance."""
        observer = BackgroundObserver(
            config=ObserverConfig(relevance_threshold=0.3),
        )
        event = IntegrationEvent()
        result = observer.ingest(event)
        # Empty event has source="" -> "system" category, base relevance 0.1
        assert result.skipped
        assert result.facts_created == 0

    def test_store_returns_none_on_add_item(self):
        """If add_item returns None (failure), facts_created remains 0."""
        mock_store = MagicMock()
        mock_store.add_item.return_value = None

        observer = BackgroundObserver(pg_store=mock_store)
        event = IntegrationEvent(
            source="github",
            event_type="pr_merged",
            payload={"title": "Ship it"},
        )
        result = observer.ingest(event)
        assert result.facts_created == 0
