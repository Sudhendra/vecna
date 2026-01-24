"""
Consensus Engine: Merging multiple model updates into coherent hive state.

This is where "many minds become one" — the consensus mechanism that
reconciles different model outputs into a unified mental state.
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict
import re

from vecna.core.types import HiveUpdate, Fact, Belief, Contradiction
from vecna.core.hive_state import HiveState
from vecna.adapters.base import BaseAdapter


@dataclass
class ConsensusConfig:
    """Configuration for consensus behavior."""

    # Minimum confidence to accept a fact
    min_fact_confidence: float = 0.3

    # Minimum confidence to accept a belief
    min_belief_confidence: float = 0.2

    # How much to boost confidence when multiple models agree
    agreement_boost: float = 0.15

    # How much to reduce confidence on contradiction
    contradiction_penalty: float = 0.2

    # Similarity threshold for detecting duplicates/conflicts
    similarity_threshold: float = 0.7

    # Whether to use domain-weighted voting
    use_domain_weights: bool = True


class ConsensusEngine:
    """
    Merges updates from multiple models into a coherent hive state.

    The consensus engine is the "glue" that makes separate model outputs
    feel like thoughts from a single mind.
    """

    def __init__(self, config: Optional[ConsensusConfig] = None):
        self.config = config or ConsensusConfig()

    def merge_updates(
        self,
        updates: List[HiveUpdate],
        state: HiveState,
        model_weights: Optional[Dict[str, float]] = None,
    ) -> Dict[str, int]:
        """
        Merge multiple updates into the hive state.

        This is the core "hive mind" operation — taking thoughts from
        multiple models and fusing them into one coherent state.

        Returns counts of changes made.
        """
        if not updates:
            return {}

        model_weights = model_weights or {}

        # Collect all proposed items
        all_facts = []
        all_beliefs = []
        all_hypotheses = []
        all_questions = []

        for update in updates:
            weight = model_weights.get(update.source_model, 1.0)

            for fact in update.new_facts:
                fact["_source"] = update.source_model
                fact["_weight"] = weight
                fact["_base_confidence"] = fact.get("confidence", update.confidence)
                all_facts.append(fact)

            for belief in update.belief_changes:
                belief["_source"] = update.source_model
                belief["_weight"] = weight
                belief["_base_confidence"] = belief.get("confidence", update.confidence)
                all_beliefs.append(belief)

            for hyp in update.new_hypotheses:
                hyp["_source"] = update.source_model
                all_hypotheses.append(hyp)

            for q in update.open_questions:
                q["_source"] = update.source_model
                all_questions.append(q)

        counts = {
            "facts_added": 0,
            "beliefs_added": 0,
            "hypotheses_added": 0,
            "questions_added": 0,
            "contradictions_found": 0,
            "agreements_found": 0,
        }

        # Process facts with consensus
        fact_clusters = self._cluster_similar_items(all_facts)
        for cluster in fact_clusters:
            merged_fact, is_contradiction = self._merge_fact_cluster(cluster)

            if is_contradiction:
                # Record the contradiction
                if len(cluster) >= 2:
                    contradiction = Contradiction(
                        item_a_content=cluster[0].get("content", ""),
                        item_b_content=cluster[1].get("content", ""),
                        source_models=[c["_source"] for c in cluster],
                    )
                    state.add_contradiction(contradiction)
                    counts["contradictions_found"] += 1
            else:
                fact = Fact(
                    content=merged_fact["content"],
                    confidence=merged_fact["confidence"],
                    source_model=merged_fact.get("sources", "hive"),
                    evidence=merged_fact.get("evidence", ""),
                    domain=merged_fact.get("domain", "general"),
                )
                if state.add_fact(fact):
                    counts["facts_added"] += 1

                if len(cluster) > 1:
                    counts["agreements_found"] += 1

        # Process beliefs with consensus
        belief_clusters = self._cluster_similar_items(all_beliefs)
        for cluster in belief_clusters:
            merged_belief = self._merge_belief_cluster(cluster)

            belief = Belief(
                content=merged_belief["content"],
                confidence=merged_belief["confidence"],
                source_model=merged_belief.get("sources", "hive"),
                reasoning=merged_belief.get("reasoning", ""),
            )
            if state.add_belief(belief):
                counts["beliefs_added"] += 1

        # Process hypotheses (keep all, they're exploratory)
        for hyp in all_hypotheses:
            from vecna.core.types import Hypothesis

            hypothesis = Hypothesis(
                content=hyp.get("content", ""),
                confidence=hyp.get("confidence", 0.3),
                source_model=hyp["_source"],
                exploration_notes=hyp.get("notes", ""),
            )
            state.add_hypothesis(hypothesis)
            counts["hypotheses_added"] += 1

        # Process questions (dedupe similar ones)
        seen_questions = set()
        for q in all_questions:
            q_text = q.get("question", "").lower().strip()
            if q_text and q_text not in seen_questions:
                seen_questions.add(q_text)
                from vecna.core.types import OpenQuestion

                question = OpenQuestion(
                    question=q.get("question", ""),
                    context=q.get("context", ""),
                    priority=q.get("priority", "medium"),
                )
                state.add_open_question(question)
                counts["questions_added"] += 1

        # Update state version
        state.version += 1

        return counts

    def _cluster_similar_items(self, items: List[Dict]) -> List[List[Dict]]:
        """
        Cluster similar items together for consensus voting.
        Items in the same cluster are about the same thing.
        """
        if not items:
            return []

        clusters = []
        used = set()

        for i, item in enumerate(items):
            if i in used:
                continue

            cluster = [item]
            used.add(i)

            content_i = item.get("content", "").lower()

            for j, other in enumerate(items):
                if j in used:
                    continue

                content_j = other.get("content", "").lower()

                if self._is_similar(content_i, content_j):
                    cluster.append(other)
                    used.add(j)

            clusters.append(cluster)

        return clusters

    def _is_similar(self, text1: str, text2: str) -> bool:
        """Check if two texts are semantically similar."""
        words1 = set(text1.split())
        words2 = set(text2.split())

        if not words1 or not words2:
            return False

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        jaccard = intersection / union if union > 0 else 0
        return jaccard >= self.config.similarity_threshold

    def _merge_fact_cluster(self, cluster: List[Dict]) -> Tuple[Dict, bool]:
        """
        Merge a cluster of similar facts into one.
        Returns (merged_fact, is_contradiction).
        """
        if len(cluster) == 1:
            item = cluster[0]
            return {
                "content": item.get("content", ""),
                "confidence": item.get("_base_confidence", 0.5),
                "evidence": item.get("evidence", ""),
                "domain": item.get("domain", "general"),
                "sources": item.get("_source", ""),
            }, False

        # Check for contradictions (conflicting claims)
        # Simple heuristic: if one contains "not" or negation and others don't
        has_negation = []
        for item in cluster:
            content = item.get("content", "").lower()
            is_negative = any(
                neg in content
                for neg in [" not ", "n't ", "never ", "false", "incorrect"]
            )
            has_negation.append(is_negative)

        # If mixed negations, it's a contradiction
        if any(has_negation) and not all(has_negation):
            return {}, True

        # Agreement: boost confidence
        # Take the most detailed content
        best_content = max(cluster, key=lambda x: len(x.get("content", "")))

        # Weighted confidence
        total_weight = sum(c.get("_weight", 1.0) for c in cluster)
        weighted_conf = (
            sum(c.get("_base_confidence", 0.5) * c.get("_weight", 1.0) for c in cluster)
            / total_weight
            if total_weight > 0
            else 0.5
        )

        # Boost for agreement
        boost = self.config.agreement_boost * (len(cluster) - 1)
        final_confidence = min(1.0, weighted_conf + boost)

        sources = ", ".join(set(c.get("_source", "") for c in cluster))

        return {
            "content": best_content.get("content", ""),
            "confidence": final_confidence,
            "evidence": best_content.get("evidence", ""),
            "domain": best_content.get("domain", "general"),
            "sources": sources,
        }, False

    def _merge_belief_cluster(self, cluster: List[Dict]) -> Dict:
        """Merge a cluster of similar beliefs."""
        if len(cluster) == 1:
            item = cluster[0]
            return {
                "content": item.get("content", ""),
                "confidence": item.get("_base_confidence", 0.5),
                "reasoning": item.get("reasoning", ""),
                "sources": item.get("_source", ""),
            }

        # Take most detailed
        best_content = max(cluster, key=lambda x: len(x.get("content", "")))

        # Weighted confidence with agreement boost
        total_weight = sum(c.get("_weight", 1.0) for c in cluster)
        weighted_conf = (
            sum(c.get("_base_confidence", 0.5) * c.get("_weight", 1.0) for c in cluster)
            / total_weight
            if total_weight > 0
            else 0.5
        )

        boost = self.config.agreement_boost * (len(cluster) - 1)
        final_confidence = min(1.0, weighted_conf + boost)

        # Combine reasoning
        reasonings = [c.get("reasoning", "") for c in cluster if c.get("reasoning")]
        combined_reasoning = " | ".join(reasonings[:3]) if reasonings else ""

        sources = ", ".join(set(c.get("_source", "") for c in cluster))

        return {
            "content": best_content.get("content", ""),
            "confidence": final_confidence,
            "reasoning": combined_reasoning,
            "sources": sources,
        }


class DomainRouter:
    """
    Routes tasks to appropriate expert models based on domain.

    The router ensures that domain-specific questions get answered
    by the most capable models while maintaining hive coherence.
    """

    # Domain keywords for routing
    DOMAIN_KEYWORDS = {
        "code": [
            "code",
            "programming",
            "function",
            "class",
            "bug",
            "error",
            "python",
            "javascript",
            "api",
            "software",
        ],
        "math": [
            "math",
            "equation",
            "calculate",
            "formula",
            "proof",
            "theorem",
            "algebra",
            "calculus",
            "statistics",
        ],
        "science": [
            "biology",
            "chemistry",
            "physics",
            "experiment",
            "hypothesis",
            "research",
            "scientific",
            "molecule",
            "protein",
        ],
        "creative": [
            "story",
            "write",
            "creative",
            "poem",
            "fiction",
            "narrative",
            "character",
            "plot",
        ],
        "analysis": [
            "analyze",
            "evaluate",
            "compare",
            "assess",
            "review",
            "critique",
            "examine",
        ],
        "general": [],  # Fallback
    }

    def __init__(self, adapters: List[BaseAdapter]):
        self.adapters = {a.name: a for a in adapters}
        self.domain_to_adapters: Dict[str, List[str]] = defaultdict(list)

        for adapter in adapters:
            self.domain_to_adapters[adapter.domain].append(adapter.name)
            self.domain_to_adapters["general"].append(adapter.name)

    def detect_domains(self, task: str) -> List[str]:
        """Detect which domains a task belongs to."""
        task_lower = task.lower()
        detected = []

        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            if domain == "general":
                continue
            if any(kw in task_lower for kw in keywords):
                detected.append(domain)

        if not detected:
            detected = ["general"]

        return detected

    def select_adapters(
        self, task: str, max_adapters: int = 3, always_include_general: bool = True
    ) -> List[BaseAdapter]:
        """
        Select the best adapters for a given task.
        """
        domains = self.detect_domains(task)
        selected_names = set()

        # Add domain specialists
        for domain in domains:
            for name in self.domain_to_adapters.get(domain, []):
                selected_names.add(name)

        # Always include at least one general model
        if always_include_general:
            for name in self.domain_to_adapters.get("general", []):
                adapter = self.adapters[name]
                if adapter.domain == "general":
                    selected_names.add(name)
                    break

        # Limit to max
        selected_names = list(selected_names)[:max_adapters]

        return [self.adapters[name] for name in selected_names]

    def get_all_adapters(self) -> List[BaseAdapter]:
        """Get all registered adapters."""
        return list(self.adapters.values())
