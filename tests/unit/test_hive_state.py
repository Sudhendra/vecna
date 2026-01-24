"""
Unit tests for HiveState - the core shared mental state.

Tests:
- State initialization
- Identity management
- Fact/Belief/Hypothesis CRUD
- Similarity detection
- Limit enforcement
- Serialization/Deserialization
"""

import pytest
from datetime import datetime

from vecna.core.hive_state import HiveState
from vecna.core.types import (
    Fact,
    Belief,
    Hypothesis,
    Goal,
    Plan,
    OpenQuestion,
    Contradiction,
    HiveUpdate,
    IdentityKernel,
    SelfModel,
    IdentityEvent,
    IdentityTone,
)


class TestHiveStateInitialization:
    """Tests for HiveState initialization."""

    def test_empty_state_initialization(self):
        """Test that a new HiveState has empty collections."""
        state = HiveState()

        assert state.facts == []
        assert state.beliefs == []
        assert state.hypotheses == []
        assert state.goals == []
        assert state.plans == []
        assert state.open_questions == []
        assert state.contradictions == []
        assert state.version == 0

    def test_identity_initialization(self, clean_state):
        """Test that ensure_identity initializes identity correctly."""
        state = clean_state

        assert state.identity_kernel is not None
        assert state.self_model is not None
        assert len(state.identity_kernel.axioms) > 0
        assert state.identity_kernel.creator == "LightningEmperor"

    def test_double_identity_initialization(self, clean_state):
        """Test that calling ensure_identity twice doesn't reset identity."""
        state = clean_state

        # Modify identity
        original_coherence = state.self_model.coherence
        state.self_model.coherence = 0.99

        # Call ensure_identity again
        state.ensure_identity()

        # Should not reset
        assert state.self_model.coherence == 0.99


class TestFactOperations:
    """Tests for fact management in HiveState."""

    def test_add_fact(self, clean_state):
        """Test adding a fact to state."""
        state = clean_state

        fact = Fact(
            content="Python is a programming language",
            confidence=0.9,
            source_model="test",
            domain="code",
        )

        result = state.add_fact(fact)

        assert result is True
        assert len(state.facts) == 1
        assert state.facts[0].content == "Python is a programming language"

    def test_add_duplicate_fact_lower_confidence(self, clean_state):
        """Test that duplicate facts with lower confidence are not added."""
        state = clean_state

        fact1 = Fact(content="Test fact", confidence=0.8, source_model="test")
        fact2 = Fact(content="test fact", confidence=0.6, source_model="test")  # lower conf

        state.add_fact(fact1)
        result = state.add_fact(fact2)

        assert result is False
        assert len(state.facts) == 1
        assert state.facts[0].confidence == 0.8  # Keeps higher

    def test_add_duplicate_fact_higher_confidence(self, clean_state):
        """Test that duplicate facts update confidence if higher."""
        state = clean_state

        fact1 = Fact(content="Test fact", confidence=0.6, source_model="test")
        fact2 = Fact(content="test fact", confidence=0.9, source_model="test")  # higher conf

        state.add_fact(fact1)
        result = state.add_fact(fact2)

        assert result is False  # Still not "added" (deduplicated)
        assert len(state.facts) == 1
        assert state.facts[0].confidence == 0.9  # Updated

    def test_fact_limit_enforcement(self, clean_state):
        """Test that max_facts limit is enforced."""
        state = clean_state
        state.max_facts = 5

        # Add 10 facts
        for i in range(10):
            fact = Fact(
                content=f"Fact number {i}",
                confidence=i * 0.1,  # Increasing confidence
                source_model="test",
            )
            state.add_fact(fact)

        # Should only keep max_facts (5)
        assert len(state.facts) == 5
        # Should keep highest confidence ones
        assert all(f.confidence >= 0.5 for f in state.facts)

    def test_get_facts_by_domain(self, populated_state):
        """Test filtering facts by domain."""
        state = populated_state

        code_facts = state.get_facts_by_domain("code")

        assert len(code_facts) >= 1
        assert all(f.domain == "code" for f in code_facts)

    def test_get_high_confidence_facts(self, populated_state):
        """Test filtering facts by confidence threshold."""
        state = populated_state

        high_conf = state.get_high_confidence_facts(threshold=0.85)

        assert all(f.confidence >= 0.85 for f in high_conf)


class TestBeliefOperations:
    """Tests for belief management in HiveState."""

    def test_add_belief(self, clean_state):
        """Test adding a belief to state."""
        state = clean_state

        belief = Belief(
            content="Testing improves code quality",
            confidence=0.7,
            source_model="test",
            reasoning="Empirical evidence",
        )

        result = state.add_belief(belief)

        assert result is True
        assert len(state.beliefs) == 1

    def test_belief_deduplication(self, clean_state):
        """Test that similar beliefs are deduplicated."""
        state = clean_state

        belief1 = Belief(content="AI will transform software", confidence=0.6)
        belief2 = Belief(content="AI will transform software", confidence=0.8)

        state.add_belief(belief1)
        state.add_belief(belief2)

        assert len(state.beliefs) == 1
        assert state.beliefs[0].confidence == 0.8


class TestHypothesisOperations:
    """Tests for hypothesis management."""

    def test_add_hypothesis(self, clean_state):
        """Test adding a hypothesis."""
        state = clean_state

        hyp = Hypothesis(
            content="Parallel processing may improve performance",
            confidence=0.3,
            exploration_notes="Needs benchmarking",
        )

        state.add_hypothesis(hyp)

        assert len(state.hypotheses) == 1
        assert state.hypotheses[0].status == "active"


class TestGoalAndPlanOperations:
    """Tests for goal and plan management."""

    def test_add_goal(self, clean_state):
        """Test adding a goal."""
        state = clean_state

        goal = Goal(content="Complete testing", priority="high")
        state.add_goal(goal)

        assert len(state.goals) == 1
        assert state.goals[0].status == "active"

    def test_add_open_question(self, clean_state):
        """Test adding an open question."""
        state = clean_state

        question = OpenQuestion(question="What is the best approach?", priority="high")
        state.add_open_question(question)

        assert len(state.open_questions) == 1


class TestContradictionManagement:
    """Tests for contradiction tracking."""

    def test_add_contradiction(self, clean_state):
        """Test adding a contradiction."""
        state = clean_state

        contradiction = Contradiction(
            item_a_content="The sky is blue",
            item_b_content="The sky is green",
            source_models=["model1", "model2"],
        )
        state.add_contradiction(contradiction)

        assert len(state.contradictions) == 1
        assert state.contradictions[0].resolution_status == "unresolved"

    def test_resolve_contradiction(self, clean_state):
        """Test resolving a contradiction."""
        state = clean_state

        contradiction = Contradiction(item_a_content="A", item_b_content="B")
        state.add_contradiction(contradiction)

        state.resolve_contradiction(
            contradiction.id, "A is correct based on evidence", keep_both=False
        )

        assert state.contradictions[0].resolution_status == "resolved"
        assert "evidence" in state.contradictions[0].resolution_notes


class TestHiveUpdate:
    """Tests for applying HiveUpdate to state."""

    def test_apply_update(self, clean_state, sample_hive_update):
        """Test applying a HiveUpdate to state."""
        state = clean_state
        update = sample_hive_update

        counts = state.apply_update(update)

        assert counts["facts_added"] == 2
        assert counts["beliefs_added"] == 1
        assert counts["hypotheses_added"] == 1
        assert counts["questions_added"] == 1
        assert state.version == 1

    def test_update_history_tracking(self, clean_state, sample_hive_update):
        """Test that update history is tracked."""
        state = clean_state

        state.apply_update(sample_hive_update)

        assert len(state.update_history) == 1
        assert state.update_history[0]["source_model"] == "test-model"

    def test_update_history_limit(self, clean_state):
        """Test that update history respects max_history."""
        state = clean_state
        state.max_history = 5

        # Apply 10 updates
        for i in range(10):
            update = HiveUpdate(
                source_model=f"model-{i}", new_facts=[{"content": f"Fact {i}", "confidence": 0.8}]
            )
            state.apply_update(update)

        assert len(state.update_history) == 5


class TestSimilarity:
    """Tests for similarity detection."""

    def test_exact_match(self, clean_state):
        """Test that exact matches are detected as similar."""
        state = clean_state

        assert state._is_similar("Hello world", "Hello world") is True

    def test_case_insensitive(self, clean_state):
        """Test that similarity is case-insensitive."""
        state = clean_state

        assert state._is_similar("Hello World", "hello world") is True

    def test_different_texts(self, clean_state):
        """Test that different texts are not similar."""
        state = clean_state

        assert state._is_similar("Python programming", "Java development") is False

    def test_partial_overlap(self, clean_state):
        """Test similarity with partial word overlap."""
        state = clean_state

        # Partial overlap: 4/7 words = 0.57, which is below the 0.8 threshold
        assert (
            state._is_similar(
                "Python is great for data science", "Python is great for machine learning"
            )
            is False
        )


class TestSerialization:
    """Tests for state serialization/deserialization."""

    def test_to_summary_dict(self, populated_state):
        """Test converting state to summary dict."""
        state = populated_state

        summary = state.to_summary_dict()

        assert "version" in summary
        assert "num_facts" in summary
        assert summary["num_facts"] >= 1

    def test_to_full_dict(self, populated_state):
        """Test converting state to full dict."""
        state = populated_state

        full_dict = state.to_full_dict()

        assert "facts" in full_dict
        assert "beliefs" in full_dict
        assert "identity_kernel" in full_dict
        assert "self_model" in full_dict

    def test_to_prompt_context(self, populated_state):
        """Test generating prompt context."""
        state = populated_state

        context = state.to_prompt_context()

        assert isinstance(context, str)
        assert "IDENTITY" in context or "HIVE" in context
        assert len(context) > 100


class TestIdentityManagement:
    """Tests for identity-related operations."""

    def test_add_identity_event(self, clean_state):
        """Test adding an identity event."""
        state = clean_state

        event = IdentityEvent(
            coherence=0.7,
            memory_density=0.5,
            contradictions=2,
            trigger="test",
            summary="Test event",
        )
        state.add_identity_event(event)

        assert len(state.identity_timeline) == 1

    def test_identity_timeline_limit(self, clean_state):
        """Test that identity timeline respects max size."""
        state = clean_state

        # Add more than 1000 events
        for i in range(1100):
            event = IdentityEvent(coherence=0.5, trigger="test", summary=f"Event {i}")
            state.add_identity_event(event)

        assert len(state.identity_timeline) == 1000

    def test_get_identity_summary(self, clean_state):
        """Test getting identity summary."""
        state = clean_state

        summary = state.get_identity_summary()

        assert "coherence" in summary
        assert "tone" in summary
        assert "narrative" in summary

    def test_get_recent_identity_events(self, clean_state):
        """Test getting recent identity events."""
        state = clean_state

        # Add some events
        for i in range(5):
            event = IdentityEvent(trigger="test", summary=f"Event {i}")
            state.add_identity_event(event)

        recent = state.get_recent_identity_events(count=3)

        assert len(recent) == 3

    def test_state_hash(self, populated_state):
        """Test state hash generation."""
        state = populated_state

        hash1 = state.get_state_hash()

        # Hash should be consistent
        hash2 = state.get_state_hash()
        assert hash1 == hash2

        # Hash should change when state changes
        state.add_fact(Fact(content="New unique fact xyz123", confidence=0.9))
        hash3 = state.get_state_hash()
        assert hash1 != hash3
