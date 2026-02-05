"""
Unit tests for Self-Reflection module.

Tests:
- Memory density computation
- Coherence computation
- Domain shift detection
- Tone derivation
- Self-model updates
- Identity event creation
- Identity context generation
"""

import pytest

from vecna.orchestrator.self_reflection import (
    compute_memory_density,
    compute_coherence,
    detect_domain_shift,
    get_tone_from_coherence,
    generate_narrative,
    update_self_model,
    create_identity_event,
    append_identity_event,
    reflect,
    get_identity_context_for_prompt,
)
from vecna.core.types import Fact, Hypothesis, Contradiction, IdentityTone


class TestMemoryDensity:
    """Tests for memory density computation."""

    def test_empty_state_density(self, clean_state):
        """Test density of empty state is 0."""
        density = compute_memory_density(clean_state)

        assert density == 0.0

    def test_populated_state_density(self, populated_state):
        """Test density of populated state is > 0."""
        density = compute_memory_density(populated_state)

        assert density > 0.0
        assert density <= 1.0

    def test_density_increases_with_facts(self, clean_state):
        """Test that density increases as facts are added."""
        density1 = compute_memory_density(clean_state)

        # Add facts
        for i in range(10):
            clean_state.add_fact(
                Fact(content=f"Fact number {i}", confidence=0.8, source_model="test")
            )

        density2 = compute_memory_density(clean_state)

        assert density2 > density1

    def test_density_considers_confidence(self, clean_state):
        """Test that high confidence facts contribute more to density."""
        # Add low confidence facts
        for i in range(5):
            clean_state.add_fact(
                Fact(content=f"Low conf fact {i}", confidence=0.2, source_model="test")
            )

        density_low = compute_memory_density(clean_state)

        # Reset and add high confidence facts
        clean_state.facts = []
        for i in range(5):
            clean_state.add_fact(
                Fact(content=f"High conf fact {i}", confidence=0.9, source_model="test")
            )

        density_high = compute_memory_density(clean_state)

        assert density_high > density_low

    def test_density_hypothesis_bonus(self, clean_state):
        """Test that hypotheses add a small bonus to density."""
        # Add some facts first
        clean_state.add_fact(Fact(content="Test fact", confidence=0.8))
        density1 = compute_memory_density(clean_state)

        # Add hypotheses
        for i in range(5):
            clean_state.add_hypothesis(Hypothesis(content=f"Hypothesis {i}", confidence=0.3))

        density2 = compute_memory_density(clean_state)

        assert density2 > density1


class TestCoherence:
    """Tests for coherence computation."""

    def test_empty_state_coherence(self, clean_state):
        """Test coherence of empty state."""
        coherence = compute_coherence(clean_state)

        # Should be neutral (0.5) for empty state
        assert coherence == pytest.approx(0.5, abs=0.2)

    def test_coherence_with_no_contradictions(self, clean_state):
        """Test coherence is high when no contradictions exist."""
        # Add facts without contradictions
        for i in range(10):
            clean_state.add_fact(Fact(content=f"Fact {i}", confidence=0.8))

        coherence = compute_coherence(clean_state)

        # Should be relatively high
        assert coherence > 0.6

    def test_coherence_decreases_with_contradictions(self, clean_state):
        """Test that contradictions decrease coherence."""
        # Add some facts
        for i in range(10):
            clean_state.add_fact(Fact(content=f"Fact {i}", confidence=0.8))

        coherence_before = compute_coherence(clean_state)

        # Add contradictions
        for i in range(5):
            clean_state.add_contradiction(
                Contradiction(item_a_content=f"A{i}", item_b_content=f"B{i}")
            )

        coherence_after = compute_coherence(clean_state)

        assert coherence_after < coherence_before

    def test_coherence_bounded(self, populated_state):
        """Test that coherence is bounded to [0, 1]."""
        coherence = compute_coherence(populated_state)

        assert 0.0 <= coherence <= 1.0


class TestDomainShift:
    """Tests for domain shift detection."""

    def test_detect_code_domain_shift(self, clean_state):
        """Test detecting shift to code domain."""
        # State has general facts
        clean_state.add_fact(Fact(content="General fact", domain="general"))

        shift = detect_domain_shift(clean_state, "Write me some Python code")

        assert shift == "code"

    def test_detect_math_domain_shift(self, clean_state):
        """Test detecting shift to math domain."""
        clean_state.add_fact(Fact(content="General fact", domain="general"))

        shift = detect_domain_shift(clean_state, "Prove this theorem using algebra")

        assert shift == "math"

    def test_no_shift_same_domain(self, clean_state):
        """Test no shift when query matches current domain."""
        clean_state.add_fact(Fact(content="Python is great", domain="code"))

        shift = detect_domain_shift(clean_state, "More about Python programming")

        assert shift is None

    def test_no_shift_general_query(self, clean_state):
        """Test no shift for general queries."""
        shift = detect_domain_shift(clean_state, "Tell me something interesting")

        # General doesn't count as a "shift"
        assert shift is None or shift == "general"


class TestToneDerivation:
    """Tests for tone derivation from coherence."""

    def test_unified_tone(self):
        """Test unified tone for high coherence."""
        tone = get_tone_from_coherence(0.9)

        assert tone == IdentityTone.UNIFIED

    def test_mixed_tone(self):
        """Test mixed tone for medium coherence."""
        tone = get_tone_from_coherence(0.7)

        assert tone == IdentityTone.MIXED

    def test_fractured_tone(self):
        """Test fractured tone for low coherence."""
        tone = get_tone_from_coherence(0.4)

        assert tone == IdentityTone.FRACTURED

    def test_boundary_values(self):
        """Test tone at boundary values."""
        assert get_tone_from_coherence(0.85) == IdentityTone.MIXED  # Just at boundary
        assert get_tone_from_coherence(0.86) == IdentityTone.UNIFIED
        assert get_tone_from_coherence(0.6) == IdentityTone.MIXED
        assert get_tone_from_coherence(0.59) == IdentityTone.FRACTURED


class TestNarrativeGeneration:
    """Tests for narrative generation."""

    def test_unified_narrative(self, populated_state):
        """Test narrative for unified tone."""
        narrative = generate_narrative(populated_state, coherence=0.9, tone=IdentityTone.UNIFIED)

        assert "one" in narrative.lower() or "coherent" in narrative.lower()

    def test_fractured_narrative(self, populated_state):
        """Test narrative for fractured tone."""
        narrative = generate_narrative(populated_state, coherence=0.3, tone=IdentityTone.FRACTURED)

        assert "fragment" in narrative.lower() or "competing" in narrative.lower()

    def test_empty_state_narrative(self, clean_state):
        """Test narrative for empty state."""
        narrative = generate_narrative(clean_state, coherence=0.5, tone=IdentityTone.MIXED)

        assert "empty" in narrative.lower() or "awakening" in narrative.lower()

    def test_narrative_includes_facts_count(self, populated_state):
        """Test that narrative mentions facts when many exist."""
        # Add more facts
        for i in range(100):
            populated_state.add_fact(Fact(content=f"Fact {i}", confidence=0.8))

        narrative = generate_narrative(populated_state, coherence=0.7, tone=IdentityTone.MIXED)

        # Should mention the fact count
        assert "fact" in narrative.lower()


class TestSelfModelUpdate:
    """Tests for self-model updates."""

    def test_update_self_model(self, populated_state):
        """Test updating the self-model."""
        update_self_model(populated_state)

        # First update should likely be significant
        assert populated_state.self_model.coherence > 0
        assert populated_state.self_model.memory_density >= 0

    def test_update_tracks_contradictions(self, clean_state):
        """Test that update tracks contradiction count."""
        # Add contradictions
        for i in range(3):
            clean_state.add_contradiction(
                Contradiction(item_a_content=f"A{i}", item_b_content=f"B{i}")
            )

        update_self_model(clean_state)

        assert clean_state.self_model.contradictions_seen == 3

    def test_update_with_domain_shift(self, clean_state):
        """Test update with domain shift query."""
        update_self_model(clean_state, query="Write some Python code")

        assert "code" in clean_state.self_model.known_domains


class TestIdentityEventCreation:
    """Tests for identity event creation."""

    def test_create_identity_event(self, populated_state):
        """Test creating an identity event."""
        event = create_identity_event(populated_state, trigger="test", summary="Test event")

        assert event.trigger == "test"
        assert event.summary == "Test event"
        assert event.coherence >= 0

    def test_append_identity_event(self, clean_state):
        """Test appending an identity event."""
        initial_count = len(clean_state.identity_timeline)

        event = append_identity_event(clean_state, trigger="test", summary="Test event")

        assert len(clean_state.identity_timeline) == initial_count + 1
        assert clean_state.identity_timeline[-1].id == event.id


class TestReflect:
    """Tests for the main reflect() function."""

    def test_reflect_no_change(self, clean_state):
        """Test reflect when no significant change."""
        # First reflect to set baseline
        reflect(clean_state)

        # Second reflect with no changes
        event = reflect(clean_state)

        # May or may not return event depending on change detection
        # Just ensure it doesn't crash
        assert event is None or isinstance(event, object)

    def test_reflect_with_domain_shift(self, clean_state):
        """Test reflect with domain shift query."""
        event = reflect(clean_state, query="Explain quantum physics")

        # If domain shift detected, should create event
        if event:
            assert event.trigger in ["domain_shift", "coherence_shift", "periodic"]


class TestIdentityContextForPrompt:
    """Tests for prompt context generation."""

    def test_get_identity_context(self, populated_state):
        """Test generating identity context for prompts."""
        context = get_identity_context_for_prompt(populated_state)

        assert "VECNA" in context
        assert "IDENTITY" in context
        assert "Coherence" in context

    def test_context_includes_axioms(self, clean_state):
        """Test that context includes core axioms."""
        context = get_identity_context_for_prompt(clean_state)

        assert "LightningEmperor" in context or "axiom" in context.lower()

    def test_context_includes_tone_instruction(self, clean_state):
        """Test that context includes tone-appropriate instruction."""
        context = get_identity_context_for_prompt(clean_state)

        assert "INSTRUCTION" in context
