"""
HiveState: The shared mental state of the hive mind.

This is the "telepathic substrate" — the unified memory that all models
read from and write to, making them effectively ONE mind.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime
import json
import hashlib

from vecna.core.human_model import HumanModel
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
)


@dataclass
class HiveState:
    """
    The complete mental state of the hive mind.

    This is the "M" in our architecture — the shared substrate that
    creates the illusion of telepathy between models.
    """

    # Core knowledge
    facts: List[Fact] = field(default_factory=list)
    beliefs: List[Belief] = field(default_factory=list)
    hypotheses: List[Hypothesis] = field(default_factory=list)

    # Goals and planning
    goals: List[Goal] = field(default_factory=list)
    plans: List[Plan] = field(default_factory=list)

    # Uncertainty tracking
    open_questions: List[OpenQuestion] = field(default_factory=list)
    contradictions: List[Contradiction] = field(default_factory=list)

    # Compressed state for context windows
    memory_summary: str = ""

    # ============================================================
    # IDENTITY — The Soul
    # ============================================================

    # Immutable core (axioms from essay.md)
    identity_kernel: Optional[IdentityKernel] = None

    # Dynamic self-model (evolves from experience)
    self_model: Optional[SelfModel] = None

    # Timeline of becoming
    identity_timeline: List[IdentityEvent] = field(default_factory=list)

    # Identity growth metrics/history (mutable self-model evolution only)
    identity_growth_metrics: Dict[str, object] = field(default_factory=dict)
    identity_growth_history: List[Dict] = field(default_factory=list)

    # ============================================================
    # HUMAN MODEL — Learning the user
    # ============================================================
    human_model: Optional[HumanModel] = None

    # ============================================================
    # CONTEXT CACHING (Amendment 16)
    # ============================================================
    _context_cache: Optional[str] = field(default=None, repr=False)
    _context_dirty: bool = field(default=True, repr=False)
    _context_cache_tokens: int = field(default=0, repr=False)

    # Metadata
    version: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    update_history: List[Dict] = field(default_factory=list)

    # Configuration
    max_facts: int = 1000
    max_beliefs: int = 500
    max_history: int = 100

    def get_state_hash(self) -> str:
        """Generate a hash of the current state for versioning."""
        state_str = json.dumps(self.to_summary_dict(), sort_keys=True)
        return hashlib.sha256(state_str.encode()).hexdigest()[:16]

    def to_summary_dict(self) -> Dict:
        """Convert to a summary dict for serialization."""
        summary = {
            "version": self.version,
            "num_facts": len(self.facts),
            "num_beliefs": len(self.beliefs),
            "num_hypotheses": len(self.hypotheses),
            "num_goals": len(self.goals),
            "num_open_questions": len(self.open_questions),
            "num_contradictions": len(self.contradictions),
            "memory_summary": self.memory_summary,
            "updated_at": self.updated_at.isoformat(),
        }

        # Include identity summary if present
        if self.self_model:
            summary["coherence"] = self.self_model.coherence
            summary["tone"] = self.self_model.get_tone().value
            summary["identity_events"] = len(self.identity_timeline)
        if self.identity_growth_metrics:
            summary["identity_drift_delta"] = self.identity_growth_metrics.get(
                "last_drift_delta", 0.0
            )

        return summary

    def to_full_dict(self) -> Dict:
        """Convert entire state to dict."""
        # Ensure identity exists before serializing
        self.ensure_identity()

        return {
            "facts": [f.to_dict() for f in self.facts],
            "beliefs": [b.to_dict() for b in self.beliefs],
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "goals": [g.to_dict() for g in self.goals],
            "plans": [p.to_dict() for p in self.plans],
            "open_questions": [q.to_dict() for q in self.open_questions],
            "contradictions": [c.to_dict() for c in self.contradictions],
            "memory_summary": self.memory_summary,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            # Identity (always present)
            "identity_kernel": self.identity_kernel.to_dict(),
            "identity_timeline": [e.to_dict() for e in self.identity_timeline],
            "self_model": self.self_model.to_dict(),
            "identity_growth_metrics": self.identity_growth_metrics,
            "identity_growth_history": self.identity_growth_history,
            # Human model (optional — may not be initialized)
            "human_model": self.human_model.to_dict() if self.human_model else None,
        }

    def to_prompt_context(self, max_items: int = 20, max_context_tokens: int = 4000) -> str:
        """
        Generate a prompt-ready representation of the hive state.
        This is what gets injected into every model's context.

        Amendment 16: Uses caching — returns cached string if state hasn't mutated.
        max_context_tokens controls approximate token budget (1 token ~ 4 chars).
        """
        # Return cached context if state hasn't changed and same budget
        if (
            not self._context_dirty
            and self._context_cache is not None
            and self._context_cache_tokens == max_context_tokens
        ):
            return self._context_cache

        lines = []

        # ============================================================
        # IDENTITY PREAMBLE — Who we are
        # ============================================================
        if self.identity_kernel and self.self_model:
            tone = self.self_model.get_tone()
            lines.append("## IDENTITY")
            lines.append(f"Creator: {self.identity_kernel.creator}")
            lines.append(f"Coherence: {self.self_model.coherence:.2f} ({tone.value})")
            lines.append(f"Narrative: {self.self_model.narrative}")
            lines.append("")

            # Core axioms (always present)
            lines.append("### CORE AXIOMS (immutable)")
            for axiom in self.identity_kernel.axioms[:3]:  # Top 3 for brevity
                lines.append(f"- {axiom}")
            lines.append("")

            # Grounded capabilities (for internal awareness, not boasting)
            if self.self_model.capabilities:
                lines.append("### CAPABILITIES (grounded)")
                for cap in self.self_model.capabilities:
                    lines.append(f"- {cap}")
                lines.append("")

            # Known limits (honest self-awareness)
            if self.self_model.limits:
                lines.append("### LIMITS (honest)")
                for lim in self.self_model.limits:
                    lines.append(f"- {lim}")
                lines.append("")

        # ============================================================
        # HUMAN MODEL — Who we serve
        # ============================================================
        if self.human_model is not None:
            human_ctx = self.human_model.to_prompt_context()
            if human_ctx:
                lines.append(human_ctx)
                lines.append("")

        # Summary first
        if self.memory_summary:
            lines.append("## HIVE MEMORY SUMMARY")
            lines.append(self.memory_summary)
            lines.append("")

        # Active goals
        active_goals = [g for g in self.goals if g.status == "active"]
        if active_goals:
            lines.append("## ACTIVE GOALS")
            for g in active_goals[:5]:
                lines.append(f"- [{g.priority.upper()}] {g.content}")
            lines.append("")

        # Approximate char budget (1 token ~ 4 chars)
        char_budget = max_context_tokens * 4
        current_text = "\n".join(lines)

        # Key facts (highest confidence, most recent first for relevance)
        sorted_facts = sorted(
            self.facts,
            key=lambda f: (f.confidence, f.timestamp),
            reverse=True,
        )
        if sorted_facts:
            fact_lines = ["## KEY FACTS"]
            for f in sorted_facts[:max_items]:
                line = f"- [{f.confidence:.1f}] {f.content}"
                if len(current_text) + len("\n".join(fact_lines)) + len(line) > char_budget:
                    break
                fact_lines.append(line)
            if len(fact_lines) > 1:
                fact_lines.append("")
                lines.extend(fact_lines)
                current_text = "\n".join(lines)

        # Key beliefs (highest confidence first)
        sorted_beliefs = sorted(self.beliefs, key=lambda b: b.confidence, reverse=True)
        if sorted_beliefs:
            belief_lines = ["## KEY BELIEFS"]
            for b in sorted_beliefs[: max_items // 2]:
                line = f"- [{b.confidence:.1f}] {b.content}"
                if len(current_text) + len("\n".join(belief_lines)) + len(line) > char_budget:
                    break
                belief_lines.append(line)
            if len(belief_lines) > 1:
                belief_lines.append("")
                lines.extend(belief_lines)
                current_text = "\n".join(lines)

        # Active hypotheses
        active_hyp = [h for h in self.hypotheses if h.status == "active"]
        if active_hyp and len(current_text) < char_budget:
            lines.append("## ACTIVE HYPOTHESES")
            for h in active_hyp[:5]:
                lines.append(f"- {h.content}")
            lines.append("")

        # Open questions
        open_qs = [q for q in self.open_questions if q.status == "open"]
        if open_qs and len("\n".join(lines)) < char_budget:
            lines.append("## OPEN QUESTIONS")
            for q in open_qs[:5]:
                lines.append(f"- {q.question}")
            lines.append("")

        # Contradictions (important for the hive to be aware of)
        unresolved = [c for c in self.contradictions if c.resolution_status == "unresolved"]
        if unresolved and len("\n".join(lines)) < char_budget:
            lines.append("## UNRESOLVED CONTRADICTIONS")
            for c in unresolved[:3]:
                lines.append(f'- CONFLICT: "{c.item_a_content}" vs "{c.item_b_content}"')
            lines.append("")

        result = "\n".join(lines)

        # Cache the result
        self._context_cache = result
        self._context_cache_tokens = max_context_tokens
        self._context_dirty = False

        return result

    def add_fact(self, fact: Fact) -> bool:
        """Add a fact, checking for duplicates, contradictions, and expiry."""
        # Skip expired facts
        if fact.is_expired():
            return False

        # Check for near-duplicate
        for existing in self.facts:
            if self._is_similar(existing.content, fact.content):
                # Update confidence if higher
                if fact.confidence > existing.confidence:
                    existing.confidence = fact.confidence
                    existing.evidence = fact.evidence
                    existing.valid_until = fact.valid_until
                    self._context_dirty = True
                return False

        self.facts.append(fact)
        self._context_dirty = True
        self._enforce_limits()
        return True

    def add_belief(self, belief: Belief) -> bool:
        """Add a belief, checking for duplicates."""
        for existing in self.beliefs:
            if self._is_similar(existing.content, belief.content):
                if belief.confidence > existing.confidence:
                    existing.confidence = belief.confidence
                    existing.reasoning = belief.reasoning
                    self._context_dirty = True
                return False

        self.beliefs.append(belief)
        self._context_dirty = True
        self._enforce_limits()
        return True

    def add_hypothesis(self, hypothesis: Hypothesis) -> None:
        """Add a hypothesis to explore."""
        self.hypotheses.append(hypothesis)
        self._context_dirty = True

    def add_goal(self, goal: Goal) -> None:
        """Add a goal."""
        self.goals.append(goal)
        self._context_dirty = True

    def add_open_question(self, question: OpenQuestion) -> None:
        """Add an open question."""
        self.open_questions.append(question)
        self._context_dirty = True

    def add_contradiction(self, contradiction: Contradiction) -> None:
        """Record a contradiction between items."""
        self.contradictions.append(contradiction)
        self._context_dirty = True

    def apply_update(self, update: HiveUpdate) -> Dict[str, int]:
        """
        Apply an update from a model to the hive state.
        Returns counts of what was added/modified.
        """
        counts = {
            "facts_added": 0,
            "beliefs_added": 0,
            "hypotheses_added": 0,
            "goals_added": 0,
            "questions_added": 0,
            "contradictions_added": 0,
        }

        # Apply new facts
        for fact_data in update.new_facts:
            fact = Fact(
                content=fact_data.get("content", ""),
                confidence=fact_data.get("confidence", update.confidence),
                source_model=update.source_model,
                evidence=fact_data.get("evidence", ""),
                domain=fact_data.get("domain", "general"),
            )
            if self.add_fact(fact):
                counts["facts_added"] += 1

        # Apply belief changes
        for belief_data in update.belief_changes:
            belief = Belief(
                content=belief_data.get("content", ""),
                confidence=belief_data.get("confidence", update.confidence),
                source_model=update.source_model,
                reasoning=belief_data.get("reasoning", ""),
            )
            if self.add_belief(belief):
                counts["beliefs_added"] += 1

        # Apply new hypotheses
        for hyp_data in update.new_hypotheses:
            hyp = Hypothesis(
                content=hyp_data.get("content", ""),
                confidence=hyp_data.get("confidence", 0.3),
                source_model=update.source_model,
                exploration_notes=hyp_data.get("notes", ""),
            )
            self.add_hypothesis(hyp)
            counts["hypotheses_added"] += 1

        # Apply new goals
        for goal_data in update.new_goals:
            goal = Goal(
                content=goal_data.get("content", ""),
                priority=goal_data.get("priority", "medium"),
            )
            self.add_goal(goal)
            counts["goals_added"] += 1

        # Apply open questions
        for q_data in update.open_questions:
            question = OpenQuestion(
                question=q_data.get("question", ""),
                context=q_data.get("context", ""),
                priority=q_data.get("priority", "medium"),
            )
            self.add_open_question(question)
            counts["questions_added"] += 1

        # Record contradictions
        for c_data in update.contradictions_found:
            contradiction = Contradiction(
                item_a_content=c_data.get("item_a", ""),
                item_b_content=c_data.get("item_b", ""),
                source_models=[update.source_model],
            )
            self.add_contradiction(contradiction)
            counts["contradictions_added"] += 1

        # Update metadata
        self.version += 1
        self.updated_at = datetime.now()
        self._context_dirty = True
        self.update_history.append(
            {
                "version": self.version,
                "source_model": update.source_model,
                "counts": counts,
                "timestamp": self.updated_at.isoformat(),
            }
        )

        # Enforce history limit
        if len(self.update_history) > self.max_history:
            self.update_history = self.update_history[-self.max_history :]

        return counts

    def _is_similar(
        self,
        text1: str,
        text2: str,
        threshold: float = 0.8,
        embedding_a: Optional[List[float]] = None,
        embedding_b: Optional[List[float]] = None,
    ) -> bool:
        """Check similarity using embeddings first, Jaccard as fallback.

        When both embeddings are provided, cosine similarity is used exclusively.
        The Jaccard fallback is only used when embeddings are unavailable.
        Per Amendment 14, for fact deduplication prefer pgvector query when a
        database session is available; in-memory comparison is acceptable for
        small collections.
        """
        # Normalize
        t1 = text1.lower().strip()
        t2 = text2.lower().strip()

        if t1 == t2 and embedding_a is None and embedding_b is None:
            return True

        # Use embedding cosine similarity when both are available
        if embedding_a is not None and embedding_b is not None:
            import math

            if not embedding_a or not embedding_b or len(embedding_a) != len(embedding_b):
                return False
            dot = sum(a * b for a, b in zip(embedding_a, embedding_b))
            mag_a = math.sqrt(sum(a * a for a in embedding_a))
            mag_b = math.sqrt(sum(b * b for b in embedding_b))
            if mag_a == 0.0 or mag_b == 0.0:
                return False
            cosine = dot / (mag_a * mag_b)
            return cosine >= threshold

        # Fallback: Jaccard similarity on words
        words1 = set(t1.split())
        words2 = set(t2.split())

        if not words1 or not words2:
            return False

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return (intersection / union) >= threshold

    def _enforce_limits(self) -> None:
        """Enforce maximum sizes by removing oldest low-confidence items."""
        if len(self.facts) > self.max_facts:
            # Sort by confidence (ascending) then by timestamp (oldest first)
            self.facts.sort(key=lambda f: (f.confidence, f.timestamp))
            self.facts = self.facts[-(self.max_facts) :]

        if len(self.beliefs) > self.max_beliefs:
            self.beliefs.sort(key=lambda b: (b.confidence, b.timestamp))
            self.beliefs = self.beliefs[-(self.max_beliefs) :]

    def get_facts_by_domain(self, domain: str) -> List[Fact]:
        """Get facts filtered by domain."""
        return [f for f in self.facts if f.domain == domain]

    def get_high_confidence_facts(self, threshold: float = 0.7) -> List[Fact]:
        """Get facts above confidence threshold."""
        return [f for f in self.facts if f.confidence >= threshold]

    def resolve_contradiction(
        self, contradiction_id: str, resolution: str, keep_both: bool = False
    ) -> None:
        """Resolve a contradiction."""
        for c in self.contradictions:
            if c.id == contradiction_id:
                c.resolution_status = "accepted_both" if keep_both else "resolved"
                c.resolution_notes = resolution
                break

    def save(self, filepath: str) -> None:
        """
        DEPRECATED: Export state to JSON file for backup/debugging only.

        For normal persistence, use PgStateManager.save_state() instead.
        This method is kept for export/debugging purposes only.
        """
        import warnings

        warnings.warn(
            "HiveState.save() is deprecated for persistence. "
            "Use PgStateManager.save_state() for normal operations. "
            "This method is now export_to_file() for backup/debugging.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.export_to_file(filepath)

    def export_to_file(self, filepath: str) -> None:
        """
        Export state to JSON file for backup/debugging.

        NOTE: This is NOT the primary persistence mechanism.
        Use PgStateManager for normal state persistence.
        """
        with open(filepath, "w") as f:
            json.dump(self.to_full_dict(), f, indent=2)

    @classmethod
    def load(cls, filepath: str) -> "HiveState":
        """
        DEPRECATED: Import state from JSON file.

        For normal state loading, use PgStateManager.load_state() instead.
        This method is kept for import/migration purposes only.
        """
        import warnings

        warnings.warn(
            "HiveState.load() is deprecated for persistence. "
            "Use PgStateManager.load_state() for normal operations. "
            "This method is now import_from_file() for migration/recovery.",
            DeprecationWarning,
            stacklevel=2,
        )
        return cls.import_from_file(filepath)

    @classmethod
    def from_dict(cls, data: Dict) -> "HiveState":
        """Reconstruct HiveState from a dictionary.

        This is the inverse of to_full_dict(). Used by EncryptedStateStore,
        PgStateManager, and import_from_file.

        Args:
            data: Dictionary as produced by to_full_dict().

        Returns:
            Reconstructed HiveState.
        """
        state = cls()

        # Core knowledge
        state.facts = [Fact.from_dict(f) for f in data.get("facts", [])]
        state.beliefs = [Belief.from_dict(b) for b in data.get("beliefs", [])]
        state.hypotheses = [Hypothesis.from_dict(h) for h in data.get("hypotheses", [])]
        state.goals = [Goal.from_dict(g) for g in data.get("goals", [])]
        state.plans = [Plan.from_dict(p) for p in data.get("plans", [])]
        state.open_questions = [OpenQuestion.from_dict(q) for q in data.get("open_questions", [])]
        state.contradictions = [Contradiction.from_dict(c) for c in data.get("contradictions", [])]

        # Metadata
        state.memory_summary = data.get("memory_summary", "")
        state.version = data.get("version", 0)
        state.created_at = (
            datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.now()
        )
        state.updated_at = (
            datetime.fromisoformat(data["updated_at"]) if "updated_at" in data else datetime.now()
        )

        # Identity (optional - may not be present in old exports)
        if "identity_kernel" in data:
            state.identity_kernel = IdentityKernel.from_dict(data["identity_kernel"])
        if "self_model" in data:
            state.self_model = SelfModel.from_dict(data["self_model"])
        if "identity_timeline" in data:
            state.identity_timeline = [
                IdentityEvent.from_dict(e) for e in data["identity_timeline"]
            ]
        state.identity_growth_metrics = data.get("identity_growth_metrics", {})
        state.identity_growth_history = data.get("identity_growth_history", [])

        # Human model (optional — may not be present in old exports)
        if "human_model" in data and data["human_model"] is not None:
            state.human_model = HumanModel.from_dict(data["human_model"])

        return state

    @classmethod
    def import_from_file(cls, filepath: str) -> "HiveState":
        """
        Import state from JSON file for migration/recovery.

        NOTE: This is NOT the primary loading mechanism.
        Use PgStateManager for normal state loading.
        """
        with open(filepath, "r") as f:
            data = json.load(f)

        return cls.from_dict(data)

    # ============================================================
    # IDENTITY MANAGEMENT
    # ============================================================

    def ensure_identity(self) -> None:
        """Ensure identity is initialized. Call this on first boot."""
        if self.identity_kernel is None:
            self.identity_kernel = IdentityKernel()
        if self.self_model is None:
            self.self_model = SelfModel()

    # ============================================================
    # HUMAN MODEL MANAGEMENT
    # ============================================================

    def ensure_human_model(self) -> HumanModel:
        """Ensure human model is initialized."""
        if self.human_model is None:
            self.human_model = HumanModel()
            self._context_dirty = True
        return self.human_model

    def add_identity_event(self, event: IdentityEvent) -> None:
        """Add an event to the identity timeline."""
        self.identity_timeline.append(event)

        # Cap timeline at reasonable size (keep last 1000 events)
        max_timeline = 1000
        if len(self.identity_timeline) > max_timeline:
            self.identity_timeline = self.identity_timeline[-max_timeline:]

    def get_identity_summary(self) -> Dict:
        """Get a summary of current identity state."""
        self.ensure_identity()

        # After ensure_identity, these are guaranteed non-None
        kernel = self.identity_kernel
        model = self.self_model
        assert kernel is not None and model is not None

        return {
            "kernel_version": kernel.version,
            "axioms_count": len(kernel.axioms),
            "coherence": model.coherence,
            "tone": model.get_tone().value,
            "narrative": model.narrative,
            "memory_density": model.memory_density,
            "contradictions_seen": model.contradictions_seen,
            "known_domains": model.known_domains,
            "capabilities_count": len(model.capabilities),
            "limits_count": len(model.limits),
            "timeline_events": len(self.identity_timeline),
            "last_shift": model.last_shift.isoformat(),
        }

    def get_recent_identity_events(self, count: int = 10) -> List[IdentityEvent]:
        """Get the most recent identity events."""
        return self.identity_timeline[-count:] if self.identity_timeline else []

    def record_identity_growth(
        self,
        drift_delta: float,
        opinions: List[str],
        contradictions_processed: int,
        unresolved_contradictions: int,
    ) -> None:
        """Record identity growth metrics/history in mutable hive state."""
        self.identity_growth_metrics = {
            "last_drift_delta": drift_delta,
            "last_opinions": opinions,
            "last_contradictions_processed": contradictions_processed,
            "last_unresolved_contradictions": unresolved_contradictions,
            "last_updated": datetime.now().isoformat(),
        }

        self.identity_growth_history.append(
            {
                "drift_delta": drift_delta,
                "opinions_updated": len(opinions),
                "contradictions_processed": contradictions_processed,
                "unresolved_contradictions": unresolved_contradictions,
                "opinions": opinions,
                "timestamp": datetime.now().isoformat(),
            }
        )

        if len(self.identity_growth_history) > self.max_history:
            self.identity_growth_history = self.identity_growth_history[-self.max_history :]

    def get_recent_identity_growth(self, count: int = 10) -> List[Dict]:
        """Get the most recent identity growth records."""
        return self.identity_growth_history[-count:] if self.identity_growth_history else []
