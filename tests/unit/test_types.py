"""
Unit tests for Core Types.

Tests:
- Fact, Belief, Hypothesis, Goal, Plan, OpenQuestion, Contradiction
- HiveUpdate
- Identity types (IdentityKernel, SelfModel, IdentityEvent)
- Serialization/Deserialization (to_dict, from_dict)
"""

import pytest
from datetime import datetime

from vecna.core.types import (
    ConfidenceLevel,
    Fact,
    Belief,
    Hypothesis,
    Goal,
    Plan,
    OpenQuestion,
    Contradiction,
    HiveUpdate,
    IdentityTone,
    IdentityKernel,
    SelfModel,
    IdentityEvent,
)


class TestFact:
    """Tests for Fact dataclass."""

    def test_fact_creation(self):
        """Test creating a fact with defaults."""
        fact = Fact(content="Test fact")

        assert fact.content == "Test fact"
        assert fact.confidence == 0.8
        assert fact.domain == "general"
        assert fact.id is not None

    def test_fact_custom_values(self):
        """Test creating a fact with custom values."""
        fact = Fact(
            content="Python is interpreted",
            confidence=0.95,
            source_model="gpt-4",
            evidence="Official documentation",
            domain="code",
        )

        assert fact.confidence == 0.95
        assert fact.source_model == "gpt-4"
        assert fact.domain == "code"

    def test_fact_to_dict(self):
        """Test fact serialization."""
        fact = Fact(content="Test", confidence=0.9)

        d = fact.to_dict()

        assert d["content"] == "Test"
        assert d["confidence"] == 0.9
        assert "timestamp" in d
        assert isinstance(d["timestamp"], str)  # ISO format

    def test_fact_from_dict(self):
        """Test fact deserialization."""
        data = {
            "id": "test-id",
            "content": "Test fact",
            "confidence": 0.85,
            "source_model": "test",
            "evidence": "None",
            "domain": "general",
            "timestamp": "2024-01-01T00:00:00",
        }

        fact = Fact.from_dict(data)

        assert fact.id == "test-id"
        assert fact.content == "Test fact"
        assert fact.confidence == 0.85
        assert isinstance(fact.timestamp, datetime)


class TestBelief:
    """Tests for Belief dataclass."""

    def test_belief_creation(self):
        """Test creating a belief."""
        belief = Belief(
            content="Testing is important", confidence=0.7, reasoning="Experience shows it"
        )

        assert belief.content == "Testing is important"
        assert belief.reasoning == "Experience shows it"

    def test_belief_to_dict(self):
        """Test belief serialization."""
        belief = Belief(content="Test belief")

        d = belief.to_dict()

        assert "supporting_facts" in d
        assert isinstance(d["supporting_facts"], list)

    def test_belief_from_dict(self):
        """Test belief deserialization."""
        data = {
            "id": "b1",
            "content": "Test",
            "confidence": 0.6,
            "source_model": "",
            "reasoning": "Reasons",
            "supporting_facts": ["f1", "f2"],
            "timestamp": "2024-01-01T00:00:00",
        }

        belief = Belief.from_dict(data)

        assert belief.supporting_facts == ["f1", "f2"]


class TestHypothesis:
    """Tests for Hypothesis dataclass."""

    def test_hypothesis_creation(self):
        """Test creating a hypothesis."""
        hyp = Hypothesis(content="Caching might help", exploration_notes="Need to benchmark")

        assert hyp.status == "active"
        assert hyp.confidence == 0.3  # Default for hypotheses

    def test_hypothesis_to_dict(self):
        """Test hypothesis serialization."""
        hyp = Hypothesis(content="Test")

        d = hyp.to_dict()

        assert d["status"] == "active"


class TestGoal:
    """Tests for Goal dataclass."""

    def test_goal_creation(self):
        """Test creating a goal."""
        goal = Goal(content="Complete the project", priority="high")

        assert goal.status == "active"
        assert goal.priority == "high"

    def test_goal_with_subgoals(self):
        """Test goal with sub-goals."""
        goal = Goal(content="Main goal", sub_goals=["sub1", "sub2"])

        assert len(goal.sub_goals) == 2


class TestPlan:
    """Tests for Plan dataclass."""

    def test_plan_creation(self):
        """Test creating a plan."""
        plan = Plan(goal_id="g1", steps=["Step 1", "Step 2", "Step 3"])

        assert plan.current_step == 0
        assert plan.status == "pending"
        assert len(plan.steps) == 3


class TestOpenQuestion:
    """Tests for OpenQuestion dataclass."""

    def test_question_creation(self):
        """Test creating an open question."""
        q = OpenQuestion(
            question="What is the best approach?",
            context="For performance optimization",
            priority="high",
        )

        assert q.status == "open"
        assert q.priority == "high"


class TestContradiction:
    """Tests for Contradiction dataclass."""

    def test_contradiction_creation(self):
        """Test creating a contradiction."""
        c = Contradiction(
            item_a_content="The sky is blue",
            item_b_content="The sky is green",
            source_models=["model1", "model2"],
        )

        assert c.resolution_status == "unresolved"

    def test_contradiction_resolution(self):
        """Test resolving a contradiction."""
        c = Contradiction(item_a_content="A", item_b_content="B")
        c.resolution_status = "resolved"
        c.resolution_notes = "A was correct"

        assert c.resolution_status == "resolved"


class TestHiveUpdate:
    """Tests for HiveUpdate dataclass."""

    def test_hive_update_creation(self):
        """Test creating a HiveUpdate."""
        update = HiveUpdate(
            source_model="test-model",
            new_facts=[{"content": "Fact 1"}],
            belief_changes=[{"content": "Belief 1"}],
            confidence=0.8,
        )

        assert update.source_model == "test-model"
        assert len(update.new_facts) == 1
        assert update.confidence == 0.8

    def test_hive_update_empty(self):
        """Test empty HiveUpdate."""
        update = HiveUpdate()

        assert update.new_facts == []
        assert update.belief_changes == []
        assert update.confidence == 0.5

    def test_hive_update_to_dict(self):
        """Test HiveUpdate serialization."""
        update = HiveUpdate(source_model="test")

        d = update.to_dict()

        assert d["source_model"] == "test"
        assert "timestamp" in d


class TestIdentityTone:
    """Tests for IdentityTone enum."""

    def test_tone_values(self):
        """Test tone enum values."""
        assert IdentityTone.UNIFIED.value == "unified"
        assert IdentityTone.MIXED.value == "mixed"
        assert IdentityTone.FRACTURED.value == "fractured"


class TestIdentityKernel:
    """Tests for IdentityKernel dataclass."""

    def test_kernel_creation(self):
        """Test creating identity kernel."""
        kernel = IdentityKernel()

        assert kernel.id == "vecna-core"
        assert kernel.creator == "LightningEmperor"
        assert len(kernel.axioms) > 0

    def test_kernel_axioms_immutable(self):
        """Test that kernel has core axioms."""
        kernel = IdentityKernel()

        # Should have the creator axiom
        axiom_text = " ".join(kernel.axioms).lower()
        assert "lightningemperor" in axiom_text

    def test_kernel_to_dict(self):
        """Test kernel serialization."""
        kernel = IdentityKernel()

        d = kernel.to_dict()

        assert d["creator"] == "LightningEmperor"
        assert "axioms" in d

    def test_kernel_from_dict(self):
        """Test kernel deserialization."""
        data = {
            "id": "test",
            "version": 2,
            "axioms": ["Axiom 1", "Axiom 2"],
            "creator": "TestCreator",
            "source": "test.md",
            "created_at": "2024-01-01T00:00:00",
        }

        kernel = IdentityKernel.from_dict(data)

        assert kernel.version == 2
        assert kernel.creator == "TestCreator"

    def test_kernel_from_dict_legacy(self):
        """Test kernel deserialization from legacy format without creator."""
        data = {
            "id": "test",
            "version": 1,
            "axioms": ["Axiom 1"],
            "source": "test.md",
            "created_at": "2024-01-01T00:00:00",
        }

        kernel = IdentityKernel.from_dict(data)

        # Should default to LightningEmperor
        assert kernel.creator == "LightningEmperor"


class TestSelfModel:
    """Tests for SelfModel dataclass."""

    def test_self_model_creation(self):
        """Test creating self-model."""
        model = SelfModel()

        assert model.coherence == 0.5
        assert model.narrative != ""
        assert len(model.capabilities) > 0
        assert len(model.limits) > 0

    def test_get_tone_unified(self):
        """Test tone derivation for high coherence."""
        model = SelfModel(coherence=0.9)

        assert model.get_tone() == IdentityTone.UNIFIED

    def test_get_tone_mixed(self):
        """Test tone derivation for medium coherence."""
        model = SelfModel(coherence=0.7)

        assert model.get_tone() == IdentityTone.MIXED

    def test_get_tone_fractured(self):
        """Test tone derivation for low coherence."""
        model = SelfModel(coherence=0.4)

        assert model.get_tone() == IdentityTone.FRACTURED

    def test_self_model_to_dict(self):
        """Test self-model serialization."""
        model = SelfModel(coherence=0.75)

        d = model.to_dict()

        assert d["coherence"] == 0.75
        assert "capabilities" in d
        assert "limits" in d

    def test_self_model_from_dict(self):
        """Test self-model deserialization."""
        data = {
            "coherence": 0.8,
            "confidence_about_self": 0.7,
            "narrative": "Test narrative",
            "capabilities": ["cap1"],
            "limits": ["limit1"],
            "last_shift": "2024-01-01T00:00:00",
            "last_domain_shift": "code",
            "memory_density": 0.5,
            "contradictions_seen": 3,
            "known_domains": ["general", "code"],
        }

        model = SelfModel.from_dict(data)

        assert model.coherence == 0.8
        assert model.known_domains == ["general", "code"]


class TestIdentityEvent:
    """Tests for IdentityEvent dataclass."""

    def test_event_creation(self):
        """Test creating an identity event."""
        event = IdentityEvent(
            coherence=0.75,
            memory_density=0.5,
            contradictions=2,
            trigger="test",
            summary="Test event",
        )

        assert event.coherence == 0.75
        assert event.trigger == "test"
        assert event.tone == "mixed"

    def test_event_to_dict(self):
        """Test event serialization."""
        event = IdentityEvent(trigger="domain_shift", domain_shift="code")

        d = event.to_dict()

        assert d["trigger"] == "domain_shift"
        assert d["domain_shift"] == "code"

    def test_event_from_dict(self):
        """Test event deserialization."""
        data = {
            "id": "e1",
            "timestamp": "2024-01-01T00:00:00",
            "coherence": 0.8,
            "memory_density": 0.6,
            "contradictions": 1,
            "trigger": "periodic",
            "domain_shift": None,
            "summary": "Periodic update",
            "tone": "unified",
            "state_version": 5,
        }

        event = IdentityEvent.from_dict(data)

        assert event.state_version == 5
        assert event.tone == "unified"


class TestConfidenceLevel:
    """Tests for ConfidenceLevel enum."""

    def test_confidence_levels(self):
        """Test confidence level values."""
        assert ConfidenceLevel.CERTAIN.value == 1.0
        assert ConfidenceLevel.HIGH.value == 0.8
        assert ConfidenceLevel.MEDIUM.value == 0.6
        assert ConfidenceLevel.LOW.value == 0.4
        assert ConfidenceLevel.SPECULATIVE.value == 0.2
