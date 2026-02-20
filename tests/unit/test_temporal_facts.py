"""Tests for temporal fact awareness and SerializableMixin.

Tests:
- Fact temporal fields (valid_until, source_type)
- Fact expiry detection (is_expired)
- Fact staleness scoring (staleness_score)
- Fact effective confidence (effective_confidence)
- SerializableMixin (to_dict via mixin, generic datetime/enum handling)
- Serialization round-trip with temporal fields
- HiveState.add_fact expiry filtering
- Edge cases: boundary times, negative confidence, missing fields
"""

from datetime import datetime, timedelta

import pytest

from vecna.core.types import Fact, Belief, SerializableMixin


class TestTemporalFacts:
    """Tests for temporal fields on Fact dataclass."""

    def test_fact_has_valid_until_approximately_correct(self):
        """Fact with valid_until set to ~1 hour from now is not expired."""
        before = datetime.now() + timedelta(hours=1) - timedelta(seconds=1)
        fact = Fact(
            content="Bitcoin is at $95,000",
            confidence=0.9,
            valid_until=datetime.now() + timedelta(hours=1),
        )
        after = datetime.now() + timedelta(hours=1) + timedelta(seconds=1)

        # Amendment 9: assert specific time range, not just existence
        assert fact.valid_until >= before
        assert fact.valid_until <= after
        assert not fact.is_expired()

    def test_fact_expires_when_valid_until_is_past(self):
        """Fact with valid_until in the past is expired."""
        fact = Fact(
            content="Weather is sunny",
            confidence=0.8,
            valid_until=datetime.now() - timedelta(hours=1),
        )
        assert fact.is_expired()

    def test_fact_without_validity_never_expires(self):
        """Fact without valid_until (None) never expires."""
        fact = Fact(content="Python is a programming language", confidence=0.95)
        assert fact.valid_until is None
        assert not fact.is_expired()

    def test_fact_staleness_score_increases_with_age(self):
        """Older facts have higher staleness scores than newer ones."""
        old_fact = Fact(
            content="Something old",
            confidence=0.9,
            timestamp=datetime.now() - timedelta(days=30),
        )
        new_fact = Fact(
            content="Something new",
            confidence=0.9,
            timestamp=datetime.now(),
        )
        old_score = old_fact.staleness_score()
        new_score = new_fact.staleness_score()
        assert old_score > new_score
        # 30-day-old fact should be near 1.0 (log1p(720)/log1p(720) ≈ 1.0)
        assert old_score > 0.9
        # Brand new fact should be near 0.0
        assert new_score < 0.1

    def test_fact_staleness_score_bounded_zero_to_one(self):
        """Staleness score is always between 0.0 and 1.0."""
        very_old = Fact(
            content="Ancient fact",
            confidence=0.5,
            timestamp=datetime.now() - timedelta(days=365),
        )
        brand_new = Fact(
            content="Fresh fact",
            confidence=0.5,
            timestamp=datetime.now(),
        )
        assert 0.0 <= very_old.staleness_score() <= 1.0
        assert 0.0 <= brand_new.staleness_score() <= 1.0

    def test_fact_source_type_default(self):
        """Fact source_type defaults to 'stated'."""
        fact = Fact(content="Default source type test")
        assert fact.source_type == "stated"

    def test_fact_source_type_custom(self):
        """Fact source_type can be set to custom values."""
        fact = Fact(
            content="User prefers dark mode",
            source_type="observation",
        )
        assert fact.source_type == "observation"

    def test_fact_effective_confidence_zero_when_expired(self):
        """Expired facts have 0.0 effective confidence."""
        fact = Fact(
            content="Expired data",
            confidence=0.9,
            valid_until=datetime.now() - timedelta(hours=1),
        )
        assert fact.effective_confidence() == 0.0

    def test_fact_effective_confidence_reduced_by_staleness(self):
        """Old but not expired facts have reduced effective confidence."""
        old_fact = Fact(
            content="Old but still valid",
            confidence=0.9,
            timestamp=datetime.now() - timedelta(days=30),
        )
        # staleness penalty is up to 30%, so effective confidence is >= 0.6
        effective = old_fact.effective_confidence()
        assert effective < old_fact.confidence
        assert effective >= 0.6  # 0.9 - 0.3 max penalty

    def test_fact_effective_confidence_near_original_when_fresh(self):
        """Fresh facts have effective confidence close to original."""
        fresh_fact = Fact(
            content="Just happened",
            confidence=0.9,
            timestamp=datetime.now(),
        )
        effective = fresh_fact.effective_confidence()
        # Very small staleness penalty for brand new fact
        assert effective > 0.85
        assert effective <= 0.9


class TestTemporalFactSerialization:
    """Tests for serialization of temporal Fact fields."""

    def test_fact_serialization_includes_temporal_fields(self):
        """to_dict includes valid_until and source_type."""
        valid_until = datetime.now() + timedelta(days=1)
        fact = Fact(
            content="Test",
            valid_until=valid_until,
            source_type="inference",
        )
        d = fact.to_dict()
        assert d["source_type"] == "inference"
        assert "valid_until" in d
        assert d["valid_until"] == valid_until.isoformat()

    def test_fact_serialization_without_valid_until_omits_key(self):
        """to_dict omits valid_until when it is None."""
        fact = Fact(content="No expiry")
        d = fact.to_dict()
        assert "valid_until" not in d
        assert d["source_type"] == "stated"

    def test_fact_round_trip_with_temporal_fields(self):
        """Fact can be serialized and deserialized with temporal fields intact."""
        valid_until = datetime(2026, 6, 15, 12, 0, 0)
        fact = Fact(
            content="Round trip test",
            confidence=0.85,
            valid_until=valid_until,
            source_type="inference",
            source_model="test-model",
        )
        d = fact.to_dict()
        restored = Fact.from_dict(d)

        assert restored.content == "Round trip test"
        assert restored.confidence == 0.85
        assert restored.source_type == "inference"
        assert restored.valid_until == valid_until
        assert restored.source_model == "test-model"

    def test_fact_from_dict_without_temporal_fields(self):
        """Fact.from_dict handles legacy dicts without temporal fields."""
        legacy_data = {
            "id": "legacy-id",
            "content": "Legacy fact",
            "confidence": 0.8,
            "source_model": "old-model",
            "evidence": "some evidence",
            "domain": "general",
            "timestamp": "2024-01-01T00:00:00",
        }
        fact = Fact.from_dict(legacy_data)
        assert fact.content == "Legacy fact"
        assert fact.valid_until is None
        assert fact.source_type == "stated"  # default


class TestHiveStateExpiredFactFiltering:
    """Tests for HiveState.add_fact filtering expired facts."""

    def test_add_expired_fact_returns_false(self):
        """Adding an expired fact to HiveState returns False."""
        from vecna.core.hive_state import HiveState

        state = HiveState()
        expired_fact = Fact(
            content="Old weather data",
            confidence=0.9,
            valid_until=datetime.now() - timedelta(hours=1),
        )
        result = state.add_fact(expired_fact)
        assert result is False
        assert len(state.facts) == 0

    def test_add_valid_fact_returns_true(self):
        """Adding a non-expired fact to HiveState works normally."""
        from vecna.core.hive_state import HiveState

        state = HiveState()
        valid_fact = Fact(
            content="Current weather data",
            confidence=0.9,
            valid_until=datetime.now() + timedelta(hours=1),
        )
        result = state.add_fact(valid_fact)
        assert result is True
        assert len(state.facts) == 1
        assert state.facts[0].content == "Current weather data"

    def test_add_fact_no_expiry_still_works(self):
        """Adding a fact without valid_until still works normally."""
        from vecna.core.hive_state import HiveState

        state = HiveState()
        fact = Fact(content="Timeless truth", confidence=0.95)
        result = state.add_fact(fact)
        assert result is True
        assert len(state.facts) == 1

    def test_duplicate_update_preserves_valid_until(self):
        """When a duplicate with higher confidence updates, valid_until is also updated."""
        from vecna.core.hive_state import HiveState

        state = HiveState()
        new_valid_until = datetime.now() + timedelta(hours=2)
        fact1 = Fact(content="Temperature is 72F", confidence=0.7)
        fact2 = Fact(
            content="Temperature is 72F",
            confidence=0.9,
            valid_until=new_valid_until,
        )
        state.add_fact(fact1)
        state.add_fact(fact2)

        assert len(state.facts) == 1
        assert state.facts[0].confidence == 0.9
        assert state.facts[0].valid_until == new_valid_until


class TestTemporalEdgeCases:
    """Edge case and error tests for temporal facts (Amendment 10)."""

    def test_fact_expiring_right_now_is_expired(self):
        """A fact whose valid_until is slightly in the past is expired."""
        # Set valid_until to 1 microsecond ago
        fact = Fact(
            content="Just expired",
            confidence=0.9,
            valid_until=datetime.now() - timedelta(microseconds=1),
        )
        assert fact.is_expired()

    def test_fact_staleness_with_future_timestamp(self):
        """A fact with a future timestamp has 0.0 staleness (clamped)."""
        future_fact = Fact(
            content="Future fact",
            confidence=0.9,
            timestamp=datetime.now() + timedelta(hours=1),
        )
        # Future timestamp results in negative age, log1p of negative -> staleness
        # Implementation should clamp to 0.0
        score = future_fact.staleness_score()
        assert score >= 0.0

    def test_effective_confidence_never_negative(self):
        """effective_confidence should never go below 0.0."""
        low_confidence_old_fact = Fact(
            content="Very low confidence old fact",
            confidence=0.1,
            timestamp=datetime.now() - timedelta(days=60),
        )
        assert low_confidence_old_fact.effective_confidence() >= 0.0

    def test_staleness_score_at_exactly_zero_age(self):
        """A fact created at exactly datetime.now() has near-zero staleness."""
        now = datetime.now()
        fact = Fact(content="Right now", confidence=0.9, timestamp=now)
        score = fact.staleness_score()
        # Should be very close to 0 (within floating point tolerance)
        assert score < 0.01

    def test_all_source_types_accepted(self):
        """Various source_type values are accepted without error."""
        for source_type in ["stated", "observation", "inference", "user_provided"]:
            fact = Fact(content=f"Type: {source_type}", source_type=source_type)
            assert fact.source_type == source_type

    def test_fact_from_dict_invalid_timestamp_raises_value_error(self):
        """Invalid ISO timestamp should raise ValueError in from_dict."""
        with pytest.raises(ValueError, match="Invalid isoformat string"):
            Fact.from_dict(
                {
                    "content": "broken",
                    "timestamp": "not-a-timestamp",
                }
            )

    def test_fact_from_dict_invalid_valid_until_raises_value_error(self):
        """Invalid ISO valid_until should raise ValueError in from_dict."""
        with pytest.raises(ValueError, match="Invalid isoformat string"):
            Fact.from_dict(
                {
                    "content": "broken-valid-until",
                    "valid_until": "tomorrowish",
                }
            )


class TestSerializableMixin:
    """Tests for SerializableMixin (Amendment 7)."""

    def test_mixin_exists_and_is_importable(self):
        """SerializableMixin is importable from vecna.core.types."""
        assert SerializableMixin.__module__ == "vecna.core.types"

    def test_fact_inherits_from_serializable_mixin(self):
        """Fact class inherits from SerializableMixin."""
        fact = Fact(content="Test")
        serialized = fact.to_dict()
        assert serialized["content"] == "Test"
        assert "timestamp" in serialized

    def test_belief_inherits_from_serializable_mixin(self):
        """Belief class inherits from SerializableMixin."""
        belief = Belief(content="Test")
        serialized = belief.to_dict()
        assert serialized["content"] == "Test"
        assert serialized["confidence"] == 0.6

    def test_mixin_to_dict_handles_datetime(self):
        """SerializableMixin.to_dict() converts datetime to ISO string."""
        fact = Fact(content="Datetime test", confidence=0.9)
        d = fact.to_dict()
        # timestamp should be an ISO-format string, not a datetime object
        assert isinstance(d["timestamp"], str)
        # Should be parseable back
        parsed = datetime.fromisoformat(d["timestamp"])
        assert parsed.year == fact.timestamp.year

    def test_mixin_to_dict_handles_enum(self):
        """SerializableMixin.to_dict() converts enums to their value."""
        from vecna.core.types import IdentityKernel

        kernel = IdentityKernel()
        d = kernel.to_dict()
        # All values should be JSON-serializable (no Enum objects)
        import json

        json.dumps(d)  # Should not raise
