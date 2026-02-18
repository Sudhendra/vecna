"""Unit tests for the Autonomous Thoughtfulness Engine."""

from datetime import datetime, timedelta

from vecna.orchestrator.thoughtfulness import (
    ProactiveMessage,
    ThoughtfulnessEngine,
)
from vecna.orchestrator.heartbeat import (
    HeartbeatRunner,
    _default_actions,
)
from vecna.core.hive_state import HiveState
from vecna.core.types import Fact


class TestProactiveMessage:
    """Tests for ProactiveMessage dataclass."""

    def test_proactive_message_creation(self):
        """ProactiveMessage creates with all fields and correct values."""
        before = datetime.now()
        msg = ProactiveMessage(
            content="You might find this useful",
            trigger="follow_up",
            relevance_score=0.8,
        )
        after = datetime.now()
        assert msg.content == "You might find this useful"
        assert msg.trigger == "follow_up"
        assert msg.relevance_score == 0.8
        # Amendment 9: Assert created_at is recent, not just existence
        assert before <= msg.created_at <= after
        assert msg.expires_at is None

    def test_proactive_message_to_dict(self):
        """ProactiveMessage serializes correctly with expected keys and values."""
        msg = ProactiveMessage(
            content="Insight content",
            trigger="dream",
            relevance_score=0.6,
        )
        d = msg.to_dict()
        assert d["content"] == "Insight content"
        assert d["trigger"] == "dream"
        assert d["relevance_score"] == 0.6
        assert "created_at" in d
        # Amendment 9: Verify created_at is ISO format string
        datetime.fromisoformat(d["created_at"])  # Raises ValueError if invalid

    def test_proactive_message_to_dict_with_expiry(self):
        """ProactiveMessage serializes expires_at when set."""
        expiry = datetime(2026, 3, 1, 12, 0, 0)
        msg = ProactiveMessage(
            content="Expiring",
            trigger="follow_up",
            relevance_score=0.5,
            expires_at=expiry,
        )
        d = msg.to_dict()
        assert d["expires_at"] == expiry.isoformat()

    def test_proactive_message_to_dict_without_expiry(self):
        """ProactiveMessage serializes expires_at as None when not set."""
        msg = ProactiveMessage(
            content="Timeless",
            trigger="insight",
            relevance_score=0.7,
        )
        d = msg.to_dict()
        assert d["expires_at"] is None

    def test_proactive_message_is_expired(self):
        """is_expired returns True when past expires_at."""
        msg = ProactiveMessage(
            content="Old message",
            trigger="insight",
            relevance_score=0.5,
            expires_at=datetime.now() - timedelta(hours=1),
        )
        assert msg.is_expired() is True

    def test_proactive_message_not_expired(self):
        """is_expired returns False when before expires_at."""
        msg = ProactiveMessage(
            content="Fresh message",
            trigger="anticipation",
            relevance_score=0.9,
            expires_at=datetime.now() + timedelta(hours=24),
        )
        assert msg.is_expired() is False

    def test_proactive_message_no_expiry(self):
        """is_expired returns False when expires_at is None."""
        msg = ProactiveMessage(
            content="Timeless",
            trigger="follow_up",
            relevance_score=0.7,
        )
        assert msg.is_expired() is False


class TestThoughtfulnessEngine:
    """Tests for ThoughtfulnessEngine core functionality."""

    def test_engine_initialization(self):
        """ThoughtfulnessEngine initializes with empty queues and zero count."""
        engine = ThoughtfulnessEngine()
        assert engine.get_pending_messages() == []
        assert engine.daily_message_count == 0
        assert engine.max_daily_messages == 3

    def test_engine_custom_config(self):
        """ThoughtfulnessEngine accepts custom configuration."""
        engine = ThoughtfulnessEngine(
            max_daily_messages=5,
            default_expiry_hours=72,
            min_relevance=0.5,
        )
        assert engine.max_daily_messages == 5
        assert engine.default_expiry_hours == 72
        assert engine.min_relevance == 0.5

    def test_generate_follow_ups_from_recent_facts(self):
        """generate_follow_ups creates follow_up messages from recent state facts."""
        engine = ThoughtfulnessEngine()
        state = HiveState()
        state.add_fact(
            Fact(
                content="User is learning Rust programming",
                confidence=0.9,
                source_model="conversation",
            )
        )
        state.add_fact(
            Fact(
                content="User has a project deadline on Friday",
                confidence=0.85,
                source_model="conversation",
            )
        )
        messages = engine.generate_follow_ups(state)
        # Amendment 9: Assert specific values, not just isinstance
        assert len(messages) == 2
        for msg in messages:
            assert msg.trigger == "follow_up"
            assert msg.relevance_score > 0
            assert msg.expires_at is not None

    def test_generate_follow_ups_respects_rate_limit(self):
        """generate_follow_ups stops when daily limit is reached."""
        engine = ThoughtfulnessEngine(max_daily_messages=1)
        state = HiveState()
        state.add_fact(
            Fact(
                content="Fact one",
                confidence=0.9,
                source_model="test",
            )
        )
        state.add_fact(
            Fact(
                content="Fact two about completely different topic",
                confidence=0.8,
                source_model="test",
            )
        )
        messages = engine.generate_follow_ups(state)
        # Only 1 due to rate limit
        assert len(messages) == 1
        assert engine.daily_message_count == 1

    def test_generate_anticipations_from_patterns(self):
        """generate_anticipations creates anticipation messages from patterns."""
        engine = ThoughtfulnessEngine()
        patterns = [
            {
                "type": "recurring",
                "description": "Weekly standup preparation",
                "day_of_week": 0,
            },
        ]
        messages = engine.generate_anticipations(patterns)
        assert len(messages) == 1
        assert messages[0].trigger == "anticipation"
        assert "Weekly standup preparation" in messages[0].content
        assert messages[0].relevance_score == 0.7

    def test_generate_anticipations_empty_patterns(self):
        """generate_anticipations returns empty list for no patterns."""
        engine = ThoughtfulnessEngine()
        messages = engine.generate_anticipations([])
        assert messages == []

    def test_generate_dream_insights(self):
        """generate_dream_insights wraps dream results as proactive messages."""
        engine = ThoughtfulnessEngine()
        insights = [
            "Pattern detected: user frequently asks about async programming",
            "Contradiction resolved: Python GIL affects threads but not processes",
        ]
        messages = engine.generate_dream_insights(insights)
        assert len(messages) == 2
        assert messages[0].content == insights[0]
        assert messages[1].content == insights[1]
        for msg in messages:
            assert msg.trigger == "dream"
            assert msg.relevance_score == 0.6
            assert msg.expires_at is not None

    def test_generate_dream_insights_empty(self):
        """generate_dream_insights returns empty list for no insights."""
        engine = ThoughtfulnessEngine()
        messages = engine.generate_dream_insights([])
        assert messages == []

    def test_daily_rate_limit(self):
        """Engine enforces max_daily_messages via enqueue_message."""
        engine = ThoughtfulnessEngine(max_daily_messages=3)
        for i in range(5):
            engine.enqueue_message(
                ProactiveMessage(
                    content=f"Message {i}",
                    trigger="insight",
                    relevance_score=0.7,
                )
            )
        # Amendment 11: Using public enqueue_message()
        pending = engine.get_pending_messages()
        assert len(pending) <= 3

    def test_get_pending_messages_excludes_expired(self):
        """get_pending_messages filters out expired messages."""
        engine = ThoughtfulnessEngine()
        engine.enqueue_message(
            ProactiveMessage(
                content="Expired",
                trigger="follow_up",
                relevance_score=0.5,
                expires_at=datetime.now() - timedelta(hours=1),
            )
        )
        engine.enqueue_message(
            ProactiveMessage(
                content="Valid",
                trigger="follow_up",
                relevance_score=0.8,
                expires_at=datetime.now() + timedelta(hours=24),
            )
        )
        pending = engine.get_pending_messages()
        assert len(pending) == 1
        assert pending[0].content == "Valid"

    def test_get_pending_messages_sorted_by_relevance(self):
        """Pending messages are sorted by relevance (highest first)."""
        engine = ThoughtfulnessEngine()
        engine.enqueue_message(
            ProactiveMessage(
                content="Low relevance",
                trigger="insight",
                relevance_score=0.3,
            )
        )
        engine.enqueue_message(
            ProactiveMessage(
                content="High relevance",
                trigger="follow_up",
                relevance_score=0.95,
            )
        )
        engine.enqueue_message(
            ProactiveMessage(
                content="Medium relevance",
                trigger="dream",
                relevance_score=0.6,
            )
        )
        pending = engine.get_pending_messages()
        assert pending[0].content == "High relevance"
        assert pending[0].relevance_score == 0.95
        assert pending[1].content == "Medium relevance"
        assert pending[2].content == "Low relevance"

    def test_clear_delivered_messages(self):
        """clear_delivered removes all messages from the queue."""
        engine = ThoughtfulnessEngine()
        engine.enqueue_message(
            ProactiveMessage(
                content="Will be cleared",
                trigger="insight",
                relevance_score=0.7,
            )
        )
        assert len(engine.get_pending_messages()) == 1
        engine.clear_delivered()
        assert engine.get_pending_messages() == []

    def test_reset_daily_count(self):
        """reset_daily_count resets the daily message counter to zero."""
        engine = ThoughtfulnessEngine()
        engine.daily_message_count = 3
        engine.reset_daily_count()
        assert engine.daily_message_count == 0

    def test_engine_to_dict(self):
        """ThoughtfulnessEngine state serializes with expected structure."""
        engine = ThoughtfulnessEngine()
        engine.enqueue_message(
            ProactiveMessage(
                content="Serialized",
                trigger="insight",
                relevance_score=0.7,
            )
        )
        d = engine.to_dict()
        assert d["daily_message_count"] == 1
        assert d["max_daily_messages"] == 3
        assert len(d["pending_messages"]) == 1
        assert d["pending_messages"][0]["content"] == "Serialized"
        assert d["pending_messages"][0]["trigger"] == "insight"

    # ============================================================
    # Error / Edge-case tests (Amendment 10: at least 2)
    # ============================================================

    def test_generate_follow_ups_empty_state(self):
        """generate_follow_ups returns empty list when state has no facts."""
        engine = ThoughtfulnessEngine()
        state = HiveState()
        messages = engine.generate_follow_ups(state)
        assert messages == []

    def test_generate_dream_insights_respects_rate_limit(self):
        """generate_dream_insights stops at daily limit."""
        engine = ThoughtfulnessEngine(max_daily_messages=1)
        insights = [
            "Insight one",
            "Insight two",
            "Insight three",
        ]
        messages = engine.generate_dream_insights(insights)
        assert len(messages) == 1
        assert messages[0].content == "Insight one"
        assert engine.daily_message_count == 1

    def test_generate_anticipations_respects_rate_limit(self):
        """generate_anticipations stops at daily limit."""
        engine = ThoughtfulnessEngine(max_daily_messages=1)
        patterns = [
            {"description": "Pattern A"},
            {"description": "Pattern B"},
        ]
        messages = engine.generate_anticipations(patterns)
        assert len(messages) == 1
        assert engine.daily_message_count == 1

    def test_enqueue_message_increments_daily_count(self):
        """enqueue_message increments daily_message_count each time."""
        engine = ThoughtfulnessEngine()
        assert engine.daily_message_count == 0
        engine.enqueue_message(
            ProactiveMessage(
                content="First",
                trigger="insight",
                relevance_score=0.5,
            )
        )
        assert engine.daily_message_count == 1
        engine.enqueue_message(
            ProactiveMessage(
                content="Second",
                trigger="insight",
                relevance_score=0.5,
            )
        )
        assert engine.daily_message_count == 2

    def test_proactive_message_default_values(self):
        """ProactiveMessage has correct default values."""
        msg = ProactiveMessage()
        assert msg.content == ""
        assert msg.trigger == "insight"
        assert msg.relevance_score == 0.5
        assert msg.expires_at is None

    def test_relevance_score_clamped_in_follow_ups(self):
        """generate_follow_ups clamps relevance_score to max 1.0."""
        engine = ThoughtfulnessEngine()
        state = HiveState()
        # A fact with confidence > 1.0 shouldn't produce relevance > 1.0
        state.add_fact(
            Fact(
                content="Extremely high confidence fact for testing",
                confidence=1.5,
                source_model="test",
            )
        )
        messages = engine.generate_follow_ups(state)
        for msg in messages:
            assert msg.relevance_score <= 1.0

    def test_pattern_missing_description_uses_default(self):
        """generate_anticipations handles patterns without description key."""
        engine = ThoughtfulnessEngine()
        patterns = [{"type": "recurring"}]  # No description key
        messages = engine.generate_anticipations(patterns)
        assert len(messages) == 1
        assert "Detected pattern" in messages[0].content

    def test_clear_delivered_is_idempotent(self):
        """clear_delivered on empty queue does not error."""
        engine = ThoughtfulnessEngine()
        engine.clear_delivered()  # Should not raise
        assert engine.get_pending_messages() == []

    def test_multiple_generate_cycles_accumulate_messages(self):
        """Messages from multiple generate calls accumulate in pending."""
        engine = ThoughtfulnessEngine(max_daily_messages=10)
        state = HiveState()
        state.add_fact(
            Fact(
                content="A fact about Python programming",
                confidence=0.9,
                source_model="test",
            )
        )
        engine.generate_follow_ups(state)
        engine.generate_dream_insights(["An insight about code patterns"])
        pending = engine.get_pending_messages()
        assert len(pending) == 2
        triggers = {msg.trigger for msg in pending}
        assert triggers == {"follow_up", "dream"}


class TestHeartbeatThoughtfulnessIntegration:
    """Tests for thoughtfulness integration in HeartbeatRunner."""

    def test_default_actions_include_thoughtfulness(self):
        """Default heartbeat actions include a thoughtfulness action."""
        actions = _default_actions()
        action_names = [a.name for a in actions]
        assert "thoughtfulness" in action_names
        thoughtfulness_action = next(a for a in actions if a.name == "thoughtfulness")
        assert thoughtfulness_action.interval_seconds == 1800
        assert thoughtfulness_action.description == "Generate proactive follow-ups and insights"

    def test_heartbeat_runner_accepts_thoughtfulness_engine(self):
        """HeartbeatRunner can be constructed with a ThoughtfulnessEngine."""

        class _FakeLoop:
            pass

        class _FakeQueue:
            pass

        engine = ThoughtfulnessEngine()
        runner = HeartbeatRunner(
            autonomy_loop=_FakeLoop(),
            goal_queue=_FakeQueue(),
            thoughtfulness=engine,
        )
        assert runner.thoughtfulness is engine

    def test_heartbeat_runner_default_no_thoughtfulness(self):
        """HeartbeatRunner defaults to no thoughtfulness engine."""

        class _FakeLoop:
            pass

        class _FakeQueue:
            pass

        runner = HeartbeatRunner(
            autonomy_loop=_FakeLoop(),
            goal_queue=_FakeQueue(),
        )
        assert runner.thoughtfulness is None

    async def test_run_thoughtfulness_generates_follow_ups(self):
        """run_thoughtfulness generates follow-ups from autonomy_loop.state."""

        class _FakeLoop:
            def __init__(self) -> None:
                self.state = HiveState()

        fake_loop = _FakeLoop()
        fake_loop.state.add_fact(
            Fact(
                content="User asked about database optimization",
                confidence=0.9,
                source_model="test",
            )
        )
        engine = ThoughtfulnessEngine(max_daily_messages=5)
        runner = HeartbeatRunner(
            autonomy_loop=fake_loop,
            goal_queue=None,
            thoughtfulness=engine,
        )
        await runner.run_thoughtfulness()
        pending = engine.get_pending_messages()
        assert len(pending) == 1
        assert pending[0].trigger == "follow_up"

    async def test_run_thoughtfulness_skips_when_no_engine(self):
        """run_thoughtfulness does nothing when engine is None."""

        class _FakeLoop:
            def __init__(self) -> None:
                self.state = HiveState()

        runner = HeartbeatRunner(
            autonomy_loop=_FakeLoop(),
            goal_queue=None,
            thoughtfulness=None,
        )
        # Should not raise
        await runner.run_thoughtfulness()

    async def test_run_thoughtfulness_skips_when_no_state(self):
        """run_thoughtfulness skips when autonomy_loop has no state attribute."""

        class _StatelessLoop:
            pass

        engine = ThoughtfulnessEngine()
        runner = HeartbeatRunner(
            autonomy_loop=_StatelessLoop(),
            goal_queue=None,
            thoughtfulness=engine,
        )
        # Should not raise, engine stays empty
        await runner.run_thoughtfulness()
        assert engine.get_pending_messages() == []
