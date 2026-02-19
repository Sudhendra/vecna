"""Tests for the HumanModel — learning who the user is."""

from vecna.core.human_model import (
    HumanModel,
    Preference,
    CommunicationStyle,
    EmotionalContext,
)


class TestHumanModelCreation:
    def test_empty_human_model(self):
        model = HumanModel()
        assert model.name is None
        assert model.preferences == []
        assert model.communication_style is not None
        assert model.interaction_count == 0

    def test_human_model_with_name(self):
        model = HumanModel(name="Sudhen")
        assert model.name == "Sudhen"


class TestPreferenceLearning:
    def test_add_preference(self):
        model = HumanModel()
        pref = Preference(
            key="response_length",
            value="concise",
            confidence=0.7,
            observed_count=3,
        )
        model.add_preference(pref)
        assert len(model.preferences) == 1
        assert model.preferences[0].key == "response_length"
        assert model.preferences[0].value == "concise"
        assert model.preferences[0].confidence == 0.7

    def test_preference_strengthens_with_repetition(self):
        model = HumanModel()
        pref1 = Preference(key="tone", value="direct", confidence=0.5, observed_count=1)
        model.add_preference(pref1)
        pref2 = Preference(key="tone", value="direct", confidence=0.6, observed_count=1)
        model.add_preference(pref2)
        # Should merge, not duplicate
        assert len(model.preferences) == 1
        assert model.preferences[0].confidence > 0.5
        assert model.preferences[0].observed_count == 2

    def test_contradicting_preference_tracked(self):
        model = HumanModel()
        pref1 = Preference(key="tone", value="direct", confidence=0.8, observed_count=5)
        model.add_preference(pref1)
        pref2 = Preference(key="tone", value="gentle", confidence=0.6, observed_count=2)
        model.add_preference(pref2)
        # Both should exist — preference can be context-dependent
        assert len(model.preferences) == 2
        values = {p.value for p in model.preferences}
        assert values == {"direct", "gentle"}

    def test_get_preference(self):
        model = HumanModel()
        model.add_preference(
            Preference(key="language", value="python", confidence=0.9, observed_count=10)
        )
        result = model.get_preference("language")
        assert result is not None
        assert result.value == "python"
        assert result.confidence == 0.9

    def test_get_preference_highest_confidence(self):
        model = HumanModel()
        model.add_preference(
            Preference(key="editor", value="vim", confidence=0.4, observed_count=2)
        )
        model.add_preference(
            Preference(key="editor", value="vscode", confidence=0.8, observed_count=8)
        )
        result = model.get_preference("editor")
        assert result.value == "vscode"
        assert result.confidence == 0.8

    def test_get_preference_nonexistent_returns_none(self):
        """Edge case: querying a preference that doesn't exist."""
        model = HumanModel()
        result = model.get_preference("nonexistent_key")
        assert result is None

    def test_preference_confidence_capped_at_one(self):
        """Edge case: repeated merges should not exceed confidence 1.0."""
        model = HumanModel()
        pref = Preference(key="lang", value="python", confidence=0.95, observed_count=1)
        model.add_preference(pref)
        # Add same preference many times to push confidence
        for _ in range(50):
            model.add_preference(
                Preference(key="lang", value="python", confidence=0.99, observed_count=1)
            )
        assert len(model.preferences) == 1
        assert model.preferences[0].confidence <= 1.0


class TestCommunicationStyle:
    def test_default_style(self):
        style = CommunicationStyle()
        assert style.verbosity == 0.5  # neutral default
        assert style.formality == 0.5
        assert style.technical_depth == 0.5

    def test_update_from_interaction(self):
        style = CommunicationStyle()
        style.update_from_signal("short_response_preferred", strength=0.8)
        assert style.verbosity < 0.5  # Should decrease

    def test_style_to_prompt_directive(self):
        style = CommunicationStyle(verbosity=0.2, formality=0.8, technical_depth=0.9)
        directive = style.to_prompt_directive()
        assert isinstance(directive, str)
        assert len(directive) > 0
        # Amendment 9: assert directive contains expected style keywords
        assert "concise" in directive.lower()
        assert "formal" in directive.lower()
        assert "expert" in directive.lower() or "technical" in directive.lower()

    def test_update_unknown_signal_is_noop(self):
        """Edge case: unknown signal should not crash or change anything."""
        style = CommunicationStyle()
        original_verbosity = style.verbosity
        original_formality = style.formality
        style.update_from_signal("totally_unknown_signal", strength=1.0)
        assert style.verbosity == original_verbosity
        assert style.formality == original_formality

    def test_style_dimensions_clamped_to_zero_one(self):
        """Edge case: extreme signals should not push dimensions outside [0.0, 1.0]."""
        style = CommunicationStyle(verbosity=0.05)
        # Apply a very strong negative signal many times
        for _ in range(100):
            style.update_from_signal("short_response_preferred", strength=10.0)
        assert style.verbosity >= 0.0

        style2 = CommunicationStyle(verbosity=0.95)
        for _ in range(100):
            style2.update_from_signal("long_response_preferred", strength=10.0)
        assert style2.verbosity <= 1.0

    def test_neutral_style_gives_natural_directive(self):
        """Default style (excluding emoji) should produce expected directive."""
        style = CommunicationStyle(emoji_usage=0.5)  # Override emoji to be neutral too
        directive = style.to_prompt_directive()
        assert directive == "Respond naturally."


class TestInteractionPatterns:
    def test_record_interaction(self):
        model = HumanModel()
        model.record_interaction(
            topic="python debugging",
            satisfaction_signal=1.0,  # positive
            duration_seconds=120,
        )
        assert model.interaction_count == 1
        assert len(model.interaction_patterns) == 1
        assert model.interaction_patterns[0].topic == "python debugging"
        assert model.interaction_patterns[0].satisfaction_signal == 1.0
        assert model.interaction_patterns[0].duration_seconds == 120

    def test_detect_recurring_topic(self):
        model = HumanModel()
        for _ in range(5):
            model.record_interaction(topic="kubernetes", satisfaction_signal=0.8)
        topics = model.get_recurring_topics(min_count=3)
        assert "kubernetes" in topics

    def test_no_recurring_topics_below_threshold(self):
        """Edge case: topics below min_count should not appear."""
        model = HumanModel()
        model.record_interaction(topic="docker", satisfaction_signal=0.5)
        model.record_interaction(topic="docker", satisfaction_signal=0.6)
        topics = model.get_recurring_topics(min_count=3)
        assert "docker" not in topics


class TestEmotionalContext:
    def test_default_neutral(self):
        ctx = EmotionalContext()
        assert ctx.current_state == "neutral"
        assert ctx.confidence == 0.5

    def test_update_emotional_state(self):
        ctx = EmotionalContext()
        ctx.update("frustrated", confidence=0.7, trigger="repeated_errors")
        assert ctx.current_state == "frustrated"
        assert ctx.last_trigger == "repeated_errors"
        assert ctx.confidence == 0.7

    def test_emotional_history_tracks_previous_states(self):
        """Verify that updating preserves previous state in history."""
        ctx = EmotionalContext()
        ctx.update("focused", confidence=0.8, trigger="deep_work")
        ctx.update("frustrated", confidence=0.7, trigger="repeated_errors")
        assert len(ctx.history) == 2
        assert ctx.history[0]["state"] == "neutral"
        assert ctx.history[1]["state"] == "focused"
        assert ctx.current_state == "frustrated"

    def test_emotional_history_capped_at_50(self):
        """Edge case: history should not grow unbounded."""
        ctx = EmotionalContext()
        for i in range(60):
            ctx.update(f"state_{i}", confidence=0.5)
        assert len(ctx.history) <= 50


class TestHumanModelSerialization:
    def test_round_trip(self):
        model = HumanModel(name="TestUser")
        model.add_preference(
            Preference(key="lang", value="python", confidence=0.9, observed_count=5)
        )
        model.record_interaction(topic="testing", satisfaction_signal=0.8)

        d = model.to_dict()
        restored = HumanModel.from_dict(d)
        assert restored.name == "TestUser"
        assert len(restored.preferences) == 1
        assert restored.preferences[0].key == "lang"
        assert restored.preferences[0].value == "python"
        assert restored.preferences[0].confidence == 0.9
        assert restored.interaction_count == 1

    def test_to_prompt_context(self):
        model = HumanModel(name="Sudhen")
        model.add_preference(
            Preference(key="style", value="no-fluff", confidence=0.95, observed_count=20)
        )
        ctx = model.to_prompt_context()
        assert "Sudhen" in ctx
        assert "no-fluff" in ctx

    def test_round_trip_preserves_communication_style(self):
        """Serialization should preserve communication style dimensions."""
        model = HumanModel()
        model.communication_style.update_from_signal("short_response_preferred", strength=1.0)
        original_verbosity = model.communication_style.verbosity

        d = model.to_dict()
        restored = HumanModel.from_dict(d)
        assert restored.communication_style.verbosity == original_verbosity

    def test_round_trip_preserves_emotional_context(self):
        """Serialization should preserve emotional context."""
        model = HumanModel()
        model.emotional_context.update("excited", confidence=0.9, trigger="good_news")

        d = model.to_dict()
        restored = HumanModel.from_dict(d)
        assert restored.emotional_context.current_state == "excited"
        assert restored.emotional_context.confidence == 0.9
        assert restored.emotional_context.last_trigger == "good_news"

    def test_from_dict_with_empty_data(self):
        """Edge case: from_dict with minimal data should produce valid model."""
        restored = HumanModel.from_dict({})
        assert restored.name is None
        assert restored.preferences == []
        assert restored.interaction_count == 0

    def test_to_prompt_context_without_name(self):
        """Edge case: prompt context without a name should still work."""
        model = HumanModel()
        ctx = model.to_prompt_context()
        assert "USER PROFILE" in ctx


class TestHiveStateHumanModelIntegration:
    """Test HumanModel integration into HiveState."""

    def test_hive_state_has_human_model_field(self):
        from vecna.core.hive_state import HiveState

        state = HiveState()
        assert state.human_model is None

    def test_ensure_human_model_creates_one(self):
        from vecna.core.hive_state import HiveState

        state = HiveState()
        model = state.ensure_human_model()
        assert model.name is None
        assert model.interaction_count == 0
        # Calling again returns the same instance
        model2 = state.ensure_human_model()
        assert model2 is model

    def test_human_model_in_to_full_dict(self):
        from vecna.core.hive_state import HiveState

        state = HiveState()
        state.ensure_identity()
        state.ensure_human_model()
        state.human_model.name = "Sudhen"

        d = state.to_full_dict()
        assert "human_model" in d
        assert d["human_model"]["name"] == "Sudhen"

    def test_human_model_in_prompt_context(self):
        from vecna.core.hive_state import HiveState

        state = HiveState()
        state.ensure_identity()
        hm = state.ensure_human_model()
        hm.name = "Sudhen"
        hm.add_preference(Preference(key="lang", value="python", confidence=0.9, observed_count=10))

        ctx = state.to_prompt_context()
        assert "Sudhen" in ctx
        assert "python" in ctx


class TestContextCaching:
    """Amendment 16: to_prompt_context() caching in HiveState."""

    def test_context_cache_returns_same_string(self):
        from vecna.core.hive_state import HiveState

        state = HiveState()
        state.ensure_identity()
        ctx1 = state.to_prompt_context()
        ctx2 = state.to_prompt_context()
        assert ctx1 == ctx2

    def test_mutation_invalidates_cache(self):
        from vecna.core.hive_state import HiveState
        from vecna.core.types import Fact

        state = HiveState()
        state.ensure_identity()
        state.to_prompt_context()
        state.add_fact(Fact(content="New fact for cache test", confidence=0.9))
        ctx_after = state.to_prompt_context()
        assert "New fact for cache test" in ctx_after

    def test_add_belief_invalidates_cache(self):
        from vecna.core.hive_state import HiveState
        from vecna.core.types import Belief

        state = HiveState()
        state.ensure_identity()
        _ = state.to_prompt_context()
        state.add_belief(Belief(content="Cache test belief", confidence=0.9))
        ctx = state.to_prompt_context()
        assert "Cache test belief" in ctx

    def test_apply_update_invalidates_cache(self):
        from vecna.core.hive_state import HiveState
        from vecna.core.types import HiveUpdate

        state = HiveState()
        state.ensure_identity()
        _ = state.to_prompt_context()

        update = HiveUpdate(
            source_model="test",
            new_facts=[{"content": "Update cache fact", "confidence": 0.8}],
        )
        state.apply_update(update)
        ctx = state.to_prompt_context()
        assert "Update cache fact" in ctx

    def test_max_context_tokens_truncation(self):
        """Amendment 16: context should respect max_context_tokens budget."""
        from vecna.core.hive_state import HiveState
        from vecna.core.types import Fact

        state = HiveState()
        # Do NOT init identity — keep preamble small so truncation is testable
        # Add many diverse facts (unique enough to avoid Jaccard dedup)
        domains = [
            "python",
            "javascript",
            "rust",
            "golang",
            "kubernetes",
            "docker",
            "terraform",
            "ansible",
            "react",
            "vue",
            "django",
            "flask",
            "fastapi",
            "sqlalchemy",
            "redis",
            "postgres",
            "mongodb",
            "elasticsearch",
            "kafka",
            "rabbitmq",
        ]
        for i, domain in enumerate(domains):
            state.add_fact(
                Fact(
                    content=f"The {domain} ecosystem is widely used in production",
                    confidence=0.9 - (i * 0.005),
                    domain=domain,
                )
            )

        # Different token budgets produce different lengths
        # (cache auto-invalidates on budget change)
        small_ctx = state.to_prompt_context(max_context_tokens=50)
        large_ctx = state.to_prompt_context(max_context_tokens=50000)
        assert len(small_ctx) < len(large_ctx)
