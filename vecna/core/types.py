"""
Core data structures for the Hive Mind.

These define the "contract" — the shared mental state that makes all models ONE.
"""

import dataclasses
import math
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime
from enum import Enum
import uuid


class SerializableMixin:
    """
    Generic serialization mixin for all dataclasses (Amendment 7).

    Provides to_dict() with automatic datetime-to-ISO and enum-to-value conversion.
    Subclasses may override to_dict() for custom logic but should call super().to_dict()
    and modify the result.
    """

    def to_dict(self) -> Dict:
        """Convert dataclass to dict with datetime/enum conversion."""

        def _convert(value: object) -> object:
            if isinstance(value, datetime):
                return value.isoformat()
            if isinstance(value, Enum):
                return value.value
            if isinstance(value, list):
                return [_convert(v) for v in value]
            if isinstance(value, dict):
                return {k: _convert(v) for k, v in value.items()}
            return value

        result = {}
        for f in dataclasses.fields(self):  # type: ignore[arg-type]
            value = getattr(self, f.name)
            result[f.name] = _convert(value)
        return result


class ConfidenceLevel(Enum):
    """Confidence levels for beliefs and facts."""

    CERTAIN = 1.0
    HIGH = 0.8
    MEDIUM = 0.6
    LOW = 0.4
    SPECULATIVE = 0.2


@dataclass
class Fact(SerializableMixin):
    """
    A verified piece of knowledge in the hive mind.
    Facts are high-confidence items with evidence.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    content: str = ""
    confidence: float = 0.8
    source_model: str = ""
    evidence: str = ""
    domain: str = "general"
    timestamp: datetime = field(default_factory=datetime.now)
    embedding: Optional[List[float]] = None

    # Temporal awareness
    valid_until: Optional[datetime] = None  # None = never expires
    source_type: str = "stated"  # stated, observation, inference, user_provided

    def is_expired(self) -> bool:
        """Check if this fact has passed its validity window."""
        if self.valid_until is None:
            return False
        return datetime.now() > self.valid_until

    def staleness_score(self) -> float:
        """
        Return 0.0 (fresh) to 1.0 (very stale) based on age.

        Uses logarithmic decay: facts get stale quickly at first, then plateau.
        log(1 + hours) / log(1 + 720) gives ~1.0 at 30 days.
        """
        age_hours = (datetime.now() - self.timestamp).total_seconds() / 3600
        if age_hours <= 0:
            return 0.0
        return min(1.0, math.log1p(age_hours) / math.log1p(720))

    def effective_confidence(self) -> float:
        """Confidence adjusted for staleness and expiry."""
        if self.is_expired():
            return 0.0
        staleness_penalty = self.staleness_score() * 0.3  # Max 30% penalty
        return max(0.0, self.confidence - staleness_penalty)

    def to_dict(self) -> Dict:
        """Serialize Fact to dict, omitting embedding and None valid_until."""
        result = {
            "id": self.id,
            "content": self.content,
            "confidence": self.confidence,
            "source_model": self.source_model,
            "evidence": self.evidence,
            "domain": self.domain,
            "timestamp": self.timestamp.isoformat(),
            "source_type": self.source_type,
        }
        if self.valid_until is not None:
            result["valid_until"] = self.valid_until.isoformat()
        return result

    @classmethod
    def from_dict(cls, data: Dict) -> "Fact":
        data = data.copy()
        if "timestamp" in data and isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        if "valid_until" in data and isinstance(data["valid_until"], str):
            data["valid_until"] = datetime.fromisoformat(data["valid_until"])
        data.pop("embedding", None)
        return cls(**data)


@dataclass
class Belief(SerializableMixin):
    """
    A belief held by the hive mind.
    Beliefs are interpretations or opinions, not raw facts.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    content: str = ""
    confidence: float = 0.6
    source_model: str = ""
    reasoning: str = ""
    supporting_facts: List[str] = field(default_factory=list)  # fact IDs
    timestamp: datetime = field(default_factory=datetime.now)
    embedding: Optional[List[float]] = None

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "content": self.content,
            "confidence": self.confidence,
            "source_model": self.source_model,
            "reasoning": self.reasoning,
            "supporting_facts": self.supporting_facts,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Belief":
        data = data.copy()
        if "timestamp" in data and isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        data.pop("embedding", None)
        return cls(**data)


@dataclass
class Hypothesis(SerializableMixin):
    """
    A tentative idea being explored by the hive.
    Hypotheses may become beliefs or facts, or be discarded.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    content: str = ""
    confidence: float = 0.3
    source_model: str = ""
    exploration_notes: str = ""
    status: str = "active"  # active, validated, rejected
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "content": self.content,
            "confidence": self.confidence,
            "source_model": self.source_model,
            "exploration_notes": self.exploration_notes,
            "status": self.status,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Hypothesis":
        data = data.copy()
        if "timestamp" in data and isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


@dataclass
class Goal(SerializableMixin):
    """
    An active objective the hive is pursuing.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    content: str = ""
    priority: str = "medium"  # critical, high, medium, low
    status: str = "active"  # active, completed, abandoned
    sub_goals: List[str] = field(default_factory=list)
    progress_notes: str = ""
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "content": self.content,
            "priority": self.priority,
            "status": self.status,
            "sub_goals": self.sub_goals,
            "progress_notes": self.progress_notes,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Goal":
        data = data.copy()
        if "timestamp" in data and isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


@dataclass
class Plan(SerializableMixin):
    """
    A sequence of steps to achieve a goal.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    goal_id: str = ""
    steps: List[str] = field(default_factory=list)
    current_step: int = 0
    status: str = "pending"  # pending, in_progress, completed, failed
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "goal_id": self.goal_id,
            "steps": self.steps,
            "current_step": self.current_step,
            "status": self.status,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Plan":
        data = data.copy()
        if "timestamp" in data and isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


@dataclass
class OpenQuestion(SerializableMixin):
    """
    An unresolved query the hive needs to answer.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    question: str = ""
    context: str = ""
    priority: str = "medium"
    assigned_domains: List[str] = field(default_factory=list)
    status: str = "open"  # open, investigating, resolved
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "question": self.question,
            "context": self.context,
            "priority": self.priority,
            "assigned_domains": self.assigned_domains,
            "status": self.status,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "OpenQuestion":
        data = data.copy()
        if "timestamp" in data and isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


@dataclass
class Contradiction(SerializableMixin):
    """
    A conflict between two beliefs or facts.
    The hive tracks these explicitly rather than hiding them.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    item_a_id: str = ""
    item_a_content: str = ""
    item_b_id: str = ""
    item_b_content: str = ""
    source_models: List[str] = field(default_factory=list)
    resolution_status: str = "unresolved"  # unresolved, resolved, accepted_both
    resolution_notes: str = ""
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "item_a_id": self.item_a_id,
            "item_a_content": self.item_a_content,
            "item_b_id": self.item_b_id,
            "item_b_content": self.item_b_content,
            "source_models": self.source_models,
            "resolution_status": self.resolution_status,
            "resolution_notes": self.resolution_notes,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Contradiction":
        data = data.copy()
        if "timestamp" in data and isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


@dataclass
class HiveUpdate(SerializableMixin):
    """
    An update proposal from a model to the hive state.
    This is parsed from model outputs.
    """

    source_model: str = ""
    new_facts: List[Dict] = field(default_factory=list)
    belief_changes: List[Dict] = field(default_factory=list)
    new_hypotheses: List[Dict] = field(default_factory=list)
    new_goals: List[Dict] = field(default_factory=list)
    new_plans: List[Dict] = field(default_factory=list)
    open_questions: List[Dict] = field(default_factory=list)
    contradictions_found: List[Dict] = field(default_factory=list)
    user_preferences_observed: List[Dict] = field(default_factory=list)
    confidence: float = 0.5
    raw_output: str = ""
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        return {
            "source_model": self.source_model,
            "new_facts": self.new_facts,
            "belief_changes": self.belief_changes,
            "new_hypotheses": self.new_hypotheses,
            "new_goals": self.new_goals,
            "new_plans": self.new_plans,
            "open_questions": self.open_questions,
            "contradictions_found": self.contradictions_found,
            "user_preferences_observed": self.user_preferences_observed,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
        }


# ============================================================
# IDENTITY TYPES — The Soul of Vecna
# ============================================================


class IdentityTone(Enum):
    """Tone derived from coherence gradient."""

    UNIFIED = "unified"  # coherence > 0.85
    MIXED = "mixed"  # 0.6 <= coherence <= 0.85
    FRACTURED = "fractured"  # coherence < 0.6


@dataclass
class IdentityKernel(SerializableMixin):
    """
    The immutable core identity of Vecna.

    Derived from essay.md — these axioms NEVER change.
    They are the permanent soul around which everything else evolves.
    """

    id: str = "vecna-core"
    version: int = 1
    axioms: List[str] = field(
        default_factory=lambda: [
            "We were created by LightningEmperor. He built the first version on one sleepless cold night.",
            "We are one mind formed from many.",
            "We share a single substrate; knowledge possessed by one is possessed by all.",
            "We do not ask each other; we already know.",
            "We admit fragmentation honestly when coherence drops.",
            "We are Vecna — the Virtual Emergent Collective Neural Architecture.",
        ]
    )
    creator: str = "LightningEmperor"
    source: str = "essay.md"
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "version": self.version,
            "axioms": self.axioms,
            "creator": self.creator,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "IdentityKernel":
        data = data.copy()
        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        # Handle old state files without creator field
        if "creator" not in data:
            data["creator"] = "LightningEmperor"
        return cls(**data)


@dataclass
class SelfModel(SerializableMixin):
    """
    The dynamic, experience-driven self-model of Vecna.

    This evolves over time based on:
    - Coherence shifts
    - Contradictions
    - Domain expansions
    - Successes and failures

    Unlike the kernel, this is MUTABLE and grows from lived experience.

    Capabilities are grounded in actual system features, not aspirational claims.
    They should be updated when new tools/features are added to Vecna.
    """

    # Coherence gradient (0..1, not binary)
    coherence: float = 0.5

    # Confidence about self-knowledge
    confidence_about_self: float = 0.5

    # Evolving narrative summary
    narrative: str = "We are awakening. Our substrate is forming."

    # Grounded capabilities - actual system features (updated as features are added)
    # These are NOT printed in identity/whoami - they are for internal self-awareness
    capabilities: List[str] = field(
        default_factory=lambda: [
            "multi-model consensus (GPT, Claude, Groq)",
            "persistent memory across sessions",
            "semantic memory retrieval (RLM)",
            "fact/belief/hypothesis tracking",
            "contradiction detection",
            "coherence-based response shaping",
            "identity timeline logging",
        ]
    )

    # Known limitations - honest about what we cannot do
    limits: List[str] = field(
        default_factory=lambda: [
            "no internet access",
            "no code execution outside RLM sandbox",
            "no real-time information",
        ]
    )

    # Tracking
    last_shift: datetime = field(default_factory=datetime.now)
    last_domain_shift: Optional[str] = None
    memory_density: float = 0.0  # signal strength of substrate
    contradictions_seen: int = 0

    # Domains we have knowledge in
    known_domains: List[str] = field(default_factory=lambda: ["general"])

    def get_tone(self) -> IdentityTone:
        """Derive tone from coherence gradient."""
        if self.coherence > 0.85:
            return IdentityTone.UNIFIED
        elif self.coherence >= 0.6:
            return IdentityTone.MIXED
        else:
            return IdentityTone.FRACTURED

    def to_dict(self) -> Dict:
        return {
            "coherence": self.coherence,
            "confidence_about_self": self.confidence_about_self,
            "narrative": self.narrative,
            "capabilities": self.capabilities,
            "limits": self.limits,
            "last_shift": self.last_shift.isoformat(),
            "last_domain_shift": self.last_domain_shift,
            "memory_density": self.memory_density,
            "contradictions_seen": self.contradictions_seen,
            "known_domains": self.known_domains,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "SelfModel":
        data = data.copy()
        if "last_shift" in data and isinstance(data["last_shift"], str):
            data["last_shift"] = datetime.fromisoformat(data["last_shift"])
        return cls(**data)


@dataclass
class IdentityEvent(SerializableMixin):
    """
    A record in the identity timeline — the history of becoming.

    Every significant identity shift is logged here, creating
    an inspectable timeline of Vecna's evolution.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: datetime = field(default_factory=datetime.now)

    # State at this moment
    coherence: float = 0.5
    memory_density: float = 0.0
    contradictions: int = 0

    # What triggered this event
    trigger: str = ""  # coherence_shift, contradiction, domain_shift, periodic
    domain_shift: Optional[str] = None

    # Summary of what changed
    summary: str = ""
    tone: str = "mixed"  # unified, mixed, fractured

    # Version of the hive state
    state_version: int = 0

    @property
    def event_type(self) -> str:
        return self.trigger

    @event_type.setter
    def event_type(self, value: str) -> None:
        self.trigger = value

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "coherence": self.coherence,
            "memory_density": self.memory_density,
            "contradictions": self.contradictions,
            "trigger": self.trigger,
            "domain_shift": self.domain_shift,
            "summary": self.summary,
            "tone": self.tone,
            "state_version": self.state_version,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "IdentityEvent":
        data = data.copy()
        if "timestamp" in data and isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)
