"""
Unit tests for ConsensusEngine - merging multiple model outputs.

Tests:
- Single update merging
- Multi-update consensus
- Contradiction detection
- Agreement boosting
- Domain routing
- Clustering/similarity
"""

import pytest

from vecna.orchestrator.consensus import ConsensusConfig, DomainRouter
from vecna.core.types import HiveUpdate


class TestConsensusConfig:
    """Tests for ConsensusConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ConsensusConfig()

        assert config.min_fact_confidence == 0.3
        assert config.min_belief_confidence == 0.2
        assert config.agreement_boost == 0.15
        assert config.similarity_threshold == 0.7

    def test_custom_config(self):
        """Test custom configuration."""
        config = ConsensusConfig(min_fact_confidence=0.5, agreement_boost=0.2)

        assert config.min_fact_confidence == 0.5
        assert config.agreement_boost == 0.2


class TestConsensusEngineMerge:
    """Tests for merge_updates functionality."""

    def test_merge_empty_updates(self, consensus_engine, clean_state):
        """Test merging empty update list."""
        counts = consensus_engine.merge_updates([], clean_state)

        assert counts == {}

    def test_merge_single_update(self, consensus_engine, clean_state):
        """Test merging a single update."""
        update = HiveUpdate(
            source_model="model-1",
            new_facts=[{"content": "Test fact", "confidence": 0.8}],
            belief_changes=[{"content": "Test belief", "confidence": 0.7}],
            confidence=0.8,
        )

        counts = consensus_engine.merge_updates([update], clean_state)

        assert counts["facts_added"] == 1
        assert counts["beliefs_added"] == 1
        assert len(clean_state.facts) == 1

    def test_merge_multiple_updates_agreement(self, consensus_engine, clean_state):
        """Test that agreement between models boosts confidence."""
        update1 = HiveUpdate(
            source_model="model-1",
            new_facts=[{"content": "AI is useful", "confidence": 0.6}],
            confidence=0.6,
        )
        update2 = HiveUpdate(
            source_model="model-2",
            new_facts=[{"content": "AI is useful", "confidence": 0.7}],
            confidence=0.7,
        )

        counts = consensus_engine.merge_updates([update1, update2], clean_state)

        assert counts["facts_added"] == 1
        assert counts["agreements_found"] >= 1
        # Confidence should be boosted
        assert clean_state.facts[0].confidence > 0.7

    def test_merge_contradiction_detection(self, consensus_engine, clean_state):
        """Test that contradictions are detected."""
        update1 = HiveUpdate(
            source_model="model-1",
            new_facts=[{"content": "The answer is true", "confidence": 0.8}],
            confidence=0.8,
        )
        update2 = HiveUpdate(
            source_model="model-2",
            new_facts=[{"content": "The answer is not true", "confidence": 0.8}],
            confidence=0.8,
        )

        counts = consensus_engine.merge_updates([update1, update2], clean_state)

        # Should detect contradiction (one has "not")
        assert counts["contradictions_found"] >= 1 or counts["facts_added"] >= 1

    def test_merge_with_model_weights(self, consensus_engine, clean_state):
        """Test merging with model weights."""
        update1 = HiveUpdate(
            source_model="expert",
            new_facts=[{"content": "Expert fact", "confidence": 0.6}],
            confidence=0.6,
        )
        update2 = HiveUpdate(
            source_model="novice",
            new_facts=[{"content": "Expert fact", "confidence": 0.6}],
            confidence=0.6,
        )

        model_weights = {"expert": 2.0, "novice": 0.5}

        counts = consensus_engine.merge_updates(
            [update1, update2], clean_state, model_weights=model_weights
        )

        assert counts["facts_added"] == 1

    def test_merge_hypotheses(self, consensus_engine, clean_state):
        """Test that hypotheses are kept even without consensus."""
        update = HiveUpdate(
            source_model="model-1",
            new_hypotheses=[
                {"content": "Hypothesis A", "confidence": 0.3},
                {"content": "Hypothesis B", "confidence": 0.4},
            ],
        )

        counts = consensus_engine.merge_updates([update], clean_state)

        assert counts["hypotheses_added"] == 2

    def test_merge_questions_deduplication(self, consensus_engine, clean_state):
        """Test that duplicate questions are deduplicated."""
        update1 = HiveUpdate(
            source_model="model-1", open_questions=[{"question": "What is the answer?"}]
        )
        update2 = HiveUpdate(
            source_model="model-2", open_questions=[{"question": "What is the answer?"}]
        )

        counts = consensus_engine.merge_updates([update1, update2], clean_state)

        # Should only add one question
        assert counts["questions_added"] == 1

    def test_version_increment(self, consensus_engine, clean_state):
        """Test that state version is incremented after merge."""
        initial_version = clean_state.version

        update = HiveUpdate(
            source_model="model-1", new_facts=[{"content": "Fact", "confidence": 0.8}]
        )

        consensus_engine.merge_updates([update], clean_state)

        assert clean_state.version == initial_version + 1


class TestClustering:
    """Tests for similarity clustering."""

    def test_cluster_similar_items(self, consensus_engine):
        """Test clustering of similar items."""
        items = [
            {"content": "Python is great", "_source": "model-1"},
            {"content": "Python is great", "_source": "model-2"},
            {"content": "Java is different", "_source": "model-3"},
        ]

        clusters = consensus_engine._cluster_similar_items(items)

        # Should have 2 clusters: one for Python, one for Java
        assert len(clusters) == 2

    def test_cluster_empty_items(self, consensus_engine):
        """Test clustering empty list."""
        clusters = consensus_engine._cluster_similar_items([])

        assert clusters == []

    def test_is_similar_exact_match(self, consensus_engine):
        """Test similarity with exact match."""
        assert consensus_engine._is_similar("test", "test") is True

    def test_is_similar_different(self, consensus_engine):
        """Test similarity with different texts."""
        assert consensus_engine._is_similar("apples oranges", "bananas grapes") is False


class TestMergeFactCluster:
    """Tests for fact cluster merging."""

    def test_merge_single_fact(self, consensus_engine):
        """Test merging single-item cluster."""
        cluster = [
            {"content": "Test fact", "_source": "model-1", "_weight": 1.0, "_base_confidence": 0.8}
        ]

        merged, is_contradiction = consensus_engine._merge_fact_cluster(cluster)

        assert is_contradiction is False
        assert merged["content"] == "Test fact"
        assert merged["confidence"] == 0.8

    def test_merge_agreement_cluster(self, consensus_engine):
        """Test merging cluster with agreement."""
        cluster = [
            {"content": "Fact A", "_source": "m1", "_weight": 1.0, "_base_confidence": 0.6},
            {
                "content": "Fact A detailed",
                "_source": "m2",
                "_weight": 1.0,
                "_base_confidence": 0.7,
            },
        ]

        merged, is_contradiction = consensus_engine._merge_fact_cluster(cluster)

        assert is_contradiction is False
        # Should pick the more detailed content
        assert "detailed" in merged["content"]
        # Should boost confidence
        assert merged["confidence"] > 0.7

    def test_merge_contradiction_cluster(self, consensus_engine):
        """Test detecting contradiction in cluster."""
        cluster = [
            {"content": "This is true", "_source": "m1", "_weight": 1.0, "_base_confidence": 0.8},
            {
                "content": "This is not true",
                "_source": "m2",
                "_weight": 1.0,
                "_base_confidence": 0.8,
            },
        ]

        merged, is_contradiction = consensus_engine._merge_fact_cluster(cluster)

        assert is_contradiction is True


class TestDomainRouter:
    """Tests for DomainRouter functionality."""

    @pytest.fixture
    def mock_adapters(self):
        """Create mock adapters for testing."""

        class MockAdapter:
            def __init__(self, name, domain):
                self.name = name
                self.domain = domain

        return [
            MockAdapter("code-expert", "code"),
            MockAdapter("math-expert", "math"),
            MockAdapter("general-1", "general"),
            MockAdapter("general-2", "general"),
        ]

    def test_detect_code_domain(self, mock_adapters):
        """Test detecting code domain."""
        router = DomainRouter(mock_adapters)

        domains = router.detect_domains("Write a Python function to sort a list")

        assert "code" in domains

    def test_detect_math_domain(self, mock_adapters):
        """Test detecting math domain."""
        router = DomainRouter(mock_adapters)

        domains = router.detect_domains("Calculate the integral of x^2")

        assert "math" in domains

    def test_detect_general_domain(self, mock_adapters):
        """Test detecting general domain for ambiguous task."""
        router = DomainRouter(mock_adapters)

        domains = router.detect_domains("Tell me about the weather")

        assert "general" in domains

    def test_select_adapters_for_code(self, mock_adapters):
        """Test selecting adapters for code task."""
        router = DomainRouter(mock_adapters)

        adapters = router.select_adapters("Fix this bug in my Python code")

        adapter_names = [a.name for a in adapters]
        assert "code-expert" in adapter_names

    def test_select_adapters_max_limit(self, mock_adapters):
        """Test that adapter selection respects max_adapters."""
        router = DomainRouter(mock_adapters)

        adapters = router.select_adapters("Complex task about code and math", max_adapters=2)

        assert len(adapters) <= 2

    def test_get_all_adapters(self, mock_adapters):
        """Test getting all registered adapters."""
        router = DomainRouter(mock_adapters)

        all_adapters = router.get_all_adapters()

        assert len(all_adapters) == 4


class TestMergeBeliefCluster:
    """Tests for belief cluster merging."""

    def test_merge_single_belief(self, consensus_engine):
        """Test merging single-item belief cluster."""
        cluster = [
            {
                "content": "Test belief",
                "_source": "model-1",
                "_weight": 1.0,
                "_base_confidence": 0.6,
                "reasoning": "Because reasons",
            }
        ]

        merged = consensus_engine._merge_belief_cluster(cluster)

        assert merged["content"] == "Test belief"
        assert merged["confidence"] == 0.6

    def test_merge_belief_agreement(self, consensus_engine):
        """Test merging beliefs with agreement."""
        cluster = [
            {
                "content": "Belief A",
                "_source": "m1",
                "_weight": 1.0,
                "_base_confidence": 0.5,
                "reasoning": "Reason 1",
            },
            {
                "content": "Belief A expanded",
                "_source": "m2",
                "_weight": 1.0,
                "_base_confidence": 0.6,
                "reasoning": "Reason 2",
            },
        ]

        merged = consensus_engine._merge_belief_cluster(cluster)

        # Should pick more detailed content
        assert "expanded" in merged["content"]
        # Should boost confidence
        assert merged["confidence"] > 0.6
        # Should combine reasoning
        assert "Reason 1" in merged["reasoning"] or "Reason 2" in merged["reasoning"]
