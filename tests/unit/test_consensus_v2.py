"""Tests for upgraded consensus engine with embedding similarity and MoA."""

import math

import pytest

from vecna.core.hive_state import HiveState
from vecna.core.types import HiveUpdate
from vecna.orchestrator.consensus import ConsensusConfig, ConsensusEngine


class TestCosineSimilarity:
    """Tests for cosine similarity computation."""

    def test_cosine_similarity_identical(self):
        """Identical vectors should have similarity 1.0."""
        engine = ConsensusEngine()
        vec = [1.0, 0.0, 0.0]
        assert engine._cosine_similarity(vec, vec) == pytest.approx(1.0)

    def test_cosine_similarity_orthogonal(self):
        """Orthogonal vectors should have similarity 0.0."""
        engine = ConsensusEngine()
        assert engine._cosine_similarity([1, 0, 0], [0, 1, 0]) == pytest.approx(0.0)

    def test_cosine_similarity_opposite(self):
        """Opposite vectors should have similarity -1.0."""
        engine = ConsensusEngine()
        assert engine._cosine_similarity([1, 0], [-1, 0]) == pytest.approx(-1.0)

    def test_cosine_similarity_known_value(self):
        """Test with a known hand-calculated cosine similarity."""
        engine = ConsensusEngine()
        # [1, 2, 3] . [4, 5, 6] = 32
        # |[1,2,3]| = sqrt(14), |[4,5,6]| = sqrt(77)
        # cos = 32 / (sqrt(14)*sqrt(77))
        expected = 32.0 / (math.sqrt(14) * math.sqrt(77))
        result = engine._cosine_similarity([1, 2, 3], [4, 5, 6])
        assert result == pytest.approx(expected, abs=1e-9)

    def test_cosine_similarity_high_dimensional(self):
        """Cosine similarity works correctly with higher-dimensional vectors."""
        engine = ConsensusEngine()
        # Identical 100-dim vectors should still give 1.0
        vec = [float(i) for i in range(1, 101)]
        assert engine._cosine_similarity(vec, vec) == pytest.approx(1.0)

    # === Error/Edge-case tests (Amendment 10) ===

    def test_cosine_similarity_empty_vectors(self):
        """Empty vectors should return 0.0."""
        engine = ConsensusEngine()
        assert engine._cosine_similarity([], []) == 0.0

    def test_cosine_similarity_mismatched_lengths(self):
        """Mismatched vector lengths should return 0.0."""
        engine = ConsensusEngine()
        assert engine._cosine_similarity([1, 2], [1, 2, 3]) == 0.0

    def test_cosine_similarity_zero_vector(self):
        """A zero vector should return 0.0 (no division by zero)."""
        engine = ConsensusEngine()
        assert engine._cosine_similarity([0, 0, 0], [1, 2, 3]) == 0.0

    def test_cosine_similarity_both_zero_vectors(self):
        """Both zero vectors should return 0.0."""
        engine = ConsensusEngine()
        assert engine._cosine_similarity([0, 0], [0, 0]) == 0.0


class TestEmbeddingSimilarity:
    """Tests for _is_similar with embedding-based comparison."""

    def test_similarity_uses_embeddings_when_available(self):
        """Embedding-based similarity should cluster semantically similar texts."""
        engine = ConsensusEngine()
        # Embeddings close in cosine space → similar
        result = engine._is_similar(
            "The car is fast",
            "The automobile is speedy",
            embedding_a=[0.9, 0.1, 0.0],
            embedding_b=[0.85, 0.15, 0.0],
        )
        assert result is True

    def test_similarity_rejects_dissimilar_embeddings(self):
        """Embeddings far apart should not be considered similar."""
        engine = ConsensusEngine()
        result = engine._is_similar(
            "The car is fast",
            "Quantum physics is complex",
            embedding_a=[1.0, 0.0, 0.0],
            embedding_b=[0.0, 1.0, 0.0],
        )
        assert result is False

    def test_fallback_to_jaccard_without_embeddings(self):
        """Without embeddings, falls back to Jaccard word overlap."""
        engine = ConsensusEngine()
        # Exact same text → high Jaccard overlap
        result = engine._is_similar("hello world foo bar", "hello world foo bar")
        assert result is True

    def test_fallback_rejects_different_text(self):
        """Jaccard fallback rejects lexically different texts."""
        engine = ConsensusEngine()
        result = engine._is_similar("apples oranges bananas", "dogs cats hamsters")
        assert result is False

    def test_embedding_overrides_jaccard(self):
        """Embeddings should override Jaccard even for lexically similar texts.

        Two identical texts with orthogonal embeddings should be considered
        dissimilar when embeddings are provided.
        """
        engine = ConsensusEngine()
        # Same text but orthogonal embeddings → NOT similar (embeddings win)
        result = engine._is_similar(
            "hello world",
            "hello world",
            embedding_a=[1.0, 0.0, 0.0],
            embedding_b=[0.0, 1.0, 0.0],
        )
        assert result is False

    def test_custom_similarity_threshold(self):
        """Custom threshold affects the similarity decision."""
        config = ConsensusConfig(similarity_threshold=0.99)
        engine = ConsensusEngine(config=config)

        # These embeddings have high but not 0.99 cosine similarity
        # cos([0.9,0.1,0],[0.85,0.15,0]) ≈ 0.9978 which is > 0.99, so use more divergent vectors
        result_different = engine._is_similar(
            "text a",
            "text b",
            embedding_a=[1.0, 0.0, 0.0],
            embedding_b=[0.8, 0.6, 0.0],
        )
        # cos = 0.8 / (1.0 * 1.0) = 0.8 < 0.99
        assert result_different is False

    # === Error/Edge-case tests (Amendment 10) ===

    def test_one_embedding_none_falls_back_to_jaccard(self):
        """If only one embedding is provided, fall back to Jaccard."""
        engine = ConsensusEngine()
        result = engine._is_similar(
            "same words here",
            "same words here",
            embedding_a=[1.0, 0.0, 0.0],
            embedding_b=None,
        )
        # Falls back to Jaccard — identical text → True
        assert result is True

    def test_empty_text_without_embeddings(self):
        """Empty texts without embeddings should not be considered similar."""
        engine = ConsensusEngine()
        assert engine._is_similar("", "") is False

    def test_single_word_jaccard_fallback(self):
        """Single identical word gives Jaccard=1.0, should be similar."""
        engine = ConsensusEngine()
        assert engine._is_similar("python", "python") is True


class TestPrimaryCortexSelection:
    """Tests for primary cortex (highest-weight model) getting priority."""

    def test_primary_gets_highest_weight(self):
        """The most capable model's fact should have higher final confidence."""
        engine = ConsensusEngine()
        updates = [
            HiveUpdate(
                source_model="gpt-5.2",
                new_facts=[{"content": "X is true"}],
                confidence=0.9,
            ),
            HiveUpdate(
                source_model="gpt-4o-mini",
                new_facts=[{"content": "X is probably true"}],
                confidence=0.7,
            ),
        ]
        model_weights = {"gpt-5.2": 2.0, "gpt-4o-mini": 0.8}
        state = HiveState()
        state.ensure_identity()
        counts = engine.merge_updates(updates, state, model_weights=model_weights)
        # At least one fact should be added
        assert counts["facts_added"] >= 1
        # The fact that was added should reflect the higher-weight model's influence
        # (weighted confidence should be higher than the simple average)
        for fact in state.facts:
            # With weight 2.0 for gpt-5.2 (conf 0.9) and 0.8 for mini (conf 0.7)
            # weighted = (0.9*2.0 + 0.7*0.8)/(2.0+0.8) = 2.36/2.8 ≈ 0.843
            # plus agreement boost 0.15 → ~0.993, capped at 1.0
            assert fact.confidence >= 0.8  # Weighted average is above simple 0.7

    def test_single_model_no_agreement_boost(self):
        """A single model's update should not get agreement boost."""
        engine = ConsensusEngine()
        updates = [
            HiveUpdate(
                source_model="model-a",
                new_facts=[{"content": "solo fact"}],
                confidence=0.6,
            ),
        ]
        state = HiveState()
        state.ensure_identity()
        engine.merge_updates(updates, state)
        # Confidence should be exactly 0.6 (no boost from agreement)
        assert state.facts[0].confidence == pytest.approx(0.6)


class TestHiveStateSimilarityUpgrade:
    """Tests for the upgraded _is_similar in HiveState."""

    def test_hive_state_embedding_similarity(self):
        """HiveState._is_similar should accept optional embedding params."""
        state = HiveState()
        state.ensure_identity()
        result = state._is_similar(
            "The car is fast",
            "The automobile is speedy",
            embedding_a=[0.9, 0.1, 0.0],
            embedding_b=[0.85, 0.15, 0.0],
        )
        assert result is True

    def test_hive_state_jaccard_fallback(self):
        """HiveState._is_similar still works without embeddings (backward compat)."""
        state = HiveState()
        state.ensure_identity()
        # Exact match → True
        assert state._is_similar("exact same text", "exact same text") is True
        # Completely different → False
        assert state._is_similar("alpha beta gamma", "delta epsilon zeta") is False

    def test_hive_state_custom_threshold(self):
        """HiveState._is_similar respects the threshold parameter."""
        state = HiveState()
        state.ensure_identity()
        # With threshold=0.0, everything should be similar
        assert state._is_similar("a b c", "d e f", threshold=0.0) is True
        # With threshold=1.0, only identical texts should match
        assert state._is_similar("a b c", "a b d", threshold=1.0) is False


class TestMoAConsensus:
    """Tests for Mixture of Agents consensus."""

    def test_moa_basic_merge(self):
        from vecna.orchestrator.moa import MoAConsensus

        moa = MoAConsensus()
        responses = {
            "gpt-5.2": "Python is great for data science because of NumPy and Pandas.",
            "claude-sonnet": "Python excels at data science with its rich ecosystem.",
            "gpt-4o-mini": "Python is good for data work.",
        }
        merged = moa.merge_responses(responses)
        # Amendment 9: Assert specific content, not just type/length
        # The sync fallback picks the longest response
        assert "Python" in merged
        assert "data science" in merged
        assert "NumPy" in merged

    def test_moa_single_response(self):
        """Single response should be returned as-is."""
        from vecna.orchestrator.moa import MoAConsensus

        moa = MoAConsensus()
        responses = {"model-a": "This is the only response."}
        merged = moa.merge_responses(responses)
        assert merged == "This is the only response."

    def test_moa_empty_responses(self):
        """Empty response dict should return empty string."""
        from vecna.orchestrator.moa import MoAConsensus

        moa = MoAConsensus()
        assert moa.merge_responses({}) == ""

    def test_moa_build_aggregator_prompt(self):
        """Aggregator prompt should contain all model responses."""
        from vecna.orchestrator.moa import MoAConsensus

        moa = MoAConsensus()
        responses = {
            "model-a": "Response A content",
            "model-b": "Response B content",
        }
        prompt = moa.build_aggregator_prompt(responses, original_task="Test query")
        # Should contain model names
        assert "model-a" in prompt
        assert "model-b" in prompt
        # Should contain response contents
        assert "Response A content" in prompt
        assert "Response B content" in prompt
        # Should contain original task
        assert "Test query" in prompt

    def test_moa_build_prompt_without_model_names(self):
        """Aggregator prompt without model names should use generic headers."""
        from vecna.orchestrator.moa import MoAConfig, MoAConsensus

        config = MoAConfig(include_model_names=False)
        moa = MoAConsensus(config=config)
        responses = {"model-a": "Content A"}
        prompt = moa.build_aggregator_prompt(responses)
        assert "model-a" not in prompt
        assert "### Response" in prompt
        assert "Content A" in prompt

    def test_moa_truncation(self):
        """Proposer responses should be truncated to max_proposer_tokens."""
        from vecna.orchestrator.moa import MoAConfig, MoAConsensus

        config = MoAConfig(max_proposer_tokens=10)
        moa = MoAConsensus(config=config)
        responses = {"model-a": "A" * 1000}
        prompt = moa.build_aggregator_prompt(responses)
        # The response portion should be truncated (10 chars of 'A')
        # Count occurrences of 'A' — should be exactly 10 in the response area
        # (prompt template text might contain 'A' too, so check truncated content)
        assert "AAAAAAAAAA" in prompt  # 10 A's
        assert "A" * 1000 not in prompt  # Full 1000 A's should NOT be present

    # === Error/Edge-case tests (Amendment 10) ===

    def test_moa_merge_picks_longest_as_fallback(self):
        """Sync fallback picks longest response (documented behavior)."""
        from vecna.orchestrator.moa import MoAConsensus

        moa = MoAConsensus()
        responses = {
            "short": "Hi.",
            "long": "This is a much longer and more detailed response with lots of content.",
        }
        merged = moa.merge_responses(responses)
        assert merged == responses["long"]

    def test_moa_config_defaults(self):
        """MoAConfig has sensible defaults."""
        from vecna.orchestrator.moa import MoAConfig

        config = MoAConfig()
        assert config.include_model_names is True
        assert config.max_proposer_tokens == 2000
        assert "synthesize" in config.aggregator_prompt.lower()


class TestMoAAsync:
    """Tests for async MoA functionality."""

    async def test_merge_responses_async_empty(self):
        """Async merge with empty responses returns empty string."""
        from vecna.orchestrator.moa import MoAConsensus

        moa = MoAConsensus()
        result = await moa.merge_responses_async({}, aggregator_adapter=None)
        assert result == ""

    async def test_merge_responses_async_single(self):
        """Async merge with single response returns it directly."""
        from vecna.orchestrator.moa import MoAConsensus

        moa = MoAConsensus()
        result = await moa.merge_responses_async(
            {"model-a": "Only one response"},
            aggregator_adapter=None,
        )
        assert result == "Only one response"

    async def test_merge_responses_async_calls_aggregator(self):
        """Async merge with multiple responses calls the aggregator adapter."""
        from vecna.orchestrator.moa import MoAConsensus

        moa = MoAConsensus()

        class MockAggregator:
            async def generate(self, prompt: str) -> str:
                return f"Synthesized: {len(prompt)} chars processed"

        result = await moa.merge_responses_async(
            {"model-a": "Response A", "model-b": "Response B"},
            aggregator_adapter=MockAggregator(),
            original_task="Test task",
        )
        assert "Synthesized:" in result
        assert "chars processed" in result


class TestConsensusClusteringWithEmbeddings:
    """Tests for clustering that uses the updated _is_similar."""

    def test_clustering_backward_compatible(self):
        """Clustering still works with text-only items (no embeddings)."""
        engine = ConsensusEngine()
        items = [
            {"content": "Python is great", "_source": "m1"},
            {"content": "Python is great", "_source": "m2"},
            {"content": "Java is different", "_source": "m3"},
        ]
        clusters = engine._cluster_similar_items(items)
        # "Python is great" should cluster together
        assert len(clusters) == 2
        # Find the Python cluster
        python_cluster = [c for c in clusters if any("Python" in i["content"] for i in c)]
        assert len(python_cluster) == 1
        assert len(python_cluster[0]) == 2  # Two "Python is great" items
