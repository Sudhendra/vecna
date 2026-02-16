"""Unit tests for identity growth opinion and drift tracking."""

import pytest

from vecna.core.types import Belief, Contradiction
from vecna.orchestrator.identity_growth import IdentityGrowthEngine


class TestIdentityGrowthEngine:
    """Tests for identity growth updates."""

    def test_identity_growth_forms_opinion_from_repeated_evidence(self, clean_state):
        """Repeated high-confidence beliefs should form an opinion."""
        clean_state.add_belief(
            Belief(
                content="Prefer explicit error messages over silent failures",
                confidence=0.9,
                source_model="a",
            )
        )
        clean_state.add_belief(
            Belief(
                content="Explicit error messages are better than silent failures",
                confidence=0.92,
                source_model="b",
            )
        )

        result = IdentityGrowthEngine().run(clean_state)

        assert result.opinions_updated >= 1
        assert "Emerging opinions" in clean_state.self_model.narrative
        assert "explicit error messages" in clean_state.self_model.narrative.lower()

    def test_identity_growth_tracks_personality_drift_metric(self, clean_state):
        """Drift delta should increase when opinion profile changes."""
        clean_state.add_belief(
            Belief(
                content="Prefer concise responses for direct requests",
                confidence=0.9,
                source_model="a",
            )
        )
        clean_state.add_belief(
            Belief(
                content="Direct requests should get concise responses",
                confidence=0.91,
                source_model="b",
            )
        )

        engine = IdentityGrowthEngine()
        first = engine.run(clean_state)

        clean_state.add_belief(
            Belief(
                content="Prefer step-by-step guidance for multi-part tasks",
                confidence=0.93,
                source_model="c",
            )
        )
        clean_state.add_belief(
            Belief(
                content="Multi-part tasks should receive step-by-step guidance",
                confidence=0.95,
                source_model="d",
            )
        )

        second = engine.run(clean_state)

        assert first.drift_delta == 0.0
        assert second.drift_delta > 0.0

    def test_contradiction_driven_growth_adjusts_self_model_not_soul_file(self, clean_state):
        """Contradiction processing should update self-model while preserving kernel axioms."""
        original_axioms = list(clean_state.identity_kernel.axioms)
        clean_state.add_contradiction(
            Contradiction(item_a_content="A", item_b_content="B", resolution_status="unresolved")
        )
        clean_state.add_contradiction(
            Contradiction(item_a_content="C", item_b_content="D", resolution_status="unresolved")
        )

        result = IdentityGrowthEngine().run(clean_state)

        assert result.contradictions_processed == 2
        assert clean_state.self_model.contradictions_seen >= 2
        assert clean_state.identity_kernel.axioms == original_axioms

    def test_same_unresolved_contradictions_do_not_repeatedly_penalize_confidence(
        self, clean_state
    ):
        """Existing unresolved contradictions should not reduce confidence again on repeat runs."""
        clean_state.add_contradiction(
            Contradiction(item_a_content="A", item_b_content="B", resolution_status="unresolved")
        )

        engine = IdentityGrowthEngine()
        first = engine.run(clean_state)
        confidence_after_first = clean_state.self_model.confidence_about_self

        second = engine.run(clean_state)
        confidence_after_second = clean_state.self_model.confidence_about_self

        assert first.contradictions_processed == 1
        assert second.contradictions_processed == 0
        assert confidence_after_second == pytest.approx(confidence_after_first)

    def test_empty_current_opinions_does_not_create_max_drift(self, clean_state):
        """Low-signal cycles with no opinions should not force drift to 1.0."""
        clean_state.add_belief(
            Belief(
                content="Prefer explicit error messages over silent failures",
                confidence=0.9,
                source_model="a",
            )
        )
        clean_state.add_belief(
            Belief(
                content="Explicit error messages are better than silent failures",
                confidence=0.92,
                source_model="b",
            )
        )

        engine = IdentityGrowthEngine()
        first = engine.run(clean_state)
        assert first.opinions_updated > 0

        clean_state.beliefs = []

        second = engine.run(clean_state)

        assert second.opinions_updated == 0
        assert second.drift_delta == 0.0
