"""Identity growth engine for opinion formation and drift tracking."""

from dataclasses import dataclass, field
from typing import Dict, List, Set

from vecna.core.hive_state import HiveState


@dataclass
class IdentityGrowthResult:
    """Result of a single identity growth cycle."""

    opinions_updated: int = 0
    drift_delta: float = 0.0
    contradictions_processed: int = 0
    opinions: List[str] = field(default_factory=list)


class IdentityGrowthEngine:
    """Forms opinions from repeated beliefs and tracks personality drift."""

    def __init__(self, confidence_threshold: float = 0.8, min_shared_tokens: int = 2):
        self.confidence_threshold = confidence_threshold
        self.min_shared_tokens = min_shared_tokens

    def run(self, state: HiveState) -> IdentityGrowthResult:
        """Run one growth step and update the mutable self-model."""
        state.ensure_identity()
        model = state.self_model
        assert model is not None

        opinions = self._derive_opinions(state)
        drift_delta = self._compute_drift_delta(state, opinions)
        unresolved_contradictions = sum(
            1 for item in state.contradictions if item.resolution_status == "unresolved"
        )
        previous_unresolved = state.identity_growth_metrics.get("last_unresolved_contradictions", 0)
        if isinstance(previous_unresolved, int):
            contradictions_processed = max(0, unresolved_contradictions - previous_unresolved)
        else:
            contradictions_processed = unresolved_contradictions

        if opinions:
            model.narrative = self._merge_opinions_into_narrative(model.narrative, opinions)

        model.contradictions_seen = max(model.contradictions_seen, unresolved_contradictions)
        model.confidence_about_self = self._updated_self_confidence(
            current=model.confidence_about_self,
            opinions_updated=len(opinions),
            contradictions_processed=contradictions_processed,
        )

        state.record_identity_growth(
            drift_delta=drift_delta,
            opinions=opinions,
            contradictions_processed=contradictions_processed,
            unresolved_contradictions=unresolved_contradictions,
        )

        return IdentityGrowthResult(
            opinions_updated=len(opinions),
            drift_delta=drift_delta,
            contradictions_processed=contradictions_processed,
            opinions=opinions,
        )

    def _derive_opinions(self, state: HiveState) -> List[str]:
        high_conf_beliefs = [
            belief.content.strip()
            for belief in state.beliefs
            if belief.confidence >= self.confidence_threshold and belief.content.strip()
        ]
        if len(high_conf_beliefs) < 2:
            return []

        tokenized: List[Set[str]] = [self._tokenize(text) for text in high_conf_beliefs]
        shared_counts: Dict[str, int] = {}
        for tokens in tokenized:
            for token in tokens:
                shared_counts[token] = shared_counts.get(token, 0) + 1

        repeated_tokens = {token for token, count in shared_counts.items() if count >= 2}
        if not repeated_tokens:
            return []

        opinions: List[str] = []
        for text, tokens in zip(high_conf_beliefs, tokenized):
            shared = len(tokens & repeated_tokens)
            if shared >= self.min_shared_tokens and text not in opinions:
                opinions.append(text)

        return opinions[:3]

    def _compute_drift_delta(self, state: HiveState, new_opinions: List[str]) -> float:
        previous_raw = state.identity_growth_metrics.get("last_opinions", [])
        previous = {item.lower() for item in previous_raw if isinstance(item, str)}
        current = {item.lower() for item in new_opinions}

        if not previous or not current:
            return 0.0

        union = previous | current
        if not union:
            return 0.0

        overlap = previous & current
        return 1.0 - (len(overlap) / len(union))

    def _merge_opinions_into_narrative(self, narrative: str, opinions: List[str]) -> str:
        marker = "Emerging opinions:"
        base = narrative.split(marker)[0].strip() if marker in narrative else narrative.strip()
        opinion_text = "; ".join(opinions)
        if base:
            return f"{base} {marker} {opinion_text}."
        return f"{marker} {opinion_text}."

    def _updated_self_confidence(
        self, current: float, opinions_updated: int, contradictions_processed: int
    ) -> float:
        adjusted = current + (0.02 * opinions_updated) - (0.01 * contradictions_processed)
        return max(0.0, min(1.0, adjusted))

    def _tokenize(self, text: str) -> Set[str]:
        tokens = []
        for word in text.lower().replace("-", " ").split():
            cleaned = "".join(ch for ch in word if ch.isalpha())
            if len(cleaned) >= 4:
                tokens.append(cleaned)
        return set(tokens)
