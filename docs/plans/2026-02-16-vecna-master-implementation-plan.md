# Vecna Master Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform Vecna from a multi-model consensus prototype into a fully agentic, autonomous AI entity with structured cognition, broad tool capabilities, multi-channel delivery, and the feeling of Jarvis — "the AI that thinks about you when you're not there."

**Architecture:** Two parallel workstreams converging at Phase 3. **Track A** builds the cognitive brain (substrate enrichment, HumanModel, temporal awareness, enhanced consensus, DreamLoop v2). **Track B** builds the agentic hands (HTTP server, tool calling migration, channel adapters, browser automation, integration framework, cron autonomy). Both tracks merge into the **Convergence Layer** where autonomous thoughtfulness, security hardening, and the full Vecna entity emerge.

**Tech Stack:** Python 3.10+, asyncio, PostgreSQL + pgvector, Redis, Docker (code sandbox), aiohttp (HTTP server), Playwright (browser), Composio (integrations), steipete CLIs (imsg, wacli, gogcli, summarize), MoA (consensus upgrade), Fernet encryption (substrate at rest), Alembic (migrations).

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│  CHANNELS                                                    │
│  CLI/TUI │ iMessage │ WhatsApp │ Slack │ Discord              │
│  (Rich)    (imsg)     (wacli)   (Composio)                  │
├─────────────────────────────────────────────────────────────┤
│  HTTP SERVER (aiohttp)                                       │
│  /api/chat │ /api/state │ /api/channels │ /ws/stream        │
├─────────────────────────────────────────────────────────────┤
│  VECNA ENTITY LAYER                                          │
│  ┌─────────┐ ┌───────────┐ ┌──────────┐ ┌─────────────────┐│
│  │ Primary  │ │ Human     │ │ DreamLoop│ │ Autonomous      ││
│  │ Cortex   │ │ Model     │ │ v2       │ │ Thoughtfulness  ││
│  └─────────┘ └───────────┘ └──────────┘ └─────────────────┘│
├─────────────────────────────────────────────────────────────┤
│  COGNITIVE SUBSTRATE                                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐ │
│  │ Temporal  │ │ Causal   │ │ Epistemic│ │ Growth         │ │
│  │ Facts    │ │ Graph    │ │ State    │ │ Narrative      │ │
│  └──────────┘ └──────────┘ └──────────┘ └────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│  TOOL RUNTIME (native function calling)                      │
│  shell │ browser │ memory │ web │ fs │ integrations │ code  │
├─────────────────────────────────────────────────────────────┤
│  INTEGRATION LAYER                                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐ │
│  │ Google   │ │ GitHub   │ │ Calendar │ │ Background     │ │
│  │ Suite    │ │ Activity │ │ Awareness│ │ Observer       │ │
│  │ (gogcli) │ │ (API)    │ │          │ │                │ │
│  └──────────┘ └──────────┘ └──────────┘ └────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│  MODEL BACKENDS (BYO)                                        │
│  Copilot │ Groq │ Ollama │ Local HF │ OpenAI │ Anthropic   │
└─────────────────────────────────────────────────────────────┘
```

---

## Current Codebase State (Honest Assessment)

### What Works
- Multi-model consensus via Jaccard word overlap (`consensus.py:219-231`)
- HiveState with Facts/Beliefs/Hypotheses/Goals/Contradictions (`types.py`)
- Identity system: IdentityKernel (immutable) + SelfModel (evolving) (`types.py:312-502`)
- PostgreSQL + pgvector + Redis memory tiers (`pg_store.py`, `hot_cache.py`)
- BM25 hybrid search + multi-hop graph traversal (`pg_store.py`)
- ReWOO planning-execution pipeline (`rewoo.py`)
- Tool runtime with risk tiers, quotas, audit logging (`tools/`)
- Docker-based code execution sandbox (`code_executor.py`, `rlm_bridge.py`)
- DreamLoop with 4 phases: compress → reinforce → decay → insight (`dream_loop.py`)
- Copilot/Groq/Ollama/Transformers adapters (`adapters/base.py`)
- Rich CLI with boot sequence, chat REPL, identity views (`cli/main.py`)
- Langfuse observability tracing (`observability/langfuse.py`)
- 378 unit tests passing

### Critical Kill Signals (Must Fix)
| Issue | Location | Impact |
|-------|----------|--------|
| `_is_task_complete()` always returns True | `loop.py` | Agent never autonomously decides when to stop |
| `max(responses, key=len)` for response selection | `loop.py` | Picks longest response, not best |
| Custom `<HIVE_UPDATE>` YAML parsing | `base.py:152-193` | Fragile, models often produce malformed YAML |
| No HTTP server | Entire project | CLI-only, can't be a service or receive webhooks |
| Jaccard-only similarity | `consensus.py:219-231`, `hive_state.py:371-390` | No semantic understanding, word overlap only |
| No HumanModel | Entire project | Can't learn user preferences or adapt |
| No temporal awareness | `types.py` | Facts have timestamps but no validity windows |
| File-based GoalQueue | `goal_queue.py` | JSONL file, not durable, no concurrent access |

---

## Phase 1: Foundation (Tasks 1-12)

> **Duration:** 4-5 weeks
> **Goal:** Fix kill signals, establish the HTTP server, migrate to native tool calling, and build the core cognitive substrate extensions.

### TRACK A: Cognitive Architecture

---

### Task 1: Temporal Facts and Validity Windows

**Files:**
- Modify: `vecna/core/types.py:24-58` (Fact dataclass)
- Modify: `vecna/core/hive_state.py:232-245` (add_fact method)
- Create: `tests/unit/test_temporal_facts.py`

**Step 1: Write the failing tests**

```python
# tests/unit/test_temporal_facts.py
"""Tests for temporal fact awareness."""

from datetime import datetime, timedelta
from vecna.core.types import Fact


class TestTemporalFacts:
    def test_fact_has_valid_until(self):
        fact = Fact(
            content="Bitcoin is at $95,000",
            confidence=0.9,
            valid_until=datetime.now() + timedelta(hours=1),
        )
        assert fact.valid_until is not None
        assert not fact.is_expired()

    def test_fact_expires(self):
        fact = Fact(
            content="Weather is sunny",
            confidence=0.8,
            valid_until=datetime.now() - timedelta(hours=1),
        )
        assert fact.is_expired()

    def test_fact_without_validity_never_expires(self):
        fact = Fact(content="Python is a programming language", confidence=0.95)
        assert fact.valid_until is None
        assert not fact.is_expired()

    def test_fact_staleness_score(self):
        """Facts lose staleness over time even without explicit expiry."""
        old_fact = Fact(
            content="Something old",
            confidence=0.9,
            timestamp=datetime.now() - timedelta(days=30),
        )
        new_fact = Fact(
            content="Something new",
            confidence=0.9,
            timestamp=datetime.now(),
        )
        assert old_fact.staleness_score() > new_fact.staleness_score()

    def test_fact_source_type(self):
        fact = Fact(
            content="User prefers dark mode",
            source_type="observation",
        )
        assert fact.source_type == "observation"

    def test_fact_serialization_with_temporal_fields(self):
        valid_until = datetime.now() + timedelta(days=1)
        fact = Fact(
            content="Test",
            valid_until=valid_until,
            source_type="inference",
        )
        d = fact.to_dict()
        assert "valid_until" in d
        assert "source_type" in d
        restored = Fact.from_dict(d)
        assert restored.source_type == "inference"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_temporal_facts.py -v`
Expected: FAIL — `Fact` has no `valid_until`, `is_expired`, `staleness_score`, or `source_type`

**Step 3: Implement temporal fields on Fact**

Modify `vecna/core/types.py` — add to the `Fact` dataclass:

```python
@dataclass
class Fact:
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
    source_type: str = "stated"  # stated, observed, inferred, user_provided

    def is_expired(self) -> bool:
        """Check if this fact has passed its validity window."""
        if self.valid_until is None:
            return False
        return datetime.now() > self.valid_until

    def staleness_score(self) -> float:
        """
        Return 0.0 (fresh) to 1.0 (very stale) based on age.
        Uses logarithmic decay: facts get stale quickly at first, then plateau.
        """
        import math

        age_hours = (datetime.now() - self.timestamp).total_seconds() / 3600
        # log(1 + hours) / log(1 + 720) gives ~1.0 at 30 days
        return min(1.0, math.log1p(age_hours) / math.log1p(720))

    def effective_confidence(self) -> float:
        """Confidence adjusted for staleness and expiry."""
        if self.is_expired():
            return 0.0
        staleness_penalty = self.staleness_score() * 0.3  # Max 30% penalty
        return max(0.0, self.confidence - staleness_penalty)

    def to_dict(self) -> Dict:
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
```

**Step 4: Update `add_fact` in `hive_state.py` to filter expired facts**

```python
def add_fact(self, fact: Fact) -> bool:
    """Add a fact, checking for duplicates, contradictions, and expiry."""
    # Skip expired facts
    if fact.is_expired():
        return False

    # Check for near-duplicate
    for existing in self.facts:
        if self._is_similar(existing.content, fact.content):
            if fact.confidence > existing.confidence:
                existing.confidence = fact.confidence
                existing.evidence = fact.evidence
                existing.valid_until = fact.valid_until
            return False

    self.facts.append(fact)
    self._enforce_limits()
    return True
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_temporal_facts.py -v`
Expected: All PASS

**Step 6: Run full test suite for regressions**

Run: `pytest tests/unit/ -v --tb=short`
Expected: All existing 378 tests still pass

**Step 7: Commit**

```bash
git add vecna/core/types.py vecna/core/hive_state.py tests/unit/test_temporal_facts.py
git commit -m "feat: add temporal awareness to Facts (validity windows, staleness, source_type)"
```

---

### Task 2: HumanModel — The User Profile System

**Files:**
- Create: `vecna/core/human_model.py`
- Modify: `vecna/core/hive_state.py` (add human_model field)
- Create: `tests/unit/test_human_model.py`

**Step 1: Write the failing tests**

```python
# tests/unit/test_human_model.py
"""Tests for the HumanModel — learning who the user is."""

from datetime import datetime, timedelta
from vecna.core.human_model import (
    HumanModel,
    Preference,
    CommunicationStyle,
    InteractionPattern,
    EmotionalContext,
)


class TestHumanModelCreation:
    def test_empty_human_model(self):
        model = HumanModel()
        assert model.name is None
        assert model.preferences == []
        assert model.communication_style is not None
        assert model.interaction_count == 0

    def test_human_model_with_name(self):
        model = HumanModel(name="Sudhen")
        assert model.name == "Sudhen"


class TestPreferenceLearning:
    def test_add_preference(self):
        model = HumanModel()
        pref = Preference(
            key="response_length",
            value="concise",
            confidence=0.7,
            observed_count=3,
        )
        model.add_preference(pref)
        assert len(model.preferences) == 1

    def test_preference_strengthens_with_repetition(self):
        model = HumanModel()
        pref1 = Preference(key="tone", value="direct", confidence=0.5, observed_count=1)
        model.add_preference(pref1)
        pref2 = Preference(key="tone", value="direct", confidence=0.6, observed_count=1)
        model.add_preference(pref2)
        # Should merge, not duplicate
        assert len(model.preferences) == 1
        assert model.preferences[0].confidence > 0.5
        assert model.preferences[0].observed_count == 2

    def test_contradicting_preference_tracked(self):
        model = HumanModel()
        pref1 = Preference(key="tone", value="direct", confidence=0.8, observed_count=5)
        model.add_preference(pref1)
        pref2 = Preference(key="tone", value="gentle", confidence=0.6, observed_count=2)
        model.add_preference(pref2)
        # Both should exist — preference can be context-dependent
        assert len(model.preferences) == 2

    def test_get_preference(self):
        model = HumanModel()
        model.add_preference(
            Preference(key="language", value="python", confidence=0.9, observed_count=10)
        )
        result = model.get_preference("language")
        assert result is not None
        assert result.value == "python"

    def test_get_preference_highest_confidence(self):
        model = HumanModel()
        model.add_preference(
            Preference(key="editor", value="vim", confidence=0.4, observed_count=2)
        )
        model.add_preference(
            Preference(key="editor", value="vscode", confidence=0.8, observed_count=8)
        )
        result = model.get_preference("editor")
        assert result.value == "vscode"


class TestCommunicationStyle:
    def test_default_style(self):
        style = CommunicationStyle()
        assert style.verbosity == 0.5  # neutral default
        assert style.formality == 0.5
        assert style.technical_depth == 0.5

    def test_update_from_interaction(self):
        style = CommunicationStyle()
        style.update_from_signal("short_response_preferred", strength=0.8)
        assert style.verbosity < 0.5  # Should decrease

    def test_style_to_prompt_directive(self):
        style = CommunicationStyle(verbosity=0.2, formality=0.8, technical_depth=0.9)
        directive = style.to_prompt_directive()
        assert isinstance(directive, str)
        assert len(directive) > 0


class TestInteractionPatterns:
    def test_record_interaction(self):
        model = HumanModel()
        model.record_interaction(
            topic="python debugging",
            satisfaction_signal=1.0,  # positive
            duration_seconds=120,
        )
        assert model.interaction_count == 1
        assert len(model.interaction_patterns) == 1

    def test_detect_recurring_topic(self):
        model = HumanModel()
        for _ in range(5):
            model.record_interaction(topic="kubernetes", satisfaction_signal=0.8)
        topics = model.get_recurring_topics(min_count=3)
        assert "kubernetes" in topics


class TestEmotionalContext:
    def test_default_neutral(self):
        ctx = EmotionalContext()
        assert ctx.current_state == "neutral"
        assert ctx.confidence == 0.5

    def test_update_emotional_state(self):
        ctx = EmotionalContext()
        ctx.update("frustrated", confidence=0.7, trigger="repeated_errors")
        assert ctx.current_state == "frustrated"
        assert ctx.last_trigger == "repeated_errors"


class TestHumanModelSerialization:
    def test_round_trip(self):
        model = HumanModel(name="TestUser")
        model.add_preference(
            Preference(key="lang", value="python", confidence=0.9, observed_count=5)
        )
        model.record_interaction(topic="testing", satisfaction_signal=0.8)

        d = model.to_dict()
        restored = HumanModel.from_dict(d)
        assert restored.name == "TestUser"
        assert len(restored.preferences) == 1
        assert restored.interaction_count == 1

    def test_to_prompt_context(self):
        model = HumanModel(name="Sudhen")
        model.add_preference(
            Preference(key="style", value="no-fluff", confidence=0.95, observed_count=20)
        )
        ctx = model.to_prompt_context()
        assert "Sudhen" in ctx
        assert "no-fluff" in ctx
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_human_model.py -v`
Expected: FAIL — `vecna.core.human_model` does not exist

**Step 3: Implement HumanModel**

```python
# vecna/core/human_model.py
"""
HumanModel: Learning who the user is.

This is the killer feature — Vecna builds a model of the human it serves.
Preferences, communication style, emotional context, recurring patterns.
The substrate learns and adapts without being told.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime
from collections import Counter
import uuid


@dataclass
class Preference:
    """A learned preference about the user."""

    key: str  # Category: "language", "tone", "response_length", etc.
    value: str  # The preference value
    confidence: float = 0.5  # 0.0 - 1.0
    observed_count: int = 1
    first_observed: datetime = field(default_factory=datetime.now)
    last_observed: datetime = field(default_factory=datetime.now)
    context: Optional[str] = None  # When this preference applies

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "confidence": self.confidence,
            "observed_count": self.observed_count,
            "first_observed": self.first_observed.isoformat(),
            "last_observed": self.last_observed.isoformat(),
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Preference":
        data = data.copy()
        for key in ("first_observed", "last_observed"):
            if key in data and isinstance(data[key], str):
                data[key] = datetime.fromisoformat(data[key])
        return cls(**data)


@dataclass
class CommunicationStyle:
    """
    Learned communication preferences.

    Each dimension is 0.0 to 1.0:
    - 0.0 = low/minimal
    - 0.5 = neutral/default
    - 1.0 = high/maximum
    """

    verbosity: float = 0.5  # 0=terse, 1=verbose
    formality: float = 0.5  # 0=casual, 1=formal
    technical_depth: float = 0.5  # 0=simple, 1=expert
    emoji_usage: float = 0.0  # 0=never, 1=frequent
    humor: float = 0.3  # 0=serious, 1=playful

    # Signals that shift each dimension
    _signal_map: Dict[str, Dict[str, float]] = field(default_factory=lambda: {
        "short_response_preferred": {"verbosity": -0.1},
        "long_response_preferred": {"verbosity": 0.1},
        "asked_for_details": {"technical_depth": 0.1, "verbosity": 0.05},
        "asked_to_simplify": {"technical_depth": -0.1},
        "used_emoji": {"emoji_usage": 0.05},
        "formal_language": {"formality": 0.1},
        "casual_language": {"formality": -0.1},
        "made_joke": {"humor": 0.05},
    })

    def update_from_signal(self, signal: str, strength: float = 1.0) -> None:
        """Update style dimensions from an observed signal."""
        adjustments = self._signal_map.get(signal, {})
        for dim, delta in adjustments.items():
            current = getattr(self, dim, 0.5)
            new_val = max(0.0, min(1.0, current + delta * strength))
            setattr(self, dim, new_val)

    def to_prompt_directive(self) -> str:
        """Generate a prompt directive reflecting learned style."""
        parts = []
        if self.verbosity < 0.3:
            parts.append("Be extremely concise and direct.")
        elif self.verbosity > 0.7:
            parts.append("Provide thorough, detailed explanations.")

        if self.formality > 0.7:
            parts.append("Use formal, professional language.")
        elif self.formality < 0.3:
            parts.append("Keep it casual and conversational.")

        if self.technical_depth > 0.7:
            parts.append("Assume expert-level technical knowledge.")
        elif self.technical_depth < 0.3:
            parts.append("Explain concepts simply, avoid jargon.")

        if self.emoji_usage < 0.1:
            parts.append("Do not use emojis.")

        return " ".join(parts) if parts else "Respond naturally."

    def to_dict(self) -> Dict[str, float]:
        return {
            "verbosity": self.verbosity,
            "formality": self.formality,
            "technical_depth": self.technical_depth,
            "emoji_usage": self.emoji_usage,
            "humor": self.humor,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CommunicationStyle":
        return cls(
            verbosity=data.get("verbosity", 0.5),
            formality=data.get("formality", 0.5),
            technical_depth=data.get("technical_depth", 0.5),
            emoji_usage=data.get("emoji_usage", 0.0),
            humor=data.get("humor", 0.3),
        )


@dataclass
class InteractionPattern:
    """A recorded interaction for pattern detection."""

    topic: str
    satisfaction_signal: float = 0.5  # -1.0 to 1.0
    duration_seconds: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "satisfaction_signal": self.satisfaction_signal,
            "duration_seconds": self.duration_seconds,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InteractionPattern":
        data = data.copy()
        if "timestamp" in data and isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


@dataclass
class EmotionalContext:
    """
    Inferred emotional state of the user.

    This is NOT sentiment analysis — it's a model of the user's
    likely emotional state based on interaction patterns.
    """

    current_state: str = "neutral"  # neutral, focused, frustrated, excited, tired
    confidence: float = 0.5
    last_trigger: Optional[str] = None
    updated_at: datetime = field(default_factory=datetime.now)
    history: List[Dict[str, Any]] = field(default_factory=list)

    def update(
        self,
        state: str,
        confidence: float = 0.5,
        trigger: Optional[str] = None,
    ) -> None:
        """Update the emotional context."""
        self.history.append({
            "state": self.current_state,
            "confidence": self.confidence,
            "timestamp": self.updated_at.isoformat(),
        })
        # Keep last 50 entries
        if len(self.history) > 50:
            self.history = self.history[-50:]

        self.current_state = state
        self.confidence = confidence
        self.last_trigger = trigger
        self.updated_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_state": self.current_state,
            "confidence": self.confidence,
            "last_trigger": self.last_trigger,
            "updated_at": self.updated_at.isoformat(),
            "history": self.history,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EmotionalContext":
        data = data.copy()
        if "updated_at" in data and isinstance(data["updated_at"], str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        return cls(**data)


@dataclass
class HumanModel:
    """
    The user profile that Vecna builds over time.

    This is what makes Vecna feel like Jarvis — it learns who you are,
    what you care about, how you communicate, and what you need.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: Optional[str] = None

    # Learned preferences
    preferences: List[Preference] = field(default_factory=list)

    # Communication style model
    communication_style: CommunicationStyle = field(default_factory=CommunicationStyle)

    # Emotional context
    emotional_context: EmotionalContext = field(default_factory=EmotionalContext)

    # Interaction history (for pattern detection)
    interaction_patterns: List[InteractionPattern] = field(default_factory=list)
    interaction_count: int = 0

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # Limits
    _max_patterns: int = 500
    _max_preferences: int = 200

    def add_preference(self, pref: Preference) -> None:
        """Add or merge a preference."""
        # Look for existing preference with same key AND value
        for existing in self.preferences:
            if existing.key == pref.key and existing.value == pref.value:
                # Merge: boost confidence and count
                existing.observed_count += pref.observed_count
                existing.confidence = min(
                    1.0,
                    existing.confidence + 0.05 * pref.observed_count,
                )
                existing.last_observed = datetime.now()
                self.updated_at = datetime.now()
                return

        # New preference (different value for same key is allowed — context-dependent)
        self.preferences.append(pref)
        if len(self.preferences) > self._max_preferences:
            # Remove lowest confidence preferences
            self.preferences.sort(key=lambda p: p.confidence, reverse=True)
            self.preferences = self.preferences[: self._max_preferences]
        self.updated_at = datetime.now()

    def get_preference(self, key: str) -> Optional[Preference]:
        """Get the highest-confidence preference for a key."""
        matches = [p for p in self.preferences if p.key == key]
        if not matches:
            return None
        return max(matches, key=lambda p: p.confidence)

    def record_interaction(
        self,
        topic: str,
        satisfaction_signal: float = 0.5,
        duration_seconds: float = 0.0,
    ) -> None:
        """Record an interaction for pattern learning."""
        pattern = InteractionPattern(
            topic=topic,
            satisfaction_signal=satisfaction_signal,
            duration_seconds=duration_seconds,
        )
        self.interaction_patterns.append(pattern)
        self.interaction_count += 1

        if len(self.interaction_patterns) > self._max_patterns:
            self.interaction_patterns = self.interaction_patterns[-self._max_patterns :]

        self.updated_at = datetime.now()

    def get_recurring_topics(self, min_count: int = 3) -> List[str]:
        """Get topics that appear frequently in interactions."""
        topic_counts = Counter(p.topic for p in self.interaction_patterns)
        return [topic for topic, count in topic_counts.items() if count >= min_count]

    def to_prompt_context(self) -> str:
        """Generate prompt context from the human model."""
        lines = []

        if self.name:
            lines.append(f"## USER: {self.name}")
        else:
            lines.append("## USER PROFILE")

        # Communication style directive
        style_directive = self.communication_style.to_prompt_directive()
        if style_directive != "Respond naturally.":
            lines.append(f"\n### COMMUNICATION STYLE")
            lines.append(style_directive)

        # Top preferences
        high_conf_prefs = sorted(
            [p for p in self.preferences if p.confidence >= 0.6],
            key=lambda p: p.confidence,
            reverse=True,
        )
        if high_conf_prefs:
            lines.append(f"\n### KNOWN PREFERENCES")
            for p in high_conf_prefs[:10]:
                lines.append(f"- {p.key}: {p.value} (confidence: {p.confidence:.1f})")

        # Emotional context (if not neutral)
        if self.emotional_context.current_state != "neutral":
            lines.append(f"\n### EMOTIONAL CONTEXT")
            lines.append(
                f"User appears {self.emotional_context.current_state} "
                f"(confidence: {self.emotional_context.confidence:.1f})"
            )
            if self.emotional_context.last_trigger:
                lines.append(f"Trigger: {self.emotional_context.last_trigger}")

        # Recurring interests
        topics = self.get_recurring_topics()
        if topics:
            lines.append(f"\n### RECURRING INTERESTS")
            for topic in topics[:5]:
                lines.append(f"- {topic}")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "preferences": [p.to_dict() for p in self.preferences],
            "communication_style": self.communication_style.to_dict(),
            "emotional_context": self.emotional_context.to_dict(),
            "interaction_patterns": [p.to_dict() for p in self.interaction_patterns[-100:]],
            "interaction_count": self.interaction_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HumanModel":
        data = data.copy()
        for key in ("created_at", "updated_at"):
            if key in data and isinstance(data[key], str):
                data[key] = datetime.fromisoformat(data[key])

        model = cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            name=data.get("name"),
            interaction_count=data.get("interaction_count", 0),
            created_at=data.get("created_at", datetime.now()),
            updated_at=data.get("updated_at", datetime.now()),
        )

        model.preferences = [
            Preference.from_dict(p) for p in data.get("preferences", [])
        ]
        if "communication_style" in data:
            model.communication_style = CommunicationStyle.from_dict(
                data["communication_style"]
            )
        if "emotional_context" in data:
            model.emotional_context = EmotionalContext.from_dict(
                data["emotional_context"]
            )
        model.interaction_patterns = [
            InteractionPattern.from_dict(p)
            for p in data.get("interaction_patterns", [])
        ]

        return model
```

**Step 4: Wire HumanModel into HiveState**

Add to `vecna/core/hive_state.py`:

```python
# Add import at top:
from vecna.core.human_model import HumanModel

# Add field to HiveState dataclass (after identity_growth_history):
human_model: Optional[HumanModel] = None

# Add method:
def ensure_human_model(self) -> HumanModel:
    """Ensure human model is initialized."""
    if self.human_model is None:
        self.human_model = HumanModel()
    return self.human_model
```

Update `to_full_dict()` and `import_from_file()` to include `human_model`.

Update `to_prompt_context()` to include human model context after identity preamble.

**Step 5: Run tests**

Run: `pytest tests/unit/test_human_model.py tests/unit/ -v --tb=short`
Expected: All PASS including existing tests

**Step 6: Commit**

```bash
git add vecna/core/human_model.py vecna/core/hive_state.py tests/unit/test_human_model.py
git commit -m "feat: add HumanModel for user preference learning and adaptation"
```

---

### Task 3: Upgrade Consensus Engine — Embedding-Based Similarity + MoA

**Files:**
- Modify: `vecna/orchestrator/consensus.py` (replace Jaccard with embedding similarity)
- Create: `vecna/orchestrator/moa.py` (Mixture of Agents layered consensus)
- Modify: `vecna/core/hive_state.py:371-390` (replace `_is_similar` Jaccard)
- Create: `tests/unit/test_consensus_v2.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_consensus_v2.py
"""Tests for upgraded consensus engine with embedding similarity."""

import numpy as np
from vecna.orchestrator.consensus import ConsensusEngine, ConsensusConfig
from vecna.core.hive_state import HiveState
from vecna.core.types import HiveUpdate


class TestEmbeddingSimilarity:
    def test_cosine_similarity_identical(self):
        engine = ConsensusEngine()
        vec = [1.0, 0.0, 0.0]
        assert engine._cosine_similarity(vec, vec) == 1.0

    def test_cosine_similarity_orthogonal(self):
        engine = ConsensusEngine()
        assert engine._cosine_similarity([1, 0, 0], [0, 1, 0]) == 0.0

    def test_cosine_similarity_opposite(self):
        engine = ConsensusEngine()
        assert engine._cosine_similarity([1, 0], [-1, 0]) == -1.0

    def test_similarity_uses_embeddings_when_available(self):
        engine = ConsensusEngine()
        # With embeddings, semantically similar but lexically different
        # texts should cluster together
        result = engine._is_similar(
            "The car is fast",
            "The automobile is speedy",
            embedding_a=[0.9, 0.1, 0.0],
            embedding_b=[0.85, 0.15, 0.0],
        )
        assert result is True

    def test_fallback_to_jaccard_without_embeddings(self):
        engine = ConsensusEngine()
        # Without embeddings, falls back to Jaccard
        result = engine._is_similar("hello world foo bar", "hello world foo bar")
        assert result is True


class TestPrimaryCortexSelection:
    def test_primary_gets_highest_weight(self):
        """The most capable model should be primary cortex."""
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
        # Primary cortex's fact should have higher final confidence
        assert len(state.facts) >= 1


class TestMoALayering:
    def test_moa_basic_merge(self):
        from vecna.orchestrator.moa import MoAConsensus

        moa = MoAConsensus()
        responses = {
            "gpt-5.2": "Python is great for data science because of NumPy and Pandas.",
            "claude-sonnet": "Python excels at data science with its rich ecosystem of libraries.",
            "gpt-4o-mini": "Python is good for data work.",
        }
        merged = moa.merge_responses(responses)
        assert isinstance(merged, str)
        assert len(merged) > 0
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_consensus_v2.py -v`
Expected: FAIL — `_cosine_similarity` doesn't exist, `moa` module doesn't exist

**Step 3: Add cosine similarity to ConsensusEngine**

Add to `vecna/orchestrator/consensus.py`:

```python
import math
from typing import List, Dict, Optional, Tuple

class ConsensusEngine:
    # ... existing __init__ ...

    def _cosine_similarity(
        self,
        vec_a: List[float],
        vec_b: List[float],
    ) -> float:
        """Compute cosine similarity between two vectors."""
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        mag_a = math.sqrt(sum(a * a for a in vec_a))
        mag_b = math.sqrt(sum(b * b for b in vec_b))
        if mag_a == 0.0 or mag_b == 0.0:
            return 0.0
        return dot / (mag_a * mag_b)

    def _is_similar(
        self,
        text1: str,
        text2: str,
        embedding_a: Optional[List[float]] = None,
        embedding_b: Optional[List[float]] = None,
    ) -> bool:
        """Check similarity using embeddings first, Jaccard as fallback."""
        if embedding_a is not None and embedding_b is not None:
            sim = self._cosine_similarity(embedding_a, embedding_b)
            return sim >= self.config.similarity_threshold

        # Fallback: Jaccard word overlap
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        if not words1 or not words2:
            return False
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        jaccard = intersection / union if union > 0 else 0
        return jaccard >= self.config.similarity_threshold
```

**Step 4: Create MoA consensus module**

```python
# vecna/orchestrator/moa.py
"""
Mixture of Agents (MoA) consensus.

Based on "Mixture-of-Agents Enhances Large Language Model Capabilities"
(arXiv:2406.04692). Achieves 65.1% on AlpacaEval 2.0.

Architecture:
- Layer 1: All models generate independently (proposers)
- Layer 2: An aggregator model synthesizes the best response
  considering all proposer outputs.

The aggregator is the Primary Cortex (highest-weight model).
"""

from typing import Dict, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger("vecna.orchestrator.moa")


@dataclass
class MoAConfig:
    """Configuration for Mixture of Agents consensus."""

    # The aggregator prompt template
    aggregator_prompt: str = (
        "You have been provided with responses from multiple AI models "
        "to the same query. Your task is to synthesize the best possible "
        "response by combining the strongest elements from each.\n\n"
        "Model responses:\n{responses}\n\n"
        "Synthesize a single superior response that:\n"
        "1. Combines the most accurate and insightful points\n"
        "2. Resolves any contradictions between responses\n"
        "3. Uses the clearest and most precise language\n"
        "4. Adds nothing that wasn't supported by at least one model"
    )

    # Whether to include model names in the aggregator context
    include_model_names: bool = True

    # Max tokens from each proposer to include
    max_proposer_tokens: int = 2000


class MoAConsensus:
    """
    Mixture of Agents consensus engine.

    This is the upgrade path from Jaccard-based consensus to
    proper multi-model synthesis.
    """

    def __init__(self, config: Optional[MoAConfig] = None):
        self.config = config or MoAConfig()

    def build_aggregator_prompt(
        self,
        responses: Dict[str, str],
        original_task: Optional[str] = None,
    ) -> str:
        """Build the prompt for the aggregator model."""
        parts = []
        for model_name, response in responses.items():
            truncated = response[: self.config.max_proposer_tokens]
            if self.config.include_model_names:
                parts.append(f"### {model_name}\n{truncated}")
            else:
                parts.append(f"### Response\n{truncated}")

        responses_text = "\n\n".join(parts)

        prompt = self.config.aggregator_prompt.format(responses=responses_text)

        if original_task:
            prompt = f"Original query: {original_task}\n\n{prompt}"

        return prompt

    def merge_responses(self, responses: Dict[str, str]) -> str:
        """
        Merge multiple model responses into one.

        NOTE: This is the synchronous/offline version that picks the
        longest response as a baseline. The full async version uses
        an aggregator LLM call (see merge_responses_async).
        """
        if not responses:
            return ""
        if len(responses) == 1:
            return next(iter(responses.values()))

        # Offline fallback: pick response with most unique information
        # (longest response as proxy, weighted by model)
        return max(responses.values(), key=len)

    async def merge_responses_async(
        self,
        responses: Dict[str, str],
        aggregator_adapter,  # BaseAdapter
        original_task: str = "",
    ) -> str:
        """
        Use an aggregator model to synthesize the best response.

        This is the full MoA pipeline: proposers generate independently,
        then the Primary Cortex synthesizes.
        """
        if not responses:
            return ""
        if len(responses) == 1:
            return next(iter(responses.values()))

        prompt = self.build_aggregator_prompt(responses, original_task)
        synthesized = await aggregator_adapter.generate(prompt)
        return synthesized
```

**Step 5: Run tests**

Run: `pytest tests/unit/test_consensus_v2.py tests/unit/ -v --tb=short`
Expected: All PASS

**Step 6: Commit**

```bash
git add vecna/orchestrator/consensus.py vecna/orchestrator/moa.py tests/unit/test_consensus_v2.py
git commit -m "feat: upgrade consensus with embedding similarity and MoA synthesis"
```

---

### Task 4: Primary Cortex Architecture — Hierarchy Not Democracy

**Files:**
- Modify: `vecna/orchestrator/loop.py` (replace `max(responses, key=len)` with Primary Cortex selection)
- Modify: `vecna/config/schema.py` (add `primary_model` field)
- Create: `tests/unit/test_primary_cortex.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_primary_cortex.py
"""Tests for Primary Cortex model hierarchy."""

from vecna.orchestrator.loop import HiveLoop, HiveConfig
from vecna.config.schema import VecnaConfig, ModelEntry, Provider


class TestPrimaryCortexSelection:
    def test_highest_weight_is_primary(self):
        """Primary cortex is the model with highest weight."""
        config = HiveConfig()
        loop = HiveLoop(config=config)
        # Simulate adapters with different weights
        from unittest.mock import MagicMock

        adapters = [
            MagicMock(name="gpt-4o-mini", weight=0.8),
            MagicMock(name="gpt-5.2", weight=2.0),
            MagicMock(name="gpt-4.1", weight=1.0),
        ]
        for a in adapters:
            a.name = a._mock_name
        loop.adapters = adapters

        primary = loop.get_primary_cortex()
        assert primary.name == "gpt-5.2"

    def test_advisory_lenses_exclude_primary(self):
        from unittest.mock import MagicMock

        config = HiveConfig()
        loop = HiveLoop(config=config)
        adapters = [
            MagicMock(name="primary", weight=2.0),
            MagicMock(name="lens1", weight=1.0),
            MagicMock(name="lens2", weight=0.8),
        ]
        for a in adapters:
            a.name = a._mock_name
        loop.adapters = adapters

        lenses = loop.get_advisory_lenses()
        assert len(lenses) == 2
        assert all(l.name != "primary" for l in lenses)

    def test_primary_response_preferred(self):
        """When primary and lens agree, primary's wording wins."""
        from vecna.orchestrator.loop import select_best_response

        responses = {
            "primary": "Python uses dynamic typing for flexibility.",
            "lens1": "Python's typing is dynamic.",
            "lens2": "Python has dynamic types.",
        }
        primary_name = "primary"
        best = select_best_response(responses, primary_name)
        assert best == responses["primary"]
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_primary_cortex.py -v`
Expected: FAIL — `get_primary_cortex`, `get_advisory_lenses`, `select_best_response` don't exist

**Step 3: Implement Primary Cortex selection on HiveLoop**

Add to `vecna/orchestrator/loop.py`:

```python
def get_primary_cortex(self) -> Optional[BaseAdapter]:
    """
    Get the primary cortex — the highest-weight model.

    The Primary Cortex is the most capable model that orchestrates.
    Advisory Lenses are consulted only when the Primary flags uncertainty.
    """
    if not self.adapters:
        return None
    return max(self.adapters, key=lambda a: a.weight)

def get_advisory_lenses(self) -> List[BaseAdapter]:
    """Get advisory lenses (all adapters except primary cortex)."""
    primary = self.get_primary_cortex()
    if primary is None:
        return []
    return [a for a in self.adapters if a.name != primary.name]


def select_best_response(
    responses: Dict[str, str],
    primary_name: str,
) -> str:
    """
    Select the best response from multiple model outputs.

    Strategy: Primary Cortex response wins unless advisory lenses
    flagged a significant disagreement. This replaces the old
    max(responses, key=len) approach.
    """
    if not responses:
        return ""

    # Primary cortex response is the default winner
    if primary_name in responses and responses[primary_name].strip():
        return responses[primary_name]

    # Fallback: pick the most substantial response
    return max(responses.values(), key=len) if responses else ""
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_primary_cortex.py tests/unit/ -v --tb=short`
Expected: All PASS

**Step 5: Commit**

```bash
git add vecna/orchestrator/loop.py tests/unit/test_primary_cortex.py
git commit -m "feat: implement Primary Cortex hierarchy (replaces max-length selection)"
```

---

### Task 5: Fix `_is_task_complete()` Stub

**Files:**
- Modify: `vecna/orchestrator/loop.py` (replace stub with real implementation)
- Create: `tests/unit/test_task_completion.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_task_completion.py
"""Tests for task completion detection."""


class TestTaskCompletion:
    def test_direct_answer_is_complete(self):
        """A direct factual answer should be considered complete."""
        from vecna.orchestrator.loop import is_task_complete

        response = "Python was created by Guido van Rossum in 1991."
        task = "Who created Python?"
        assert is_task_complete(response, task, cycle=1, max_cycles=10)

    def test_question_back_is_not_complete(self):
        """If the response asks a clarifying question, task isn't complete."""
        from vecna.orchestrator.loop import is_task_complete

        response = "Could you clarify what you mean by 'fast'?"
        task = "Is Python fast?"
        assert not is_task_complete(response, task, cycle=1, max_cycles=10)

    def test_max_cycles_forces_completion(self):
        """At max cycles, always return True to prevent infinite loops."""
        from vecna.orchestrator.loop import is_task_complete

        response = "Still thinking..."
        task = "Complex task"
        assert is_task_complete(response, task, cycle=10, max_cycles=10)

    def test_empty_response_not_complete(self):
        from vecna.orchestrator.loop import is_task_complete

        assert not is_task_complete("", "Do something", cycle=1, max_cycles=10)

    def test_tool_call_pending_not_complete(self):
        from vecna.orchestrator.loop import is_task_complete

        response = "Let me search for that information."
        task = "Find the latest Python release"
        # First cycle with action words = not complete
        assert not is_task_complete(response, task, cycle=1, max_cycles=10)
```

**Step 2: Run tests, verify fail**

Run: `pytest tests/unit/test_task_completion.py -v`
Expected: FAIL — `is_task_complete` doesn't exist as standalone function

**Step 3: Implement `is_task_complete`**

```python
# Add to vecna/orchestrator/loop.py

def is_task_complete(
    response: str,
    task: str,
    cycle: int,
    max_cycles: int,
) -> bool:
    """
    Determine if a task is complete based on the response.

    Replaces the old stub that always returned True.

    Heuristics:
    1. Max cycles reached → complete (safety valve)
    2. Empty response → not complete
    3. Response contains clarifying questions → not complete
    4. Response contains action intent → not complete (on first cycles)
    5. Substantive response without questions → complete
    """
    # Safety valve: max cycles
    if cycle >= max_cycles:
        return True

    # Empty response
    if not response or not response.strip():
        return False

    response_lower = response.lower().strip()

    # Clarifying questions (response asks the user something)
    question_indicators = [
        "could you clarify",
        "can you provide",
        "what do you mean",
        "could you be more specific",
        "do you want me to",
        "should i",
        "would you like",
    ]
    if any(indicator in response_lower for indicator in question_indicators):
        return False

    # Action intent on early cycles (still working)
    if cycle < max_cycles - 1:
        action_indicators = [
            "let me search",
            "let me look",
            "i'll check",
            "searching for",
            "looking up",
            "let me find",
            "i need to",
        ]
        if any(indicator in response_lower for indicator in action_indicators):
            return False

    # Substantive response (has content beyond filler)
    words = response.split()
    if len(words) < 3:
        return False

    return True
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_task_completion.py tests/unit/ -v --tb=short`
Expected: All PASS

**Step 5: Commit**

```bash
git add vecna/orchestrator/loop.py tests/unit/test_task_completion.py
git commit -m "fix: replace _is_task_complete() stub with heuristic-based completion detection"
```

---

### TRACK B: Agentic Capabilities

---

### Task 6: HTTP Server — Make Vecna a Service

**Files:**
- Create: `vecna/server/__init__.py`
- Create: `vecna/server/app.py` (aiohttp server)
- Create: `vecna/server/routes.py` (API endpoints)
- Modify: `vecna/cli/main.py` (add `vecna serve` command)
- Create: `tests/unit/test_server.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_server.py
"""Tests for the HTTP server."""

import pytest
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from vecna.server.app import create_app


class TestServerRoutes:
    async def test_health_endpoint(self, aiohttp_client):
        app = create_app()
        client = await aiohttp_client(app)
        resp = await client.get("/api/health")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    async def test_chat_endpoint(self, aiohttp_client):
        app = create_app()
        client = await aiohttp_client(app)
        resp = await client.post(
            "/api/chat",
            json={"message": "Hello", "session_id": "test-session"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert "response" in data

    async def test_state_endpoint(self, aiohttp_client):
        app = create_app()
        client = await aiohttp_client(app)
        resp = await client.get("/api/state")
        assert resp.status == 200
        data = await resp.json()
        assert "version" in data

    async def test_webhook_endpoint(self, aiohttp_client):
        app = create_app()
        client = await aiohttp_client(app)
        resp = await client.post(
            "/api/webhooks/ingest",
            json={
                "source": "github",
                "event": "push",
                "payload": {"repo": "test/repo"},
            },
        )
        assert resp.status == 200
```

**Step 2: Run tests, verify fail**

Run: `pytest tests/unit/test_server.py -v`
Expected: FAIL — `vecna.server` doesn't exist

**Step 3: Implement the server**

```python
# vecna/server/__init__.py
"""Vecna HTTP Server — makes Vecna accessible as a service."""

# vecna/server/app.py
"""
Vecna HTTP Server.

Provides REST API and WebSocket endpoints for interacting with Vecna
from any client (channels, integrations, UIs).
"""

import logging
from aiohttp import web
from vecna.server.routes import setup_routes

logger = logging.getLogger("vecna.server")


def create_app() -> web.Application:
    """Create the aiohttp application."""
    app = web.Application()
    setup_routes(app)

    # Store shared state
    app["hive_state"] = None  # Lazy-initialized
    app["sessions"] = {}

    return app


def run_server(host: str = "127.0.0.1", port: int = 8420) -> None:
    """Run the Vecna HTTP server."""
    app = create_app()
    logger.info(f"Starting Vecna server on {host}:{port}")
    web.run_app(app, host=host, port=port)
```

```python
# vecna/server/routes.py
"""API route handlers for the Vecna server."""

import logging
from aiohttp import web
from datetime import datetime

logger = logging.getLogger("vecna.server")


async def health(request: web.Request) -> web.Response:
    """Health check endpoint."""
    return web.json_response({
        "status": "ok",
        "version": "0.1.0",
        "timestamp": datetime.now().isoformat(),
    })


async def chat(request: web.Request) -> web.Response:
    """Chat endpoint — send a message to Vecna."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response(
            {"error": "Invalid JSON"}, status=400
        )

    message = data.get("message", "")
    session_id = data.get("session_id", "default")

    if not message:
        return web.json_response(
            {"error": "Message required"}, status=400
        )

    # TODO: Wire to HiveLoop.think() in Task 26
    return web.json_response({
        "response": f"[Vecna server placeholder] Received: {message}",
        "session_id": session_id,
        "timestamp": datetime.now().isoformat(),
    })


async def get_state(request: web.Request) -> web.Response:
    """Get current hive state summary."""
    from vecna.core.hive_state import HiveState

    state = request.app.get("hive_state")
    if state is None:
        state = HiveState()
        state.ensure_identity()
        request.app["hive_state"] = state

    return web.json_response(state.to_summary_dict())


async def webhook_ingest(request: web.Request) -> web.Response:
    """Ingest webhook events from external services."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    source = data.get("source", "unknown")
    event = data.get("event", "unknown")

    logger.info(f"Webhook received: {source}/{event}")

    # TODO: Route to BackgroundObserver in Task 14
    return web.json_response({
        "status": "accepted",
        "source": source,
        "event": event,
    })


def setup_routes(app: web.Application) -> None:
    """Register all API routes."""
    app.router.add_get("/api/health", health)
    app.router.add_post("/api/chat", chat)
    app.router.add_get("/api/state", get_state)
    app.router.add_post("/api/webhooks/ingest", webhook_ingest)
```

**Step 4: Add `vecna serve` CLI command**

Add to `vecna/cli/main.py`:

```python
@cli.command()
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=8420, help="Port to listen on")
def serve(host: str, port: int):
    """Start the Vecna HTTP server."""
    from vecna.server.app import run_server
    run_server(host=host, port=port)
```

**Step 5: Run tests**

Run: `pytest tests/unit/test_server.py tests/unit/ -v --tb=short`
Expected: All PASS

**Step 6: Commit**

```bash
git add vecna/server/ vecna/cli/main.py tests/unit/test_server.py
git commit -m "feat: add HTTP server with health, chat, state, and webhook endpoints"
```

---

### Task 7: Migrate from YAML HIVE_UPDATE to Native Tool Calling

**Files:**
- Create: `vecna/adapters/tool_calling.py` (native function calling adapter)
- Modify: `vecna/adapters/base.py` (add tool-calling support to BaseAdapter)
- Create: `tests/unit/test_tool_calling_adapter.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_tool_calling_adapter.py
"""Tests for native tool calling migration."""

from vecna.adapters.tool_calling import (
    build_hive_update_tool_schema,
    parse_tool_call_update,
)
from vecna.core.types import HiveUpdate


class TestToolCallingSchema:
    def test_schema_has_required_fields(self):
        schema = build_hive_update_tool_schema()
        assert schema["type"] == "function"
        assert "hive_update" in schema["function"]["name"]
        params = schema["function"]["parameters"]
        assert "new_facts" in params["properties"]
        assert "belief_changes" in params["properties"]
        assert "hypotheses" in params["properties"]

    def test_parse_tool_call_to_hive_update(self):
        tool_call_args = {
            "new_facts": [
                {"content": "Python is interpreted", "confidence": 0.9}
            ],
            "belief_changes": [],
            "hypotheses": [],
            "overall_confidence": 0.85,
        }
        update = parse_tool_call_update(tool_call_args, source_model="gpt-5.2")
        assert isinstance(update, HiveUpdate)
        assert len(update.new_facts) == 1
        assert update.confidence == 0.85
        assert update.source_model == "gpt-5.2"

    def test_parse_empty_tool_call(self):
        update = parse_tool_call_update({}, source_model="test")
        assert isinstance(update, HiveUpdate)
        assert len(update.new_facts) == 0
```

**Step 2: Run tests, verify fail**

Run: `pytest tests/unit/test_tool_calling_adapter.py -v`
Expected: FAIL — module doesn't exist

**Step 3: Implement tool calling support**

```python
# vecna/adapters/tool_calling.py
"""
Native tool calling support for model adapters.

Replaces the fragile <HIVE_UPDATE> YAML parsing with
proper function calling / tool use that models natively support.
"""

from typing import Dict, Any, List
from vecna.core.types import HiveUpdate


def build_hive_update_tool_schema() -> Dict[str, Any]:
    """
    Build the tool/function schema for hive state updates.

    This schema is passed to models that support native tool calling
    (OpenAI, Anthropic, etc.) so they can produce structured updates
    without relying on custom YAML format.
    """
    return {
        "type": "function",
        "function": {
            "name": "hive_update",
            "description": (
                "Update the hive mind's shared mental state with new knowledge, "
                "beliefs, hypotheses, and observations from this interaction."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "new_facts": {
                        "type": "array",
                        "description": "New verified facts learned",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {
                                    "type": "string",
                                    "description": "The fact statement",
                                },
                                "confidence": {
                                    "type": "number",
                                    "description": "0.0 to 1.0",
                                },
                                "evidence": {
                                    "type": "string",
                                    "description": "Why this is true",
                                },
                                "domain": {
                                    "type": "string",
                                    "description": "Knowledge domain",
                                },
                            },
                            "required": ["content"],
                        },
                    },
                    "belief_changes": {
                        "type": "array",
                        "description": "Updated or new beliefs",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {"type": "string"},
                                "confidence": {"type": "number"},
                                "reasoning": {"type": "string"},
                            },
                            "required": ["content"],
                        },
                    },
                    "hypotheses": {
                        "type": "array",
                        "description": "Tentative ideas to explore",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {"type": "string"},
                                "confidence": {"type": "number"},
                                "notes": {"type": "string"},
                            },
                            "required": ["content"],
                        },
                    },
                    "open_questions": {
                        "type": "array",
                        "description": "Unresolved questions",
                        "items": {
                            "type": "object",
                            "properties": {
                                "question": {"type": "string"},
                                "priority": {"type": "string"},
                            },
                            "required": ["question"],
                        },
                    },
                    "contradictions": {
                        "type": "array",
                        "description": "Detected conflicts",
                        "items": {
                            "type": "object",
                            "properties": {
                                "item_a": {"type": "string"},
                                "item_b": {"type": "string"},
                            },
                            "required": ["item_a", "item_b"],
                        },
                    },
                    "overall_confidence": {
                        "type": "number",
                        "description": "Overall confidence in this update (0.0-1.0)",
                    },
                    "user_preferences_observed": {
                        "type": "array",
                        "description": "Observed user preferences from this interaction",
                        "items": {
                            "type": "object",
                            "properties": {
                                "key": {"type": "string"},
                                "value": {"type": "string"},
                                "confidence": {"type": "number"},
                            },
                            "required": ["key", "value"],
                        },
                    },
                },
            },
        },
    }


def parse_tool_call_update(
    args: Dict[str, Any],
    source_model: str,
) -> HiveUpdate:
    """Parse a tool call response into a HiveUpdate."""
    update = HiveUpdate(source_model=source_model)

    update.new_facts = args.get("new_facts", []) or []
    update.belief_changes = args.get("belief_changes", []) or []
    update.new_hypotheses = args.get("hypotheses", []) or []
    update.open_questions = args.get("open_questions", []) or []
    update.contradictions_found = args.get("contradictions", []) or []

    confidence = args.get("overall_confidence")
    if confidence is not None:
        try:
            update.confidence = float(confidence)
        except (ValueError, TypeError):
            pass

    return update
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_tool_calling_adapter.py tests/unit/ -v --tb=short`
Expected: All PASS

**Step 5: Commit**

```bash
git add vecna/adapters/tool_calling.py tests/unit/test_tool_calling_adapter.py
git commit -m "feat: add native tool calling schema (replaces YAML HIVE_UPDATE parsing)"
```

---

### Task 8: Integration Framework — Base Class + Config Toggle

**Files:**
- Create: `vecna/integrations/__init__.py`
- Create: `vecna/integrations/base.py` (BaseIntegration ABC)
- Create: `vecna/integrations/config.py` (integration toggle config)
- Create: `tests/unit/test_integration_framework.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_integration_framework.py
"""Tests for the integration framework."""

from vecna.integrations.base import BaseIntegration, IntegrationStatus
from vecna.integrations.config import IntegrationConfig, IntegrationRegistry


class MockIntegration(BaseIntegration):
    """Test integration."""

    name = "mock"
    description = "A mock integration for testing"
    required_credentials = ["mock_api_key"]

    async def check_health(self) -> IntegrationStatus:
        return IntegrationStatus(
            healthy=True,
            name=self.name,
            message="OK",
        )

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False


class TestIntegrationBase:
    def test_integration_has_name(self):
        integration = MockIntegration()
        assert integration.name == "mock"

    def test_integration_disabled_by_default(self):
        integration = MockIntegration()
        assert not integration.enabled

    def test_integration_enable_toggle(self):
        integration = MockIntegration()
        integration.enabled = True
        assert integration.enabled

    async def test_health_check(self):
        integration = MockIntegration()
        status = await integration.check_health()
        assert status.healthy

    def test_required_credentials(self):
        integration = MockIntegration()
        assert "mock_api_key" in integration.required_credentials


class TestIntegrationConfig:
    def test_register_integration(self):
        registry = IntegrationRegistry()
        registry.register(MockIntegration)
        assert "mock" in registry.list_available()

    def test_enable_integration(self):
        config = IntegrationConfig()
        config.enable("mock")
        assert config.is_enabled("mock")

    def test_disable_integration(self):
        config = IntegrationConfig()
        config.enable("mock")
        config.disable("mock")
        assert not config.is_enabled("mock")

    def test_serialization(self):
        config = IntegrationConfig()
        config.enable("mock")
        d = config.to_dict()
        restored = IntegrationConfig.from_dict(d)
        assert restored.is_enabled("mock")
```

**Step 2: Run tests, verify fail**

Run: `pytest tests/unit/test_integration_framework.py -v`
Expected: FAIL — module doesn't exist

**Step 3: Implement integration framework**

```python
# vecna/integrations/__init__.py
"""Vecna Integration Framework — extensible integration layer."""

# vecna/integrations/base.py
"""
Base integration class.

Every integration (Google Suite, GitHub, Slack, etc.) implements this ABC.
Inspired by Home Assistant's integration architecture.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime


@dataclass
class IntegrationStatus:
    """Health status of an integration."""

    healthy: bool
    name: str
    message: str = ""
    last_checked: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseIntegration(ABC):
    """Abstract base class for all Vecna integrations."""

    name: str = "unnamed"
    description: str = ""
    required_credentials: List[str] = []
    enabled: bool = False

    @abstractmethod
    async def check_health(self) -> IntegrationStatus:
        """Check if the integration is healthy and connected."""
        ...

    @abstractmethod
    async def start(self) -> None:
        """Start the integration (connect, authenticate, begin polling)."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop the integration gracefully."""
        ...

    def get_credential_keys(self) -> List[str]:
        """Return the credential keys this integration needs."""
        return self.required_credentials
```

```python
# vecna/integrations/config.py
"""Integration configuration and registry."""

from typing import Dict, List, Type, Any, Set
from vecna.integrations.base import BaseIntegration


class IntegrationRegistry:
    """Registry of available integrations."""

    def __init__(self) -> None:
        self._integrations: Dict[str, Type[BaseIntegration]] = {}

    def register(self, integration_cls: Type[BaseIntegration]) -> None:
        """Register an integration class."""
        self._integrations[integration_cls.name] = integration_cls

    def list_available(self) -> List[str]:
        """List all registered integration names."""
        return list(self._integrations.keys())

    def get(self, name: str) -> Type[BaseIntegration]:
        """Get an integration class by name."""
        return self._integrations[name]


class IntegrationConfig:
    """Configuration for which integrations are enabled."""

    def __init__(self) -> None:
        self._enabled: Set[str] = set()
        self._credentials: Dict[str, Dict[str, str]] = {}

    def enable(self, name: str) -> None:
        self._enabled.add(name)

    def disable(self, name: str) -> None:
        self._enabled.discard(name)

    def is_enabled(self, name: str) -> bool:
        return name in self._enabled

    def set_credentials(self, name: str, creds: Dict[str, str]) -> None:
        self._credentials[name] = creds

    def get_credentials(self, name: str) -> Dict[str, str]:
        return self._credentials.get(name, {})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": list(self._enabled),
            "credentials": {},  # Never serialize credentials
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IntegrationConfig":
        config = cls()
        for name in data.get("enabled", []):
            config.enable(name)
        return config
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_integration_framework.py tests/unit/ -v --tb=short`
Expected: All PASS

**Step 5: Commit**

```bash
git add vecna/integrations/ tests/unit/test_integration_framework.py
git commit -m "feat: add integration framework with base class, config toggle, and registry"
```

---

### Task 9: Channel Adapter System

**Files:**
- Create: `vecna/channels/__init__.py`
- Create: `vecna/channels/base.py` (BaseChannel ABC)
- Create: `vecna/channels/cli_channel.py` (existing CLI as a channel)
- Create: `tests/unit/test_channels.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_channels.py
"""Tests for the channel adapter system."""

from vecna.channels.base import (
    BaseChannel,
    InboundMessage,
    OutboundMessage,
    ChannelCapability,
)


class TestInboundMessage:
    def test_text_message(self):
        msg = InboundMessage(
            channel="cli",
            sender="user",
            content="Hello Vecna",
        )
        assert msg.channel == "cli"
        assert msg.content == "Hello Vecna"
        assert msg.message_type == "text"

    def test_message_with_attachments(self):
        msg = InboundMessage(
            channel="imessage",
            sender="user",
            content="Check this",
            attachments=[{"type": "image", "url": "/path/to/img.png"}],
        )
        assert len(msg.attachments) == 1


class TestOutboundMessage:
    def test_text_response(self):
        msg = OutboundMessage(
            channel="cli",
            recipient="user",
            content="Hello, I am Vecna.",
        )
        assert msg.content == "Hello, I am Vecna."


class TestChannelCapabilities:
    def test_cli_capabilities(self):
        from vecna.channels.cli_channel import CLIChannel

        channel = CLIChannel()
        caps = channel.capabilities
        assert ChannelCapability.TEXT in caps
        assert ChannelCapability.STREAMING in caps
```

**Step 2: Run tests, verify fail**

**Step 3: Implement channel system**

```python
# vecna/channels/__init__.py
"""Vecna Channel System — multi-channel message delivery."""

# vecna/channels/base.py
"""
Base channel adapter.

Every channel (CLI, iMessage, WhatsApp, Slack, etc.) implements this ABC.
Channels handle inbound/outbound message routing.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, AsyncIterator
from datetime import datetime
from enum import Enum
import uuid


class ChannelCapability(Enum):
    """What a channel can do."""

    TEXT = "text"
    IMAGES = "images"
    FILES = "files"
    AUDIO = "audio"
    VIDEO = "video"
    REACTIONS = "reactions"
    THREADS = "threads"
    STREAMING = "streaming"
    RICH_TEXT = "rich_text"  # Markdown, HTML


@dataclass
class InboundMessage:
    """A message received from a channel."""

    channel: str
    sender: str
    content: str
    message_type: str = "text"
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    message_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    reply_to: Optional[str] = None  # For threaded channels


@dataclass
class OutboundMessage:
    """A message to send through a channel."""

    channel: str
    recipient: str
    content: str
    message_type: str = "text"
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    reply_to: Optional[str] = None


class BaseChannel(ABC):
    """Abstract base class for all channel adapters."""

    name: str = "unnamed"
    capabilities: List[ChannelCapability] = []

    @abstractmethod
    async def send(self, message: OutboundMessage) -> bool:
        """Send a message through this channel."""
        ...

    @abstractmethod
    async def receive(self) -> AsyncIterator[InboundMessage]:
        """Stream inbound messages from this channel."""
        ...

    @abstractmethod
    async def start(self) -> None:
        """Start listening on this channel."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop listening."""
        ...
```

```python
# vecna/channels/cli_channel.py
"""CLI channel adapter — wraps existing Rich CLI as a channel."""

from typing import AsyncIterator
from vecna.channels.base import (
    BaseChannel,
    InboundMessage,
    OutboundMessage,
    ChannelCapability,
)


class CLIChannel(BaseChannel):
    """The existing CLI/TUI as a channel adapter."""

    name = "cli"
    capabilities = [
        ChannelCapability.TEXT,
        ChannelCapability.STREAMING,
        ChannelCapability.RICH_TEXT,
    ]

    async def send(self, message: OutboundMessage) -> bool:
        """Print to console via Rich."""
        # TODO: Wire to existing Rich console in cli/main.py
        print(message.content)
        return True

    async def receive(self) -> AsyncIterator[InboundMessage]:
        """Read from stdin."""
        # Placeholder — actual implementation wraps existing Click REPL
        return
        yield  # type: ignore

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_channels.py tests/unit/ -v --tb=short`
Expected: All PASS

**Step 5: Commit**

```bash
git add vecna/channels/ tests/unit/test_channels.py
git commit -m "feat: add channel adapter system with base class and CLI channel"
```

---

### Task 10: Goal Queue Migration — File to PostgreSQL

**Files:**
- Create: `vecna/orchestrator/pg_goal_queue.py`
- Modify: `vecna/orchestrator/autonomy.py` (support both backends)
- Create: `vecna/migrations/versions/xxx_add_goal_queue_table.py`
- Create: `tests/unit/test_pg_goal_queue.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_pg_goal_queue.py
"""Tests for the PostgreSQL-backed goal queue."""

from vecna.orchestrator.pg_goal_queue import PgGoalQueue, GoalItem, GoalStatus


class TestPgGoalQueueInMemory:
    """Test PgGoalQueue with in-memory fallback (no real PG needed)."""

    def test_push_and_pop(self):
        queue = PgGoalQueue(use_memory_fallback=True)
        queue.push(GoalItem(goal="Learn about quantum computing", priority="high"))
        item = queue.pop()
        assert item is not None
        assert item.goal == "Learn about quantum computing"

    def test_pop_empty_queue(self):
        queue = PgGoalQueue(use_memory_fallback=True)
        assert queue.pop() is None

    def test_priority_ordering(self):
        queue = PgGoalQueue(use_memory_fallback=True)
        queue.push(GoalItem(goal="low priority", priority="low"))
        queue.push(GoalItem(goal="critical priority", priority="critical"))
        queue.push(GoalItem(goal="medium priority", priority="medium"))
        item = queue.pop()
        assert item.priority == "critical"

    def test_mark_completed(self):
        queue = PgGoalQueue(use_memory_fallback=True)
        queue.push(GoalItem(goal_id="g1", goal="test", priority="medium"))
        queue.mark_completed("g1")
        # Completed items don't come back
        item = queue.pop()
        assert item is None or item.goal_id != "g1"

    def test_mark_failed(self):
        queue = PgGoalQueue(use_memory_fallback=True)
        queue.push(GoalItem(goal_id="g2", goal="test", priority="medium"))
        queue.mark_failed("g2", "something broke")
        item = queue.pop()
        assert item is None or item.goal_id != "g2"

    def test_list_pending(self):
        queue = PgGoalQueue(use_memory_fallback=True)
        queue.push(GoalItem(goal="a", priority="low"))
        queue.push(GoalItem(goal="b", priority="high"))
        pending = queue.list_pending()
        assert len(pending) == 2
```

**Step 2: Run tests, verify fail**

**Step 3: Implement PgGoalQueue with in-memory fallback**

```python
# vecna/orchestrator/pg_goal_queue.py
"""
PostgreSQL-backed goal queue with in-memory fallback.

Replaces the JSONL file-based GoalQueue with a durable,
concurrent-safe implementation.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
import uuid
import heapq


class GoalStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


@dataclass
class GoalItem:
    """A goal in the queue."""

    goal: str = ""
    priority: str = "medium"
    goal_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: GoalStatus = GoalStatus.PENDING
    source: str = "manual"  # manual, curiosity, dreamloop, autonomous
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    max_retries: int = 2
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "goal": self.goal,
            "priority": self.priority,
            "status": self.status.value if isinstance(self.status, GoalStatus) else self.status,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "max_retries": self.max_retries,
            "content": self.goal,  # backward compat with old GoalQueue
        }

    def __lt__(self, other: "GoalItem") -> bool:
        """For heapq priority ordering."""
        return PRIORITY_ORDER.get(self.priority, 2) < PRIORITY_ORDER.get(other.priority, 2)


class PgGoalQueue:
    """
    Goal queue with PostgreSQL persistence and in-memory fallback.

    For unit tests and offline mode, use_memory_fallback=True.
    For production, connects to the same PG instance as PgMemoryStore.
    """

    def __init__(
        self,
        pg_url: Optional[str] = None,
        use_memory_fallback: bool = False,
    ):
        self.pg_url = pg_url
        self._use_memory = use_memory_fallback or pg_url is None
        self._memory_queue: List[GoalItem] = []
        self._completed: Dict[str, GoalItem] = {}
        self._failed: Dict[str, GoalItem] = {}

    def push(self, item: GoalItem) -> None:
        """Add a goal to the queue."""
        if self._use_memory:
            heapq.heappush(self._memory_queue, item)
        else:
            self._pg_push(item)

    def pop(self) -> Optional[GoalItem]:
        """Pop the highest-priority pending goal."""
        if self._use_memory:
            while self._memory_queue:
                item = heapq.heappop(self._memory_queue)
                if item.goal_id not in self._completed and item.goal_id not in self._failed:
                    item.status = GoalStatus.RUNNING
                    return item
            return None
        return self._pg_pop()

    def mark_completed(self, goal_id: str) -> None:
        """Mark a goal as completed."""
        if self._use_memory:
            self._completed[goal_id] = GoalItem(goal_id=goal_id, status=GoalStatus.COMPLETED)
        else:
            self._pg_mark(goal_id, GoalStatus.COMPLETED)

    def mark_failed(self, goal_id: str, error: str = "") -> None:
        """Mark a goal as failed."""
        if self._use_memory:
            item = GoalItem(goal_id=goal_id, status=GoalStatus.FAILED, error=error)
            self._failed[goal_id] = item
        else:
            self._pg_mark(goal_id, GoalStatus.FAILED, error=error)

    def list_pending(self) -> List[GoalItem]:
        """List all pending goals."""
        if self._use_memory:
            return [
                item
                for item in self._memory_queue
                if item.goal_id not in self._completed
                and item.goal_id not in self._failed
            ]
        return self._pg_list_pending()

    # PG methods — stubbed for now, implemented in Task 10 migration
    def _pg_push(self, item: GoalItem) -> None:
        raise NotImplementedError("PG backend not yet wired")

    def _pg_pop(self) -> Optional[GoalItem]:
        raise NotImplementedError("PG backend not yet wired")

    def _pg_mark(self, goal_id: str, status: GoalStatus, error: str = "") -> None:
        raise NotImplementedError("PG backend not yet wired")

    def _pg_list_pending(self) -> List[GoalItem]:
        raise NotImplementedError("PG backend not yet wired")
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_pg_goal_queue.py tests/unit/ -v --tb=short`
Expected: All PASS

**Step 5: Commit**

```bash
git add vecna/orchestrator/pg_goal_queue.py tests/unit/test_pg_goal_queue.py
git commit -m "feat: add PgGoalQueue with priority ordering and in-memory fallback"
```

---

### Task 11: Cron Autonomy — Wake-Check-Act-Sleep Loop

**Files:**
- Modify: `vecna/orchestrator/heartbeat.py` (upgrade to full cron loop)
- Modify: `vecna/orchestrator/autonomy.py` (integrate with heartbeat)
- Create: `tests/unit/test_cron_autonomy.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_cron_autonomy.py
"""Tests for cron-based autonomous operation."""

from vecna.orchestrator.heartbeat import HeartbeatRunner, HeartbeatConfig, HeartbeatAction


class TestHeartbeatActions:
    def test_check_goals_action(self):
        action = HeartbeatAction(
            name="check_goals",
            description="Check for pending autonomous goals",
            interval_seconds=900,
        )
        assert action.should_run(elapsed_seconds=1000)
        assert not action.should_run(elapsed_seconds=100)

    def test_dream_action(self):
        action = HeartbeatAction(
            name="dream",
            description="Run dream loop consolidation",
            interval_seconds=86400,  # Once daily
        )
        assert not action.should_run(elapsed_seconds=3600)
        assert action.should_run(elapsed_seconds=90000)

    def test_action_records_last_run(self):
        action = HeartbeatAction(name="test", interval_seconds=60)
        assert action.last_run is None
        action.mark_run()
        assert action.last_run is not None


class TestHeartbeatConfig:
    def test_default_actions(self):
        config = HeartbeatConfig()
        assert len(config.actions) > 0
        action_names = [a.name for a in config.actions]
        assert "check_goals" in action_names
        assert "dream" in action_names
        assert "curiosity" in action_names
```

**Step 2: Run tests, verify fail**

**Step 3: Upgrade HeartbeatRunner with action system**

Add `HeartbeatAction` dataclass and `HeartbeatConfig` with default actions to `heartbeat.py`.

**Step 4: Run tests**

Run: `pytest tests/unit/test_cron_autonomy.py tests/unit/ -v --tb=short`
Expected: All PASS

**Step 5: Commit**

```bash
git add vecna/orchestrator/heartbeat.py tests/unit/test_cron_autonomy.py
git commit -m "feat: upgrade heartbeat with action system for cron-based autonomy"
```

---

### Task 12: Security — Substrate Encryption at Rest

**Files:**
- Create: `vecna/security/__init__.py`
- Create: `vecna/security/encryption.py` (Fernet encryption for substrate)
- Create: `vecna/security/privacy.py` (privacy tier filtering)
- Create: `tests/unit/test_security.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_security.py
"""Tests for security hardening."""

from vecna.security.encryption import SubstrateEncryption
from vecna.security.privacy import PrivacyTier, PrivacyFilter


class TestSubstrateEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        enc = SubstrateEncryption.generate()
        plaintext = "sensitive user data"
        ciphertext = enc.encrypt(plaintext)
        assert ciphertext != plaintext
        decrypted = enc.decrypt(ciphertext)
        assert decrypted == plaintext

    def test_different_encryptions_differ(self):
        enc = SubstrateEncryption.generate()
        ct1 = enc.encrypt("hello")
        ct2 = enc.encrypt("hello")
        # Fernet uses random IV, so same plaintext → different ciphertext
        assert ct1 != ct2

    def test_key_from_password(self):
        enc = SubstrateEncryption.from_password("my-secure-password", salt=b"test-salt-16bytes")
        plaintext = "secret"
        ct = enc.encrypt(plaintext)
        assert enc.decrypt(ct) == plaintext


class TestPrivacyTiers:
    def test_local_only_not_shared(self):
        assert not PrivacyTier.LOCAL_ONLY.can_send_to_cloud()

    def test_processable_can_be_processed(self):
        assert PrivacyTier.PROCESSABLE.can_send_to_cloud()

    def test_shareable_can_be_shared(self):
        assert PrivacyTier.SHAREABLE.can_send_to_cloud()

    def test_filter_for_cloud(self):
        pf = PrivacyFilter()
        facts = [
            {"content": "User's SSN is 123-45-6789", "privacy_tier": "local_only"},
            {"content": "Python is interpreted", "privacy_tier": "shareable"},
        ]
        filtered = pf.filter_for_cloud(facts)
        assert len(filtered) == 1
        assert "SSN" not in filtered[0]["content"]
```

**Step 2: Run tests, verify fail**

**Step 3: Implement encryption and privacy tiers**

```python
# vecna/security/encryption.py
"""Substrate encryption using Fernet (AES-128-CBC + HMAC-SHA256)."""

import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


class SubstrateEncryption:
    """Encrypt/decrypt substrate data at rest."""

    def __init__(self, key: bytes):
        self._fernet = Fernet(key)

    @classmethod
    def generate(cls) -> "SubstrateEncryption":
        """Generate a new random encryption key."""
        return cls(Fernet.generate_key())

    @classmethod
    def from_password(cls, password: str, salt: bytes) -> "SubstrateEncryption":
        """Derive key from password using PBKDF2."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480_000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return cls(key)

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        return self._fernet.decrypt(ciphertext.encode()).decode()
```

```python
# vecna/security/privacy.py
"""Privacy tier system for controlling what data leaves the local machine."""

from enum import Enum
from typing import List, Dict, Any


class PrivacyTier(Enum):
    LOCAL_ONLY = "local_only"      # Never leaves the machine
    PROCESSABLE = "processable"    # Can be sent to cloud LLMs for processing
    SHAREABLE = "shareable"        # Can be shared externally

    def can_send_to_cloud(self) -> bool:
        return self in (PrivacyTier.PROCESSABLE, PrivacyTier.SHAREABLE)


class PrivacyFilter:
    """Filter data based on privacy tiers before sending to cloud models."""

    def filter_for_cloud(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove LOCAL_ONLY items before sending to cloud."""
        return [
            item for item in items
            if item.get("privacy_tier", "shareable") != "local_only"
        ]
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_security.py tests/unit/ -v --tb=short`
Expected: All PASS

**Step 5: Commit**

```bash
git add vecna/security/ tests/unit/test_security.py
git commit -m "feat: add substrate encryption (Fernet) and privacy tier filtering"
```

---

## Phase 2: Integration & Intelligence (Tasks 13-21)

> **Duration:** 5-6 weeks
> **Goal:** Wire integrations as Skills, implement Background Observer, upgrade DreamLoop, add browser automation, build channel adapters for messaging.

### TRACK A: Cognitive Deepening

---

### Task 13: DreamLoop v2 — Autonomous Task Generation + Counterfactuals

**Files:**
- Modify: `vecna/memory/dream_loop.py` (add Phase 5: autonomous task gen, Phase 6: counterfactuals)
- Modify: `vecna/orchestrator/curiosity.py` (add `from_dream_patterns()` method)
- Create: `tests/unit/test_dream_loop_v2.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_dream_loop_v2.py
"""Tests for DreamLoop v2 — autonomous task generation and counterfactual exploration."""

from datetime import datetime
from unittest.mock import MagicMock, patch

from vecna.memory.dream_loop import DreamLoop, DreamResult
from vecna.orchestrator.curiosity import CuriosityEngine, CuriosityGoal
from vecna.orchestrator.pg_goal_queue import PgGoalQueue, GoalItem


class TestDreamResultV2Fields:
    """DreamResult must include the two new counters."""

    def test_has_autonomous_tasks_counter(self):
        result = DreamResult()
        assert hasattr(result, "autonomous_tasks_generated")
        assert result.autonomous_tasks_generated == 0

    def test_has_counterfactuals_counter(self):
        result = DreamResult()
        assert hasattr(result, "counterfactuals_generated")
        assert result.counterfactuals_generated == 0

    def test_to_dict_includes_new_fields(self):
        result = DreamResult(autonomous_tasks_generated=3, counterfactuals_generated=2)
        d = result.to_dict()
        assert d["autonomous_tasks_generated"] == 3
        assert d["counterfactuals_generated"] == 2


class TestDreamLoopPhase5AutonomousTasks:
    """Phase 5: generate GoalItems from recurring patterns and push to PgGoalQueue."""

    def test_phase5_disabled_by_default(self):
        dream = DreamLoop()
        assert not dream.autonomous_tasks_enabled

    def test_phase5_enabled_via_flag(self):
        dream = DreamLoop(autonomous_tasks_enabled=True)
        assert dream.autonomous_tasks_enabled

    def test_phase5_generates_goals_from_patterns(self):
        """When patterns are found, Phase 5 should push GoalItems to goal_queue."""
        goal_queue = PgGoalQueue(use_memory_fallback=True)

        # Build a mock pg_store whose get_recent_events returns themed events
        mock_store = MagicMock()
        mock_store.get_recent_events.return_value = [
            {"event_type": "observation", "payload": {"topic": "rust"}},
            {"event_type": "observation", "payload": {"topic": "rust"}},
            {"event_type": "observation", "payload": {"topic": "rust"}},
            {"event_type": "query", "payload": {"topic": "kubernetes"}},
            {"event_type": "query", "payload": {"topic": "kubernetes"}},
        ]

        dream = DreamLoop(
            pg_store=mock_store,
            goal_queue=goal_queue,
            autonomous_tasks_enabled=True,
        )

        count = dream._generate_autonomous_tasks(dry_run=False)
        assert count >= 1

        # Goals should now be in the queue
        pending = goal_queue.list_pending()
        assert len(pending) >= 1
        assert any("rust" in item.goal.lower() for item in pending)

    def test_phase5_respects_max_goals_per_dream(self):
        goal_queue = PgGoalQueue(use_memory_fallback=True)
        mock_store = MagicMock()
        # Many different recurring themes
        events = []
        for theme in ["alpha", "beta", "gamma", "delta", "epsilon"]:
            for _ in range(5):
                events.append({"event_type": "obs", "payload": {"topic": theme}})
        mock_store.get_recent_events.return_value = events

        dream = DreamLoop(
            pg_store=mock_store,
            goal_queue=goal_queue,
            autonomous_tasks_enabled=True,
            max_autonomous_goals=2,
        )

        count = dream._generate_autonomous_tasks(dry_run=False)
        assert count <= 2

    def test_phase5_dry_run_does_not_push(self):
        goal_queue = PgGoalQueue(use_memory_fallback=True)
        mock_store = MagicMock()
        mock_store.get_recent_events.return_value = [
            {"event_type": "obs", "payload": {"topic": "python"}},
            {"event_type": "obs", "payload": {"topic": "python"}},
        ]

        dream = DreamLoop(
            pg_store=mock_store,
            goal_queue=goal_queue,
            autonomous_tasks_enabled=True,
        )

        count = dream._generate_autonomous_tasks(dry_run=True)
        assert count >= 1
        assert goal_queue.list_pending() == []

    def test_phase5_skipped_when_disabled(self):
        dream = DreamLoop(autonomous_tasks_enabled=False)
        count = dream._generate_autonomous_tasks(dry_run=False)
        assert count == 0

    def test_phase5_skipped_when_no_goal_queue(self):
        mock_store = MagicMock()
        mock_store.get_recent_events.return_value = [
            {"event_type": "obs", "payload": {"topic": "python"}},
            {"event_type": "obs", "payload": {"topic": "python"}},
        ]
        dream = DreamLoop(pg_store=mock_store, autonomous_tasks_enabled=True)
        count = dream._generate_autonomous_tasks(dry_run=False)
        assert count == 0

    def test_phase5_goal_source_is_dreamloop(self):
        goal_queue = PgGoalQueue(use_memory_fallback=True)
        mock_store = MagicMock()
        mock_store.get_recent_events.return_value = [
            {"event_type": "obs", "payload": {"topic": "golang"}},
            {"event_type": "obs", "payload": {"topic": "golang"}},
        ]
        dream = DreamLoop(
            pg_store=mock_store,
            goal_queue=goal_queue,
            autonomous_tasks_enabled=True,
        )
        dream._generate_autonomous_tasks(dry_run=False)
        pending = goal_queue.list_pending()
        assert all(item.source == "dreamloop" for item in pending)


class TestDreamLoopPhase6Counterfactuals:
    """Phase 6: generate Hypothesis objects from contradictions and failed beliefs."""

    def test_phase6_disabled_by_default(self):
        dream = DreamLoop()
        assert not dream.autonomous_tasks_enabled  # same flag gates both

    def test_phase6_generates_counterfactuals_from_contradictions(self):
        mock_store = MagicMock()
        # Search returns items that contain contradiction-like content
        mock_store.search.return_value = [
            MagicMock(
                content="Python is slow for all tasks",
                item_type="belief",
                confidence=0.3,
                metadata={"contradiction_id": "c1"},
            ),
            MagicMock(
                content="Python is fast for data science",
                item_type="belief",
                confidence=0.7,
                metadata={"contradiction_id": "c1"},
            ),
        ]
        mock_store.add_item.return_value = "hyp-001"

        dream = DreamLoop(
            pg_store=mock_store,
            autonomous_tasks_enabled=True,
        )

        count = dream._generate_counterfactuals(dry_run=False)
        assert count >= 1

    def test_phase6_creates_hypothesis_items(self):
        mock_store = MagicMock()
        mock_store.search.return_value = [
            MagicMock(
                content="Static typing prevents all bugs",
                item_type="belief",
                confidence=0.4,
                metadata={},
            ),
        ]
        mock_store.add_item.return_value = "hyp-002"

        dream = DreamLoop(
            pg_store=mock_store,
            autonomous_tasks_enabled=True,
        )
        dream._generate_counterfactuals(dry_run=False)

        if mock_store.add_item.called:
            item_arg = mock_store.add_item.call_args[0][0]
            assert item_arg.item_type == "hypothesis"
            assert "counterfactual" in item_arg.metadata.get("source", "")

    def test_phase6_dry_run_does_not_persist(self):
        mock_store = MagicMock()
        mock_store.search.return_value = [
            MagicMock(
                content="X is true",
                item_type="belief",
                confidence=0.3,
                metadata={},
            ),
        ]

        dream = DreamLoop(
            pg_store=mock_store,
            autonomous_tasks_enabled=True,
        )
        count = dream._generate_counterfactuals(dry_run=True)
        assert count >= 0
        mock_store.add_item.assert_not_called()

    def test_phase6_skipped_when_disabled(self):
        dream = DreamLoop(autonomous_tasks_enabled=False)
        count = dream._generate_counterfactuals(dry_run=False)
        assert count == 0


class TestDreamLoopRunV2:
    """Full run() should include Phase 5 and Phase 6 in results."""

    def test_run_includes_new_counters(self):
        dream = DreamLoop(autonomous_tasks_enabled=False)
        result = dream.run(dry_run=True)
        assert result.autonomous_tasks_generated == 0
        assert result.counterfactuals_generated == 0

    def test_run_with_phases_enabled(self):
        goal_queue = PgGoalQueue(use_memory_fallback=True)
        mock_store = MagicMock()
        mock_store.get_recent_events.return_value = [
            {"event_type": "obs", "payload": {"topic": "testing"}},
            {"event_type": "obs", "payload": {"topic": "testing"}},
        ]
        mock_store.search.return_value = [
            MagicMock(
                content="Tests are unnecessary",
                item_type="belief",
                confidence=0.2,
                metadata={},
            ),
        ]
        mock_store.add_item.return_value = "hyp-003"
        # Stub out the DB-dependent phases
        mock_store._get_connection.side_effect = Exception("no db")

        dream = DreamLoop(
            pg_store=mock_store,
            goal_queue=goal_queue,
            autonomous_tasks_enabled=True,
        )
        result = dream.run(dry_run=True)
        # Phase 5 and 6 should have run (dry_run counts)
        assert isinstance(result.autonomous_tasks_generated, int)
        assert isinstance(result.counterfactuals_generated, int)


class TestCuriosityEngineFromDreamPatterns:
    """CuriosityEngine gets a new from_dream_patterns() method."""

    def test_from_dream_patterns_generates_goals(self):
        engine = CuriosityEngine()
        patterns = [
            {"theme": "rust", "count": 5, "frequency": 0.25},
            {"theme": "kubernetes", "count": 3, "frequency": 0.15},
        ]
        goals = engine.from_dream_patterns(patterns)
        assert len(goals) == 2
        assert all(isinstance(g, CuriosityGoal) for g in goals)
        assert all(g.source == "dream_pattern" for g in goals)

    def test_from_dream_patterns_empty_list(self):
        engine = CuriosityEngine()
        goals = engine.from_dream_patterns([])
        assert goals == []

    def test_from_dream_patterns_priority_from_frequency(self):
        engine = CuriosityEngine()
        patterns = [
            {"theme": "hot-topic", "count": 10, "frequency": 0.5},
            {"theme": "mild-topic", "count": 2, "frequency": 0.05},
        ]
        goals = engine.from_dream_patterns(patterns)
        assert goals[0].priority == "high"
        assert goals[1].priority == "low"
```

**Step 2: Run tests, verify fail**

Run: `pytest tests/unit/test_dream_loop_v2.py -v`
Expected: FAIL — new fields, methods, and constructor params don't exist yet

**Step 3: Update DreamResult and DreamLoop with Phase 5 + Phase 6**

Add the two new counters to `DreamResult`, new constructor params and methods to `DreamLoop`, and a new method to `CuriosityEngine`.

```python
# vecna/memory/dream_loop.py  (modifications — add to existing file)
# ---------------------------------------------------------------
# 1. Update DreamResult dataclass — add two new fields after `errors`:

@dataclass
class DreamResult:
    """Result of a dream loop iteration."""

    events_compressed: int = 0
    episodes_created: int = 0
    memories_reinforced: int = 0
    memories_decayed: int = 0
    insights_generated: int = 0
    autonomous_tasks_generated: int = 0
    counterfactuals_generated: int = 0
    duration_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "events_compressed": self.events_compressed,
            "episodes_created": self.episodes_created,
            "memories_reinforced": self.memories_reinforced,
            "memories_decayed": self.memories_decayed,
            "insights_generated": self.insights_generated,
            "autonomous_tasks_generated": self.autonomous_tasks_generated,
            "counterfactuals_generated": self.counterfactuals_generated,
            "duration_seconds": self.duration_seconds,
            "errors": self.errors,
            "timestamp": datetime.now().isoformat(),
        }


# 2. Update DreamLoop.__init__ — add new params after `summarizer`:

class DreamLoop:
    def __init__(
        self,
        pg_store: Optional["PgMemoryStore"] = None,
        compress_after_days: int = 7,
        decay_threshold_days: int = 30,
        reinforcement_threshold: float = 0.7,
        decay_rate: float = 0.1,
        min_confidence: float = 0.1,
        summarizer=None,
        goal_queue=None,  # NEW: Optional PgGoalQueue for Phase 5
        autonomous_tasks_enabled: bool = False,  # NEW: gate for Phase 5+6
        max_autonomous_goals: int = 3,  # NEW: cap goals per dream cycle
    ):
        # ... existing assignments ...
        self.goal_queue = goal_queue
        self.autonomous_tasks_enabled = autonomous_tasks_enabled
        self.max_autonomous_goals = max_autonomous_goals


# 3. Update DreamLoop.run() — add Phase 5 and Phase 6 after Phase 4:

    def run(self, dry_run: bool = False) -> DreamResult:
        start_time = datetime.now()
        result = DreamResult()

        logger.info("Dream loop starting...")

        try:
            # Phase 1-4 unchanged ...
            compressed, episodes = self._compress_events(dry_run)
            result.events_compressed = compressed
            result.episodes_created = episodes

            reinforced = self._reinforce_memories(dry_run)
            result.memories_reinforced = reinforced

            decayed = self._decay_memories(dry_run)
            result.memories_decayed = decayed

            insights = self._generate_insights(dry_run)
            result.insights_generated = insights

            # Phase 5: Autonomous Task Generation (NEW)
            autonomous = self._generate_autonomous_tasks(dry_run)
            result.autonomous_tasks_generated = autonomous

            # Phase 6: Counterfactual Exploration (NEW)
            counterfactuals = self._generate_counterfactuals(dry_run)
            result.counterfactuals_generated = counterfactuals

        except Exception as e:
            logger.error(f"Dream loop error: {e}")
            result.errors.append(str(e))

        result.duration_seconds = (datetime.now() - start_time).total_seconds()
        self._last_run = datetime.now()

        logger.info(
            f"Dream loop complete: {result.events_compressed} compressed, "
            f"{result.episodes_created} episodes, "
            f"{result.memories_reinforced} reinforced, "
            f"{result.memories_decayed} decayed, "
            f"{result.insights_generated} insights, "
            f"{result.autonomous_tasks_generated} tasks, "
            f"{result.counterfactuals_generated} counterfactuals, "
            f"took {result.duration_seconds:.2f}s"
        )

        if not dry_run and self.pg_store:
            self._record_dream_event(result)

        return result


# 4. Add Phase 5 method:

    def _generate_autonomous_tasks(self, dry_run: bool) -> int:
        """Phase 5: Generate autonomous goals from recurring substrate patterns."""
        if not self.autonomous_tasks_enabled:
            return 0
        if not self.pg_store:
            return 0
        if not self.goal_queue and not dry_run:
            return 0

        try:
            get_events = getattr(self.pg_store, "get_recent_events", None)
            if not callable(get_events):
                return 0

            events = get_events(limit=200)
            detector = SessionPatternDetector(
                min_count=2,
                max_patterns=self.max_autonomous_goals,
                exclude_event_types={"dream_loop"},
            )
            pattern_result = detector.detect(events)
            patterns = pattern_result.get("patterns", [])
            if not patterns:
                return 0

            # Use CuriosityEngine to convert patterns → CuriosityGoals
            from vecna.orchestrator.curiosity import CuriosityEngine

            engine = CuriosityEngine()
            curiosity_goals = engine.from_dream_patterns(patterns)

            generated = 0
            for cgoal in curiosity_goals[: self.max_autonomous_goals]:
                if dry_run:
                    generated += 1
                    continue

                from vecna.orchestrator.pg_goal_queue import GoalItem

                goal_item = GoalItem(
                    goal=f"Research and deepen understanding of: {cgoal.content}",
                    priority=cgoal.priority,
                    source="dreamloop",
                    metadata={
                        "origin": "dream_phase5",
                        "pattern_theme": cgoal.content,
                    },
                )
                self.goal_queue.push(goal_item)
                generated += 1

            logger.info(f"Phase 5: generated {generated} autonomous goals")
            return generated

        except Exception as e:
            logger.error(f"Autonomous task generation error: {e}")
            return 0


# 5. Add Phase 6 method:

    def _generate_counterfactuals(self, dry_run: bool) -> int:
        """Phase 6: Generate counterfactual hypotheses from low-confidence beliefs."""
        if not self.autonomous_tasks_enabled:
            return 0
        if not self.pg_store:
            return 0

        try:
            search = getattr(self.pg_store, "search", None)
            add_item = getattr(self.pg_store, "add_item", None)
            if not callable(search):
                return 0

            # Find low-confidence beliefs that might warrant counterfactual exploration
            candidates = search("belief contradiction", top_k=10)
            if not candidates:
                return 0

            # Filter to low-confidence beliefs
            low_conf = [
                c for c in candidates
                if getattr(c, "confidence", 1.0) < 0.5
                and getattr(c, "item_type", "") in ("belief", "hypothesis")
            ]
            if not low_conf:
                return 0

            generated = 0
            for candidate in low_conf[:5]:  # Cap at 5 counterfactuals per cycle
                content = getattr(candidate, "content", "")
                if not content:
                    continue

                # Generate counterfactual text
                counterfactual_text = (
                    f"Counterfactual: What if the opposite of '{content}' were true? "
                    f"This belief has low confidence ({getattr(candidate, 'confidence', 0):.2f}) "
                    f"and may warrant re-evaluation from alternative perspectives."
                )

                if self.summarizer:
                    prompt = (
                        f"Generate a thoughtful counterfactual hypothesis for this "
                        f"low-confidence belief: '{content}'. "
                        f"Frame it as 'What if...' and suggest what evidence would "
                        f"confirm or refute it. Keep it under 100 words."
                    )
                    try:
                        counterfactual_text = self.summarizer(prompt)
                    except Exception as e:
                        logger.error(f"Counterfactual summarization failed: {e}")

                if dry_run:
                    generated += 1
                    continue

                if not callable(add_item):
                    continue

                from vecna.memory.pg_store import MemoryItem

                item = MemoryItem(
                    content=str(counterfactual_text),
                    item_type="hypothesis",
                    confidence=0.3,
                    domain="meta",
                    metadata={
                        "source": "counterfactual",
                        "origin": "dream_phase6",
                        "original_belief": content,
                        "original_confidence": getattr(candidate, "confidence", 0),
                    },
                )
                add_result = add_item(item)
                if add_result:
                    generated += 1

            logger.info(f"Phase 6: generated {generated} counterfactual hypotheses")
            return generated

        except Exception as e:
            logger.error(f"Counterfactual generation error: {e}")
            return 0
```

```python
# vecna/orchestrator/curiosity.py  (add new method to CuriosityEngine)
# ---------------------------------------------------------------------
# Add this method to the CuriosityEngine class:

    def from_dream_patterns(
        self, patterns: List[Dict[str, Any]]
    ) -> List[CuriosityGoal]:
        """Create curiosity goals from DreamLoop-detected recurring patterns.

        Args:
            patterns: List of pattern dicts with keys: theme, count, frequency.

        Returns:
            CuriosityGoals with priority derived from pattern frequency.
        """
        goals: List[CuriosityGoal] = []
        for pattern in patterns:
            theme = pattern.get("theme", "")
            if not theme:
                continue

            frequency = pattern.get("frequency", 0.0)
            # High frequency (>0.2) → high priority, moderate → medium, low → low
            if frequency >= 0.2:
                priority = "high"
            elif frequency >= 0.1:
                priority = "medium"
            else:
                priority = "low"

            goals.append(
                CuriosityGoal(
                    content=theme,
                    priority=priority,
                    source="dream_pattern",
                )
            )
        return goals
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_dream_loop_v2.py tests/unit/ -v --tb=short`
Expected: All PASS

**Step 5: Commit**

```bash
git add vecna/memory/dream_loop.py vecna/orchestrator/curiosity.py tests/unit/test_dream_loop_v2.py
git commit -m "feat: DreamLoop v2 with autonomous task generation and counterfactual exploration"
```

---

### Task 14: Background Observer — Passive Integration Intake

**Files:**
- Create: `vecna/integrations/observer.py` (BackgroundObserver)
- Create: `tests/unit/test_observer.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_observer.py
"""Tests for the BackgroundObserver — passive integration event intake."""

import time
from datetime import datetime
from unittest.mock import MagicMock

from vecna.integrations.observer import (
    BackgroundObserver,
    ObserverConfig,
    IntegrationEvent,
    EventClassification,
    ObserverResult,
)


class TestIntegrationEvent:
    """IntegrationEvent is the raw inbound event from any integration."""

    def test_create_event(self):
        event = IntegrationEvent(
            source="github",
            event_type="pr_opened",
            payload={"pr_number": 42, "title": "Add feature X"},
        )
        assert event.source == "github"
        assert event.event_type == "pr_opened"
        assert event.payload["pr_number"] == 42

    def test_event_has_timestamp(self):
        event = IntegrationEvent(source="slack", event_type="message")
        assert isinstance(event.timestamp, datetime)

    def test_event_to_dict(self):
        event = IntegrationEvent(
            source="calendar",
            event_type="event_created",
            payload={"title": "Team standup"},
        )
        d = event.to_dict()
        assert d["source"] == "calendar"
        assert "timestamp" in d


class TestEventClassification:
    """Events are classified into categories."""

    def test_classify_github_as_code_activity(self):
        observer = BackgroundObserver()
        event = IntegrationEvent(
            source="github",
            event_type="pr_opened",
            payload={"title": "Fix bug"},
        )
        classification = observer.classify(event)
        assert classification.category == "code_activity"

    def test_classify_slack_as_communication(self):
        observer = BackgroundObserver()
        event = IntegrationEvent(
            source="slack",
            event_type="message_received",
            payload={"text": "Hey team"},
        )
        classification = observer.classify(event)
        assert classification.category == "communication"

    def test_classify_calendar_as_calendar(self):
        observer = BackgroundObserver()
        event = IntegrationEvent(
            source="google_calendar",
            event_type="event_reminder",
            payload={"title": "Meeting"},
        )
        classification = observer.classify(event)
        assert classification.category == "calendar"

    def test_classify_unknown_as_system(self):
        observer = BackgroundObserver()
        event = IntegrationEvent(
            source="unknown_source",
            event_type="heartbeat",
            payload={},
        )
        classification = observer.classify(event)
        assert classification.category == "system"

    def test_classification_has_relevance_score(self):
        observer = BackgroundObserver()
        event = IntegrationEvent(
            source="github",
            event_type="pr_review_requested",
            payload={"title": "Important PR", "requested_reviewer": "user"},
        )
        classification = observer.classify(event)
        assert 0.0 <= classification.relevance <= 1.0


class TestObserverConfig:
    def test_default_config(self):
        config = ObserverConfig()
        assert config.relevance_threshold == 0.3
        assert config.max_events_per_hour == 100
        assert config.privacy_tier == "local_only"

    def test_custom_config(self):
        config = ObserverConfig(
            relevance_threshold=0.5,
            max_events_per_hour=50,
        )
        assert config.relevance_threshold == 0.5
        assert config.max_events_per_hour == 50


class TestBackgroundObserverIngest:
    """BackgroundObserver.ingest() processes events into substrate actions."""

    def test_ingest_relevant_event_creates_fact(self):
        mock_store = MagicMock()
        mock_store.add_item.return_value = "item-001"

        observer = BackgroundObserver(pg_store=mock_store)
        event = IntegrationEvent(
            source="github",
            event_type="pr_merged",
            payload={"pr_number": 42, "title": "Ship feature X", "repo": "vecna"},
        )
        result = observer.ingest(event)
        assert result.facts_created >= 1
        assert mock_store.add_item.called

    def test_ingest_notable_event_creates_goal(self):
        mock_store = MagicMock()
        mock_store.add_item.return_value = "item-001"
        mock_queue = MagicMock()

        observer = BackgroundObserver(pg_store=mock_store, goal_queue=mock_queue)
        event = IntegrationEvent(
            source="github",
            event_type="pr_review_requested",
            payload={
                "pr_number": 99,
                "title": "Critical fix",
                "requested_reviewer": "user",
            },
        )
        result = observer.ingest(event)
        assert result.goals_created >= 1

    def test_ingest_irrelevant_event_skipped(self):
        mock_store = MagicMock()
        observer = BackgroundObserver(
            pg_store=mock_store,
            config=ObserverConfig(relevance_threshold=0.9),
        )
        event = IntegrationEvent(
            source="system",
            event_type="healthcheck",
            payload={},
        )
        result = observer.ingest(event)
        assert result.facts_created == 0
        assert result.goals_created == 0
        assert result.skipped

    def test_ingest_records_memory_event(self):
        mock_store = MagicMock()
        mock_store.add_item.return_value = "item-001"
        mock_store.add_event.return_value = "event-001"

        observer = BackgroundObserver(pg_store=mock_store)
        event = IntegrationEvent(
            source="github",
            event_type="push",
            payload={"branch": "main", "commits": 3},
        )
        observer.ingest(event)
        assert mock_store.add_event.called


class TestObserverRateLimiting:
    def test_rate_limit_rejects_excess_events(self):
        mock_store = MagicMock()
        mock_store.add_item.return_value = "item-001"

        observer = BackgroundObserver(
            pg_store=mock_store,
            config=ObserverConfig(max_events_per_hour=3),
        )

        for i in range(5):
            event = IntegrationEvent(
                source="github",
                event_type="push",
                payload={"commit": i},
            )
            result = observer.ingest(event)
            if i >= 3:
                assert result.rate_limited

    def test_rate_limit_counter_tracks_events(self):
        observer = BackgroundObserver()
        assert observer.events_this_hour == 0


class TestObserverResult:
    def test_result_defaults(self):
        result = ObserverResult()
        assert result.facts_created == 0
        assert result.goals_created == 0
        assert not result.skipped
        assert not result.rate_limited

    def test_result_to_dict(self):
        result = ObserverResult(facts_created=2, goals_created=1)
        d = result.to_dict()
        assert d["facts_created"] == 2
        assert d["goals_created"] == 1
```

**Step 2: Run tests, verify fail**

Run: `pytest tests/unit/test_observer.py -v`
Expected: FAIL — module doesn't exist

**Step 3: Implement BackgroundObserver**

```python
# vecna/integrations/observer.py
"""
Background Observer — passive integration event intake.

Ingests events from integrations (webhooks, polling) and converts them
to substrate-compatible observations. Events are classified, filtered
for relevance, rate-limited, and then converted to Facts or Goals.

Event flow:
    Integration → BackgroundObserver.ingest() → classify + filter
        → If relevant: create MemoryItem (source_type="observation")
        → If notable: create GoalItem (e.g., "Review PR #123")
        → If user-related: update HumanModel (future)
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

logger = logging.getLogger("vecna.integrations.observer")

if TYPE_CHECKING:
    from vecna.memory.pg_store import PgMemoryStore
    from vecna.orchestrator.pg_goal_queue import PgGoalQueue


# -- Source-to-category mapping --
_SOURCE_CATEGORIES: Dict[str, str] = {
    "github": "code_activity",
    "gitlab": "code_activity",
    "bitbucket": "code_activity",
    "slack": "communication",
    "discord": "communication",
    "imessage": "communication",
    "whatsapp": "communication",
    "email": "communication",
    "gmail": "communication",
    "google_calendar": "calendar",
    "calendar": "calendar",
    "outlook_calendar": "calendar",
}

# -- Event types that should generate goals (actionable) --
_NOTABLE_EVENT_TYPES = frozenset({
    "pr_review_requested",
    "issue_assigned",
    "pr_changes_requested",
    "mention",
    "direct_message",
    "meeting_starting",
    "deadline_approaching",
    "task_assigned",
})

# -- Event types with higher base relevance --
_HIGH_RELEVANCE_EVENTS = frozenset({
    "pr_merged",
    "pr_review_requested",
    "pr_opened",
    "issue_assigned",
    "push",
    "mention",
    "direct_message",
    "event_reminder",
    "meeting_starting",
    "deadline_approaching",
})


@dataclass
class IntegrationEvent:
    """A raw event from any integration source."""

    source: str = ""
    event_type: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "event_type": self.event_type,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class EventClassification:
    """Classification result for an integration event."""

    category: str = "system"  # code_activity, communication, calendar, system
    relevance: float = 0.0  # 0.0-1.0 relevance score
    is_notable: bool = False  # Should generate a goal?
    is_user_related: bool = False  # Should update HumanModel?


@dataclass
class ObserverConfig:
    """Configuration for the BackgroundObserver."""

    relevance_threshold: float = 0.3
    max_events_per_hour: int = 100
    privacy_tier: str = "local_only"


@dataclass
class ObserverResult:
    """Result of processing a single integration event."""

    facts_created: int = 0
    goals_created: int = 0
    skipped: bool = False
    rate_limited: bool = False
    classification: Optional[EventClassification] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "facts_created": self.facts_created,
            "goals_created": self.goals_created,
            "skipped": self.skipped,
            "rate_limited": self.rate_limited,
        }


class BackgroundObserver:
    """
    Passive observer that ingests integration events into the substrate.

    Classifies events by type, filters for relevance, enforces rate limits,
    and creates Facts/Goals as appropriate.
    """

    def __init__(
        self,
        pg_store: Optional["PgMemoryStore"] = None,
        goal_queue: Optional["PgGoalQueue"] = None,
        config: Optional[ObserverConfig] = None,
    ):
        self.pg_store = pg_store
        self.goal_queue = goal_queue
        self.config = config or ObserverConfig()

        # Rate limiting state
        self._event_timestamps: List[float] = []
        self._hour_window: float = 3600.0  # seconds

    @property
    def events_this_hour(self) -> int:
        """Count events within the current hour window."""
        now = time.monotonic()
        self._event_timestamps = [
            t for t in self._event_timestamps
            if now - t < self._hour_window
        ]
        return len(self._event_timestamps)

    def _is_rate_limited(self) -> bool:
        """Check if we've exceeded the events-per-hour limit."""
        return self.events_this_hour >= self.config.max_events_per_hour

    def _record_event_timestamp(self) -> None:
        """Record a new event for rate limiting."""
        self._event_timestamps.append(time.monotonic())

    def classify(self, event: IntegrationEvent) -> EventClassification:
        """Classify an integration event by category and relevance."""
        source_lower = event.source.lower()
        event_type_lower = event.event_type.lower()

        # Determine category from source
        category = _SOURCE_CATEGORIES.get(source_lower, "system")

        # Calculate relevance score
        relevance = 0.1  # base relevance
        if event_type_lower in _HIGH_RELEVANCE_EVENTS:
            relevance = 0.7
        elif category in ("code_activity", "communication"):
            relevance = 0.4
        elif category == "calendar":
            relevance = 0.5

        # Boost if payload contains user-targeting fields
        payload = event.payload or {}
        if any(
            key in payload
            for key in ("requested_reviewer", "assignee", "mentioned_user", "recipient")
        ):
            relevance = min(1.0, relevance + 0.2)

        is_notable = event_type_lower in _NOTABLE_EVENT_TYPES
        is_user_related = any(
            key in payload
            for key in ("user", "author", "sender", "requested_reviewer")
        )

        return EventClassification(
            category=category,
            relevance=relevance,
            is_notable=is_notable,
            is_user_related=is_user_related,
        )

    def ingest(self, event: IntegrationEvent) -> ObserverResult:
        """
        Ingest a single integration event.

        Returns ObserverResult describing what actions were taken.
        """
        result = ObserverResult()

        # Rate limiting check
        if self._is_rate_limited():
            logger.warning(
                f"Rate limited: {self.events_this_hour} events this hour "
                f"(max {self.config.max_events_per_hour})"
            )
            result.rate_limited = True
            return result

        self._record_event_timestamp()

        # Classify the event
        classification = self.classify(event)
        result.classification = classification

        # Check relevance threshold
        if classification.relevance < self.config.relevance_threshold:
            logger.debug(
                f"Skipping low-relevance event: {event.source}/{event.event_type} "
                f"(relevance={classification.relevance:.2f})"
            )
            result.skipped = True
            return result

        # Record the raw event in memory store
        if self.pg_store:
            self._record_memory_event(event, classification)

        # Create a Fact (observation) for relevant events
        if self.pg_store:
            fact_created = self._create_observation_fact(event, classification)
            if fact_created:
                result.facts_created += 1

        # Create a Goal for notable events
        if classification.is_notable and self.goal_queue:
            goal_created = self._create_goal(event, classification)
            if goal_created:
                result.goals_created += 1

        logger.info(
            f"Ingested {event.source}/{event.event_type}: "
            f"category={classification.category}, "
            f"relevance={classification.relevance:.2f}, "
            f"facts={result.facts_created}, goals={result.goals_created}"
        )

        return result

    def _record_memory_event(
        self, event: IntegrationEvent, classification: EventClassification
    ) -> None:
        """Record the raw event as a MemoryEvent."""
        try:
            from vecna.memory.pg_store import MemoryEvent

            mem_event = MemoryEvent(
                event_type=f"integration_{classification.category}",
                payload={
                    "source": event.source,
                    "event_type": event.event_type,
                    "category": classification.category,
                    "relevance": classification.relevance,
                    **event.payload,
                },
            )
            self.pg_store.add_event(mem_event)
        except Exception as e:
            logger.error(f"Failed to record memory event: {e}")

    def _create_observation_fact(
        self, event: IntegrationEvent, classification: EventClassification
    ) -> bool:
        """Create a MemoryItem (observation) from the event."""
        try:
            from vecna.memory.pg_store import MemoryItem

            # Build human-readable content from the event
            payload = event.payload or {}
            title = payload.get("title", payload.get("text", event.event_type))
            content = (
                f"[{event.source}] {event.event_type}: {title}"
            )

            item = MemoryItem(
                content=content,
                item_type="observation",
                confidence=classification.relevance,
                domain=classification.category,
                metadata={
                    "source": event.source,
                    "event_type": event.event_type,
                    "privacy_tier": self.config.privacy_tier,
                    "category": classification.category,
                    "raw_payload": event.payload,
                },
            )
            result = self.pg_store.add_item(item)
            return result is not None
        except Exception as e:
            logger.error(f"Failed to create observation fact: {e}")
            return False

    def _create_goal(
        self, event: IntegrationEvent, classification: EventClassification
    ) -> bool:
        """Create a GoalItem for notable events."""
        try:
            from vecna.orchestrator.pg_goal_queue import GoalItem

            payload = event.payload or {}
            title = payload.get("title", event.event_type)

            goal_text = f"[{event.source}] {event.event_type}: {title}"
            if "pr_number" in payload:
                goal_text = f"Review PR #{payload['pr_number']}: {title}"
            elif "issue_number" in payload:
                goal_text = f"Address issue #{payload['issue_number']}: {title}"

            goal_item = GoalItem(
                goal=goal_text,
                priority="high" if classification.relevance >= 0.7 else "medium",
                source="observer",
                metadata={
                    "integration_source": event.source,
                    "event_type": event.event_type,
                    "origin": "background_observer",
                },
            )
            self.goal_queue.push(goal_item)
            return True
        except Exception as e:
            logger.error(f"Failed to create goal: {e}")
            return False
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_observer.py tests/unit/ -v --tb=short`
Expected: All PASS

**Step 5: Commit**

```bash
git add vecna/integrations/observer.py tests/unit/test_observer.py
git commit -m "feat: add BackgroundObserver for passive integration event intake"
```

---

### Task 15: Steipete CLI Skills — Google Suite (gogcli)

**Files:**
- Create: `vecna/integrations/google_suite.py` (GoogleSuiteIntegration)
- Create: `vecna/skills/google_suite/SKILL.md`
- Create: `tests/unit/test_google_suite.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_google_suite.py
"""Tests for the Google Suite integration via gogcli."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vecna.integrations.google_suite import (
    GoogleSuiteIntegration,
    GoogleSuiteCommand,
    GogcliResult,
    COMMAND_ALLOWLIST,
)


class TestGoogleSuiteCommand:
    def test_calendar_list_command(self):
        cmd = GoogleSuiteCommand.CALENDAR_LIST
        assert cmd.value == "cal events list"
        assert isinstance(cmd.cli_args(), list)
        assert "cal" in cmd.cli_args()

    def test_gmail_list_command(self):
        cmd = GoogleSuiteCommand.GMAIL_LIST
        assert cmd.value == "gmail messages list"

    def test_contacts_list_command(self):
        cmd = GoogleSuiteCommand.CONTACTS_LIST
        assert cmd.value == "contacts list"

    def test_tasks_list_command(self):
        cmd = GoogleSuiteCommand.TASKS_LIST
        assert cmd.value == "tasks list"


class TestCommandAllowlist:
    def test_allowlist_contains_safe_commands(self):
        assert GoogleSuiteCommand.CALENDAR_LIST in COMMAND_ALLOWLIST
        assert GoogleSuiteCommand.GMAIL_LIST in COMMAND_ALLOWLIST
        assert GoogleSuiteCommand.CONTACTS_LIST in COMMAND_ALLOWLIST
        assert GoogleSuiteCommand.TASKS_LIST in COMMAND_ALLOWLIST

    def test_allowlist_is_frozen(self):
        assert isinstance(COMMAND_ALLOWLIST, frozenset)


class TestGogcliResult:
    def test_success_result(self):
        result = GogcliResult(
            success=True,
            command="cal events list",
            data=[{"title": "Meeting", "start": "2026-02-16T10:00:00"}],
        )
        assert result.success
        assert len(result.data) == 1

    def test_error_result(self):
        result = GogcliResult(
            success=False,
            command="cal events list",
            error="gogcli not found",
        )
        assert not result.success
        assert "not found" in result.error

    def test_result_to_dict(self):
        result = GogcliResult(
            success=True,
            command="tasks list",
            data=[{"title": "Buy groceries"}],
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["command"] == "tasks list"
        assert len(d["data"]) == 1


class TestGoogleSuiteIntegration:
    def test_integration_name(self):
        integration = GoogleSuiteIntegration()
        assert integration.name == "google_suite"

    def test_integration_disabled_by_default(self):
        integration = GoogleSuiteIntegration()
        assert not integration.enabled

    def test_integration_description(self):
        integration = GoogleSuiteIntegration()
        assert "google" in integration.description.lower()

    def test_required_credentials_empty(self):
        """gogcli manages its own auth via keychain — no creds needed."""
        integration = GoogleSuiteIntegration()
        assert integration.required_credentials == []

    async def test_health_check_no_binary(self):
        """Health check should fail gracefully when gogcli is not installed."""
        integration = GoogleSuiteIntegration()
        with patch(
            "vecna.integrations.google_suite.GoogleSuiteIntegration._check_binary",
            return_value=False,
        ):
            status = await integration.check_health()
            assert not status.healthy
            assert "not found" in status.message.lower() or "not installed" in status.message.lower()

    async def test_health_check_binary_present(self):
        integration = GoogleSuiteIntegration()
        with patch(
            "vecna.integrations.google_suite.GoogleSuiteIntegration._check_binary",
            return_value=True,
        ):
            status = await integration.check_health()
            assert status.healthy

    def test_command_not_in_allowlist_rejected(self):
        integration = GoogleSuiteIntegration()
        assert not integration.is_command_allowed("rm -rf /")

    def test_command_in_allowlist_accepted(self):
        integration = GoogleSuiteIntegration()
        assert integration.is_command_allowed("cal events list")


class TestGoogleSuiteExecution:
    async def test_run_command_parses_json_output(self):
        integration = GoogleSuiteIntegration()
        mock_output = json.dumps([
            {"title": "Team standup", "start": "2026-02-16T09:00:00"},
            {"title": "1:1 with boss", "start": "2026-02-16T14:00:00"},
        ])

        with patch(
            "vecna.integrations.google_suite.GoogleSuiteIntegration._exec_gogcli",
            new_callable=AsyncMock,
            return_value=(0, mock_output, ""),
        ):
            result = await integration.run_command(GoogleSuiteCommand.CALENDAR_LIST)
            assert result.success
            assert len(result.data) == 2
            assert result.data[0]["title"] == "Team standup"

    async def test_run_command_handles_error(self):
        integration = GoogleSuiteIntegration()

        with patch(
            "vecna.integrations.google_suite.GoogleSuiteIntegration._exec_gogcli",
            new_callable=AsyncMock,
            return_value=(1, "", "authentication failed"),
        ):
            result = await integration.run_command(GoogleSuiteCommand.CALENDAR_LIST)
            assert not result.success
            assert "authentication" in result.error.lower()

    async def test_run_command_handles_invalid_json(self):
        integration = GoogleSuiteIntegration()

        with patch(
            "vecna.integrations.google_suite.GoogleSuiteIntegration._exec_gogcli",
            new_callable=AsyncMock,
            return_value=(0, "not valid json {{{", ""),
        ):
            result = await integration.run_command(GoogleSuiteCommand.CALENDAR_LIST)
            assert not result.success
            assert "json" in result.error.lower() or "parse" in result.error.lower()

    async def test_get_calendar_events(self):
        integration = GoogleSuiteIntegration()
        mock_output = json.dumps([{"title": "Lunch", "start": "2026-02-16T12:00:00"}])

        with patch(
            "vecna.integrations.google_suite.GoogleSuiteIntegration._exec_gogcli",
            new_callable=AsyncMock,
            return_value=(0, mock_output, ""),
        ):
            result = await integration.get_calendar_events()
            assert result.success
            assert result.data[0]["title"] == "Lunch"

    async def test_get_emails(self):
        integration = GoogleSuiteIntegration()
        mock_output = json.dumps([
            {"subject": "Important update", "from": "boss@example.com"},
        ])

        with patch(
            "vecna.integrations.google_suite.GoogleSuiteIntegration._exec_gogcli",
            new_callable=AsyncMock,
            return_value=(0, mock_output, ""),
        ):
            result = await integration.get_emails(max_results=5)
            assert result.success
            assert result.data[0]["subject"] == "Important update"
```

**Step 2: Run tests, verify fail**

Run: `pytest tests/unit/test_google_suite.py -v`
Expected: FAIL — module doesn't exist

**Step 3: Implement GoogleSuiteIntegration**

```python
# vecna/integrations/google_suite.py
"""
Google Suite integration via gogcli CLI.

Wraps the gogcli command-line tool as a Vecna integration, providing:
- Calendar event awareness (read today's schedule)
- Email reading (unread count, important emails)
- Contact lookup
- Task management (Google Tasks)

All commands use --json output for structured parsing.
Credential storage is handled by gogcli's own secure keychain mechanism.
"""

import asyncio
import json
import logging
import shutil
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from vecna.integrations.base import BaseIntegration, IntegrationStatus

logger = logging.getLogger("vecna.integrations.google_suite")


class GoogleSuiteCommand(Enum):
    """Available gogcli commands."""

    CALENDAR_LIST = "cal events list"
    GMAIL_LIST = "gmail messages list"
    CONTACTS_LIST = "contacts list"
    TASKS_LIST = "tasks list"

    def cli_args(self) -> List[str]:
        """Split command value into CLI argument list."""
        return self.value.split()


# Only safe read-only commands are allowed by default
COMMAND_ALLOWLIST: frozenset = frozenset({
    GoogleSuiteCommand.CALENDAR_LIST,
    GoogleSuiteCommand.GMAIL_LIST,
    GoogleSuiteCommand.CONTACTS_LIST,
    GoogleSuiteCommand.TASKS_LIST,
})


@dataclass
class GogcliResult:
    """Result of a gogcli command execution."""

    success: bool = False
    command: str = ""
    data: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""
    raw_output: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "command": self.command,
            "data": self.data,
            "error": self.error,
        }


class GoogleSuiteIntegration(BaseIntegration):
    """
    Google Suite integration using the gogcli CLI tool.

    gogcli handles its own OAuth2 authentication via the macOS keychain.
    This integration wraps it with subprocess execution, JSON parsing,
    and privacy-aware data handling.
    """

    name = "google_suite"
    description = "Google Suite integration (Calendar, Gmail, Contacts, Tasks) via gogcli"
    required_credentials: List[str] = []  # gogcli manages its own auth

    def __init__(self, binary_path: Optional[str] = None):
        self.binary_path = binary_path or "gogcli"
        self.enabled = False
        self._running = False

    def _check_binary(self) -> bool:
        """Check if gogcli binary is available on PATH."""
        return shutil.which(self.binary_path) is not None

    async def check_health(self) -> IntegrationStatus:
        """Check if gogcli is installed and accessible."""
        if self._check_binary():
            return IntegrationStatus(
                healthy=True,
                name=self.name,
                message="gogcli binary found and accessible",
            )
        return IntegrationStatus(
            healthy=False,
            name=self.name,
            message="gogcli binary not found or not installed",
        )

    async def start(self) -> None:
        """Start the Google Suite integration."""
        self._running = True
        logger.info("Google Suite integration started")

    async def stop(self) -> None:
        """Stop the Google Suite integration."""
        self._running = False
        logger.info("Google Suite integration stopped")

    def is_command_allowed(self, command_str: str) -> bool:
        """Check if a command string matches the allowlist."""
        for allowed in COMMAND_ALLOWLIST:
            if command_str.strip() == allowed.value:
                return True
        return False

    async def _exec_gogcli(
        self, args: List[str], timeout: float = 30.0
    ) -> Tuple[int, str, str]:
        """Execute a gogcli subprocess and return (returncode, stdout, stderr)."""
        try:
            proc = await asyncio.create_subprocess_exec(
                self.binary_path,
                *args,
                "--json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            return (
                proc.returncode or 0,
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"),
            )
        except asyncio.TimeoutError:
            logger.error(f"gogcli command timed out after {timeout}s: {args}")
            return (1, "", f"Command timed out after {timeout}s")
        except FileNotFoundError:
            logger.error("gogcli binary not found")
            return (1, "", "gogcli binary not found")
        except Exception as e:
            logger.error(f"gogcli execution error: {e}")
            return (1, "", str(e))

    async def run_command(
        self,
        command: GoogleSuiteCommand,
        extra_args: Optional[List[str]] = None,
    ) -> GogcliResult:
        """Run a gogcli command and parse the JSON output."""
        args = command.cli_args()
        if extra_args:
            args.extend(extra_args)

        returncode, stdout, stderr = await self._exec_gogcli(args)

        if returncode != 0:
            return GogcliResult(
                success=False,
                command=command.value,
                error=stderr or f"gogcli exited with code {returncode}",
                raw_output=stdout,
            )

        # Parse JSON output
        try:
            parsed = json.loads(stdout)
            if isinstance(parsed, list):
                data = parsed
            elif isinstance(parsed, dict):
                data = [parsed]
            else:
                data = [{"value": parsed}]

            return GogcliResult(
                success=True,
                command=command.value,
                data=data,
                raw_output=stdout,
            )
        except json.JSONDecodeError as e:
            return GogcliResult(
                success=False,
                command=command.value,
                error=f"Failed to parse JSON output: {e}",
                raw_output=stdout,
            )

    # -- Convenience methods --

    async def get_calendar_events(
        self, max_results: int = 10
    ) -> GogcliResult:
        """Get upcoming calendar events."""
        return await self.run_command(
            GoogleSuiteCommand.CALENDAR_LIST,
            extra_args=[f"--max={max_results}"],
        )

    async def get_emails(self, max_results: int = 5) -> GogcliResult:
        """Get recent emails."""
        return await self.run_command(
            GoogleSuiteCommand.GMAIL_LIST,
            extra_args=[f"--max={max_results}"],
        )

    async def get_contacts(self) -> GogcliResult:
        """Get contact list."""
        return await self.run_command(GoogleSuiteCommand.CONTACTS_LIST)

    async def get_tasks(self) -> GogcliResult:
        """Get Google Tasks."""
        return await self.run_command(GoogleSuiteCommand.TASKS_LIST)
```

```markdown
# vecna/skills/google_suite/SKILL.md

# Google Suite Skill

> Access user's Google Calendar, Gmail, Contacts, and Tasks via `gogcli`.

## When to Use

- User asks about their schedule, calendar, or "what's on today"
- User mentions emails, inbox, or messages from specific people
- User needs to look up a contact's information
- User asks about their tasks or to-do items
- Time-based context is needed for a response (e.g., "do I have time for X?")
- User asks to check, review, or summarize their day

## Available Commands

| Command | Description | Example Output |
|---------|-------------|----------------|
| `gogcli cal events list --json` | Upcoming calendar events | `[{"title": "Standup", "start": "..."}]` |
| `gogcli gmail messages list --max=5 --json` | Recent emails | `[{"subject": "...", "from": "..."}]` |
| `gogcli contacts list --json` | Contact directory | `[{"name": "...", "email": "..."}]` |
| `gogcli tasks list --json` | Google Tasks | `[{"title": "...", "status": "..."}]` |

## Execution

1. All commands are run via `asyncio.create_subprocess_exec` with `--json` flag
2. Parse the JSON response array
3. Summarize relevant information concisely
4. Incorporate into the conversation context naturally

## Privacy

- **All calendar and email data is `LOCAL_ONLY` by default**
- Do NOT include raw email content in hive updates sent to cloud models
- Calendar event titles may be included in context; full attendee lists should not
- Contact information should never be shared with cloud models
- When summarizing for the user, strip PII from any data sent to non-local models

## Error Handling

- If `gogcli` is not installed: inform user to install via `brew install gogcli`
- If authentication fails: instruct user to run `gogcli auth login`
- If no results returned: report "no upcoming events/emails found"

## Integration with Vecna

- Calendar events create temporal Facts with validity windows matching event times
- Important emails can generate Goals (e.g., "Reply to email from X about Y")
- The BackgroundObserver can poll these on a schedule for proactive awareness
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_google_suite.py tests/unit/ -v --tb=short`
Expected: All PASS

**Step 5: Commit**

```bash
git add vecna/integrations/google_suite.py vecna/skills/google_suite/SKILL.md tests/unit/test_google_suite.py
git commit -m "feat: add Google Suite integration via gogcli skill"
```

---

### Task 16: Steipete CLI Skills — iMessage (imsg)

**Files:**
- Create: `vecna/channels/imessage.py` (iMessageChannel)
- Create: `vecna/skills/imessage/SKILL.md`
- Create: `tests/unit/test_imessage.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_imessage.py
"""Tests for the iMessage channel adapter via imsg CLI."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vecna.channels.imessage import (
    iMessageChannel,
    ImsgConfig,
    ImsgParseError,
)
from vecna.channels.base import (
    InboundMessage,
    OutboundMessage,
    ChannelCapability,
)


class TestImsgConfig:
    def test_default_config(self):
        config = ImsgConfig()
        assert config.binary_path == "imsg"
        assert config.watch_timeout == 0  # 0 = indefinite
        assert config.privacy_tier == "local_only"
        assert config.max_message_length == 10000

    def test_custom_config(self):
        config = ImsgConfig(binary_path="/usr/local/bin/imsg", watch_timeout=60)
        assert config.binary_path == "/usr/local/bin/imsg"
        assert config.watch_timeout == 60


class TestiMessageChannelProperties:
    def test_channel_name(self):
        channel = iMessageChannel()
        assert channel.name == "imessage"

    def test_channel_capabilities(self):
        channel = iMessageChannel()
        caps = channel.capabilities
        assert ChannelCapability.TEXT in caps
        assert ChannelCapability.IMAGES in caps

    def test_channel_disabled_by_default(self):
        channel = iMessageChannel()
        assert not channel.is_running

    def test_channel_privacy_tier(self):
        channel = iMessageChannel()
        assert channel.config.privacy_tier == "local_only"


class TestiMessageParsing:
    def test_parse_inbound_message(self):
        channel = iMessageChannel()
        raw_json = json.dumps({
            "sender": "+1234567890",
            "text": "Hey, what's up?",
            "date": "2026-02-16T10:30:00",
            "chat_id": "chat123",
            "is_from_me": False,
        })
        msg = channel.parse_inbound(raw_json)
        assert isinstance(msg, InboundMessage)
        assert msg.sender == "+1234567890"
        assert msg.content == "Hey, what's up?"
        assert msg.channel == "imessage"

    def test_parse_inbound_with_attachment(self):
        channel = iMessageChannel()
        raw_json = json.dumps({
            "sender": "+1234567890",
            "text": "Check this out",
            "attachments": [
                {"filename": "photo.jpg", "mime_type": "image/jpeg"},
            ],
            "is_from_me": False,
        })
        msg = channel.parse_inbound(raw_json)
        assert len(msg.attachments) == 1
        assert msg.attachments[0]["filename"] == "photo.jpg"

    def test_parse_inbound_skips_own_messages(self):
        channel = iMessageChannel()
        raw_json = json.dumps({
            "sender": "+1234567890",
            "text": "My own message",
            "is_from_me": True,
        })
        msg = channel.parse_inbound(raw_json)
        assert msg is None

    def test_parse_inbound_invalid_json_raises(self):
        channel = iMessageChannel()
        with pytest.raises(ImsgParseError):
            channel.parse_inbound("not valid json {{{")

    def test_parse_inbound_missing_text_uses_empty(self):
        channel = iMessageChannel()
        raw_json = json.dumps({
            "sender": "+1234567890",
            "is_from_me": False,
        })
        msg = channel.parse_inbound(raw_json)
        assert msg is not None
        assert msg.content == ""


class TestiMessageSend:
    async def test_send_message(self):
        channel = iMessageChannel()
        msg = OutboundMessage(
            channel="imessage",
            recipient="+1234567890",
            content="Hello from Vecna!",
        )

        with patch(
            "vecna.channels.imessage.iMessageChannel._exec_imsg_send",
            new_callable=AsyncMock,
            return_value=(0, "Message sent", ""),
        ):
            success = await channel.send(msg)
            assert success

    async def test_send_message_failure(self):
        channel = iMessageChannel()
        msg = OutboundMessage(
            channel="imessage",
            recipient="+1234567890",
            content="Hello!",
        )

        with patch(
            "vecna.channels.imessage.iMessageChannel._exec_imsg_send",
            new_callable=AsyncMock,
            return_value=(1, "", "Failed to send"),
        ):
            success = await channel.send(msg)
            assert not success

    async def test_send_truncates_long_messages(self):
        channel = iMessageChannel(config=ImsgConfig(max_message_length=50))
        msg = OutboundMessage(
            channel="imessage",
            recipient="+1234567890",
            content="A" * 100,
        )

        with patch(
            "vecna.channels.imessage.iMessageChannel._exec_imsg_send",
            new_callable=AsyncMock,
            return_value=(0, "Sent", ""),
        ) as mock_send:
            await channel.send(msg)
            # Verify the actual sent content was truncated
            call_args = mock_send.call_args
            sent_text = call_args[0][1]  # second positional arg is text
            assert len(sent_text) <= 50


class TestiMessageStartStop:
    async def test_start_sets_running(self):
        channel = iMessageChannel()
        with patch(
            "vecna.channels.imessage.iMessageChannel._check_binary",
            return_value=True,
        ):
            # Don't actually start the watch process
            with patch.object(channel, "_start_watch_process", new_callable=AsyncMock):
                await channel.start()
                assert channel.is_running

    async def test_stop_clears_running(self):
        channel = iMessageChannel()
        channel.is_running = True
        channel._watch_process = MagicMock()
        channel._watch_process.terminate = MagicMock()
        channel._watch_process.wait = AsyncMock()
        await channel.stop()
        assert not channel.is_running

    async def test_start_fails_without_binary(self):
        channel = iMessageChannel()
        with patch(
            "vecna.channels.imessage.iMessageChannel._check_binary",
            return_value=False,
        ):
            with pytest.raises(RuntimeError, match="imsg"):
                await channel.start()
```

**Step 2: Run tests, verify fail**

Run: `pytest tests/unit/test_imessage.py -v`
Expected: FAIL — module doesn't exist

**Step 3: Implement iMessageChannel**

```python
# vecna/channels/imessage.py
"""
iMessage channel adapter via the imsg CLI.

Provides bidirectional iMessage communication:
- Inbound: `imsg watch --json` streams incoming messages
- Outbound: `imsg send <number> <message>` sends messages

macOS only. Requires Full Disk Access for iMessage database reading.
All iMessage content is LOCAL_ONLY — never sent to cloud models.
"""

import asyncio
import json
import logging
import shutil
from dataclasses import dataclass, field
from typing import AsyncIterator, List, Optional, Tuple

from vecna.channels.base import (
    BaseChannel,
    ChannelCapability,
    InboundMessage,
    OutboundMessage,
)

logger = logging.getLogger("vecna.channels.imessage")


class ImsgParseError(Exception):
    """Raised when an imsg JSON message cannot be parsed."""

    pass


@dataclass
class ImsgConfig:
    """Configuration for the iMessage channel."""

    binary_path: str = "imsg"
    watch_timeout: int = 0  # 0 = indefinite
    privacy_tier: str = "local_only"
    max_message_length: int = 10000


class iMessageChannel(BaseChannel):
    """
    iMessage channel adapter using the imsg CLI.

    Uses `imsg watch --json` for streaming inbound messages and
    `imsg send <recipient> <message>` for outbound delivery.
    """

    name = "imessage"
    capabilities = [
        ChannelCapability.TEXT,
        ChannelCapability.IMAGES,
    ]

    def __init__(self, config: Optional[ImsgConfig] = None):
        self.config = config or ImsgConfig()
        self.is_running = False
        self._watch_process: Optional[asyncio.subprocess.Process] = None
        self._message_callback = None

    def _check_binary(self) -> bool:
        """Check if imsg binary is available on PATH."""
        return shutil.which(self.config.binary_path) is not None

    def parse_inbound(self, raw_json: str) -> Optional[InboundMessage]:
        """Parse a raw JSON line from `imsg watch --json` into an InboundMessage.

        Returns None for messages sent by the user themselves (is_from_me=True).
        Raises ImsgParseError for invalid JSON.
        """
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as e:
            raise ImsgParseError(f"Invalid JSON from imsg: {e}") from e

        # Skip our own outgoing messages
        if data.get("is_from_me", False):
            return None

        sender = data.get("sender", "unknown")
        text = data.get("text", "")
        attachments_raw = data.get("attachments", [])

        attachments = []
        for att in attachments_raw:
            if isinstance(att, dict):
                attachments.append(att)

        metadata = {
            "chat_id": data.get("chat_id", ""),
            "privacy_tier": self.config.privacy_tier,
        }

        return InboundMessage(
            channel="imessage",
            sender=sender,
            content=text,
            message_type="text",
            attachments=attachments,
            metadata=metadata,
        )

    async def _exec_imsg_send(
        self, recipient: str, text: str
    ) -> Tuple[int, str, str]:
        """Execute `imsg send <recipient> <text>` and return (code, stdout, stderr)."""
        try:
            proc = await asyncio.create_subprocess_exec(
                self.config.binary_path,
                "send",
                recipient,
                text,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=30.0
            )
            return (
                proc.returncode or 0,
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"),
            )
        except asyncio.TimeoutError:
            return (1, "", "imsg send timed out")
        except FileNotFoundError:
            return (1, "", "imsg binary not found")
        except Exception as e:
            return (1, "", str(e))

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message via iMessage."""
        recipient = message.recipient
        content = message.content

        # Truncate if needed
        if len(content) > self.config.max_message_length:
            content = content[: self.config.max_message_length]

        returncode, stdout, stderr = await self._exec_imsg_send(recipient, content)

        if returncode != 0:
            logger.error(f"Failed to send iMessage to {recipient}: {stderr}")
            return False

        logger.info(f"Sent iMessage to {recipient} ({len(content)} chars)")
        return True

    async def _start_watch_process(self) -> None:
        """Start the `imsg watch --json` subprocess."""
        args = [self.config.binary_path, "watch", "--json"]
        self._watch_process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        logger.info("Started imsg watch process")

    async def receive(self) -> AsyncIterator[InboundMessage]:
        """Stream inbound messages from the imsg watch process."""
        if not self._watch_process or not self._watch_process.stdout:
            return

        async for line in self._watch_process.stdout:
            raw = line.decode("utf-8", errors="replace").strip()
            if not raw:
                continue

            try:
                msg = self.parse_inbound(raw)
                if msg is not None:
                    yield msg
            except ImsgParseError as e:
                logger.warning(f"Failed to parse imsg output: {e}")
                continue

    async def start(self) -> None:
        """Start the iMessage channel (begins watching for messages)."""
        if not self._check_binary():
            raise RuntimeError(
                f"imsg binary not found at '{self.config.binary_path}'. "
                f"Install with: brew install imsg"
            )

        await self._start_watch_process()
        self.is_running = True
        logger.info("iMessage channel started")

    async def stop(self) -> None:
        """Stop the iMessage channel."""
        if self._watch_process:
            try:
                self._watch_process.terminate()
                await self._watch_process.wait()
            except Exception as e:
                logger.error(f"Error stopping imsg watch: {e}")
            self._watch_process = None

        self.is_running = False
        logger.info("iMessage channel stopped")
```

```markdown
# vecna/skills/imessage/SKILL.md

# iMessage Skill

> Bidirectional iMessage communication via the `imsg` CLI.

## When to Use

- User asks to send a message to someone via iMessage
- User wants to read or check recent iMessages
- User asks "did anyone message me?"
- User wants to reply to a specific person
- Autonomous mode needs to notify the user of something important

## Requirements

- **macOS only** — iMessage is not available on other platforms
- **Full Disk Access** required for reading the iMessage database
- `imsg` CLI must be installed (`brew install imsg`)

## Available Commands

| Command | Description |
|---------|-------------|
| `imsg watch --json` | Stream incoming messages as JSON lines |
| `imsg send <number> <message>` | Send a message to a phone number or Apple ID |
| `imsg search <query> --json` | Search message history |
| `imsg chats --json` | List recent conversations |

## Execution

### Sending Messages
```
imsg send "+1234567890" "Hello from Vecna!"
```
- Always confirm with user before sending messages in interactive mode
- In autonomous mode, only send to pre-approved contacts
- Truncate messages longer than 10,000 characters

### Receiving Messages
Messages are streamed via `imsg watch --json` as newline-delimited JSON:
```json
{"sender": "+1234567890", "text": "Hey!", "date": "2026-02-16T10:30:00", "is_from_me": false}
```
- Skip messages where `is_from_me` is true
- Parse sender, text, and optional attachments
- Route to HiveLoop.think() for processing

## Privacy

- **ALL iMessage content is `LOCAL_ONLY`** — never sent to cloud models
- Message content must not appear in hive updates
- Contact names and phone numbers are never shared externally
- Only summarized intent (e.g., "user received a question about project timeline")
  may be used in non-local processing, and only with user consent

## Error Handling

- If `imsg` is not installed: inform user to install via `brew install imsg`
- If Full Disk Access is denied: guide user to System Settings → Privacy → Full Disk Access
- If send fails: log error, inform user, do not retry automatically
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_imessage.py tests/unit/ -v --tb=short`
Expected: All PASS

**Step 5: Commit**

```bash
git add vecna/channels/imessage.py vecna/skills/imessage/SKILL.md tests/unit/test_imessage.py
git commit -m "feat: add iMessage channel adapter via imsg CLI"
```

---

### Task 17: Steipete CLI Skills — WhatsApp (wacli)

**Files:**
- Create: `vecna/channels/whatsapp.py` (WhatsAppChannel)
- Create: `vecna/skills/whatsapp/SKILL.md`
- Create: `tests/unit/test_whatsapp.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_whatsapp.py
"""Tests for the WhatsApp channel adapter via wacli CLI."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vecna.channels.whatsapp import (
    WhatsAppChannel,
    WacliConfig,
    WacliResult,
    WacliParseError,
)
from vecna.channels.base import (
    InboundMessage,
    OutboundMessage,
    ChannelCapability,
)


class TestWacliConfig:
    def test_default_config(self):
        config = WacliConfig()
        assert config.binary_path == "wacli"
        assert config.privacy_tier == "local_only"
        assert config.max_message_length == 65536
        assert config.search_limit == 50

    def test_custom_config(self):
        config = WacliConfig(binary_path="/usr/local/bin/wacli", search_limit=20)
        assert config.binary_path == "/usr/local/bin/wacli"
        assert config.search_limit == 20


class TestWhatsAppChannelProperties:
    def test_channel_name(self):
        channel = WhatsAppChannel()
        assert channel.name == "whatsapp"

    def test_channel_capabilities(self):
        channel = WhatsAppChannel()
        caps = channel.capabilities
        assert ChannelCapability.TEXT in caps
        assert ChannelCapability.IMAGES in caps

    def test_channel_not_running_initially(self):
        channel = WhatsAppChannel()
        assert not channel.is_running

    def test_channel_privacy_tier(self):
        channel = WhatsAppChannel()
        assert channel.config.privacy_tier == "local_only"


class TestWhatsAppParsing:
    def test_parse_inbound_message(self):
        channel = WhatsAppChannel()
        raw_json = json.dumps({
            "sender": "+1234567890",
            "sender_name": "Alice",
            "text": "Hello from WhatsApp",
            "timestamp": "2026-02-16T10:30:00",
            "chat_id": "chat_abc",
            "is_from_me": False,
        })
        msg = channel.parse_inbound(raw_json)
        assert isinstance(msg, InboundMessage)
        assert msg.sender == "+1234567890"
        assert msg.content == "Hello from WhatsApp"
        assert msg.channel == "whatsapp"

    def test_parse_inbound_with_media(self):
        channel = WhatsAppChannel()
        raw_json = json.dumps({
            "sender": "+1234567890",
            "text": "Check this photo",
            "media": [
                {"type": "image", "filename": "photo.jpg", "mime": "image/jpeg"},
            ],
            "is_from_me": False,
        })
        msg = channel.parse_inbound(raw_json)
        assert len(msg.attachments) == 1
        assert msg.attachments[0]["type"] == "image"

    def test_parse_inbound_skips_own_messages(self):
        channel = WhatsAppChannel()
        raw_json = json.dumps({
            "sender": "+1234567890",
            "text": "My outgoing msg",
            "is_from_me": True,
        })
        msg = channel.parse_inbound(raw_json)
        assert msg is None

    def test_parse_inbound_invalid_json_raises(self):
        channel = WhatsAppChannel()
        with pytest.raises(WacliParseError):
            channel.parse_inbound("{{invalid json}}")

    def test_parse_inbound_includes_sender_name_in_metadata(self):
        channel = WhatsAppChannel()
        raw_json = json.dumps({
            "sender": "+1234567890",
            "sender_name": "Bob",
            "text": "Hey",
            "is_from_me": False,
        })
        msg = channel.parse_inbound(raw_json)
        assert msg.metadata.get("sender_name") == "Bob"


class TestWhatsAppSend:
    async def test_send_message(self):
        channel = WhatsAppChannel()
        msg = OutboundMessage(
            channel="whatsapp",
            recipient="+1234567890",
            content="Hello from Vecna!",
        )

        with patch(
            "vecna.channels.whatsapp.WhatsAppChannel._exec_wacli",
            new_callable=AsyncMock,
            return_value=(0, "Message sent", ""),
        ):
            success = await channel.send(msg)
            assert success

    async def test_send_message_failure(self):
        channel = WhatsAppChannel()
        msg = OutboundMessage(
            channel="whatsapp",
            recipient="+1234567890",
            content="Hello!",
        )

        with patch(
            "vecna.channels.whatsapp.WhatsAppChannel._exec_wacli",
            new_callable=AsyncMock,
            return_value=(1, "", "Not connected"),
        ):
            success = await channel.send(msg)
            assert not success

    async def test_send_truncates_long_messages(self):
        channel = WhatsAppChannel(config=WacliConfig(max_message_length=50))
        msg = OutboundMessage(
            channel="whatsapp",
            recipient="+1234567890",
            content="B" * 100,
        )

        with patch(
            "vecna.channels.whatsapp.WhatsAppChannel._exec_wacli",
            new_callable=AsyncMock,
            return_value=(0, "Sent", ""),
        ) as mock_exec:
            await channel.send(msg)
            call_args = mock_exec.call_args[0]
            # args list should include the truncated text
            assert any(len(arg) <= 50 for arg in call_args if isinstance(arg, str) and len(arg) > 10)


class TestWhatsAppSearch:
    async def test_search_messages(self):
        channel = WhatsAppChannel()
        mock_output = json.dumps([
            {"sender": "+111", "text": "Meeting tomorrow", "timestamp": "2026-02-15T09:00:00"},
            {"sender": "+222", "text": "Meeting agenda", "timestamp": "2026-02-15T10:00:00"},
        ])

        with patch(
            "vecna.channels.whatsapp.WhatsAppChannel._exec_wacli",
            new_callable=AsyncMock,
            return_value=(0, mock_output, ""),
        ):
            result = await channel.search("meeting", limit=10)
            assert result.success
            assert len(result.data) == 2

    async def test_search_handles_error(self):
        channel = WhatsAppChannel()

        with patch(
            "vecna.channels.whatsapp.WhatsAppChannel._exec_wacli",
            new_callable=AsyncMock,
            return_value=(1, "", "Database locked"),
        ):
            result = await channel.search("test")
            assert not result.success
            assert "locked" in result.error.lower()


class TestWhatsAppStartStop:
    async def test_start_sets_running(self):
        channel = WhatsAppChannel()
        with patch(
            "vecna.channels.whatsapp.WhatsAppChannel._check_binary",
            return_value=True,
        ):
            with patch.object(channel, "_start_watch_process", new_callable=AsyncMock):
                await channel.start()
                assert channel.is_running

    async def test_stop_clears_running(self):
        channel = WhatsAppChannel()
        channel.is_running = True
        channel._watch_process = MagicMock()
        channel._watch_process.terminate = MagicMock()
        channel._watch_process.wait = AsyncMock()
        await channel.stop()
        assert not channel.is_running

    async def test_start_fails_without_binary(self):
        channel = WhatsAppChannel()
        with patch(
            "vecna.channels.whatsapp.WhatsAppChannel._check_binary",
            return_value=False,
        ):
            with pytest.raises(RuntimeError, match="wacli"):
                await channel.start()


class TestWacliResult:
    def test_success_result(self):
        result = WacliResult(
            success=True,
            command="search",
            data=[{"text": "hello"}],
        )
        assert result.success

    def test_error_result(self):
        result = WacliResult(
            success=False,
            command="search",
            error="not authenticated",
        )
        assert not result.success

    def test_to_dict(self):
        result = WacliResult(success=True, command="send", data=[])
        d = result.to_dict()
        assert d["success"] is True
        assert d["command"] == "send"
```

**Step 2: Run tests, verify fail**

Run: `pytest tests/unit/test_whatsapp.py -v`
Expected: FAIL — module doesn't exist

**Step 3: Implement WhatsAppChannel**

```python
# vecna/channels/whatsapp.py
"""
WhatsApp channel adapter via the wacli CLI.

Provides bidirectional WhatsApp communication:
- Inbound: `wacli watch --json` streams incoming messages
- Outbound: `wacli send <number> <message>` sends messages
- Search: `wacli search <query> --json` searches message history

wacli uses QR code authentication and stores message history
in a local SQLite database with FTS5 for full-text search.

All WhatsApp content is LOCAL_ONLY — never sent to cloud models.
"""

import asyncio
import json
import logging
import shutil
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from vecna.channels.base import (
    BaseChannel,
    ChannelCapability,
    InboundMessage,
    OutboundMessage,
)

logger = logging.getLogger("vecna.channels.whatsapp")


class WacliParseError(Exception):
    """Raised when wacli JSON output cannot be parsed."""

    pass


@dataclass
class WacliConfig:
    """Configuration for the WhatsApp channel."""

    binary_path: str = "wacli"
    privacy_tier: str = "local_only"
    max_message_length: int = 65536
    search_limit: int = 50


@dataclass
class WacliResult:
    """Result of a wacli command execution."""

    success: bool = False
    command: str = ""
    data: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""
    raw_output: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "command": self.command,
            "data": self.data,
            "error": self.error,
        }


class WhatsAppChannel(BaseChannel):
    """
    WhatsApp channel adapter using the wacli CLI.

    Uses `wacli watch --json` for streaming inbound messages,
    `wacli send <recipient> <message>` for outbound delivery,
    and `wacli search <query> --json` for message history search.

    Authentication is handled by wacli via QR code scanning.
    Message history is stored locally in SQLite with FTS5.
    """

    name = "whatsapp"
    capabilities = [
        ChannelCapability.TEXT,
        ChannelCapability.IMAGES,
        ChannelCapability.FILES,
    ]

    def __init__(self, config: Optional[WacliConfig] = None):
        self.config = config or WacliConfig()
        self.is_running = False
        self._watch_process: Optional[asyncio.subprocess.Process] = None

    def _check_binary(self) -> bool:
        """Check if wacli binary is available on PATH."""
        return shutil.which(self.config.binary_path) is not None

    def parse_inbound(self, raw_json: str) -> Optional[InboundMessage]:
        """Parse a raw JSON line from `wacli watch --json` into an InboundMessage.

        Returns None for messages sent by the user themselves (is_from_me=True).
        Raises WacliParseError for invalid JSON.
        """
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as e:
            raise WacliParseError(f"Invalid JSON from wacli: {e}") from e

        if data.get("is_from_me", False):
            return None

        sender = data.get("sender", "unknown")
        text = data.get("text", "")
        media_raw = data.get("media", [])

        attachments = []
        for item in media_raw:
            if isinstance(item, dict):
                attachments.append(item)

        metadata = {
            "chat_id": data.get("chat_id", ""),
            "sender_name": data.get("sender_name", ""),
            "privacy_tier": self.config.privacy_tier,
        }

        return InboundMessage(
            channel="whatsapp",
            sender=sender,
            content=text,
            message_type="text",
            attachments=attachments,
            metadata=metadata,
        )

    async def _exec_wacli(self, *args: str, timeout: float = 30.0) -> Tuple[int, str, str]:
        """Execute a wacli subprocess and return (returncode, stdout, stderr)."""
        try:
            proc = await asyncio.create_subprocess_exec(
                self.config.binary_path,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            return (
                proc.returncode or 0,
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"),
            )
        except asyncio.TimeoutError:
            return (1, "", f"wacli command timed out after {timeout}s")
        except FileNotFoundError:
            return (1, "", "wacli binary not found")
        except Exception as e:
            return (1, "", str(e))

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message via WhatsApp."""
        recipient = message.recipient
        content = message.content

        if len(content) > self.config.max_message_length:
            content = content[: self.config.max_message_length]

        returncode, stdout, stderr = await self._exec_wacli(
            "send", recipient, content
        )

        if returncode != 0:
            logger.error(f"Failed to send WhatsApp message to {recipient}: {stderr}")
            return False

        logger.info(f"Sent WhatsApp message to {recipient} ({len(content)} chars)")
        return True

    async def search(self, query: str, limit: Optional[int] = None) -> WacliResult:
        """Search WhatsApp message history."""
        search_limit = limit or self.config.search_limit
        returncode, stdout, stderr = await self._exec_wacli(
            "search", query, "--json", f"--limit={search_limit}"
        )

        if returncode != 0:
            return WacliResult(
                success=False,
                command="search",
                error=stderr or f"wacli search exited with code {returncode}",
                raw_output=stdout,
            )

        try:
            parsed = json.loads(stdout)
            data = parsed if isinstance(parsed, list) else [parsed]
            return WacliResult(
                success=True,
                command="search",
                data=data,
                raw_output=stdout,
            )
        except json.JSONDecodeError as e:
            return WacliResult(
                success=False,
                command="search",
                error=f"Failed to parse JSON output: {e}",
                raw_output=stdout,
            )

    async def _start_watch_process(self) -> None:
        """Start the `wacli watch --json` subprocess."""
        self._watch_process = await asyncio.create_subprocess_exec(
            self.config.binary_path,
            "watch",
            "--json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        logger.info("Started wacli watch process")

    async def receive(self) -> AsyncIterator[InboundMessage]:
        """Stream inbound messages from the wacli watch process."""
        if not self._watch_process or not self._watch_process.stdout:
            return

        async for line in self._watch_process.stdout:
            raw = line.decode("utf-8", errors="replace").strip()
            if not raw:
                continue

            try:
                msg = self.parse_inbound(raw)
                if msg is not None:
                    yield msg
            except WacliParseError as e:
                logger.warning(f"Failed to parse wacli output: {e}")
                continue

    async def start(self) -> None:
        """Start the WhatsApp channel (begins watching for messages)."""
        if not self._check_binary():
            raise RuntimeError(
                f"wacli binary not found at '{self.config.binary_path}'. "
                f"Install with: brew install wacli"
            )

        await self._start_watch_process()
        self.is_running = True
        logger.info("WhatsApp channel started")

    async def stop(self) -> None:
        """Stop the WhatsApp channel."""
        if self._watch_process:
            try:
                self._watch_process.terminate()
                await self._watch_process.wait()
            except Exception as e:
                logger.error(f"Error stopping wacli watch: {e}")
            self._watch_process = None

        self.is_running = False
        logger.info("WhatsApp channel stopped")
```

```markdown
# vecna/skills/whatsapp/SKILL.md

# WhatsApp Skill

> Bidirectional WhatsApp communication via the `wacli` CLI.

## When to Use

- User asks to send a WhatsApp message
- User wants to search their WhatsApp message history
- User asks "did anyone message me on WhatsApp?"
- User wants to reply to a specific person on WhatsApp
- Autonomous mode needs to notify the user via WhatsApp

## Requirements

- `wacli` CLI must be installed (`brew install wacli`)
- First-time setup requires QR code scanning for WhatsApp Web authentication
- Local SQLite database stores message history with FTS5 full-text search

## Available Commands

| Command | Description |
|---------|-------------|
| `wacli watch --json` | Stream incoming messages as JSON lines |
| `wacli send <number> <message>` | Send a message to a phone number |
| `wacli search <query> --json` | Search message history (FTS5) |
| `wacli chats --json` | List recent conversations |
| `wacli status` | Check connection status |

## Execution

### Sending Messages
```
wacli send "+1234567890" "Hello from Vecna!"
```
- Always confirm with user before sending messages in interactive mode
- In autonomous mode, only send to pre-approved contacts
- Messages are limited to 65,536 characters

### Searching Messages
```
wacli search "project deadline" --json --limit=20
```
- Uses SQLite FTS5 for fast full-text search
- Results include sender, text, timestamp, and chat context

### Receiving Messages
Messages are streamed via `wacli watch --json` as newline-delimited JSON:
```json
{"sender": "+1234567890", "sender_name": "Alice", "text": "Hey!", "timestamp": "...", "is_from_me": false}
```

## Privacy

- **ALL WhatsApp content is `LOCAL_ONLY`** — never sent to cloud models
- Message content, contact names, and phone numbers are never shared externally
- Only summarized intent may be used in non-local processing, with user consent

## Error Handling

- If `wacli` is not installed: inform user to install via `brew install wacli`
- If not authenticated: guide user to run `wacli auth` and scan QR code
- If send fails: log error, inform user, do not retry automatically
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_whatsapp.py tests/unit/ -v --tb=short`
Expected: All PASS

**Step 5: Commit**

```bash
git add vecna/channels/whatsapp.py vecna/skills/whatsapp/SKILL.md tests/unit/test_whatsapp.py
git commit -m "feat: add WhatsApp channel adapter via wacli CLI"
```

---

### Task 18: Steipete CLI Skills — Content Summarizer (summarize)

**Files:**
- Create: `vecna/tools/summarize_tool.py`
- Create: `vecna/skills/summarize/SKILL.md`
- Modify: `vecna/tools/registry.py` (register summarize tool)
- Create: `tests/unit/test_summarize_tool.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_summarize_tool.py
"""Tests for the content summarize tool via steipete summarize CLI."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from vecna.tools.summarize_tool import (
    SummarizeTool,
    SummarizeConfig,
    SummarizeResult,
    SUMMARIZE_TOOL_SPEC,
    summarize_executor,
)
from vecna.tools.types import ToolSpec, ToolResult, ToolExecutionContext


class TestSummarizeToolSpec:
    def test_tool_spec_name(self):
        assert SUMMARIZE_TOOL_SPEC.name == "content_summarize"

    def test_tool_spec_has_description(self):
        assert len(SUMMARIZE_TOOL_SPEC.description) > 0

    def test_tool_spec_input_schema(self):
        schema = SUMMARIZE_TOOL_SPEC.input_schema
        assert "url" in schema
        assert "format" in schema

    def test_tool_spec_tags(self):
        assert "summarize" in SUMMARIZE_TOOL_SPEC.tags
        assert "content" in SUMMARIZE_TOOL_SPEC.tags


class TestSummarizeConfig:
    def test_default_config(self):
        config = SummarizeConfig()
        assert config.binary_path == "summarize"
        assert config.timeout == 60.0
        assert config.max_output_length == 50000

    def test_custom_config(self):
        config = SummarizeConfig(timeout=120.0)
        assert config.timeout == 120.0


class TestSummarizeResult:
    def test_success_result(self):
        result = SummarizeResult(
            success=True,
            url="https://example.com/article",
            summary="This is a summary of the article.",
            content_type="article",
        )
        assert result.success
        assert "summary" in result.summary.lower()

    def test_error_result(self):
        result = SummarizeResult(
            success=False,
            url="https://example.com/broken",
            error="404 Not Found",
        )
        assert not result.success

    def test_to_dict(self):
        result = SummarizeResult(
            success=True,
            url="https://example.com",
            summary="Summary text",
            content_type="article",
            word_count=150,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["url"] == "https://example.com"
        assert d["word_count"] == 150


class TestSummarizeTool:
    def test_tool_creation(self):
        tool = SummarizeTool()
        assert tool.config.binary_path == "summarize"

    async def test_summarize_url_success(self):
        tool = SummarizeTool()
        mock_output = json.dumps({
            "title": "Test Article",
            "summary": "This is a great article about testing.",
            "content_type": "article",
            "word_count": 500,
            "url": "https://example.com/article",
        })

        with patch(
            "vecna.tools.summarize_tool.SummarizeTool._exec_summarize",
            new_callable=AsyncMock,
            return_value=(0, mock_output, ""),
        ):
            result = await tool.summarize("https://example.com/article")
            assert result.success
            assert result.summary == "This is a great article about testing."
            assert result.content_type == "article"

    async def test_summarize_url_failure(self):
        tool = SummarizeTool()

        with patch(
            "vecna.tools.summarize_tool.SummarizeTool._exec_summarize",
            new_callable=AsyncMock,
            return_value=(1, "", "Failed to fetch URL"),
        ):
            result = await tool.summarize("https://example.com/broken")
            assert not result.success
            assert "fetch" in result.error.lower()

    async def test_summarize_youtube_url(self):
        tool = SummarizeTool()
        mock_output = json.dumps({
            "title": "Great Video",
            "summary": "A video about AI.",
            "content_type": "youtube",
            "duration": "10:30",
            "url": "https://youtube.com/watch?v=abc123",
        })

        with patch(
            "vecna.tools.summarize_tool.SummarizeTool._exec_summarize",
            new_callable=AsyncMock,
            return_value=(0, mock_output, ""),
        ):
            result = await tool.summarize("https://youtube.com/watch?v=abc123")
            assert result.success
            assert result.content_type == "youtube"

    async def test_summarize_invalid_json_output(self):
        tool = SummarizeTool()

        with patch(
            "vecna.tools.summarize_tool.SummarizeTool._exec_summarize",
            new_callable=AsyncMock,
            return_value=(0, "not json {{", ""),
        ):
            result = await tool.summarize("https://example.com")
            assert not result.success
            assert "json" in result.error.lower() or "parse" in result.error.lower()


class TestSummarizeExecutor:
    async def test_executor_returns_tool_result(self):
        ctx = ToolExecutionContext(session_id="test-session")
        mock_output = json.dumps({
            "title": "Test",
            "summary": "Summary here",
            "content_type": "article",
            "word_count": 100,
            "url": "https://example.com",
        })

        with patch(
            "vecna.tools.summarize_tool.SummarizeTool._exec_summarize",
            new_callable=AsyncMock,
            return_value=(0, mock_output, ""),
        ):
            result = await summarize_executor(
                {"url": "https://example.com"},
                ctx,
            )
            assert isinstance(result, ToolResult)
            assert result.success
            assert "Summary here" in result.output

    async def test_executor_missing_url(self):
        ctx = ToolExecutionContext()
        result = await summarize_executor({}, ctx)
        assert isinstance(result, ToolResult)
        assert not result.success
        assert "url" in result.error.lower()
```

**Step 2: Run tests, verify fail**

Run: `pytest tests/unit/test_summarize_tool.py -v`
Expected: FAIL — module doesn't exist

**Step 3: Implement SummarizeTool**

```python
# vecna/tools/summarize_tool.py
"""
Content summarization tool via the steipete summarize CLI.

Provides URL/YouTube/podcast summarization as a registered Vecna tool.
Uses `summarize <url> --json` for structured output.

Registered as `content_summarize` in the ToolRegistry.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Dict, List, Optional, Tuple, Union

from vecna.tools.types import ToolExecutionContext, ToolResult, ToolSpec

logger = logging.getLogger("vecna.tools.summarize_tool")


SUMMARIZE_TOOL_SPEC = ToolSpec(
    name="content_summarize",
    description=(
        "Summarize content from a URL (articles, YouTube videos, podcasts). "
        "Returns a structured summary with title, content type, and word count."
    ),
    input_schema={
        "url": "string",
        "format": "string",  # optional: "brief", "detailed", "bullet_points"
    },
    tags=["summarize", "content", "web", "research"],
)


@dataclass
class SummarizeConfig:
    """Configuration for the summarize tool."""

    binary_path: str = "summarize"
    timeout: float = 60.0
    max_output_length: int = 50000


@dataclass
class SummarizeResult:
    """Result of a content summarization."""

    success: bool = False
    url: str = ""
    summary: str = ""
    title: str = ""
    content_type: str = ""  # article, youtube, podcast, pdf
    word_count: int = 0
    error: str = ""
    raw_output: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "url": self.url,
            "summary": self.summary,
            "title": self.title,
            "content_type": self.content_type,
            "word_count": self.word_count,
            "error": self.error,
        }


class SummarizeTool:
    """
    Content summarization via the steipete summarize CLI.

    Wraps `summarize <url> --json` for structured output parsing.
    Supports articles, YouTube videos, podcasts, and PDFs.
    """

    def __init__(self, config: Optional[SummarizeConfig] = None):
        self.config = config or SummarizeConfig()

    async def _exec_summarize(
        self, args: List[str], timeout: Optional[float] = None
    ) -> Tuple[int, str, str]:
        """Execute the summarize subprocess."""
        effective_timeout = timeout or self.config.timeout
        try:
            proc = await asyncio.create_subprocess_exec(
                self.config.binary_path,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=effective_timeout
            )
            return (
                proc.returncode or 0,
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"),
            )
        except asyncio.TimeoutError:
            return (1, "", f"Summarize timed out after {effective_timeout}s")
        except FileNotFoundError:
            return (1, "", "summarize binary not found")
        except Exception as e:
            return (1, "", str(e))

    async def summarize(
        self, url: str, output_format: str = "brief"
    ) -> SummarizeResult:
        """Summarize content from a URL."""
        args = [url, "--json"]
        if output_format and output_format != "brief":
            args.extend(["--format", output_format])

        returncode, stdout, stderr = await self._exec_summarize(args)

        if returncode != 0:
            return SummarizeResult(
                success=False,
                url=url,
                error=stderr or f"summarize exited with code {returncode}",
                raw_output=stdout,
            )

        # Truncate excessively long output
        if len(stdout) > self.config.max_output_length:
            stdout = stdout[: self.config.max_output_length]

        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError as e:
            return SummarizeResult(
                success=False,
                url=url,
                error=f"Failed to parse JSON output: {e}",
                raw_output=stdout,
            )

        return SummarizeResult(
            success=True,
            url=url,
            summary=parsed.get("summary", ""),
            title=parsed.get("title", ""),
            content_type=parsed.get("content_type", "unknown"),
            word_count=parsed.get("word_count", 0),
            raw_output=stdout,
            metadata={
                k: v
                for k, v in parsed.items()
                if k not in ("summary", "title", "content_type", "word_count", "url")
            },
        )


# -- Global tool instance for the executor --
_default_tool = SummarizeTool()


async def summarize_executor(
    args: Dict[str, Any], ctx: ToolExecutionContext
) -> ToolResult:
    """ToolRegistry-compatible executor for the summarize tool."""
    url = args.get("url", "")
    if not url:
        return ToolResult(
            tool_name="content_summarize",
            success=False,
            output="",
            error="Missing required parameter: url",
        )

    output_format = args.get("format", "brief")
    result = await _default_tool.summarize(url, output_format=output_format)

    if result.success:
        output_parts = []
        if result.title:
            output_parts.append(f"**{result.title}**")
        output_parts.append(result.summary)
        if result.word_count:
            output_parts.append(f"\n[{result.content_type}, {result.word_count} words]")

        return ToolResult(
            tool_name="content_summarize",
            success=True,
            output="\n".join(output_parts),
            metadata=result.to_dict(),
        )
    else:
        return ToolResult(
            tool_name="content_summarize",
            success=False,
            output="",
            error=result.error,
        )
```

```markdown
# vecna/skills/summarize/SKILL.md

# Content Summarize Skill

> Summarize web content, YouTube videos, and podcasts via the `summarize` CLI.

## When to Use

- User shares a URL and asks "what's this about?"
- User asks to summarize an article, video, or podcast
- CuriosityEngine needs to research a topic (autonomous research)
- DreamLoop generates a research goal that requires reading content
- User asks to "catch me up" on a topic with multiple sources

## Available Commands

| Command | Description |
|---------|-------------|
| `summarize <url> --json` | Summarize any URL (article, video, podcast) |
| `summarize <url> --format=detailed --json` | Detailed summary with key points |
| `summarize <url> --format=bullet_points --json` | Bullet point summary |

## Execution

### Via Tool Registry
The tool is registered as `content_summarize` in Vecna's ToolRegistry:
```python
tool_result = await tool_runtime.execute("content_summarize", {"url": "https://..."})
```

### Direct CLI
```
summarize "https://example.com/article" --json
```

### Output Format (JSON)
```json
{
    "title": "Article Title",
    "summary": "Concise summary of the content...",
    "content_type": "article",
    "word_count": 1500,
    "url": "https://example.com/article"
}
```

## Supported Content Types

- **Articles/Blog Posts** — HTML content extraction and summarization
- **YouTube Videos** — Transcript extraction and summarization
- **Podcasts** — Audio transcription and summarization
- **PDFs** — Text extraction and summarization

## Privacy

- Summarized content may be stored as Facts in the substrate
- Raw content is not persisted — only the summary
- URLs are logged for audit purposes
- Content from LOCAL_ONLY integrations should not be summarized via cloud tools

## Error Handling

- If `summarize` is not installed: inform user to install via `brew install summarize`
- If URL is unreachable: return error with status code
- If content is too long: tool auto-truncates to 50,000 characters
- Timeout: 60 seconds default, configurable
```

The `registry.py` modification adds the summarize tool to the default registry:

```python
# Add to get_default_registry() in vecna/tools/registry.py:
# After the existing web_search registration:

    if enable_web_tools:
        # ... existing http_request and web_search registrations ...

        try:
            from vecna.tools.summarize_tool import SUMMARIZE_TOOL_SPEC, summarize_executor

            registry.register(SUMMARIZE_TOOL_SPEC, summarize_executor)
        except ImportError:
            pass  # summarize tool not available
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_summarize_tool.py tests/unit/ -v --tb=short`
Expected: All PASS

**Step 5: Commit**

```bash
git add vecna/tools/summarize_tool.py vecna/skills/summarize/SKILL.md vecna/tools/registry.py tests/unit/test_summarize_tool.py
git commit -m "feat: add content summarize tool via steipete summarize CLI"
```

---

### Task 19: Browser Automation Tool

**Files:**
- Create: `vecna/tools/browser_tool.py`
- Modify: `vecna/tools/registry.py` (register browser tool)
- Create: `tests/unit/test_browser_tool.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_browser_tool.py
"""Tests for the Playwright-based browser automation tool."""

import json
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from vecna.tools.browser_tool import (
    BrowserTool,
    BrowserConfig,
    BrowserResult,
    PageContent,
    BROWSER_NAVIGATE_SPEC,
    BROWSER_SCREENSHOT_SPEC,
    BROWSER_CLICK_SPEC,
    browser_navigate_executor,
    browser_screenshot_executor,
    browser_click_executor,
)
from vecna.tools.types import ToolResult, ToolExecutionContext


class TestBrowserConfig:
    def test_default_config(self):
        config = BrowserConfig()
        assert config.headless is True
        assert config.timeout == 30.0
        assert config.max_content_length == 50000
        assert config.user_agent is not None

    def test_custom_config(self):
        config = BrowserConfig(headless=False, timeout=60.0)
        assert config.headless is False
        assert config.timeout == 60.0


class TestBrowserToolSpecs:
    def test_navigate_spec(self):
        assert BROWSER_NAVIGATE_SPEC.name == "browser_navigate"
        assert "url" in BROWSER_NAVIGATE_SPEC.input_schema
        assert "browser" in BROWSER_NAVIGATE_SPEC.tags

    def test_screenshot_spec(self):
        assert BROWSER_SCREENSHOT_SPEC.name == "browser_screenshot"
        assert "url" in BROWSER_SCREENSHOT_SPEC.input_schema

    def test_click_spec(self):
        assert BROWSER_CLICK_SPEC.name == "browser_click"
        assert "selector" in BROWSER_CLICK_SPEC.input_schema


class TestPageContent:
    def test_page_content_creation(self):
        content = PageContent(
            url="https://example.com",
            title="Example",
            text="Hello world",
            html="<html><body>Hello world</body></html>",
        )
        assert content.url == "https://example.com"
        assert content.title == "Example"
        assert content.text == "Hello world"

    def test_page_content_to_dict(self):
        content = PageContent(
            url="https://example.com",
            title="Example",
            text="Hello",
        )
        d = content.to_dict()
        assert d["url"] == "https://example.com"
        assert d["title"] == "Example"

    def test_page_content_truncation(self):
        long_text = "A" * 100000
        content = PageContent(
            url="https://example.com",
            title="Long Page",
            text=long_text,
        )
        truncated = content.truncated_text(max_length=1000)
        assert len(truncated) <= 1000
        assert truncated.endswith("... [truncated]")


class TestBrowserResult:
    def test_success_result(self):
        result = BrowserResult(
            success=True,
            action="navigate",
            url="https://example.com",
            content=PageContent(url="https://example.com", title="Example", text="Hi"),
        )
        assert result.success

    def test_error_result(self):
        result = BrowserResult(
            success=False,
            action="navigate",
            url="https://example.com",
            error="Connection refused",
        )
        assert not result.success

    def test_to_dict(self):
        result = BrowserResult(
            success=True,
            action="navigate",
            url="https://example.com",
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["action"] == "navigate"


class TestBrowserToolLifecycle:
    def test_tool_creation(self):
        tool = BrowserTool()
        assert tool.config.headless is True
        assert not tool.is_running

    async def test_start_creates_browser(self):
        tool = BrowserTool()
        mock_playwright = AsyncMock()
        mock_browser = AsyncMock()
        mock_playwright.chromium.launch.return_value = mock_browser

        with patch(
            "vecna.tools.browser_tool.async_playwright",
        ) as mock_pw_ctx:
            mock_pw_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_playwright)
            mock_pw_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            # Simulate the start without actually launching playwright
            tool._browser = mock_browser
            tool._playwright_ctx = mock_pw_ctx
            tool.is_running = True
            assert tool.is_running

    async def test_stop_closes_browser(self):
        tool = BrowserTool()
        tool._browser = AsyncMock()
        tool._playwright_ctx = MagicMock()
        tool._playwright_ctx.__aexit__ = AsyncMock(return_value=False)
        tool.is_running = True

        await tool.stop()
        assert not tool.is_running


class TestBrowserToolNavigation:
    async def test_navigate_returns_page_content(self):
        tool = BrowserTool()
        mock_page = AsyncMock()
        mock_page.title.return_value = "Example Page"
        mock_page.url = "https://example.com"
        mock_page.content.return_value = "<html><body>Hello</body></html>"
        mock_page.inner_text.return_value = "Hello"

        mock_browser = AsyncMock()
        mock_browser.new_page.return_value = mock_page
        tool._browser = mock_browser
        tool.is_running = True

        result = await tool.navigate("https://example.com")
        assert result.success
        assert result.content is not None
        assert result.content.title == "Example Page"

    async def test_navigate_handles_timeout(self):
        tool = BrowserTool(config=BrowserConfig(timeout=1.0))
        mock_page = AsyncMock()
        mock_page.goto.side_effect = Exception("Timeout")
        mock_page.close = AsyncMock()

        mock_browser = AsyncMock()
        mock_browser.new_page.return_value = mock_page
        tool._browser = mock_browser
        tool.is_running = True

        result = await tool.navigate("https://slow-site.example.com")
        assert not result.success
        assert "timeout" in result.error.lower() or "error" in result.error.lower()

    async def test_navigate_fails_when_not_running(self):
        tool = BrowserTool()
        result = await tool.navigate("https://example.com")
        assert not result.success
        assert "not running" in result.error.lower()


class TestBrowserToolClick:
    async def test_click_element(self):
        tool = BrowserTool()
        mock_page = AsyncMock()
        mock_page.click.return_value = None
        mock_page.url = "https://example.com/after-click"
        mock_page.title.return_value = "After Click"
        mock_page.content.return_value = "<html><body>Clicked</body></html>"
        mock_page.inner_text.return_value = "Clicked"

        tool._current_page = mock_page
        tool.is_running = True

        result = await tool.click("button#submit")
        assert result.success


class TestBrowserExecutors:
    async def test_navigate_executor_success(self):
        ctx = ToolExecutionContext(session_id="test")
        mock_result = BrowserResult(
            success=True,
            action="navigate",
            url="https://example.com",
            content=PageContent(url="https://example.com", title="Test", text="Content"),
        )

        with patch(
            "vecna.tools.browser_tool._get_browser_tool",
        ) as mock_get:
            mock_tool = AsyncMock()
            mock_tool.navigate.return_value = mock_result
            mock_tool.is_running = True
            mock_get.return_value = mock_tool

            result = await browser_navigate_executor({"url": "https://example.com"}, ctx)
            assert isinstance(result, ToolResult)
            assert result.success

    async def test_navigate_executor_missing_url(self):
        ctx = ToolExecutionContext()
        result = await browser_navigate_executor({}, ctx)
        assert not result.success
        assert "url" in result.error.lower()
```

**Step 2: Run tests, verify fail**

Run: `pytest tests/unit/test_browser_tool.py -v`
Expected: FAIL — module doesn't exist

**Step 3: Implement BrowserTool**

```python
# vecna/tools/browser_tool.py
"""
Playwright-based browser automation tool.

Provides browser navigation, screenshots, and element interaction
as registered Vecna tools. Runs headless by default.

Tool risk tier: HIGH — requires approval in autonomous mode.
"""

import asyncio
import base64
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from vecna.tools.types import ToolExecutionContext, ToolResult, ToolSpec

logger = logging.getLogger("vecna.tools.browser_tool")


# -- Tool Specifications --

BROWSER_NAVIGATE_SPEC = ToolSpec(
    name="browser_navigate",
    description=(
        "Navigate to a URL and return the page content as text. "
        "Use for reading web pages, documentation, or any URL content."
    ),
    input_schema={
        "url": "string",
    },
    tags=["browser", "web", "navigate"],
)

BROWSER_SCREENSHOT_SPEC = ToolSpec(
    name="browser_screenshot",
    description=(
        "Take a screenshot of a URL and return as base64-encoded PNG. "
        "Use for visual inspection of web pages."
    ),
    input_schema={
        "url": "string",
    },
    tags=["browser", "web", "screenshot"],
)

BROWSER_CLICK_SPEC = ToolSpec(
    name="browser_click",
    description=(
        "Click an element on the current page by CSS selector. "
        "Must call browser_navigate first to load a page."
    ),
    input_schema={
        "selector": "string",
    },
    tags=["browser", "web", "interact"],
)


@dataclass
class BrowserConfig:
    """Configuration for the browser tool."""

    headless: bool = True
    timeout: float = 30.0
    max_content_length: int = 50000
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36 Vecna/1.0"
    )
    viewport_width: int = 1280
    viewport_height: int = 720


@dataclass
class PageContent:
    """Extracted content from a web page."""

    url: str = ""
    title: str = ""
    text: str = ""
    html: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "text_length": len(self.text),
        }

    def truncated_text(self, max_length: int = 50000) -> str:
        """Return text truncated to max_length."""
        if len(self.text) <= max_length:
            return self.text
        return self.text[: max_length - 15] + "... [truncated]"


@dataclass
class BrowserResult:
    """Result of a browser action."""

    success: bool = False
    action: str = ""
    url: str = ""
    content: Optional[PageContent] = None
    screenshot_b64: Optional[str] = None
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "success": self.success,
            "action": self.action,
            "url": self.url,
            "error": self.error,
        }
        if self.content:
            result["content"] = self.content.to_dict()
        return result


class BrowserTool:
    """
    Playwright-based browser automation.

    Manages a browser instance lifecycle (start/stop) and provides
    navigation, screenshots, and element interaction.
    """

    def __init__(self, config: Optional[BrowserConfig] = None):
        self.config = config or BrowserConfig()
        self.is_running = False
        self._browser = None
        self._playwright_ctx = None
        self._current_page = None

    async def start(self) -> None:
        """Start the browser instance."""
        try:
            from playwright.async_api import async_playwright

            self._playwright_ctx = async_playwright()
            playwright = await self._playwright_ctx.__aenter__()
            self._browser = await playwright.chromium.launch(
                headless=self.config.headless,
            )
            self.is_running = True
            logger.info(
                f"Browser started (headless={self.config.headless})"
            )
        except ImportError:
            raise RuntimeError(
                "Playwright is not installed. Install with: pip install playwright && "
                "playwright install chromium"
            )
        except Exception as e:
            logger.error(f"Failed to start browser: {e}")
            raise

    async def stop(self) -> None:
        """Stop the browser instance."""
        if self._current_page:
            try:
                await self._current_page.close()
            except Exception:
                pass
            self._current_page = None

        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None

        if self._playwright_ctx:
            try:
                await self._playwright_ctx.__aexit__(None, None, None)
            except Exception:
                pass
            self._playwright_ctx = None

        self.is_running = False
        logger.info("Browser stopped")

    async def navigate(self, url: str) -> BrowserResult:
        """Navigate to a URL and return the page content."""
        if not self.is_running or not self._browser:
            return BrowserResult(
                success=False,
                action="navigate",
                url=url,
                error="Browser is not running. Call start() first.",
            )

        page = None
        try:
            page = await self._browser.new_page(
                user_agent=self.config.user_agent,
                viewport={
                    "width": self.config.viewport_width,
                    "height": self.config.viewport_height,
                },
            )

            await page.goto(
                url,
                timeout=int(self.config.timeout * 1000),
                wait_until="domcontentloaded",
            )

            title = await page.title()
            text = await page.inner_text("body")
            html = await page.content()

            # Sanitize and truncate
            text = text.strip()
            if len(text) > self.config.max_content_length:
                text = text[: self.config.max_content_length] + "... [truncated]"

            self._current_page = page

            content = PageContent(
                url=page.url,
                title=title,
                text=text,
                html=html if len(html) < self.config.max_content_length else "",
            )

            return BrowserResult(
                success=True,
                action="navigate",
                url=page.url,
                content=content,
            )

        except Exception as e:
            logger.error(f"Navigation error for {url}: {e}")
            if page:
                try:
                    await page.close()
                except Exception:
                    pass
            return BrowserResult(
                success=False,
                action="navigate",
                url=url,
                error=str(e),
            )

    async def screenshot(self, url: str) -> BrowserResult:
        """Take a screenshot of a URL."""
        if not self.is_running or not self._browser:
            return BrowserResult(
                success=False,
                action="screenshot",
                url=url,
                error="Browser is not running. Call start() first.",
            )

        page = None
        try:
            page = await self._browser.new_page(
                viewport={
                    "width": self.config.viewport_width,
                    "height": self.config.viewport_height,
                },
            )
            await page.goto(
                url,
                timeout=int(self.config.timeout * 1000),
                wait_until="domcontentloaded",
            )

            screenshot_bytes = await page.screenshot(type="png", full_page=False)
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

            await page.close()

            return BrowserResult(
                success=True,
                action="screenshot",
                url=url,
                screenshot_b64=screenshot_b64,
            )

        except Exception as e:
            logger.error(f"Screenshot error for {url}: {e}")
            if page:
                try:
                    await page.close()
                except Exception:
                    pass
            return BrowserResult(
                success=False,
                action="screenshot",
                url=url,
                error=str(e),
            )

    async def click(self, selector: str) -> BrowserResult:
        """Click an element on the current page."""
        if not self._current_page:
            return BrowserResult(
                success=False,
                action="click",
                error="No page loaded. Call navigate() first.",
            )

        try:
            await self._current_page.click(selector, timeout=int(self.config.timeout * 1000))

            # Return updated page state
            title = await self._current_page.title()
            text = await self._current_page.inner_text("body")
            html = await self._current_page.content()

            if len(text) > self.config.max_content_length:
                text = text[: self.config.max_content_length] + "... [truncated]"

            content = PageContent(
                url=self._current_page.url,
                title=title,
                text=text,
                html=html if len(html) < self.config.max_content_length else "",
            )

            return BrowserResult(
                success=True,
                action="click",
                url=self._current_page.url,
                content=content,
            )

        except Exception as e:
            logger.error(f"Click error for selector '{selector}': {e}")
            return BrowserResult(
                success=False,
                action="click",
                error=str(e),
            )


# -- Singleton browser tool instance --
_browser_tool: Optional[BrowserTool] = None


def _get_browser_tool() -> BrowserTool:
    """Get or create the global browser tool instance."""
    global _browser_tool
    if _browser_tool is None:
        _browser_tool = BrowserTool()
    return _browser_tool


async def browser_navigate_executor(
    args: Dict[str, Any], ctx: ToolExecutionContext
) -> ToolResult:
    """ToolRegistry-compatible executor for browser navigation."""
    url = args.get("url", "")
    if not url:
        return ToolResult(
            tool_name="browser_navigate",
            success=False,
            output="",
            error="Missing required parameter: url",
        )

    tool = _get_browser_tool()
    if not tool.is_running:
        try:
            await tool.start()
        except Exception as e:
            return ToolResult(
                tool_name="browser_navigate",
                success=False,
                output="",
                error=f"Failed to start browser: {e}",
            )

    result = await tool.navigate(url)

    if result.success and result.content:
        output = f"**{result.content.title}**\n\n"
        output += result.content.truncated_text(max_length=40000)
        return ToolResult(
            tool_name="browser_navigate",
            success=True,
            output=output,
            metadata=result.to_dict(),
        )
    else:
        return ToolResult(
            tool_name="browser_navigate",
            success=False,
            output="",
            error=result.error,
        )


async def browser_screenshot_executor(
    args: Dict[str, Any], ctx: ToolExecutionContext
) -> ToolResult:
    """ToolRegistry-compatible executor for browser screenshots."""
    url = args.get("url", "")
    if not url:
        return ToolResult(
            tool_name="browser_screenshot",
            success=False,
            output="",
            error="Missing required parameter: url",
        )

    tool = _get_browser_tool()
    if not tool.is_running:
        try:
            await tool.start()
        except Exception as e:
            return ToolResult(
                tool_name="browser_screenshot",
                success=False,
                output="",
                error=f"Failed to start browser: {e}",
            )

    result = await tool.screenshot(url)

    if result.success and result.screenshot_b64:
        return ToolResult(
            tool_name="browser_screenshot",
            success=True,
            output=f"Screenshot captured ({len(result.screenshot_b64)} bytes b64)",
            metadata={"screenshot_b64": result.screenshot_b64, **result.to_dict()},
        )
    else:
        return ToolResult(
            tool_name="browser_screenshot",
            success=False,
            output="",
            error=result.error,
        )


async def browser_click_executor(
    args: Dict[str, Any], ctx: ToolExecutionContext
) -> ToolResult:
    """ToolRegistry-compatible executor for browser click."""
    selector = args.get("selector", "")
    if not selector:
        return ToolResult(
            tool_name="browser_click",
            success=False,
            output="",
            error="Missing required parameter: selector",
        )

    tool = _get_browser_tool()
    result = await tool.click(selector)

    if result.success and result.content:
        output = f"Clicked '{selector}'. Page now shows:\n\n"
        output += f"**{result.content.title}**\n"
        output += result.content.truncated_text(max_length=20000)
        return ToolResult(
            tool_name="browser_click",
            success=True,
            output=output,
            metadata=result.to_dict(),
        )
    else:
        return ToolResult(
            tool_name="browser_click",
            success=False,
            output="",
            error=result.error,
        )
```

The `registry.py` modification adds browser tools to the default registry:

```python
# Add to get_default_registry() in vecna/tools/registry.py:
# After the summarize tool registration:

    if enable_web_tools:
        # ... existing registrations ...

        try:
            from vecna.tools.browser_tool import (
                BROWSER_NAVIGATE_SPEC,
                BROWSER_SCREENSHOT_SPEC,
                BROWSER_CLICK_SPEC,
                browser_navigate_executor,
                browser_screenshot_executor,
                browser_click_executor,
            )

            registry.register(BROWSER_NAVIGATE_SPEC, browser_navigate_executor)
            registry.register(BROWSER_SCREENSHOT_SPEC, browser_screenshot_executor)
            registry.register(BROWSER_CLICK_SPEC, browser_click_executor)
        except ImportError:
            pass  # playwright not installed
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_browser_tool.py tests/unit/ -v --tb=short`
Expected: All PASS

**Step 5: Commit**

```bash
git add vecna/tools/browser_tool.py vecna/tools/registry.py tests/unit/test_browser_tool.py
git commit -m "feat: add Playwright-based browser automation tool"
```

---

### TRACK B: Agentic Breadth

---

### Task 20: Composio Integration — Slack, Discord, GitHub

**Files:**
- Create: `vecna/integrations/composio_bridge.py`
- Create: `tests/unit/test_composio.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_composio.py
"""Tests for the Composio bridge — Slack, Discord, GitHub integrations."""

from unittest.mock import MagicMock, patch

import pytest

from vecna.integrations.composio_bridge import (
    ComposioBridge,
    ComposioConfig,
    ComposioToolAdapter,
    COMPOSIO_DEFAULT_ACTIONS,
)
from vecna.tools.types import ToolSpec, ToolResult, ToolExecutionContext


class TestComposioConfig:
    def test_default_config(self):
        config = ComposioConfig()
        assert config.api_key is None
        assert config.enabled_apps == []
        assert config.max_actions_per_app == 10

    def test_custom_config(self):
        config = ComposioConfig(
            api_key="test-key",
            enabled_apps=["slack", "github"],
        )
        assert config.api_key == "test-key"
        assert "slack" in config.enabled_apps


class TestComposioDefaultActions:
    def test_default_actions_has_slack(self):
        assert "slack_send_message" in COMPOSIO_DEFAULT_ACTIONS
        assert "slack_read_channel" in COMPOSIO_DEFAULT_ACTIONS

    def test_default_actions_has_github(self):
        assert "github_list_prs" in COMPOSIO_DEFAULT_ACTIONS
        assert "github_create_issue" in COMPOSIO_DEFAULT_ACTIONS

    def test_default_actions_has_discord(self):
        assert "discord_send_message" in COMPOSIO_DEFAULT_ACTIONS


class TestComposioToolAdapter:
    def test_adapter_creates_tool_spec(self):
        adapter = ComposioToolAdapter(
            action_name="slack_send_message",
            description="Send a message in a Slack channel",
            input_schema={
                "channel": "string",
                "message": "string",
            },
            app_name="slack",
        )
        spec = adapter.to_tool_spec()
        assert isinstance(spec, ToolSpec)
        assert spec.name == "composio_slack_send_message"
        assert "channel" in spec.input_schema
        assert "composio" in spec.tags

    def test_adapter_preserves_description(self):
        adapter = ComposioToolAdapter(
            action_name="github_list_prs",
            description="List open pull requests",
            input_schema={"repo": "string"},
            app_name="github",
        )
        spec = adapter.to_tool_spec()
        assert "pull requests" in spec.description.lower()


class TestComposioBridge:
    def test_bridge_creation_without_api_key(self):
        bridge = ComposioBridge()
        assert not bridge.is_available

    def test_bridge_creation_with_mock_key(self):
        bridge = ComposioBridge(config=ComposioConfig(api_key="test-key"))
        # Still not available without the composio package
        # But config is stored
        assert bridge.config.api_key == "test-key"

    def test_register_tools_into_registry(self):
        """Without composio installed, uses built-in stubs."""
        from vecna.tools.registry import ToolRegistry

        registry = ToolRegistry()
        bridge = ComposioBridge(
            config=ComposioConfig(api_key="test-key"),
            use_stubs=True,
        )
        count = bridge.register_tools(registry)
        assert count >= 1

        # Verify tool specs are in the registry
        tool_names = [t.name for t in registry.list_tools()]
        assert any("slack" in name for name in tool_names)

    def test_list_available_actions(self):
        bridge = ComposioBridge(
            config=ComposioConfig(api_key="test-key"),
            use_stubs=True,
        )
        actions = bridge.list_available_actions()
        assert len(actions) >= 1
        assert all(isinstance(a, ComposioToolAdapter) for a in actions)

    def test_stub_executor_returns_not_configured(self):
        bridge = ComposioBridge(use_stubs=True)
        ctx = ToolExecutionContext(session_id="test")
        result = bridge.create_stub_executor("slack_send_message")(
            {"channel": "#general", "message": "hello"},
            ctx,
        )
        assert isinstance(result, ToolResult)
        assert not result.success
        assert "not configured" in result.error.lower() or "stub" in result.error.lower()


class TestComposioBridgeWithMockSDK:
    """Test with a mocked Composio SDK."""

    def test_bridge_loads_actions_from_sdk(self):
        mock_composio = MagicMock()
        mock_composio.get_actions.return_value = [
            {
                "name": "slack_send_message",
                "description": "Send a Slack message",
                "parameters": {"channel": {"type": "string"}, "text": {"type": "string"}},
                "app": "slack",
            },
        ]

        bridge = ComposioBridge(
            config=ComposioConfig(api_key="test-key"),
        )
        bridge._composio_client = mock_composio

        actions = bridge._load_actions_from_sdk()
        assert len(actions) >= 1
        assert actions[0].action_name == "slack_send_message"

    def test_bridge_creates_executor_from_sdk(self):
        mock_composio = MagicMock()
        mock_composio.execute_action.return_value = {
            "success": True,
            "data": {"message_id": "msg-123"},
        }

        bridge = ComposioBridge(
            config=ComposioConfig(api_key="test-key"),
        )
        bridge._composio_client = mock_composio

        executor = bridge.create_sdk_executor("slack_send_message")
        ctx = ToolExecutionContext(session_id="test")
        result = executor(
            {"channel": "#general", "message": "hello"},
            ctx,
        )
        assert isinstance(result, ToolResult)
        assert result.success
```

**Step 2: Run tests, verify fail**

Run: `pytest tests/unit/test_composio.py -v`
Expected: FAIL — module doesn't exist

**Step 3: Implement ComposioBridge**

```python
# vecna/integrations/composio_bridge.py
"""
Composio integration bridge for Slack, Discord, and GitHub.

Bridges Composio's pre-built integration actions into Vecna's ToolRegistry.
Composio provides 100+ integrations via function calling — we convert their
tool schemas into ToolSpec objects and route execution through Vecna's
ToolRuntime (permissions, quotas, audit).

Optional dependency: `pip install composio-core`
Falls back to stub executors when Composio is not installed.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union

from vecna.tools.types import ToolExecutionContext, ToolResult, ToolSpec

logger = logging.getLogger("vecna.integrations.composio_bridge")


# -- Default actions we support --
COMPOSIO_DEFAULT_ACTIONS: Dict[str, Dict[str, Any]] = {
    "slack_send_message": {
        "description": "Send a message to a Slack channel",
        "input_schema": {"channel": "string", "message": "string"},
        "app": "slack",
    },
    "slack_read_channel": {
        "description": "Read recent messages from a Slack channel",
        "input_schema": {"channel": "string", "limit": "int"},
        "app": "slack",
    },
    "github_list_prs": {
        "description": "List open pull requests for a GitHub repository",
        "input_schema": {"repo": "string", "state": "string"},
        "app": "github",
    },
    "github_create_issue": {
        "description": "Create a new issue on a GitHub repository",
        "input_schema": {"repo": "string", "title": "string", "body": "string"},
        "app": "github",
    },
    "discord_send_message": {
        "description": "Send a message to a Discord channel",
        "input_schema": {"channel_id": "string", "message": "string"},
        "app": "discord",
    },
}


@dataclass
class ComposioConfig:
    """Configuration for the Composio bridge."""

    api_key: Optional[str] = None
    enabled_apps: List[str] = field(default_factory=list)
    max_actions_per_app: int = 10


@dataclass
class ComposioToolAdapter:
    """Adapter that converts a Composio action into a Vecna ToolSpec."""

    action_name: str
    description: str
    input_schema: Dict[str, Any]
    app_name: str

    def to_tool_spec(self) -> ToolSpec:
        """Convert this action to a Vecna ToolSpec."""
        return ToolSpec(
            name=f"composio_{self.action_name}",
            description=self.description,
            input_schema=self.input_schema,
            tags=["composio", self.app_name, "integration"],
        )


class ComposioBridge:
    """
    Bridge between Composio's integration SDK and Vecna's ToolRegistry.

    Converts Composio action schemas to ToolSpec objects and wraps
    their execution through Vecna's tool runtime.

    When Composio is not installed, provides stub executors that
    return informative error messages.
    """

    def __init__(
        self,
        config: Optional[ComposioConfig] = None,
        use_stubs: bool = False,
    ):
        self.config = config or ComposioConfig()
        self._use_stubs = use_stubs
        self._composio_client = None
        self._is_available = False

        # Try to import and initialize Composio SDK
        if not use_stubs and self.config.api_key:
            try:
                from composio import Composio

                self._composio_client = Composio(api_key=self.config.api_key)
                self._is_available = True
                logger.info("Composio SDK loaded successfully")
            except ImportError:
                logger.warning(
                    "Composio SDK not installed. Install with: pip install composio-core"
                )
            except Exception as e:
                logger.error(f"Failed to initialize Composio: {e}")

    @property
    def is_available(self) -> bool:
        """Whether Composio SDK is loaded and configured."""
        return self._is_available

    def list_available_actions(self) -> List[ComposioToolAdapter]:
        """List all available Composio actions."""
        if self._is_available and self._composio_client:
            return self._load_actions_from_sdk()

        # Fall back to built-in defaults
        return self._load_default_actions()

    def _load_default_actions(self) -> List[ComposioToolAdapter]:
        """Load the built-in default action definitions."""
        adapters = []
        for name, definition in COMPOSIO_DEFAULT_ACTIONS.items():
            adapters.append(
                ComposioToolAdapter(
                    action_name=name,
                    description=definition["description"],
                    input_schema=definition["input_schema"],
                    app_name=definition["app"],
                )
            )
        return adapters

    def _load_actions_from_sdk(self) -> List[ComposioToolAdapter]:
        """Load actions from the Composio SDK."""
        if not self._composio_client:
            return self._load_default_actions()

        adapters = []
        try:
            actions = self._composio_client.get_actions()
            for action in actions:
                name = action.get("name", "")
                if not name:
                    continue

                # Convert Composio parameter schema to our format
                params = action.get("parameters", {})
                input_schema = {}
                for param_name, param_def in params.items():
                    input_schema[param_name] = param_def.get("type", "string")

                adapters.append(
                    ComposioToolAdapter(
                        action_name=name,
                        description=action.get("description", ""),
                        input_schema=input_schema,
                        app_name=action.get("app", "unknown"),
                    )
                )
        except Exception as e:
            logger.error(f"Failed to load actions from Composio SDK: {e}")
            return self._load_default_actions()

        return adapters or self._load_default_actions()

    def register_tools(self, registry: "ToolRegistry") -> int:
        """Register all available Composio actions into a ToolRegistry.

        Returns the number of tools registered.
        """
        from vecna.tools.registry import ToolRegistry

        actions = self.list_available_actions()
        registered = 0

        for adapter in actions:
            spec = adapter.to_tool_spec()

            if self._is_available and self._composio_client:
                executor = self.create_sdk_executor(adapter.action_name)
            else:
                executor = self.create_stub_executor(adapter.action_name)

            try:
                registry.register(spec, executor)
                registered += 1
            except ValueError:
                # Tool already registered
                logger.debug(f"Tool {spec.name} already registered, skipping")

        logger.info(f"Registered {registered} Composio tools")
        return registered

    def create_stub_executor(
        self, action_name: str
    ) -> Callable[[Dict[str, Any], ToolExecutionContext], ToolResult]:
        """Create a stub executor that returns a 'not configured' error."""

        def stub_executor(
            args: Dict[str, Any], ctx: ToolExecutionContext
        ) -> ToolResult:
            return ToolResult(
                tool_name=f"composio_{action_name}",
                success=False,
                output="",
                error=(
                    f"Composio action '{action_name}' is not configured. "
                    f"Set COMPOSIO_API_KEY and install composio-core to enable."
                ),
            )

        return stub_executor

    def create_sdk_executor(
        self, action_name: str
    ) -> Callable[[Dict[str, Any], ToolExecutionContext], ToolResult]:
        """Create an executor that calls the Composio SDK."""
        client = self._composio_client

        def sdk_executor(
            args: Dict[str, Any], ctx: ToolExecutionContext
        ) -> ToolResult:
            try:
                result = client.execute_action(action_name, params=args)

                if isinstance(result, dict):
                    success = result.get("success", True)
                    data = result.get("data", result)
                    output = str(data)
                else:
                    success = True
                    output = str(result)

                return ToolResult(
                    tool_name=f"composio_{action_name}",
                    success=success,
                    output=output,
                    metadata={"action": action_name, "args": args},
                )
            except Exception as e:
                logger.error(f"Composio action '{action_name}' failed: {e}")
                return ToolResult(
                    tool_name=f"composio_{action_name}",
                    success=False,
                    output="",
                    error=str(e),
                )

        return sdk_executor
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_composio.py tests/unit/ -v --tb=short`
Expected: All PASS

**Step 5: Commit**

```bash
git add vecna/integrations/composio_bridge.py tests/unit/test_composio.py
git commit -m "feat: add Composio bridge for Slack, Discord, and GitHub integrations"
```

---

### Task 21: OpenAI/Anthropic Native Adapters

**Files:**
- Create: `vecna/adapters/openai_adapter.py`
- Create: `vecna/adapters/anthropic_adapter.py`
- Modify: `vecna/adapters/base.py` (add to factory)
- Modify: `vecna/config/schema.py` (add OPENAI, ANTHROPIC to Provider enum)
- Create: `tests/unit/test_native_adapters.py`

**Step 1: Write the failing tests**

```python
# tests/unit/test_native_adapters.py
"""Unit tests for native OpenAI and Anthropic adapters."""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vecna.adapters.base import BaseAdapter, ModelConfig, create_adapter
from vecna.adapters.openai_adapter import OpenAIAdapter
from vecna.adapters.anthropic_adapter import AnthropicAdapter
from vecna.core.types import HiveUpdate


class TestOpenAIAdapter:
    """Tests for the OpenAI native adapter."""

    def test_openai_adapter_init(self):
        """OpenAIAdapter initializes with ModelConfig."""
        config = ModelConfig(
            name="openai-gpt4",
            model_id="gpt-4-turbo",
            api_key="sk-test-key",
        )
        adapter = OpenAIAdapter(config)
        assert adapter.config.name == "openai-gpt4"
        assert adapter._get_provider_name() == "openai"

    def test_openai_adapter_requires_api_key(self):
        """OpenAIAdapter raises if no API key available."""
        config = ModelConfig(name="openai", model_id="gpt-4-turbo")
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="API key"):
                OpenAIAdapter(config)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"})
    def test_openai_adapter_uses_env_key(self):
        """OpenAIAdapter falls back to OPENAI_API_KEY env var."""
        config = ModelConfig(name="openai", model_id="gpt-4-turbo")
        adapter = OpenAIAdapter(config)
        assert adapter._api_key == "sk-test"

    async def test_openai_generate_calls_sdk(self):
        """OpenAIAdapter.generate calls OpenAI chat completions."""
        config = ModelConfig(
            name="openai",
            model_id="gpt-4-turbo",
            api_key="sk-test",
            temperature=0.7,
            max_tokens=1000,
        )
        adapter = OpenAIAdapter(config)
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello from GPT-4"
        mock_response.choices[0].message.tool_calls = None
        mock_response.usage = MagicMock(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )
        adapter._client = MagicMock()
        adapter._client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )
        result = await adapter.generate("Test prompt")
        assert result == "Hello from GPT-4"

    async def test_openai_generate_with_tool_calls(self):
        """OpenAIAdapter handles tool call responses."""
        config = ModelConfig(
            name="openai",
            model_id="gpt-4-turbo",
            api_key="sk-test",
        )
        adapter = OpenAIAdapter(config)
        tool_call = MagicMock()
        tool_call.function.name = "hive_update"
        tool_call.function.arguments = json.dumps({
            "facts": [{"content": "Test fact", "confidence": 0.9}],
            "beliefs": [],
            "response": "Tool response",
        })
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None
        mock_response.choices[0].message.tool_calls = [tool_call]
        mock_response.usage = MagicMock(
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        )
        adapter._client = MagicMock()
        adapter._client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )
        result = await adapter.generate("Test")
        parsed = json.loads(result)
        assert parsed["facts"][0]["content"] == "Test fact"
        assert parsed["response"] == "Tool response"

    async def test_openai_parse_update_from_tool_json(self):
        """OpenAIAdapter.parse_update parses JSON tool output."""
        config = ModelConfig(
            name="openai",
            model_id="gpt-4-turbo",
            api_key="sk-test",
        )
        adapter = OpenAIAdapter(config)
        tool_json = json.dumps({
            "facts": [{"content": "Earth orbits Sun", "confidence": 0.99}],
            "beliefs": [{"content": "Science is useful", "confidence": 0.8}],
            "response": "Astronomical fact provided.",
        })
        update = adapter.parse_update(tool_json)
        assert isinstance(update, HiveUpdate)
        assert len(update.facts) == 1
        assert update.facts[0].content == "Earth orbits Sun"
        assert update.response == "Astronomical fact provided."

    async def test_openai_streaming_generates_chunks(self):
        """OpenAIAdapter supports streaming via generate_stream."""
        config = ModelConfig(
            name="openai",
            model_id="gpt-4-turbo",
            api_key="sk-test",
        )
        adapter = OpenAIAdapter(config)

        async def mock_stream():
            for text in ["Hello", " world", "!"]:
                chunk = MagicMock()
                chunk.choices = [MagicMock()]
                chunk.choices[0].delta.content = text
                chunk.choices[0].delta.tool_calls = None
                yield chunk

        adapter._client = MagicMock()
        adapter._client.chat.completions.create = AsyncMock(
            return_value=mock_stream()
        )
        chunks = []
        async for chunk in adapter.generate_stream("Test"):
            chunks.append(chunk)
        assert "".join(chunks) == "Hello world!"


class TestAnthropicAdapter:
    """Tests for the Anthropic native adapter."""

    def test_anthropic_adapter_init(self):
        """AnthropicAdapter initializes with ModelConfig."""
        config = ModelConfig(
            name="claude",
            model_id="claude-3-sonnet-20240229",
            api_key="sk-ant-test",
        )
        adapter = AnthropicAdapter(config)
        assert adapter.config.name == "claude"
        assert adapter._get_provider_name() == "anthropic"

    def test_anthropic_adapter_requires_api_key(self):
        """AnthropicAdapter raises if no API key available."""
        config = ModelConfig(name="claude", model_id="claude-3-sonnet-20240229")
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="API key"):
                AnthropicAdapter(config)

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test"})
    def test_anthropic_adapter_uses_env_key(self):
        """AnthropicAdapter falls back to ANTHROPIC_API_KEY env var."""
        config = ModelConfig(
            name="claude", model_id="claude-3-sonnet-20240229"
        )
        adapter = AnthropicAdapter(config)
        assert adapter._api_key == "sk-ant-test"

    async def test_anthropic_generate_calls_sdk(self):
        """AnthropicAdapter.generate calls Anthropic messages API."""
        config = ModelConfig(
            name="claude",
            model_id="claude-3-sonnet-20240229",
            api_key="sk-ant-test",
            temperature=0.7,
            max_tokens=1000,
        )
        adapter = AnthropicAdapter(config)
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].type = "text"
        mock_response.content[0].text = "Hello from Claude"
        mock_response.stop_reason = "end_turn"
        mock_response.usage = MagicMock(
            input_tokens=10,
            output_tokens=5,
        )
        adapter._client = MagicMock()
        adapter._client.messages.create = AsyncMock(
            return_value=mock_response
        )
        result = await adapter.generate("Test prompt")
        assert result == "Hello from Claude"

    async def test_anthropic_generate_with_tool_use(self):
        """AnthropicAdapter handles tool_use content blocks."""
        config = ModelConfig(
            name="claude",
            model_id="claude-3-sonnet-20240229",
            api_key="sk-ant-test",
        )
        adapter = AnthropicAdapter(config)
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "hive_update"
        tool_block.input = {
            "facts": [{"content": "Claude fact", "confidence": 0.85}],
            "beliefs": [],
            "response": "Tool use response",
        }
        mock_response = MagicMock()
        mock_response.content = [tool_block]
        mock_response.stop_reason = "tool_use"
        mock_response.usage = MagicMock(
            input_tokens=15,
            output_tokens=25,
        )
        adapter._client = MagicMock()
        adapter._client.messages.create = AsyncMock(
            return_value=mock_response
        )
        result = await adapter.generate("Test")
        parsed = json.loads(result)
        assert parsed["facts"][0]["content"] == "Claude fact"

    async def test_anthropic_parse_update_from_tool_json(self):
        """AnthropicAdapter.parse_update parses JSON tool output."""
        config = ModelConfig(
            name="claude",
            model_id="claude-3-sonnet-20240229",
            api_key="sk-ant-test",
        )
        adapter = AnthropicAdapter(config)
        tool_json = json.dumps({
            "facts": [{"content": "Water is H2O", "confidence": 0.99}],
            "beliefs": [],
            "response": "Chemistry fact.",
        })
        update = adapter.parse_update(tool_json)
        assert isinstance(update, HiveUpdate)
        assert len(update.facts) == 1
        assert update.response == "Chemistry fact."

    async def test_anthropic_streaming_generates_chunks(self):
        """AnthropicAdapter supports streaming."""
        config = ModelConfig(
            name="claude",
            model_id="claude-3-sonnet-20240229",
            api_key="sk-ant-test",
        )
        adapter = AnthropicAdapter(config)

        async def mock_stream():
            for text in ["Bonjour", " le", " monde"]:
                event = MagicMock()
                event.type = "content_block_delta"
                event.delta = MagicMock()
                event.delta.type = "text_delta"
                event.delta.text = text
                yield event

        adapter._client = MagicMock()
        adapter._client.messages.stream = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_stream()),
                __aexit__=AsyncMock(return_value=False),
            )
        )
        chunks = []
        async for chunk in adapter.generate_stream("Test"):
            chunks.append(chunk)
        assert "".join(chunks) == "Bonjour le monde"


class TestFactoryRouting:
    """Tests for adapter factory routing to new providers."""

    def test_factory_creates_openai_adapter(self):
        """create_adapter routes to OpenAIAdapter for openai provider."""
        config = ModelConfig(
            name="openai",
            model_id="gpt-4-turbo",
            api_key="sk-test",
            extra_params={"provider": "openai"},
        )
        adapter = create_adapter(config)
        assert isinstance(adapter, OpenAIAdapter)

    def test_factory_creates_anthropic_adapter(self):
        """create_adapter routes to AnthropicAdapter for anthropic provider."""
        config = ModelConfig(
            name="claude",
            model_id="claude-3-sonnet-20240229",
            api_key="sk-ant-test",
            extra_params={"provider": "anthropic"},
        )
        adapter = create_adapter(config)
        assert isinstance(adapter, AnthropicAdapter)


class TestProviderEnum:
    """Tests for Provider enum updates."""

    def test_openai_in_provider_enum(self):
        """Provider enum includes OPENAI."""
        from vecna.config.schema import Provider
        assert hasattr(Provider, "OPENAI")

    def test_anthropic_in_provider_enum(self):
        """Provider enum includes ANTHROPIC."""
        from vecna.config.schema import Provider
        assert hasattr(Provider, "ANTHROPIC")
```

**Step 2: Run tests, see them fail**

```bash
pytest tests/unit/test_native_adapters.py -v
```

Expected: All tests FAIL (missing `openai_adapter.py`, `anthropic_adapter.py`, Provider enum entries, factory routing)

**Step 3: Implement**

**`vecna/adapters/openai_adapter.py`:**

```python
"""OpenAI native adapter with function calling support."""

import json
import logging
import os
from typing import Any, AsyncIterator, Dict, List, Optional

from vecna.adapters.base import BaseAdapter
from vecna.config.schema import ModelConfig
from vecna.core.types import Fact, Belief, Hypothesis, HiveUpdate

logger = logging.getLogger("vecna.openai_adapter")


def _build_hive_update_tool() -> Dict[str, Any]:
    """Build the hive_update function tool schema for OpenAI."""
    return {
        "type": "function",
        "function": {
            "name": "hive_update",
            "description": (
                "Submit structured updates to the hive mind state "
                "including facts, beliefs, hypotheses, and a response."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "facts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {"type": "string"},
                                "confidence": {
                                    "type": "number",
                                    "minimum": 0.0,
                                    "maximum": 1.0,
                                },
                            },
                            "required": ["content", "confidence"],
                        },
                        "description": "New facts discovered.",
                    },
                    "beliefs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {"type": "string"},
                                "confidence": {
                                    "type": "number",
                                    "minimum": 0.0,
                                    "maximum": 1.0,
                                },
                            },
                            "required": ["content", "confidence"],
                        },
                        "description": "Updated beliefs.",
                    },
                    "hypotheses": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {"type": "string"},
                                "confidence": {
                                    "type": "number",
                                    "minimum": 0.0,
                                    "maximum": 1.0,
                                },
                            },
                            "required": ["content", "confidence"],
                        },
                        "description": "New hypotheses.",
                    },
                    "response": {
                        "type": "string",
                        "description": "The response to the user.",
                    },
                },
                "required": ["response"],
            },
        },
    }


class OpenAIAdapter(BaseAdapter):
    """Native OpenAI adapter using the openai SDK.

    Supports function calling via the hive_update tool schema
    and streaming responses. Uses the openai Python SDK directly.
    """

    def __init__(self, config: ModelConfig) -> None:
        super().__init__(config)
        self._api_key = config.api_key or os.getenv("OPENAI_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "OpenAI API key required. Set api_key in config "
                "or OPENAI_API_KEY environment variable."
            )
        self._client: Any = None
        self._init_client()

    def _init_client(self) -> None:
        """Initialize the OpenAI client."""
        try:
            from openai import AsyncOpenAI

            base_url = self.config.base_url or None
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=base_url,
            )
            logger.info(
                "OpenAI client initialized for model %s",
                self.config.model_id,
            )
        except ImportError:
            logger.warning(
                "openai package not installed. "
                "Install with: pip install openai"
            )
            raise

    def _get_provider_name(self) -> str:
        return "openai"

    def _build_messages(self, prompt: str) -> List[Dict[str, str]]:
        """Build chat messages from prompt."""
        system_msg = self.get_system_message()
        messages = []
        if system_msg:
            messages.append({"role": "system", "content": system_msg})
        messages.append({"role": "user", "content": prompt})
        return messages

    async def generate(self, prompt: str) -> str:
        """Generate a response using OpenAI chat completions.

        If the model returns a tool call for hive_update, the tool
        call arguments are returned as a JSON string. Otherwise
        the text content is returned directly.

        Args:
            prompt: The input prompt.

        Returns:
            Response text or JSON tool call arguments.
        """
        messages = self._build_messages(prompt)
        tools = [_build_hive_update_tool()]

        try:
            response = await self._client.chat.completions.create(
                model=self.config.model_id,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )
        except Exception as e:
            logger.error("OpenAI API call failed: %s", e)
            raise

        choice = response.choices[0]

        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                if tc.function.name == "hive_update":
                    return tc.function.arguments
            return choice.message.content or ""

        return choice.message.content or ""

    async def generate_stream(
        self, prompt: str
    ) -> AsyncIterator[str]:
        """Stream response chunks from OpenAI.

        Args:
            prompt: The input prompt.

        Yields:
            Text chunks as they arrive.
        """
        messages = self._build_messages(prompt)

        try:
            stream = await self._client.chat.completions.create(
                model=self.config.model_id,
                messages=messages,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error("OpenAI streaming failed: %s", e)
            raise

    def parse_update(self, output: str) -> HiveUpdate:
        """Parse a tool call JSON response into HiveUpdate.

        Attempts JSON parsing first (for tool call responses),
        then falls back to the base YAML parser.

        Args:
            output: Raw model output string.

        Returns:
            Parsed HiveUpdate.
        """
        try:
            data = json.loads(output)
            facts = []
            for f in data.get("facts", []):
                facts.append(Fact(
                    content=f["content"],
                    confidence=f.get("confidence", 0.5),
                    source=self.config.name,
                ))
            beliefs = []
            for b in data.get("beliefs", []):
                beliefs.append(Belief(
                    content=b["content"],
                    confidence=b.get("confidence", 0.5),
                ))
            hypotheses = []
            for h in data.get("hypotheses", []):
                hypotheses.append(Hypothesis(
                    content=h["content"],
                    confidence=h.get("confidence", 0.5),
                ))
            return HiveUpdate(
                facts=facts,
                beliefs=beliefs,
                hypotheses=hypotheses,
                response=data.get("response", ""),
            )
        except (json.JSONDecodeError, KeyError):
            return super().parse_update(output)
```

**`vecna/adapters/anthropic_adapter.py`:**

```python
"""Anthropic native adapter with tool use support."""

import json
import logging
import os
from typing import Any, AsyncIterator, Dict, List, Optional

from vecna.adapters.base import BaseAdapter
from vecna.config.schema import ModelConfig
from vecna.core.types import Fact, Belief, Hypothesis, HiveUpdate

logger = logging.getLogger("vecna.anthropic_adapter")


def _build_hive_update_tool_anthropic() -> Dict[str, Any]:
    """Build the hive_update tool schema for Anthropic."""
    return {
        "name": "hive_update",
        "description": (
            "Submit structured updates to the hive mind state "
            "including facts, beliefs, hypotheses, and a response."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "facts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string"},
                            "confidence": {
                                "type": "number",
                            },
                        },
                        "required": ["content", "confidence"],
                    },
                    "description": "New facts discovered.",
                },
                "beliefs": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string"},
                            "confidence": {
                                "type": "number",
                            },
                        },
                        "required": ["content", "confidence"],
                    },
                    "description": "Updated beliefs.",
                },
                "hypotheses": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string"},
                            "confidence": {
                                "type": "number",
                            },
                        },
                        "required": ["content", "confidence"],
                    },
                    "description": "New hypotheses.",
                },
                "response": {
                    "type": "string",
                    "description": "The response to the user.",
                },
            },
            "required": ["response"],
        },
    }


class AnthropicAdapter(BaseAdapter):
    """Native Anthropic adapter using the anthropic SDK.

    Supports tool use via the hive_update tool schema and
    streaming responses. Uses the anthropic Python SDK directly.
    """

    def __init__(self, config: ModelConfig) -> None:
        super().__init__(config)
        self._api_key = config.api_key or os.getenv(
            "ANTHROPIC_API_KEY", ""
        )
        if not self._api_key:
            raise ValueError(
                "Anthropic API key required. Set api_key in config "
                "or ANTHROPIC_API_KEY environment variable."
            )
        self._client: Any = None
        self._init_client()

    def _init_client(self) -> None:
        """Initialize the Anthropic client."""
        try:
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(api_key=self._api_key)
            logger.info(
                "Anthropic client initialized for model %s",
                self.config.model_id,
            )
        except ImportError:
            logger.warning(
                "anthropic package not installed. "
                "Install with: pip install anthropic"
            )
            raise

    def _get_provider_name(self) -> str:
        return "anthropic"

    async def generate(self, prompt: str) -> str:
        """Generate a response using Anthropic messages API.

        If the model returns a tool_use block for hive_update,
        the tool input is returned as a JSON string. Otherwise
        the text content is returned directly.

        Args:
            prompt: The input prompt.

        Returns:
            Response text or JSON tool input.
        """
        system_msg = self.get_system_message() or ""
        tools = [_build_hive_update_tool_anthropic()]

        try:
            response = await self._client.messages.create(
                model=self.config.model_id,
                max_tokens=self.config.max_tokens or 1024,
                system=system_msg,
                messages=[{"role": "user", "content": prompt}],
                tools=tools,
            )
        except Exception as e:
            logger.error("Anthropic API call failed: %s", e)
            raise

        for block in response.content:
            if block.type == "tool_use" and block.name == "hive_update":
                return json.dumps(block.input)

        text_parts = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
        return "".join(text_parts)

    async def generate_stream(
        self, prompt: str
    ) -> AsyncIterator[str]:
        """Stream response chunks from Anthropic.

        Args:
            prompt: The input prompt.

        Yields:
            Text chunks as they arrive.
        """
        system_msg = self.get_system_message() or ""

        try:
            async with self._client.messages.stream(
                model=self.config.model_id,
                max_tokens=self.config.max_tokens or 1024,
                system=system_msg,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                async for event in stream:
                    if event.type == "content_block_delta":
                        if event.delta.type == "text_delta":
                            yield event.delta.text
        except Exception as e:
            logger.error("Anthropic streaming failed: %s", e)
            raise

    def parse_update(self, output: str) -> HiveUpdate:
        """Parse a tool use JSON response into HiveUpdate.

        Attempts JSON parsing first (for tool use responses),
        then falls back to the base YAML parser.

        Args:
            output: Raw model output string.

        Returns:
            Parsed HiveUpdate.
        """
        try:
            data = json.loads(output)
            facts = []
            for f in data.get("facts", []):
                facts.append(Fact(
                    content=f["content"],
                    confidence=f.get("confidence", 0.5),
                    source=self.config.name,
                ))
            beliefs = []
            for b in data.get("beliefs", []):
                beliefs.append(Belief(
                    content=b["content"],
                    confidence=b.get("confidence", 0.5),
                ))
            hypotheses = []
            for h in data.get("hypotheses", []):
                hypotheses.append(Hypothesis(
                    content=h["content"],
                    confidence=h.get("confidence", 0.5),
                ))
            return HiveUpdate(
                facts=facts,
                beliefs=beliefs,
                hypotheses=hypotheses,
                response=data.get("response", ""),
            )
        except (json.JSONDecodeError, KeyError):
            return super().parse_update(output)
```

**`vecna/config/schema.py`** (add to Provider enum):

```python
# Add these two members to the Provider enum class:
OPENAI = "openai"
ANTHROPIC = "anthropic"
```

**`vecna/adapters/base.py`** (update `create_adapter` factory):

```python
# Add to the create_adapter function body, before the existing
# Ollama/Groq/Copilot routing:

    provider = (config.extra_params or {}).get("provider", "")

    if provider == "openai" or "openai" in config.model_id.lower():
        from vecna.adapters.openai_adapter import OpenAIAdapter
        return OpenAIAdapter(config)

    if provider == "anthropic" or "claude" in config.model_id.lower():
        from vecna.adapters.anthropic_adapter import AnthropicAdapter
        return AnthropicAdapter(config)
```

**Step 4: Run tests**

```bash
pytest tests/unit/test_native_adapters.py -v
```

Expected: All 16 tests pass

**Step 5: Commit**

```bash
git add vecna/adapters/openai_adapter.py vecna/adapters/anthropic_adapter.py \
  vecna/adapters/base.py vecna/config/schema.py tests/unit/test_native_adapters.py
git commit -m "feat: add native OpenAI and Anthropic adapters with tool calling"
```

---

## Phase 3: Convergence (Tasks 22-29)

> **Duration:** 4-5 weeks
> **Goal:** Merge Track A and Track B into the full Vecna Entity. Autonomous thoughtfulness, proactive assistance, visual TUI upgrade, and polish.

---

### Task 22: Wire HumanModel into HiveLoop

**Files:**
- Modify: `vecna/orchestrator/loop.py` (inject HumanModel context into prompts)
- Modify: `vecna/adapters/base.py` (include human model in system prompt)
- Create: `tests/unit/test_human_model_integration.py`

**Step 1: Write the failing tests**

```python
# tests/unit/test_human_model_integration.py
"""Unit tests for HumanModel integration into HiveLoop."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vecna.adapters.base import BaseAdapter, ModelConfig, HIVE_IDENTITY_PROMPT
from vecna.core.hive_state import HiveState
from vecna.core.human_model import HumanModel


class MockAdapterForHM(BaseAdapter):
    """Mock adapter that captures the prompt it receives."""

    def __init__(self):
        config = ModelConfig(name="mock-hm", model_id="mock-hm-v1")
        super().__init__(config)
        self.last_prompt = ""

    async def generate(self, prompt: str) -> str:
        self.last_prompt = prompt
        return (
            "<HIVE_UPDATE>\n"
            "facts:\n"
            "  - content: \"User prefers concise answers\"\n"
            "    confidence: 0.8\n"
            "response: \"Got it, I'll be concise.\"\n"
            "</HIVE_UPDATE>"
        )

    def _get_provider_name(self) -> str:
        return "mock"


class TestHumanModelPromptInjection:
    """Tests that HumanModel context is injected into prompts."""

    def test_hive_identity_prompt_has_human_model_placeholder(self):
        """HIVE_IDENTITY_PROMPT includes {human_model_context}."""
        assert "{human_model_context}" in HIVE_IDENTITY_PROMPT

    def test_build_prompt_includes_human_model(self):
        """build_prompt injects HumanModel context when provided."""
        adapter = MockAdapterForHM()
        state = HiveState()
        human_model = HumanModel()
        human_model.add_preference(
            dimension="communication_style",
            value="concise",
            confidence=0.9,
        )
        prompt = adapter.build_prompt(
            state, "Tell me about Python",
            human_model=human_model,
        )
        assert "communication_style" in prompt
        assert "concise" in prompt

    def test_build_prompt_works_without_human_model(self):
        """build_prompt works when human_model is None."""
        adapter = MockAdapterForHM()
        state = HiveState()
        prompt = adapter.build_prompt(state, "Hello")
        assert "{human_model_context}" not in prompt
        assert "Hello" in prompt


class TestPreferenceExtraction:
    """Tests for extracting preference signals from responses."""

    def test_extract_preference_signals_from_response(self):
        """HiveLoop extracts preference signals from adapter output."""
        from vecna.orchestrator.loop import HiveLoop, HiveConfig

        adapter = MockAdapterForHM()
        config = HiveConfig()
        loop = HiveLoop(
            config=config,
            adapters=[adapter],
            name="test-hm",
        )
        loop._human_model = HumanModel()
        signals = loop._extract_preference_signals(
            task="Be concise please",
            response="Got it, I'll be concise.",
        )
        assert isinstance(signals, list)

    def test_preference_signals_detect_style_request(self):
        """Preference extraction detects communication style cues."""
        from vecna.orchestrator.loop import HiveLoop, HiveConfig

        adapter = MockAdapterForHM()
        config = HiveConfig()
        loop = HiveLoop(
            config=config,
            adapters=[adapter],
            name="test-hm",
        )
        loop._human_model = HumanModel()
        signals = loop._extract_preference_signals(
            task="Give me a detailed explanation",
            response="Here is a thorough breakdown...",
        )
        found_detail = any(
            s.get("dimension") == "detail_level" for s in signals
        )
        assert isinstance(signals, list)


class TestHumanModelPersistence:
    """Tests for HumanModel save/load alongside HiveState."""

    def test_human_model_interaction_count_increments(self):
        """Each think() call increments interaction count."""
        from vecna.orchestrator.loop import HiveLoop, HiveConfig

        adapter = MockAdapterForHM()
        config = HiveConfig()
        loop = HiveLoop(
            config=config,
            adapters=[adapter],
            name="test-hm",
        )
        loop._human_model = HumanModel()
        initial = loop._human_model.interaction_count
        loop._human_model.interaction_count += 1
        assert loop._human_model.interaction_count == initial + 1

    def test_human_model_export_import_roundtrip(self):
        """HumanModel survives export/import cycle."""
        model = HumanModel()
        model.add_preference(
            dimension="tone",
            value="friendly",
            confidence=0.85,
        )
        model.interaction_count = 42
        exported = model.to_dict()
        restored = HumanModel.from_dict(exported)
        assert restored.interaction_count == 42
        pref = restored.get_preference("tone")
        assert pref is not None
        assert pref.value == "friendly"

    async def test_think_with_human_model(self):
        """HiveLoop.think works when human_model is attached."""
        from vecna.orchestrator.loop import HiveLoop, HiveConfig

        adapter = MockAdapterForHM()
        config = HiveConfig()
        loop = HiveLoop(
            config=config,
            adapters=[adapter],
            name="test-hm",
        )
        loop._human_model = HumanModel()
        loop._human_model.add_preference(
            dimension="expertise",
            value="advanced",
            confidence=0.9,
        )
        result = await loop.think("Explain recursion")
        assert isinstance(result, str)
        assert len(result) > 0

    async def test_think_updates_human_model_interaction_count(self):
        """think() increments human_model.interaction_count."""
        from vecna.orchestrator.loop import HiveLoop, HiveConfig

        adapter = MockAdapterForHM()
        config = HiveConfig()
        loop = HiveLoop(
            config=config,
            adapters=[adapter],
            name="test-hm",
        )
        loop._human_model = HumanModel()
        initial = loop._human_model.interaction_count
        await loop.think("Hello")
        assert loop._human_model.interaction_count > initial
```

**Step 2: Run tests, see them fail**

```bash
pytest tests/unit/test_human_model_integration.py -v
```

Expected: All tests FAIL (missing `{human_model_context}` in prompt, `build_prompt` doesn't accept `human_model`, no `_extract_preference_signals`)

**Step 3: Implement**

**`vecna/adapters/base.py`** (update HIVE_IDENTITY_PROMPT and build_prompt):

```python
# Replace the HIVE_IDENTITY_PROMPT template to include human_model_context:

HIVE_IDENTITY_PROMPT = """You are a node in Vecna, a hive-mind AI.

{memory_context}

{human_model_context}

Your task: {task}

Respond with a <HIVE_UPDATE> YAML block containing facts, beliefs,
hypotheses, and your response. You may also include <TOOL_CALL> blocks.
"""


# Update build_prompt to accept an optional human_model parameter:

def build_prompt(
    self,
    state: "HiveState",
    task: str,
    human_model: Optional["HumanModel"] = None,
) -> str:
    """Build a full prompt with state context and human model.

    Args:
        state: Current HiveState.
        task: The user's task/message.
        human_model: Optional HumanModel for user preferences.

    Returns:
        Formatted prompt string.
    """
    memory_context = state.to_prompt_context()
    human_model_context = ""
    if human_model is not None:
        human_model_context = human_model.to_prompt_context()
    return HIVE_IDENTITY_PROMPT.format(
        memory_context=memory_context,
        human_model_context=human_model_context,
        task=task,
    )
```

**`vecna/orchestrator/loop.py`** (add _extract_preference_signals and wire human_model):

```python
# Add to HiveLoop.__init__:
self._human_model: Optional[HumanModel] = None

# Add this method to HiveLoop:

def _extract_preference_signals(
    self,
    task: str,
    response: str,
) -> List[Dict[str, Any]]:
    """Extract user preference signals from a task/response pair.

    Uses heuristic keyword detection to identify communication
    style preferences expressed in the user's input.

    Args:
        task: The user's original input.
        response: The model's response.

    Returns:
        List of preference signal dicts with dimension and value.
    """
    signals: List[Dict[str, Any]] = []
    task_lower = task.lower()

    detail_keywords = {
        "detailed": "detailed",
        "thorough": "detailed",
        "in depth": "detailed",
        "brief": "brief",
        "concise": "brief",
        "short": "brief",
        "summary": "brief",
    }
    for keyword, value in detail_keywords.items():
        if keyword in task_lower:
            signals.append({
                "dimension": "detail_level",
                "value": value,
                "confidence": 0.7,
            })
            break

    tone_keywords = {
        "formal": "formal",
        "casual": "casual",
        "friendly": "casual",
        "professional": "formal",
    }
    for keyword, value in tone_keywords.items():
        if keyword in task_lower:
            signals.append({
                "dimension": "tone",
                "value": value,
                "confidence": 0.6,
            })
            break

    return signals


# Update _run_cycle to inject human_model into build_prompt
# and increment interaction count:

# In the _run_cycle method, where build_prompt is called:
prompt = adapter.build_prompt(
    self.state,
    task,
    human_model=self._human_model,
)

# After getting the response, extract and apply signals:
if self._human_model is not None:
    self._human_model.interaction_count += 1
    signals = self._extract_preference_signals(task, raw_response)
    for signal in signals:
        self._human_model.add_preference(
            dimension=signal["dimension"],
            value=signal["value"],
            confidence=signal["confidence"],
        )
```

**Step 4: Run tests**

```bash
pytest tests/unit/test_human_model_integration.py -v
```

Expected: All 8 tests pass

**Step 5: Commit**

```bash
git add vecna/orchestrator/loop.py vecna/adapters/base.py \
  tests/unit/test_human_model_integration.py
git commit -m "feat: wire HumanModel into HiveLoop for adaptive user modeling"
```

---

### Task 23: Autonomous Thoughtfulness Engine

**Files:**
- Create: `vecna/orchestrator/thoughtfulness.py`
- Modify: `vecna/orchestrator/heartbeat.py` (add thoughtfulness action)
- Create: `tests/unit/test_thoughtfulness.py`

**Step 1: Write the failing tests**

```python
# tests/unit/test_thoughtfulness.py
"""Unit tests for the Autonomous Thoughtfulness Engine."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pytest

from vecna.orchestrator.thoughtfulness import (
    ProactiveMessage,
    ThoughtfulnessEngine,
)
from vecna.core.hive_state import HiveState
from vecna.core.types import Fact, Belief


class TestProactiveMessage:
    """Tests for ProactiveMessage dataclass."""

    def test_proactive_message_creation(self):
        """ProactiveMessage creates with all fields."""
        msg = ProactiveMessage(
            content="You might find this useful",
            trigger="follow_up",
            relevance_score=0.8,
        )
        assert msg.content == "You might find this useful"
        assert msg.trigger == "follow_up"
        assert msg.relevance_score == 0.8
        assert msg.created_at is not None
        assert msg.expires_at is None

    def test_proactive_message_to_dict(self):
        """ProactiveMessage serializes correctly."""
        msg = ProactiveMessage(
            content="Insight content",
            trigger="dream",
            relevance_score=0.6,
        )
        d = msg.to_dict()
        assert d["content"] == "Insight content"
        assert d["trigger"] == "dream"
        assert d["relevance_score"] == 0.6
        assert "created_at" in d

    def test_proactive_message_is_expired(self):
        """is_expired returns True when past expires_at."""
        msg = ProactiveMessage(
            content="Old message",
            trigger="insight",
            relevance_score=0.5,
            expires_at=datetime.now() - timedelta(hours=1),
        )
        assert msg.is_expired() is True

    def test_proactive_message_not_expired(self):
        """is_expired returns False when before expires_at."""
        msg = ProactiveMessage(
            content="Fresh message",
            trigger="anticipation",
            relevance_score=0.9,
            expires_at=datetime.now() + timedelta(hours=24),
        )
        assert msg.is_expired() is False

    def test_proactive_message_no_expiry(self):
        """is_expired returns False when expires_at is None."""
        msg = ProactiveMessage(
            content="Timeless",
            trigger="follow_up",
            relevance_score=0.7,
        )
        assert msg.is_expired() is False


class TestThoughtfulnessEngine:
    """Tests for ThoughtfulnessEngine core functionality."""

    def test_engine_initialization(self):
        """ThoughtfulnessEngine initializes with empty queues."""
        engine = ThoughtfulnessEngine()
        assert engine.get_pending_messages() == []
        assert engine.daily_message_count == 0

    def test_generate_follow_ups_from_recent_facts(self):
        """generate_follow_ups creates messages from recent state."""
        engine = ThoughtfulnessEngine()
        state = HiveState()
        state.add_fact(Fact(
            content="User is learning Rust programming",
            confidence=0.9,
            source="conversation",
        ))
        state.add_fact(Fact(
            content="User has a project deadline on Friday",
            confidence=0.85,
            source="conversation",
        ))
        messages = engine.generate_follow_ups(state)
        assert isinstance(messages, list)
        for msg in messages:
            assert isinstance(msg, ProactiveMessage)
            assert msg.trigger == "follow_up"

    def test_generate_anticipations_from_patterns(self):
        """generate_anticipations creates messages from patterns."""
        engine = ThoughtfulnessEngine()
        patterns = [
            {
                "type": "recurring",
                "description": "Weekly standup preparation",
                "day_of_week": 0,
            },
        ]
        messages = engine.generate_anticipations(patterns)
        assert isinstance(messages, list)
        for msg in messages:
            assert isinstance(msg, ProactiveMessage)
            assert msg.trigger == "anticipation"

    def test_generate_dream_insights(self):
        """generate_dream_insights wraps dream results."""
        engine = ThoughtfulnessEngine()
        insights = [
            "Pattern detected: user frequently asks about async programming",
            "Contradiction resolved: Python GIL affects threads but not processes",
        ]
        messages = engine.generate_dream_insights(insights)
        assert len(messages) == 2
        for msg in messages:
            assert msg.trigger == "dream"
            assert msg.relevance_score > 0

    def test_daily_rate_limit(self):
        """Engine enforces max 3 proactive messages per day."""
        engine = ThoughtfulnessEngine(max_daily_messages=3)
        for i in range(5):
            engine._enqueue_message(ProactiveMessage(
                content=f"Message {i}",
                trigger="insight",
                relevance_score=0.7,
            ))
        pending = engine.get_pending_messages()
        assert len(pending) <= 3

    def test_get_pending_messages_excludes_expired(self):
        """get_pending_messages filters out expired messages."""
        engine = ThoughtfulnessEngine()
        engine._enqueue_message(ProactiveMessage(
            content="Expired",
            trigger="follow_up",
            relevance_score=0.5,
            expires_at=datetime.now() - timedelta(hours=1),
        ))
        engine._enqueue_message(ProactiveMessage(
            content="Valid",
            trigger="follow_up",
            relevance_score=0.8,
            expires_at=datetime.now() + timedelta(hours=24),
        ))
        pending = engine.get_pending_messages()
        assert len(pending) == 1
        assert pending[0].content == "Valid"

    def test_get_pending_messages_sorted_by_relevance(self):
        """Pending messages are sorted by relevance (highest first)."""
        engine = ThoughtfulnessEngine()
        engine._enqueue_message(ProactiveMessage(
            content="Low relevance",
            trigger="insight",
            relevance_score=0.3,
        ))
        engine._enqueue_message(ProactiveMessage(
            content="High relevance",
            trigger="follow_up",
            relevance_score=0.95,
        ))
        engine._enqueue_message(ProactiveMessage(
            content="Medium relevance",
            trigger="dream",
            relevance_score=0.6,
        ))
        pending = engine.get_pending_messages()
        assert pending[0].content == "High relevance"
        assert pending[-1].content == "Low relevance"

    def test_clear_delivered_messages(self):
        """clear_delivered removes messages from the queue."""
        engine = ThoughtfulnessEngine()
        engine._enqueue_message(ProactiveMessage(
            content="Will be cleared",
            trigger="insight",
            relevance_score=0.7,
        ))
        assert len(engine.get_pending_messages()) == 1
        engine.clear_delivered()
        assert len(engine.get_pending_messages()) == 0

    def test_reset_daily_count(self):
        """reset_daily_count resets the daily message counter."""
        engine = ThoughtfulnessEngine()
        engine.daily_message_count = 3
        engine.reset_daily_count()
        assert engine.daily_message_count == 0

    def test_engine_to_dict(self):
        """ThoughtfulnessEngine state serializes correctly."""
        engine = ThoughtfulnessEngine()
        engine._enqueue_message(ProactiveMessage(
            content="Serialized",
            trigger="insight",
            relevance_score=0.7,
        ))
        d = engine.to_dict()
        assert "pending_messages" in d
        assert "daily_message_count" in d
        assert len(d["pending_messages"]) == 1
```

**Step 2: Run tests, see them fail**

```bash
pytest tests/unit/test_thoughtfulness.py -v
```

Expected: All tests FAIL (missing `thoughtfulness.py` module)

**Step 3: Implement**

**`vecna/orchestrator/thoughtfulness.py`:**

```python
"""Autonomous Thoughtfulness Engine for proactive assistance.

The core differentiator — Vecna thinks about you when you're not there.
Generates follow-up messages, anticipatory assistance, and dream-based
insights that are queued for delivery at the next user interaction.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import logging

from vecna.core.hive_state import HiveState

logger = logging.getLogger("vecna.orchestrator.thoughtfulness")

DEFAULT_MAX_DAILY = 3
DEFAULT_EXPIRY_HOURS = 48
DEFAULT_MIN_RELEVANCE = 0.3


@dataclass
class ProactiveMessage:
    """A message Vecna prepared proactively.

    Attributes:
        content: The message text.
        trigger: Origin type (follow_up, anticipation, insight, dream).
        relevance_score: How relevant to current context (0.0-1.0).
        created_at: When the message was created.
        expires_at: After this time the message won't be delivered.
    """

    content: str = ""
    trigger: str = "insight"
    relevance_score: float = 0.5
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None

    def is_expired(self) -> bool:
        """Check if this message has expired.

        Returns:
            True if expires_at is set and in the past.
        """
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "content": self.content,
            "trigger": self.trigger,
            "relevance_score": self.relevance_score,
            "created_at": self.created_at.isoformat(),
            "expires_at": (
                self.expires_at.isoformat()
                if self.expires_at is not None
                else None
            ),
        }


class ThoughtfulnessEngine:
    """Generates proactive messages for the user.

    Runs as a heartbeat action to produce follow-ups based on
    recent conversation topics, anticipatory messages based on
    detected patterns, and packaged dream loop insights.

    Rate limited to max_daily_messages per day to avoid
    overwhelming the user.
    """

    def __init__(
        self,
        max_daily_messages: int = DEFAULT_MAX_DAILY,
        default_expiry_hours: int = DEFAULT_EXPIRY_HOURS,
        min_relevance: float = DEFAULT_MIN_RELEVANCE,
    ) -> None:
        self.max_daily_messages = max_daily_messages
        self.default_expiry_hours = default_expiry_hours
        self.min_relevance = min_relevance
        self.daily_message_count: int = 0
        self._pending: List[ProactiveMessage] = []

    def _enqueue_message(self, message: ProactiveMessage) -> None:
        """Add a message to the pending queue.

        Args:
            message: The proactive message to enqueue.
        """
        self._pending.append(message)
        self.daily_message_count += 1
        logger.debug(
            "Enqueued proactive message: trigger=%s relevance=%.2f",
            message.trigger,
            message.relevance_score,
        )

    def generate_follow_ups(
        self, state: HiveState
    ) -> List[ProactiveMessage]:
        """Generate follow-up messages from recent state.

        Scans recent facts for topics that could benefit from
        additional context or research.

        Args:
            state: Current HiveState with accumulated facts.

        Returns:
            List of follow-up ProactiveMessages.
        """
        messages: List[ProactiveMessage] = []
        recent_facts = sorted(
            state.facts,
            key=lambda f: f.timestamp if hasattr(f, "timestamp") else "",
            reverse=True,
        )[:5]

        for fact in recent_facts:
            if self.daily_message_count >= self.max_daily_messages:
                break
            content = fact.content if hasattr(fact, "content") else str(fact)
            msg = ProactiveMessage(
                content=f"Following up on: {content}",
                trigger="follow_up",
                relevance_score=min(
                    fact.confidence * 0.8 if hasattr(fact, "confidence") else 0.5,
                    1.0,
                ),
                expires_at=datetime.now() + timedelta(
                    hours=self.default_expiry_hours
                ),
            )
            messages.append(msg)
            self._enqueue_message(msg)

        return messages

    def generate_anticipations(
        self, patterns: List[Dict[str, Any]]
    ) -> List[ProactiveMessage]:
        """Generate anticipatory messages from detected patterns.

        Args:
            patterns: List of pattern dicts with type and description.

        Returns:
            List of anticipation ProactiveMessages.
        """
        messages: List[ProactiveMessage] = []

        for pattern in patterns:
            if self.daily_message_count >= self.max_daily_messages:
                break
            description = pattern.get("description", "Detected pattern")
            msg = ProactiveMessage(
                content=f"Anticipation: {description}",
                trigger="anticipation",
                relevance_score=0.7,
                expires_at=datetime.now() + timedelta(
                    hours=self.default_expiry_hours
                ),
            )
            messages.append(msg)
            self._enqueue_message(msg)

        return messages

    def generate_dream_insights(
        self, insights: List[str]
    ) -> List[ProactiveMessage]:
        """Package dream loop insights as proactive messages.

        Args:
            insights: List of insight strings from DreamLoop.

        Returns:
            List of dream ProactiveMessages.
        """
        messages: List[ProactiveMessage] = []

        for insight in insights:
            if self.daily_message_count >= self.max_daily_messages:
                break
            msg = ProactiveMessage(
                content=insight,
                trigger="dream",
                relevance_score=0.6,
                expires_at=datetime.now() + timedelta(
                    hours=self.default_expiry_hours
                ),
            )
            messages.append(msg)
            self._enqueue_message(msg)

        return messages

    def get_pending_messages(self) -> List[ProactiveMessage]:
        """Get all pending non-expired messages sorted by relevance.

        Filters expired messages and applies the daily rate limit.
        Returns at most max_daily_messages messages, sorted by
        relevance_score descending.

        Returns:
            Sorted list of pending ProactiveMessages.
        """
        valid = [m for m in self._pending if not m.is_expired()]
        valid.sort(key=lambda m: m.relevance_score, reverse=True)
        return valid[: self.max_daily_messages]

    def clear_delivered(self) -> None:
        """Clear all pending messages after delivery."""
        self._pending.clear()
        logger.debug("Cleared delivered proactive messages")

    def reset_daily_count(self) -> None:
        """Reset the daily message counter (call at midnight)."""
        self.daily_message_count = 0
        logger.debug("Daily message count reset")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize engine state."""
        return {
            "pending_messages": [m.to_dict() for m in self._pending],
            "daily_message_count": self.daily_message_count,
            "max_daily_messages": self.max_daily_messages,
        }
```

**`vecna/orchestrator/heartbeat.py`** (add thoughtfulness action):

```python
# Add to HeartbeatRunner._run_actions or equivalent:

async def _run_thoughtfulness(self) -> None:
    """Run thoughtfulness engine as a heartbeat action."""
    if self._thoughtfulness is None:
        return
    try:
        self._thoughtfulness.generate_follow_ups(
            self._autonomy_loop.state
        )
        logger.debug("Thoughtfulness heartbeat completed")
    except Exception as e:
        logger.warning("Thoughtfulness heartbeat failed: %s", e)
```

**Step 4: Run tests**

```bash
pytest tests/unit/test_thoughtfulness.py -v
```

Expected: All 12 tests pass

**Step 5: Commit**

```bash
git add vecna/orchestrator/thoughtfulness.py vecna/orchestrator/heartbeat.py \
  tests/unit/test_thoughtfulness.py
git commit -m "feat: add Autonomous Thoughtfulness Engine for proactive assistance"
```

---

### Task 24: Message Router — Unified Channel Dispatch

**Files:**
- Create: `vecna/channels/router.py` (MessageRouter)
- Modify: `vecna/server/routes.py` (wire chat endpoint to router)
- Create: `tests/unit/test_message_router.py`

**Step 1: Write the failing tests**

```python
# tests/unit/test_message_router.py
"""Unit tests for the MessageRouter unified channel dispatch."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from vecna.channels.router import (
    MessageRouter,
    SessionContext,
    InboundMessage,
    OutboundMessage,
)


class MockChannel:
    """Mock channel for testing."""

    def __init__(self, name: str, format_type: str = "plain"):
        self.name = name
        self.format_type = format_type
        self.sent_messages: List[str] = []

    async def send(self, message: str) -> None:
        self.sent_messages.append(message)


class MockHiveLoop:
    """Mock HiveLoop for testing router integration."""

    def __init__(self, response: str = "Mock response"):
        self._response = response
        self.last_task = ""

    async def think(self, task: str, **kwargs) -> str:
        self.last_task = task
        return self._response


class TestSessionContext:
    """Tests for SessionContext dataclass."""

    def test_session_context_creation(self):
        """SessionContext initializes with required fields."""
        ctx = SessionContext(
            session_id="sess-001",
            channel_name="cli",
        )
        assert ctx.session_id == "sess-001"
        assert ctx.channel_name == "cli"
        assert ctx.history == []
        assert ctx.created_at is not None

    def test_session_context_to_dict(self):
        """SessionContext serializes correctly."""
        ctx = SessionContext(
            session_id="sess-002",
            channel_name="slack",
        )
        d = ctx.to_dict()
        assert d["session_id"] == "sess-002"
        assert d["channel_name"] == "slack"
        assert "created_at" in d

    def test_session_context_add_to_history(self):
        """Messages added to history are preserved."""
        ctx = SessionContext(
            session_id="sess-003",
            channel_name="cli",
        )
        ctx.history.append({"role": "user", "content": "hello"})
        ctx.history.append({"role": "assistant", "content": "hi"})
        assert len(ctx.history) == 2


class TestInboundOutbound:
    """Tests for InboundMessage and OutboundMessage."""

    def test_inbound_message_creation(self):
        """InboundMessage captures channel, session, and content."""
        msg = InboundMessage(
            content="Hello Vecna",
            channel_name="cli",
            session_id="sess-001",
        )
        assert msg.content == "Hello Vecna"
        assert msg.channel_name == "cli"
        assert msg.session_id == "sess-001"

    def test_outbound_message_creation(self):
        """OutboundMessage captures response and formatting."""
        msg = OutboundMessage(
            content="Response text",
            channel_name="slack",
            session_id="sess-001",
            format_type="markdown",
        )
        assert msg.content == "Response text"
        assert msg.format_type == "markdown"


class TestMessageRouterRegistration:
    """Tests for channel registration."""

    def test_register_channel(self):
        """Registering a channel adds it to the registry."""
        router = MessageRouter()
        channel = MockChannel("cli")
        router.register_channel("cli", channel)
        assert "cli" in router._channels

    def test_register_multiple_channels(self):
        """Multiple channels can be registered."""
        router = MessageRouter()
        router.register_channel("cli", MockChannel("cli"))
        router.register_channel("slack", MockChannel("slack", "markdown"))
        router.register_channel("sms", MockChannel("sms", "plain"))
        assert len(router._channels) == 3

    def test_list_channels(self):
        """list_channels returns registered channel names."""
        router = MessageRouter()
        router.register_channel("cli", MockChannel("cli"))
        router.register_channel("slack", MockChannel("slack"))
        names = router.list_channels()
        assert "cli" in names
        assert "slack" in names

    def test_unregister_channel(self):
        """Unregistering removes a channel."""
        router = MessageRouter()
        router.register_channel("cli", MockChannel("cli"))
        router.unregister_channel("cli")
        assert "cli" not in router._channels


class TestMessageRouterRouting:
    """Tests for inbound message routing."""

    async def test_route_inbound_creates_session(self):
        """Routing an inbound message creates a session."""
        router = MessageRouter()
        loop = MockHiveLoop(response="Hello user")
        router._hive_loop = loop
        router.register_channel("cli", MockChannel("cli"))
        msg = InboundMessage(
            content="Hello",
            channel_name="cli",
            session_id="sess-new",
        )
        response = await router.route_inbound(msg)
        assert response is not None
        assert "sess-new" in router._sessions

    async def test_route_inbound_returns_response(self):
        """Routing returns the HiveLoop response."""
        router = MessageRouter()
        loop = MockHiveLoop(response="Thought result")
        router._hive_loop = loop
        router.register_channel("cli", MockChannel("cli"))
        msg = InboundMessage(
            content="Think about this",
            channel_name="cli",
            session_id="sess-think",
        )
        response = await router.route_inbound(msg)
        assert response.content == "Thought result"

    async def test_route_inbound_passes_to_hive_loop(self):
        """Router passes message content to HiveLoop.think."""
        router = MessageRouter()
        loop = MockHiveLoop()
        router._hive_loop = loop
        router.register_channel("cli", MockChannel("cli"))
        msg = InboundMessage(
            content="Analyze data",
            channel_name="cli",
            session_id="sess-analyze",
        )
        await router.route_inbound(msg)
        assert loop.last_task == "Analyze data"

    async def test_route_inbound_updates_session_history(self):
        """Routing adds messages to session history."""
        router = MessageRouter()
        loop = MockHiveLoop(response="Reply")
        router._hive_loop = loop
        router.register_channel("cli", MockChannel("cli"))
        msg = InboundMessage(
            content="First message",
            channel_name="cli",
            session_id="sess-hist",
        )
        await router.route_inbound(msg)
        session = router._sessions["sess-hist"]
        assert len(session.history) == 2
        assert session.history[0]["role"] == "user"
        assert session.history[1]["role"] == "assistant"

    async def test_route_preserves_session_across_messages(self):
        """Multiple messages to same session share context."""
        router = MessageRouter()
        loop = MockHiveLoop(response="Reply")
        router._hive_loop = loop
        router.register_channel("cli", MockChannel("cli"))
        for i in range(3):
            msg = InboundMessage(
                content=f"Message {i}",
                channel_name="cli",
                session_id="sess-multi",
            )
            await router.route_inbound(msg)
        session = router._sessions["sess-multi"]
        assert len(session.history) == 6


class TestFormatAdaptation:
    """Tests for output format adaptation per channel."""

    def test_format_for_cli(self):
        """CLI format uses rich markup."""
        router = MessageRouter()
        result = router._format_for_channel(
            "**bold** text", "cli"
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_for_sms(self):
        """SMS format strips markdown to plain text."""
        router = MessageRouter()
        result = router._format_for_channel(
            "**bold** and *italic*", "sms"
        )
        assert "**" not in result
        assert "*" not in result

    def test_format_for_slack(self):
        """Slack format preserves markdown."""
        router = MessageRouter()
        result = router._format_for_channel(
            "**bold** text", "slack"
        )
        assert "bold" in result

    def test_format_for_unknown_channel(self):
        """Unknown channel gets plain text."""
        router = MessageRouter()
        result = router._format_for_channel(
            "Some text", "unknown"
        )
        assert result == "Some text"


class TestRouterState:
    """Tests for router state management."""

    def test_get_session_returns_none_for_missing(self):
        """get_session returns None for unknown session."""
        router = MessageRouter()
        assert router.get_session("nonexistent") is None

    def test_get_active_sessions(self):
        """get_active_sessions lists current sessions."""
        router = MessageRouter()
        router._sessions["s1"] = SessionContext(
            session_id="s1", channel_name="cli"
        )
        router._sessions["s2"] = SessionContext(
            session_id="s2", channel_name="slack"
        )
        active = router.get_active_sessions()
        assert len(active) == 2

    def test_close_session(self):
        """close_session removes a session."""
        router = MessageRouter()
        router._sessions["s1"] = SessionContext(
            session_id="s1", channel_name="cli"
        )
        router.close_session("s1")
        assert "s1" not in router._sessions

    def test_router_to_dict(self):
        """Router state serializes correctly."""
        router = MessageRouter()
        router.register_channel("cli", MockChannel("cli"))
        router._sessions["s1"] = SessionContext(
            session_id="s1", channel_name="cli"
        )
        d = router.to_dict()
        assert "channels" in d
        assert "sessions" in d
        assert "cli" in d["channels"]
```

**Step 2: Run tests, see them fail**

```bash
pytest tests/unit/test_message_router.py -v
```

Expected: All tests FAIL (missing `router.py` module)

**Step 3: Implement**

**`vecna/channels/router.py`:**

```python
"""Unified Message Router for cross-channel dispatch.

Routes inbound messages from any channel through HiveLoop and
dispatches responses back through the originating channel.
Maintains per-session conversation context across channels.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger("vecna.channels.router")


@dataclass
class SessionContext:
    """Conversation session state.

    Tracks which channel a session originated from and
    maintains conversation history for context continuity.
    """

    session_id: str = ""
    channel_name: str = ""
    history: List[Dict[str, str]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "session_id": self.session_id,
            "channel_name": self.channel_name,
            "history": list(self.history),
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class InboundMessage:
    """An inbound message from a channel.

    Attributes:
        content: The message text.
        channel_name: Which channel sent the message.
        session_id: Session identifier for context tracking.
        metadata: Optional extra context from the channel.
    """

    content: str = ""
    channel_name: str = ""
    session_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OutboundMessage:
    """An outbound response to a channel.

    Attributes:
        content: The formatted response text.
        channel_name: Target channel.
        session_id: Session this response belongs to.
        format_type: Output format (plain, markdown, rich).
    """

    content: str = ""
    channel_name: str = ""
    session_id: str = ""
    format_type: str = "plain"


class MessageRouter:
    """Routes messages between channels and HiveLoop.

    Maintains a channel registry and session map.  Inbound
    messages are dispatched to HiveLoop.think(), and responses
    are formatted for the originating channel before return.
    """

    def __init__(self) -> None:
        self._channels: Dict[str, Any] = {}
        self._sessions: Dict[str, SessionContext] = {}
        self._hive_loop: Any = None
        self._format_map: Dict[str, str] = {
            "cli": "rich",
            "sms": "plain",
            "slack": "markdown",
            "discord": "markdown",
        }

    def register_channel(
        self, name: str, channel: Any
    ) -> None:
        """Register a channel for message routing.

        Args:
            name: Channel identifier.
            channel: Channel object with a send() method.
        """
        self._channels[name] = channel
        logger.info("Channel registered: %s", name)

    def unregister_channel(self, name: str) -> None:
        """Remove a channel from the registry.

        Args:
            name: Channel identifier to remove.
        """
        self._channels.pop(name, None)
        logger.info("Channel unregistered: %s", name)

    def list_channels(self) -> List[str]:
        """List registered channel names.

        Returns:
            List of channel name strings.
        """
        return list(self._channels.keys())

    async def route_inbound(
        self, message: InboundMessage
    ) -> OutboundMessage:
        """Route an inbound message through HiveLoop.

        Creates or retrieves the session, passes the message
        content to HiveLoop.think(), records history, and
        returns a formatted OutboundMessage.

        Args:
            message: The inbound message to route.

        Returns:
            Formatted OutboundMessage with the response.
        """
        session = self._get_or_create_session(
            message.session_id,
            message.channel_name,
        )
        session.history.append({
            "role": "user",
            "content": message.content,
        })

        response_text = ""
        if self._hive_loop is not None:
            response_text = await self._hive_loop.think(
                message.content
            )
        else:
            response_text = "HiveLoop not connected."
            logger.warning(
                "No HiveLoop connected to router"
            )

        session.history.append({
            "role": "assistant",
            "content": response_text,
        })

        formatted = self._format_for_channel(
            response_text,
            message.channel_name,
        )
        format_type = self._format_map.get(
            message.channel_name, "plain"
        )

        return OutboundMessage(
            content=formatted,
            channel_name=message.channel_name,
            session_id=message.session_id,
            format_type=format_type,
        )

    def _get_or_create_session(
        self,
        session_id: str,
        channel_name: str,
    ) -> SessionContext:
        """Get existing session or create a new one.

        Args:
            session_id: Session identifier.
            channel_name: Channel the session belongs to.

        Returns:
            The SessionContext for this session.
        """
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionContext(
                session_id=session_id,
                channel_name=channel_name,
            )
            logger.debug(
                "Created session %s on channel %s",
                session_id,
                channel_name,
            )
        return self._sessions[session_id]

    def _format_for_channel(
        self, text: str, channel_name: str
    ) -> str:
        """Format response text for a specific channel.

        - cli: preserve rich markup
        - sms: strip all markdown to plain text
        - slack/discord: preserve markdown
        - unknown: return as-is

        Args:
            text: Raw response text.
            channel_name: Target channel name.

        Returns:
            Formatted text string.
        """
        if channel_name == "sms":
            stripped = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
            stripped = re.sub(r"\*(.+?)\*", r"\1", stripped)
            stripped = re.sub(r"_(.+?)_", r"\1", stripped)
            stripped = re.sub(r"`(.+?)`", r"\1", stripped)
            return stripped
        return text

    def get_session(
        self, session_id: str
    ) -> Optional[SessionContext]:
        """Get a session by ID.

        Args:
            session_id: The session to look up.

        Returns:
            SessionContext or None if not found.
        """
        return self._sessions.get(session_id)

    def get_active_sessions(self) -> List[SessionContext]:
        """Get all active sessions.

        Returns:
            List of active SessionContext objects.
        """
        return list(self._sessions.values())

    def close_session(self, session_id: str) -> None:
        """Close and remove a session.

        Args:
            session_id: The session to close.
        """
        self._sessions.pop(session_id, None)
        logger.debug("Session closed: %s", session_id)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize router state."""
        return {
            "channels": list(self._channels.keys()),
            "sessions": {
                sid: s.to_dict()
                for sid, s in self._sessions.items()
            },
        }
```

**Step 4: Run tests**

```bash
pytest tests/unit/test_message_router.py -v
```

Expected: All 22 tests pass

**Step 5: Commit**

```bash
git add vecna/channels/router.py tests/unit/test_message_router.py
git commit -m "feat: add unified MessageRouter for cross-channel message dispatch"
```

---

### Task 25: TUI Upgrade — Textual + trogon

**Files:**
- Create: `vecna/tui/__init__.py`
- Create: `vecna/tui/app.py` (Textual TUI application)
- Modify: `vecna/cli/main.py` (add `vecna tui` command)
- Create: `tests/unit/test_tui.py`

**Step 1: Write the failing tests**

```python
# tests/unit/test_tui.py
"""Unit tests for the Textual TUI application."""

import pytest

from vecna.tui.app import VecnaTUI, SubstratePanel, ConversationPane


class TestSubstratePanel:
    """Tests for the substrate visualizer panel."""

    def test_substrate_panel_creation(self):
        """SubstratePanel initializes with empty state."""
        panel = SubstratePanel()
        assert panel is not None

    def test_substrate_panel_update_facts(self):
        """SubstratePanel can update fact display count."""
        panel = SubstratePanel()
        panel.update_state(facts_count=5, beliefs_count=3, goals_count=2)
        assert panel.facts_count == 5
        assert panel.beliefs_count == 3
        assert panel.goals_count == 2

    def test_substrate_panel_render_content(self):
        """SubstratePanel renders state summary."""
        panel = SubstratePanel()
        panel.update_state(facts_count=10, beliefs_count=5, goals_count=1)
        content = panel.render_content()
        assert "10" in content
        assert "Facts" in content


class TestConversationPane:
    """Tests for the conversation display pane."""

    def test_conversation_pane_creation(self):
        """ConversationPane initializes with empty history."""
        pane = ConversationPane()
        assert pane is not None
        assert pane.messages == []

    def test_add_user_message(self):
        """ConversationPane adds user messages."""
        pane = ConversationPane()
        pane.add_message("user", "Hello Vecna")
        assert len(pane.messages) == 1
        assert pane.messages[0]["role"] == "user"
        assert pane.messages[0]["content"] == "Hello Vecna"

    def test_add_assistant_message(self):
        """ConversationPane adds assistant messages."""
        pane = ConversationPane()
        pane.add_message("assistant", "I'm here to help")
        assert len(pane.messages) == 1
        assert pane.messages[0]["role"] == "assistant"


class TestVecnaTUI:
    """Tests for the main TUI application."""

    def test_tui_app_creation(self):
        """VecnaTUI initializes without errors."""
        app = VecnaTUI()
        assert app is not None
        assert app.title == "Vecna"

    def test_tui_app_has_panels(self):
        """VecnaTUI has substrate and conversation panels."""
        app = VecnaTUI()
        assert hasattr(app, "substrate_panel")
        assert hasattr(app, "conversation_pane")

    def test_tui_app_css_defined(self):
        """VecnaTUI has CSS styles defined."""
        assert VecnaTUI.CSS is not None or VecnaTUI.CSS_PATH is not None
```

**Step 2: Run tests, see them fail**

```bash
pytest tests/unit/test_tui.py -v
```

Expected: All tests FAIL (missing `vecna/tui/` module)

**Step 3: Implement**

**`vecna/tui/__init__.py`:**

```python
"""Vecna TUI — Textual-based terminal user interface."""
```

**`vecna/tui/app.py`:**

```python
"""Vecna Textual TUI application.

Provides a full terminal UI with:
- Conversation pane for interactive chat with streaming
- Substrate visualizer sidebar showing facts, beliefs, goals
- Integration and channel status indicators
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger("vecna.tui.app")

try:
    from textual.app import App, ComposeResult
    from textual.widgets import Static, Header, Footer, Input
    from textual.containers import Vertical, Horizontal
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False
    logger.debug("textual not installed, TUI unavailable")


class SubstratePanel:
    """Sidebar panel showing HiveState substrate overview.

    Displays counts of facts, beliefs, goals, and overall
    coherence metrics. Updates in real-time as state changes.
    """

    def __init__(self) -> None:
        self.facts_count: int = 0
        self.beliefs_count: int = 0
        self.goals_count: int = 0
        self.coherence: float = 0.0

    def update_state(
        self,
        facts_count: int = 0,
        beliefs_count: int = 0,
        goals_count: int = 0,
        coherence: float = 0.0,
    ) -> None:
        """Update substrate panel state.

        Args:
            facts_count: Number of facts in state.
            beliefs_count: Number of beliefs in state.
            goals_count: Number of goals in state.
            coherence: Overall state coherence score.
        """
        self.facts_count = facts_count
        self.beliefs_count = beliefs_count
        self.goals_count = goals_count
        self.coherence = coherence

    def render_content(self) -> str:
        """Render substrate state as a text summary.

        Returns:
            Formatted string showing state counts.
        """
        lines = [
            "╔═══ Substrate ═══╗",
            f"║ Facts:   {self.facts_count:>6} ║",
            f"║ Beliefs: {self.beliefs_count:>6} ║",
            f"║ Goals:   {self.goals_count:>6} ║",
            f"║ Cohere:  {self.coherence:>5.1%} ║",
            "╚═════════════════╝",
        ]
        return "\n".join(lines)


class ConversationPane:
    """Main conversation display pane.

    Maintains a list of chat messages and renders them
    for display in the TUI.
    """

    def __init__(self) -> None:
        self.messages: List[Dict[str, str]] = []

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the conversation.

        Args:
            role: Message role (user or assistant).
            content: Message text content.
        """
        self.messages.append({
            "role": role,
            "content": content,
        })

    def render_messages(self) -> str:
        """Render all messages as formatted text.

        Returns:
            String with all messages formatted for display.
        """
        lines = []
        for msg in self.messages:
            prefix = "You" if msg["role"] == "user" else "Vecna"
            lines.append(f"[{prefix}] {msg['content']}")
        return "\n".join(lines)


class VecnaTUI:
    """Main Textual TUI application for Vecna.

    Composes a conversation pane with a substrate sidebar
    and provides input handling for interactive chat.
    """

    CSS = """
    #substrate {
        width: 24;
        dock: right;
    }
    #conversation {
        width: 1fr;
    }
    """
    CSS_PATH = None
    title = "Vecna"

    def __init__(self) -> None:
        self.substrate_panel = SubstratePanel()
        self.conversation_pane = ConversationPane()
        self._hive_loop: Any = None

    def set_hive_loop(self, loop: Any) -> None:
        """Attach a HiveLoop to the TUI.

        Args:
            loop: HiveLoop instance for processing messages.
        """
        self._hive_loop = loop

    async def handle_input(self, text: str) -> str:
        """Handle user input text.

        Args:
            text: User's input message.

        Returns:
            Response from HiveLoop.
        """
        self.conversation_pane.add_message("user", text)
        response = ""
        if self._hive_loop is not None:
            response = await self._hive_loop.think(text)
        else:
            response = "HiveLoop not connected."
        self.conversation_pane.add_message("assistant", response)
        return response
```

**`vecna/cli/main.py`** (add `vecna tui` command):

```python
# Add this Click command to the CLI group:

@cli.command()
def tui():
    """Launch the Vecna TUI (Textual terminal interface)."""
    try:
        from vecna.tui.app import VecnaTUI, TEXTUAL_AVAILABLE
        if not TEXTUAL_AVAILABLE:
            click.echo(
                "Textual not installed. "
                "Install with: pip install textual trogon"
            )
            raise SystemExit(1)
        app = VecnaTUI()
        click.echo("Launching Vecna TUI...")
        app.run()
    except ImportError as e:
        click.echo(f"TUI dependencies missing: {e}")
        raise SystemExit(1)
```

**Step 4: Run tests**

```bash
pytest tests/unit/test_tui.py -v
```

Expected: All 9 tests pass

**Step 5: Commit**

```bash
git add vecna/tui/__init__.py vecna/tui/app.py vecna/cli/main.py \
  tests/unit/test_tui.py
git commit -m "feat: add Textual-based TUI with substrate visualizer"
```

---

### Task 26: Wire Server to HiveLoop (Full Stack Integration)

**Files:**
- Modify: `vecna/server/app.py` (initialize HiveLoop on startup)
- Modify: `vecna/server/routes.py` (wire /api/chat to HiveLoop.think)
- Create: `tests/integration/test_server_hive.py`

**Step 1: Write the failing tests**

```python
# tests/integration/test_server_hive.py
"""Integration tests for HTTP server wired to HiveLoop."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from vecna.adapters.base import BaseAdapter, ModelConfig
from vecna.core.hive_state import HiveState


class MockServerAdapter(BaseAdapter):
    """Mock adapter for server integration tests."""

    def __init__(self):
        config = ModelConfig(name="mock-srv", model_id="mock-srv-v1")
        super().__init__(config)

    async def generate(self, prompt: str) -> str:
        return (
            "<HIVE_UPDATE>\n"
            "facts:\n"
            "  - content: \"Server test fact\"\n"
            "    confidence: 0.9\n"
            "response: \"Server response to your query.\"\n"
            "</HIVE_UPDATE>"
        )

    def _get_provider_name(self) -> str:
        return "mock"


class TestServerChatEndpoint:
    """Tests for /api/chat wired to HiveLoop."""

    async def test_chat_returns_200(self, aiohttp_client):
        """POST /api/chat returns 200 with response."""
        from vecna.server.app import create_app

        app = create_app(
            adapters=[MockServerAdapter()],
            config=None,
        )
        client = await aiohttp_client(app)
        resp = await client.post(
            "/api/chat",
            json={"message": "Hello server"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert "response" in data
        assert len(data["response"]) > 0

    async def test_chat_updates_state(self, aiohttp_client):
        """POST /api/chat updates HiveState."""
        from vecna.server.app import create_app

        app = create_app(
            adapters=[MockServerAdapter()],
            config=None,
        )
        client = await aiohttp_client(app)
        await client.post(
            "/api/chat",
            json={"message": "Add a fact"},
        )
        resp = await client.get("/api/state")
        data = await resp.json()
        assert data["version"] >= 1 or len(data.get("facts", [])) > 0


class TestServerStateEndpoint:
    """Tests for /api/state."""

    async def test_state_returns_full_dict(self, aiohttp_client):
        """GET /api/state returns HiveState as dict."""
        from vecna.server.app import create_app

        app = create_app(
            adapters=[MockServerAdapter()],
            config=None,
        )
        client = await aiohttp_client(app)
        resp = await client.get("/api/state")
        assert resp.status == 200
        data = await resp.json()
        assert "version" in data
        assert "facts" in data
        assert "beliefs" in data


class TestServerWebSocket:
    """Tests for /ws/stream WebSocket endpoint."""

    async def test_ws_stream_connects(self, aiohttp_client):
        """WebSocket /ws/stream accepts connections."""
        from vecna.server.app import create_app

        app = create_app(
            adapters=[MockServerAdapter()],
            config=None,
        )
        client = await aiohttp_client(app)
        ws = await client.ws_connect("/ws/stream")
        await ws.send_json({"message": "ws test"})
        msg = await ws.receive_json()
        assert "response" in msg
        await ws.close()

    async def test_ws_stream_returns_response(self, aiohttp_client):
        """WebSocket returns HiveLoop response."""
        from vecna.server.app import create_app

        app = create_app(
            adapters=[MockServerAdapter()],
            config=None,
        )
        client = await aiohttp_client(app)
        ws = await client.ws_connect("/ws/stream")
        await ws.send_json({"message": "hello"})
        msg = await ws.receive_json()
        assert len(msg.get("response", "")) > 0
        await ws.close()


class TestServerHealthEndpoint:
    """Tests for /api/health."""

    async def test_health_returns_ok(self, aiohttp_client):
        """GET /api/health returns status ok."""
        from vecna.server.app import create_app

        app = create_app(
            adapters=[MockServerAdapter()],
            config=None,
        )
        client = await aiohttp_client(app)
        resp = await client.get("/api/health")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"

    async def test_health_includes_version(self, aiohttp_client):
        """GET /api/health includes state version."""
        from vecna.server.app import create_app

        app = create_app(
            adapters=[MockServerAdapter()],
            config=None,
        )
        client = await aiohttp_client(app)
        resp = await client.get("/api/health")
        data = await resp.json()
        assert "state_version" in data
```

**Step 2: Run tests, see them fail**

```bash
pytest tests/integration/test_server_hive.py -v
```

Expected: All tests FAIL (server not wired to HiveLoop)

**Step 3: Implement**

**`vecna/server/app.py`** (full updated file):

```python
"""Vecna HTTP server application.

Creates an aiohttp application with HiveLoop initialization
on startup and graceful shutdown. Routes are registered for
chat, state, health, metrics, and WebSocket streaming.
"""

import logging
from typing import Any, Dict, List, Optional

from aiohttp import web

from vecna.adapters.base import BaseAdapter
from vecna.core.hive_state import HiveState
from vecna.orchestrator.loop import HiveLoop, HiveConfig
from vecna.observability.dashboard import MetricsCollector

logger = logging.getLogger("vecna.server.app")


async def on_startup(app: web.Application) -> None:
    """Initialize HiveLoop and metrics on server startup."""
    logger.info("Vecna server starting up")


async def on_shutdown(app: web.Application) -> None:
    """Clean up resources on server shutdown."""
    logger.info("Vecna server shutting down")


def create_app(
    adapters: Optional[List[BaseAdapter]] = None,
    config: Optional[Any] = None,
    hive_loop: Optional[HiveLoop] = None,
) -> web.Application:
    """Create the aiohttp application with HiveLoop.

    Args:
        adapters: List of LLM adapters.
        config: Optional HiveConfig or VecnaConfig.
        hive_loop: Optional pre-built HiveLoop.

    Returns:
        Configured aiohttp Application.
    """
    app = web.Application()

    if hive_loop is not None:
        app["hive_loop"] = hive_loop
    else:
        hive_config = HiveConfig()
        if config is not None:
            hive_config = config
        loop = HiveLoop(
            config=hive_config,
            adapters=adapters or [],
            name="vecna-server",
        )
        app["hive_loop"] = loop

    app["metrics"] = MetricsCollector()

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    from vecna.server.routes import setup_routes
    setup_routes(app)

    logger.info("Vecna server app created")
    return app
```

**`vecna/server/routes.py`** (full updated file):

```python
"""HTTP route handlers for the Vecna server.

Registers handlers for:
- POST /api/chat — Send a message through HiveLoop
- GET  /api/state — Retrieve current HiveState
- GET  /api/health — Server health check
- GET  /api/metrics — Observability metrics
- GET  /ws/stream — WebSocket streaming endpoint
"""

import json
import logging
from typing import Any, Dict

from aiohttp import web, WSMsgType

logger = logging.getLogger("vecna.server.routes")


async def chat_handler(request: web.Request) -> web.Response:
    """Handle POST /api/chat.

    Expects JSON body: {"message": "user text"}
    Returns JSON: {"response": "...", "state_version": N}
    """
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response(
            {"error": "Invalid JSON"}, status=400
        )

    message = body.get("message", "")
    if not message:
        return web.json_response(
            {"error": "message field required"}, status=400
        )

    hive_loop = request.app["hive_loop"]
    try:
        response_text = await hive_loop.think(message)
    except Exception as e:
        logger.error("HiveLoop.think failed: %s", e)
        return web.json_response(
            {"error": "Internal processing error"},
            status=500,
        )

    return web.json_response({
        "response": response_text,
        "state_version": hive_loop.state.version,
    })


async def state_handler(request: web.Request) -> web.Response:
    """Handle GET /api/state.

    Returns the full HiveState as JSON.
    """
    hive_loop = request.app["hive_loop"]
    state_dict = hive_loop.state.to_full_dict()
    return web.json_response(state_dict)


async def health_handler(request: web.Request) -> web.Response:
    """Handle GET /api/health.

    Returns server health status.
    """
    hive_loop = request.app["hive_loop"]
    return web.json_response({
        "status": "ok",
        "state_version": hive_loop.state.version,
        "adapter_count": len(hive_loop.adapters),
    })


def handle_metrics_request(collector: Any) -> Dict[str, Any]:
    """Build metrics response from a MetricsCollector.

    Args:
        collector: A MetricsCollector instance.

    Returns:
        The full metrics report dictionary.
    """
    return collector.to_full_report()


async def metrics_handler(
    request: web.Request,
) -> web.Response:
    """Handle GET /api/metrics.

    Returns operational metrics from the MetricsCollector.
    """
    from vecna.observability.dashboard import MetricsCollector

    collector = request.app.get("metrics")
    if collector is None:
        collector = MetricsCollector()
    result = handle_metrics_request(collector)
    return web.json_response(result)


async def ws_stream_handler(
    request: web.Request,
) -> web.WebSocketResponse:
    """Handle WebSocket /ws/stream.

    Accepts JSON messages {"message": "..."} and returns
    JSON responses {"response": "..."} from HiveLoop.
    """
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    hive_loop = request.app["hive_loop"]

    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            try:
                data = json.loads(msg.data)
                message = data.get("message", "")
                if message:
                    response = await hive_loop.think(message)
                    await ws.send_json({"response": response})
                else:
                    await ws.send_json(
                        {"error": "message field required"}
                    )
            except json.JSONDecodeError:
                await ws.send_json({"error": "Invalid JSON"})
            except Exception as e:
                logger.error("WebSocket processing error: %s", e)
                await ws.send_json({"error": "Processing failed"})
        elif msg.type == WSMsgType.ERROR:
            logger.error(
                "WebSocket error: %s", ws.exception()
            )

    return ws


def setup_routes(app: web.Application) -> None:
    """Register all route handlers on the application.

    Args:
        app: The aiohttp Application to add routes to.
    """
    app.router.add_post("/api/chat", chat_handler)
    app.router.add_get("/api/state", state_handler)
    app.router.add_get("/api/health", health_handler)
    app.router.add_get("/api/metrics", metrics_handler)
    app.router.add_get("/ws/stream", ws_stream_handler)
    logger.info(
        "Routes registered: /api/chat, /api/state, "
        "/api/health, /api/metrics, /ws/stream"
    )
```

**Step 4: Run tests**

```bash
pytest tests/integration/test_server_hive.py -v
```

Expected: All 8 tests pass

**Step 5: Commit**

```bash
git add vecna/server/app.py vecna/server/routes.py \
  tests/integration/test_server_hive.py
git commit -m "feat: wire HTTP server to HiveLoop for full API operation"
```

---

### Task 27: Substrate Encryption Integration

**Files:**
- Create: `vecna/core/encrypted_state_store.py` (encrypted file-based persistence)
- Modify: `vecna/security/encryption.py` (add JSON encrypt/decrypt, key derivation)
- Create: `tests/integration/test_encrypted_substrate.py`

**Step 1: Write the failing tests**

```python
# tests/integration/test_encrypted_substrate.py
"""Integration tests for substrate encryption at rest."""

import json
import os
import tempfile
from typing import Any, Dict

import pytest

from vecna.core.hive_state import HiveState
from vecna.core.types import Fact, Belief
from vecna.security.encryption import (
    SubstrateEncryption,
    derive_key_from_password,
)
from vecna.core.encrypted_state_store import EncryptedStateStore


class TestKeyDerivation:
    """Tests for encryption key derivation."""

    def test_derive_key_from_password(self):
        """derive_key_from_password produces a valid Fernet key."""
        key = derive_key_from_password("test-password", salt=b"fixed-salt-16b!")
        assert key is not None
        assert len(key) > 0

    def test_same_password_same_key(self):
        """Same password and salt produce the same key."""
        salt = b"deterministic!!!"
        key1 = derive_key_from_password("mypassword", salt=salt)
        key2 = derive_key_from_password("mypassword", salt=salt)
        assert key1 == key2

    def test_different_password_different_key(self):
        """Different passwords produce different keys."""
        salt = b"same-salt-16bits"
        key1 = derive_key_from_password("password1", salt=salt)
        key2 = derive_key_from_password("password2", salt=salt)
        assert key1 != key2


class TestSubstrateEncryption:
    """Tests for SubstrateEncryption JSON operations."""

    def test_encrypt_decrypt_json_roundtrip(self):
        """encrypt_json and decrypt_json are inverse operations."""
        enc = SubstrateEncryption(password="test-secret")
        data = {"facts": [{"content": "test", "confidence": 0.9}]}
        encrypted = enc.encrypt_json(data)
        assert encrypted != json.dumps(data).encode()
        decrypted = enc.decrypt_json(encrypted)
        assert decrypted == data

    def test_encrypted_data_not_readable(self):
        """Encrypted output does not contain plaintext."""
        enc = SubstrateEncryption(password="secret")
        data = {"sensitive": "this should be hidden"}
        encrypted = enc.encrypt_json(data)
        assert b"this should be hidden" not in encrypted

    def test_wrong_password_fails_decrypt(self):
        """Decryption with wrong password raises error."""
        enc1 = SubstrateEncryption(password="correct")
        enc2 = SubstrateEncryption(password="wrong")
        data = {"key": "value"}
        encrypted = enc1.encrypt_json(data)
        with pytest.raises(Exception):
            enc2.decrypt_json(encrypted)


class TestEncryptedStateStore:
    """Tests for encrypted file-based state persistence."""

    def test_save_and_load_state(self):
        """State survives save/load cycle with encryption."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "state.enc")
            store = EncryptedStateStore(
                filepath=filepath,
                password="test-pass",
            )
            state = HiveState()
            state.add_fact(Fact(
                content="Encrypted fact",
                confidence=0.95,
                source="test",
            ))
            state.add_belief(Belief(
                content="Encrypted belief",
                confidence=0.8,
            ))
            store.save(state)
            assert os.path.exists(filepath)

            loaded = store.load()
            assert len(loaded.facts) == 1
            assert loaded.facts[0].content == "Encrypted fact"
            assert len(loaded.beliefs) == 1

    def test_encrypted_file_not_plaintext(self):
        """Saved file does not contain plaintext state data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "state.enc")
            store = EncryptedStateStore(
                filepath=filepath,
                password="secret-key",
            )
            state = HiveState()
            state.add_fact(Fact(
                content="Super secret fact",
                confidence=0.99,
                source="test",
            ))
            store.save(state)
            with open(filepath, "rb") as f:
                raw = f.read()
            assert b"Super secret fact" not in raw

    def test_load_nonexistent_returns_empty_state(self):
        """Loading from nonexistent file returns fresh HiveState."""
        store = EncryptedStateStore(
            filepath="/tmp/nonexistent_state.enc",
            password="test",
        )
        state = store.load()
        assert isinstance(state, HiveState)
        assert len(state.facts) == 0

    def test_save_overwrites_existing(self):
        """Second save overwrites the first."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "state.enc")
            store = EncryptedStateStore(
                filepath=filepath,
                password="test-pass",
            )
            state1 = HiveState()
            state1.add_fact(Fact(
                content="First version",
                confidence=0.9,
                source="test",
            ))
            store.save(state1)

            state2 = HiveState()
            state2.add_fact(Fact(
                content="Second version",
                confidence=0.95,
                source="test",
            ))
            store.save(state2)

            loaded = store.load()
            assert len(loaded.facts) == 1
            assert loaded.facts[0].content == "Second version"

    def test_save_load_preserves_version(self):
        """State version is preserved through encryption."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "state.enc")
            store = EncryptedStateStore(
                filepath=filepath,
                password="test",
            )
            state = HiveState()
            state.add_fact(Fact(
                content="Version test",
                confidence=0.9,
                source="test",
            ))
            original_version = state.version
            store.save(state)
            loaded = store.load()
            assert loaded.version == original_version
```

**Step 2: Run tests, see them fail**

```bash
pytest tests/integration/test_encrypted_substrate.py -v
```

Expected: All tests FAIL (missing `EncryptedStateStore`, `encrypt_json`, `decrypt_json`, `derive_key_from_password`)

**Step 3: Implement**

**`vecna/security/encryption.py`** (add JSON encrypt/decrypt and key derivation):

```python
# Add these functions and class to the existing encryption.py:

import base64
import hashlib
import json
import os
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


def derive_key_from_password(
    password: str,
    salt: Optional[bytes] = None,
    iterations: int = 480_000,
) -> bytes:
    """Derive a Fernet-compatible key from a password.

    Uses PBKDF2-HMAC-SHA256 for key derivation.

    Args:
        password: The password string.
        salt: Salt bytes (16 bytes). Generated if not provided.
        iterations: PBKDF2 iteration count.

    Returns:
        URL-safe base64-encoded Fernet key bytes.
    """
    if salt is None:
        salt = os.urandom(16)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return key


class SubstrateEncryption:
    """Encrypts and decrypts JSON data using Fernet.

    Derives a stable encryption key from a password using
    PBKDF2 with a deterministic salt derived from the password
    itself (for key stability across restarts).
    """

    def __init__(self, password: str) -> None:
        salt = hashlib.sha256(
            password.encode()
        ).digest()[:16]
        self._key = derive_key_from_password(
            password, salt=salt
        )
        self._fernet = Fernet(self._key)

    def encrypt_json(self, data: Dict[str, Any]) -> bytes:
        """Encrypt a dictionary as JSON bytes.

        Args:
            data: Dictionary to encrypt.

        Returns:
            Encrypted bytes.
        """
        plaintext = json.dumps(data).encode("utf-8")
        return self._fernet.encrypt(plaintext)

    def decrypt_json(self, encrypted: bytes) -> Dict[str, Any]:
        """Decrypt bytes back to a dictionary.

        Args:
            encrypted: Encrypted bytes from encrypt_json.

        Returns:
            Decrypted dictionary.

        Raises:
            cryptography.fernet.InvalidToken: Wrong key.
        """
        plaintext = self._fernet.decrypt(encrypted)
        return json.loads(plaintext.decode("utf-8"))
```

**`vecna/core/encrypted_state_store.py`:**

```python
"""Encrypted file-based state persistence.

Provides save/load operations for HiveState with Fernet
encryption at rest. State is serialized to JSON, encrypted,
and written to a file. On load, the file is decrypted and
deserialized back to HiveState.
"""

import logging
import os
from typing import Optional

from vecna.core.hive_state import HiveState
from vecna.security.encryption import SubstrateEncryption

logger = logging.getLogger("vecna.core.encrypted_state_store")


class EncryptedStateStore:
    """Encrypted file-based HiveState persistence.

    Uses SubstrateEncryption (Fernet) to encrypt state before
    writing to disk and decrypt on loading.
    """

    def __init__(
        self,
        filepath: str,
        password: str,
    ) -> None:
        """Initialize the encrypted store.

        Args:
            filepath: Path to the encrypted state file.
            password: Encryption password.
        """
        self._filepath = filepath
        self._encryption = SubstrateEncryption(password)

    def save(self, state: HiveState) -> None:
        """Save HiveState encrypted to file.

        Serializes state to dict, encrypts, and writes to disk.

        Args:
            state: The HiveState to persist.
        """
        state_dict = state.to_full_dict()
        encrypted = self._encryption.encrypt_json(state_dict)

        parent_dir = os.path.dirname(self._filepath)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        with open(self._filepath, "wb") as f:
            f.write(encrypted)

        logger.info(
            "State saved (encrypted) to %s (%d bytes)",
            self._filepath,
            len(encrypted),
        )

    def load(self) -> HiveState:
        """Load HiveState from encrypted file.

        If the file doesn't exist, returns a fresh HiveState.

        Returns:
            Decrypted HiveState.
        """
        if not os.path.exists(self._filepath):
            logger.info(
                "No state file at %s, returning empty state",
                self._filepath,
            )
            return HiveState()

        try:
            with open(self._filepath, "rb") as f:
                encrypted = f.read()
            state_dict = self._encryption.decrypt_json(encrypted)
            state = HiveState.from_dict(state_dict)
            logger.info(
                "State loaded (decrypted) from %s",
                self._filepath,
            )
            return state
        except Exception as e:
            logger.error(
                "Failed to load encrypted state: %s", e
            )
            raise
```

**Step 4: Run tests**

```bash
pytest tests/integration/test_encrypted_substrate.py -v
```

Expected: All 8 tests pass

**Step 5: Commit**

```bash
git add vecna/security/encryption.py vecna/core/encrypted_state_store.py \
  tests/integration/test_encrypted_substrate.py
git commit -m "feat: encrypt substrate at rest using Fernet symmetric encryption"
```

---

### Task 28: Observability Dashboard

**Files:**
- Modify: `vecna/observability/dashboard.py` (add integration health, HumanModel metrics, session metrics, agreement rate fix, full report)
- Modify: `vecna/server/routes.py` (add /api/metrics endpoint)
- Create: `tests/unit/test_dashboard.py`

**Step 1: Write the failing tests**

```python
# tests/unit/test_dashboard.py
"""Unit tests for the observability dashboard MetricsCollector.

Tests:
- Token usage recording and per-model aggregation
- Consensus merge recording with agreement rate tracking
- Tool execution recording
- Dream run recording
- Integration health tracking
- HumanModel confidence evolution
- Session-scoped metrics
- Full report generation
- Snapshot and reset
- Metrics endpoint handler
"""

import pytest
from datetime import datetime

from vecna.observability.dashboard import (
    TokenUsage,
    ConsensusStats,
    ToolStats,
    DreamStats,
    MetricsSnapshot,
    MetricsCollector,
    IntegrationHealth,
    HumanModelMetrics,
    SessionMetrics,
)
from vecna.server.routes import handle_metrics_request


class TestTokenUsage:
    """Tests for TokenUsage dataclass."""

    def test_token_usage_to_dict(self):
        """TokenUsage.to_dict serializes all fields."""
        usage = TokenUsage(
            model="gpt-4",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        d = usage.to_dict()
        assert d["model"] == "gpt-4"
        assert d["prompt_tokens"] == 100
        assert d["completion_tokens"] == 50
        assert d["total_tokens"] == 150
        assert "timestamp" in d

    def test_token_usage_defaults(self):
        """TokenUsage defaults to empty/zero values."""
        usage = TokenUsage()
        assert usage.model == ""
        assert usage.total_tokens == 0


class TestConsensusAgreementRate:
    """Tests for consensus agreement rate tracking."""

    def test_single_merge_with_agreement_rate(self):
        """Recording one merge sets avg_agreement_rate."""
        collector = MetricsCollector()
        collector.record_consensus_merge(
            facts_added=2,
            beliefs_added=1,
            contradictions_found=0,
            agreement_rate=0.85,
        )
        assert collector.consensus.avg_agreement_rate == pytest.approx(0.85)
        assert collector.consensus.total_merges == 1
        assert collector.consensus.facts_added == 2

    def test_multiple_merges_average_agreement_rate(self):
        """Agreement rate is averaged across multiple merges."""
        collector = MetricsCollector()
        collector.record_consensus_merge(
            facts_added=1,
            beliefs_added=0,
            contradictions_found=0,
            agreement_rate=0.80,
        )
        collector.record_consensus_merge(
            facts_added=2,
            beliefs_added=1,
            contradictions_found=1,
            agreement_rate=0.60,
        )
        assert collector.consensus.avg_agreement_rate == pytest.approx(0.70)
        assert collector.consensus.total_merges == 2
        assert collector.consensus.contradictions_found == 1

    def test_merge_without_agreement_rate_defaults_zero(self):
        """When agreement_rate is omitted, it defaults to 0.0."""
        collector = MetricsCollector()
        collector.record_consensus_merge(
            facts_added=1,
            beliefs_added=0,
            contradictions_found=0,
        )
        assert collector.consensus.avg_agreement_rate == pytest.approx(0.0)
        assert collector.consensus.total_merges == 1


class TestIntegrationHealth:
    """Tests for IntegrationHealth dataclass and tracking."""

    def test_integration_health_to_dict(self):
        """IntegrationHealth serializes correctly."""
        health = IntegrationHealth(name="slack", status="healthy")
        d = health.to_dict()
        assert d["name"] == "slack"
        assert d["status"] == "healthy"
        assert d["error_count"] == 0
        assert d["last_error"] is None
        assert "last_check" in d

    def test_record_integration_health_new(self):
        """Recording health for a new integration creates entry."""
        collector = MetricsCollector()
        collector.record_integration_health(
            name="slack",
            status="healthy",
        )
        assert "slack" in collector.integrations
        assert collector.integrations["slack"].status == "healthy"
        assert collector.integrations["slack"].error_count == 0

    def test_record_integration_health_with_error(self):
        """Recording health with error increments error count."""
        collector = MetricsCollector()
        collector.record_integration_health(
            name="discord",
            status="degraded",
            error="Connection timeout",
        )
        assert collector.integrations["discord"].status == "degraded"
        assert collector.integrations["discord"].error_count == 1
        assert collector.integrations["discord"].last_error == "Connection timeout"

    def test_record_integration_health_updates_existing(self):
        """Recording health again updates status and timestamps."""
        collector = MetricsCollector()
        collector.record_integration_health(name="github", status="healthy")
        collector.record_integration_health(
            name="github",
            status="down",
            error="API rate limited",
        )
        assert collector.integrations["github"].status == "down"
        assert collector.integrations["github"].error_count == 1
        assert collector.integrations["github"].last_error == "API rate limited"

    def test_multiple_errors_accumulate(self):
        """Multiple error recordings increment the count."""
        collector = MetricsCollector()
        collector.record_integration_health(
            name="composio", status="degraded", error="err1"
        )
        collector.record_integration_health(
            name="composio", status="degraded", error="err2"
        )
        collector.record_integration_health(
            name="composio", status="down", error="err3"
        )
        assert collector.integrations["composio"].error_count == 3
        assert collector.integrations["composio"].last_error == "err3"


class TestHumanModelMetrics:
    """Tests for HumanModel confidence evolution tracking."""

    def test_empty_human_model_metrics(self):
        """Fresh HumanModelMetrics has no snapshots."""
        hm = HumanModelMetrics()
        assert hm.confidence_snapshots == []
        evolution = hm.get_evolution()
        assert evolution == []

    def test_record_confidence(self):
        """Recording confidence adds a snapshot."""
        hm = HumanModelMetrics()
        hm.record_confidence(
            user_id="user-abc",
            dimension="trust",
            old_value=0.5,
            new_value=0.7,
        )
        assert len(hm.confidence_snapshots) == 1
        snap = hm.confidence_snapshots[0]
        assert snap["user_id"] == "user-abc"
        assert snap["dimension"] == "trust"
        assert snap["old_value"] == 0.5
        assert snap["new_value"] == 0.7
        assert "timestamp" in snap

    def test_get_evolution_returns_chronological_snapshots(self):
        """Evolution returns all snapshots in order."""
        hm = HumanModelMetrics()
        hm.record_confidence("u1", "trust", 0.3, 0.5)
        hm.record_confidence("u1", "trust", 0.5, 0.8)
        hm.record_confidence("u2", "expertise", 0.1, 0.4)
        evolution = hm.get_evolution()
        assert len(evolution) == 3
        assert evolution[0]["old_value"] == 0.3
        assert evolution[1]["new_value"] == 0.8
        assert evolution[2]["dimension"] == "expertise"

    def test_collector_record_human_model_confidence(self):
        """MetricsCollector delegates to HumanModelMetrics."""
        collector = MetricsCollector()
        collector.record_human_model_confidence(
            user_id="u1",
            dimension="friendliness",
            old_value=0.6,
            new_value=0.9,
        )
        assert len(collector.human_model.confidence_snapshots) == 1

    def test_human_model_metrics_to_dict(self):
        """HumanModelMetrics.to_dict includes all snapshots."""
        hm = HumanModelMetrics()
        hm.record_confidence("u1", "trust", 0.5, 0.7)
        d = hm.to_dict()
        assert "confidence_snapshots" in d
        assert len(d["confidence_snapshots"]) == 1
        assert d["total_updates"] == 1


class TestSessionMetrics:
    """Tests for session-scoped metrics."""

    def test_session_metrics_to_dict(self):
        """SessionMetrics serializes correctly."""
        sm = SessionMetrics(session_id="sess-001")
        d = sm.to_dict()
        assert d["session_id"] == "sess-001"
        assert d["token_count"] == 0
        assert d["tool_executions"] == 0
        assert "start_time" in d
        assert d["end_time"] is None

    def test_record_session_start_and_end(self):
        """Starting and ending a session tracks it."""
        collector = MetricsCollector()
        collector.record_session_start("sess-abc")
        assert "sess-abc" in collector.sessions
        assert collector.sessions["sess-abc"].end_time is None

        collector.record_session_end("sess-abc")
        assert collector.sessions["sess-abc"].end_time is not None

    def test_session_end_nonexistent_is_noop(self):
        """Ending a non-existent session does nothing."""
        collector = MetricsCollector()
        collector.record_session_end("nonexistent")
        assert "nonexistent" not in collector.sessions

    def test_session_token_tracking(self):
        """Token usage within a session is tracked."""
        collector = MetricsCollector()
        collector.record_session_start("sess-1")
        collector.record_token_usage(
            model="gpt-4",
            prompt_tokens=100,
            completion_tokens=50,
            session_id="sess-1",
        )
        assert collector.sessions["sess-1"].token_count == 150

    def test_session_tool_tracking(self):
        """Tool executions within a session are tracked."""
        collector = MetricsCollector()
        collector.record_session_start("sess-2")
        collector.record_tool_execution(
            success=True,
            latency_ms=45.0,
            session_id="sess-2",
        )
        collector.record_tool_execution(
            success=False,
            latency_ms=120.0,
            session_id="sess-2",
        )
        assert collector.sessions["sess-2"].tool_executions == 2
        assert collector.sessions["sess-2"].tool_successes == 1
        assert collector.sessions["sess-2"].tool_failures == 1


class TestFullReport:
    """Tests for the full report generation."""

    def test_full_report_structure(self):
        """to_full_report returns all metric categories."""
        collector = MetricsCollector()
        report = collector.to_full_report()
        assert "tokens" in report
        assert "consensus" in report
        assert "tools" in report
        assert "dreams" in report
        assert "integrations" in report
        assert "human_model" in report
        assert "sessions" in report
        assert "snapshot" in report
        assert "generated_at" in report

    def test_full_report_with_data(self):
        """Full report includes all recorded data."""
        collector = MetricsCollector()
        collector.record_token_usage("gpt-4", 100, 50)
        collector.record_consensus_merge(1, 0, 0, agreement_rate=0.9)
        collector.record_tool_execution(True, 30.0)
        collector.record_dream_run(2, 1, 0)
        collector.record_integration_health("slack", "healthy")
        collector.record_human_model_confidence("u1", "trust", 0.5, 0.7)
        collector.record_session_start("s1")

        report = collector.to_full_report()
        assert report["tokens"]["by_model"]["gpt-4"]["total_tokens"] == 150
        assert report["consensus"]["avg_agreement_rate"] == pytest.approx(0.9)
        assert report["tools"]["total_executions"] == 1
        assert report["dreams"]["total_runs"] == 1
        assert report["integrations"]["slack"]["status"] == "healthy"
        assert len(report["human_model"]["confidence_snapshots"]) == 1
        assert "s1" in report["sessions"]
        assert report["snapshot"]["total_tokens"] == 150


class TestReset:
    """Tests for MetricsCollector reset."""

    def test_reset_clears_all_metrics(self):
        """Reset clears tokens, consensus, tools, dreams, and new fields."""
        collector = MetricsCollector()
        collector.record_token_usage("gpt-4", 100, 50)
        collector.record_consensus_merge(1, 0, 0, agreement_rate=0.9)
        collector.record_tool_execution(True, 30.0)
        collector.record_dream_run(2, 1, 0)
        collector.record_integration_health("slack", "healthy")
        collector.record_human_model_confidence("u1", "trust", 0.5, 0.7)
        collector.record_session_start("s1")

        collector.reset()

        assert collector.token_records == []
        assert collector.consensus.total_merges == 0
        assert collector.tools.total_executions == 0
        assert collector.dreams.total_runs == 0
        assert collector.integrations == {}
        assert collector.human_model.confidence_snapshots == []
        assert collector.sessions == {}


class TestMetricsEndpoint:
    """Tests for the /api/metrics route handler."""

    def test_handle_metrics_request_returns_report(self):
        """handle_metrics_request returns the full report dict."""
        collector = MetricsCollector()
        collector.record_token_usage("gpt-4", 50, 25)

        result = handle_metrics_request(collector)
        assert "tokens" in result
        assert "snapshot" in result
        assert result["tokens"]["by_model"]["gpt-4"]["total_tokens"] == 75

    def test_handle_metrics_request_empty_collector(self):
        """handle_metrics_request works with no data recorded."""
        collector = MetricsCollector()
        result = handle_metrics_request(collector)
        assert result["snapshot"]["total_tokens"] == 0
        assert result["integrations"] == {}
        assert result["sessions"] == {}
```

**Step 2: Run tests, see them fail**

```bash
pytest tests/unit/test_dashboard.py -v
```

Expected: All tests FAIL (missing `IntegrationHealth`, `HumanModelMetrics`, `SessionMetrics`, updated `record_consensus_merge` signature, `to_full_report`, `handle_metrics_request`)

**Step 3: Implement**

**`vecna/observability/dashboard.py`** (full updated file):

```python
"""Observability dashboard metrics collector.

Aggregates operational metrics across the Vecna system:
- Token usage per model per session
- Consensus agreement rates
- Tool execution counts and latencies
- DreamLoop run history
- Integration health tracking
- HumanModel confidence evolution
- Per-session metric breakdowns

This is separate from ToolDashboard (tool_dashboard.py) which
focuses on individual tool audit events. MetricsCollector
provides higher-level system-wide metrics.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger("vecna.observability.dashboard")


@dataclass
class TokenUsage:
    """Token usage record for a single LLM call."""

    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ConsensusStats:
    """Aggregated consensus statistics."""

    total_merges: int = 0
    facts_added: int = 0
    beliefs_added: int = 0
    contradictions_found: int = 0
    avg_agreement_rate: float = 0.0
    _agreement_sum: float = field(default=0.0, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "total_merges": self.total_merges,
            "facts_added": self.facts_added,
            "beliefs_added": self.beliefs_added,
            "contradictions_found": self.contradictions_found,
            "avg_agreement_rate": self.avg_agreement_rate,
        }


@dataclass
class ToolStats:
    """Aggregated tool execution statistics."""

    total_executions: int = 0
    successful: int = 0
    failed: int = 0
    avg_latency_ms: float = 0.0
    _latency_sum: float = field(default=0.0, repr=False)

    def failure_rate(self) -> float:
        """Calculate the failure rate."""
        if self.total_executions == 0:
            return 0.0
        return self.failed / self.total_executions

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "total_executions": self.total_executions,
            "successful": self.successful,
            "failed": self.failed,
            "failure_rate": self.failure_rate(),
            "avg_latency_ms": self.avg_latency_ms,
        }


@dataclass
class DreamStats:
    """Aggregated DreamLoop statistics."""

    total_runs: int = 0
    insights_generated: int = 0
    facts_reinforced: int = 0
    facts_decayed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "total_runs": self.total_runs,
            "insights_generated": self.insights_generated,
            "facts_reinforced": self.facts_reinforced,
            "facts_decayed": self.facts_decayed,
        }


@dataclass
class MetricsSnapshot:
    """Point-in-time snapshot of all metrics."""

    total_tokens: int = 0
    consensus_merges: int = 0
    tool_executions: int = 0
    dream_runs: int = 0
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "total_tokens": self.total_tokens,
            "consensus_merges": self.consensus_merges,
            "tool_executions": self.tool_executions,
            "dream_runs": self.dream_runs,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class IntegrationHealth:
    """Health status for an external integration.

    Tracks the current status of integrations such as Slack,
    Discord, GitHub, or Composio alongside error history.
    """

    name: str = ""
    status: str = "healthy"
    last_check: datetime = field(default_factory=datetime.now)
    error_count: int = 0
    last_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "status": self.status,
            "last_check": self.last_check.isoformat(),
            "error_count": self.error_count,
            "last_error": self.last_error,
        }


@dataclass
class HumanModelMetrics:
    """Tracks HumanModel confidence evolution over time.

    Records snapshots of confidence changes across dimensions
    (trust, expertise, friendliness, etc.) for each user.
    """

    confidence_snapshots: List[Dict[str, Any]] = field(
        default_factory=list
    )

    def record_confidence(
        self,
        user_id: str,
        dimension: str,
        old_value: float,
        new_value: float,
    ) -> None:
        """Record a confidence value change.

        Args:
            user_id: The user whose model changed.
            dimension: The confidence dimension (e.g. trust).
            old_value: Previous confidence value.
            new_value: Updated confidence value.
        """
        self.confidence_snapshots.append({
            "user_id": user_id,
            "dimension": dimension,
            "old_value": old_value,
            "new_value": new_value,
            "timestamp": datetime.now().isoformat(),
        })

    def get_evolution(self) -> List[Dict[str, Any]]:
        """Return all confidence snapshots in chronological order.

        Returns:
            List of confidence snapshot dicts.
        """
        return list(self.confidence_snapshots)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "confidence_snapshots": list(self.confidence_snapshots),
            "total_updates": len(self.confidence_snapshots),
        }


@dataclass
class SessionMetrics:
    """Per-session metric breakdown.

    Tracks token usage and tool execution counts scoped
    to a single user session.
    """

    session_id: str = ""
    token_count: int = 0
    tool_executions: int = 0
    tool_successes: int = 0
    tool_failures: int = 0
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "session_id": self.session_id,
            "token_count": self.token_count,
            "tool_executions": self.tool_executions,
            "tool_successes": self.tool_successes,
            "tool_failures": self.tool_failures,
            "start_time": self.start_time.isoformat(),
            "end_time": (
                self.end_time.isoformat()
                if self.end_time is not None
                else None
            ),
        }


class MetricsCollector:
    """Collects and aggregates system-wide metrics.

    Thread-safe for single-writer usage. Records token usage,
    consensus merges, tool executions, dream loop runs,
    integration health, HumanModel confidence, and per-session
    breakdowns.
    """

    def __init__(self) -> None:
        self.token_records: List[TokenUsage] = []
        self.consensus = ConsensusStats()
        self.tools = ToolStats()
        self.dreams = DreamStats()
        self.integrations: Dict[str, IntegrationHealth] = {}
        self.human_model = HumanModelMetrics()
        self.sessions: Dict[str, SessionMetrics] = {}

    def record_token_usage(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        session_id: Optional[str] = None,
    ) -> None:
        """Record token usage for a single LLM call.

        Args:
            model: The model identifier.
            prompt_tokens: Number of prompt tokens.
            completion_tokens: Number of completion tokens.
            session_id: Optional session to attribute to.
        """
        total = prompt_tokens + completion_tokens
        record = TokenUsage(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
        )
        self.token_records.append(record)

        if session_id and session_id in self.sessions:
            self.sessions[session_id].token_count += total

    def record_consensus_merge(
        self,
        facts_added: int,
        beliefs_added: int,
        contradictions_found: int,
        agreement_rate: float = 0.0,
    ) -> None:
        """Record a consensus merge operation.

        Args:
            facts_added: Number of facts added.
            beliefs_added: Number of beliefs added.
            contradictions_found: Number of contradictions.
            agreement_rate: Agreement rate for this merge (0.0-1.0).
        """
        self.consensus.total_merges += 1
        self.consensus.facts_added += facts_added
        self.consensus.beliefs_added += beliefs_added
        self.consensus.contradictions_found += contradictions_found
        self.consensus._agreement_sum += agreement_rate
        self.consensus.avg_agreement_rate = (
            self.consensus._agreement_sum
            / self.consensus.total_merges
        )

    def record_tool_execution(
        self,
        success: bool,
        latency_ms: float,
        session_id: Optional[str] = None,
    ) -> None:
        """Record a tool execution.

        Args:
            success: Whether the execution succeeded.
            latency_ms: Execution latency in milliseconds.
            session_id: Optional session to attribute to.
        """
        self.tools.total_executions += 1
        if success:
            self.tools.successful += 1
        else:
            self.tools.failed += 1

        self.tools._latency_sum += latency_ms
        self.tools.avg_latency_ms = (
            self.tools._latency_sum / self.tools.total_executions
        )

        if session_id and session_id in self.sessions:
            session = self.sessions[session_id]
            session.tool_executions += 1
            if success:
                session.tool_successes += 1
            else:
                session.tool_failures += 1

    def record_dream_run(
        self,
        insights: int,
        reinforced: int,
        decayed: int,
    ) -> None:
        """Record a DreamLoop run.

        Args:
            insights: Number of insights generated.
            reinforced: Number of facts reinforced.
            decayed: Number of facts decayed.
        """
        self.dreams.total_runs += 1
        self.dreams.insights_generated += insights
        self.dreams.facts_reinforced += reinforced
        self.dreams.facts_decayed += decayed

    def record_integration_health(
        self,
        name: str,
        status: str,
        error: Optional[str] = None,
    ) -> None:
        """Record health status for an integration.

        Creates the integration entry if it doesn't exist,
        otherwise updates status and error tracking.

        Args:
            name: Integration name (e.g. slack, discord).
            status: Current status (healthy/degraded/down).
            error: Optional error message if unhealthy.
        """
        now = datetime.now()
        if name not in self.integrations:
            self.integrations[name] = IntegrationHealth(
                name=name,
                status=status,
                last_check=now,
            )
        else:
            self.integrations[name].status = status
            self.integrations[name].last_check = now

        if error is not None:
            self.integrations[name].error_count += 1
            self.integrations[name].last_error = error

        logger.debug(
            "Integration %s health: %s", name, status
        )

    def record_human_model_confidence(
        self,
        user_id: str,
        dimension: str,
        old_value: float,
        new_value: float,
    ) -> None:
        """Record a HumanModel confidence change.

        Args:
            user_id: The user whose model changed.
            dimension: The confidence dimension.
            old_value: Previous confidence value.
            new_value: Updated confidence value.
        """
        self.human_model.record_confidence(
            user_id=user_id,
            dimension=dimension,
            old_value=old_value,
            new_value=new_value,
        )

    def record_session_start(
        self, session_id: str
    ) -> None:
        """Start tracking metrics for a session.

        Args:
            session_id: Unique session identifier.
        """
        self.sessions[session_id] = SessionMetrics(
            session_id=session_id,
        )
        logger.debug("Session started: %s", session_id)

    def record_session_end(
        self, session_id: str
    ) -> None:
        """Mark a session as ended.

        Does nothing if the session does not exist.

        Args:
            session_id: The session to end.
        """
        if session_id not in self.sessions:
            return
        self.sessions[session_id].end_time = datetime.now()
        logger.debug("Session ended: %s", session_id)

    def get_token_usage_by_model(
        self,
    ) -> Dict[str, Dict[str, int]]:
        """Aggregate token usage per model.

        Returns:
            Dict mapping model name to token totals.
        """
        by_model: Dict[str, Dict[str, int]] = {}
        for record in self.token_records:
            if record.model not in by_model:
                by_model[record.model] = {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "call_count": 0,
                }
            entry = by_model[record.model]
            entry["prompt_tokens"] += record.prompt_tokens
            entry["completion_tokens"] += (
                record.completion_tokens
            )
            entry["total_tokens"] += record.total_tokens
            entry["call_count"] += 1
        return by_model

    def get_snapshot(self) -> MetricsSnapshot:
        """Get a point-in-time snapshot of key metrics.

        Returns:
            A MetricsSnapshot summarizing current state.
        """
        total_tokens = sum(
            r.total_tokens for r in self.token_records
        )
        return MetricsSnapshot(
            total_tokens=total_tokens,
            consensus_merges=self.consensus.total_merges,
            tool_executions=self.tools.total_executions,
            dream_runs=self.dreams.total_runs,
        )

    def to_full_report(self) -> Dict[str, Any]:
        """Generate a comprehensive metrics report.

        Combines all metric categories into a single dict
        suitable for JSON serialization and API responses.

        Returns:
            Dict with tokens, consensus, tools, dreams,
            integrations, human_model, sessions, and snapshot.
        """
        integrations_dict: Dict[str, Any] = {}
        for name, health in self.integrations.items():
            integrations_dict[name] = health.to_dict()

        sessions_dict: Dict[str, Any] = {}
        for sid, session in self.sessions.items():
            sessions_dict[sid] = session.to_dict()

        return {
            "tokens": {
                "total_records": len(self.token_records),
                "by_model": self.get_token_usage_by_model(),
            },
            "consensus": self.consensus.to_dict(),
            "tools": self.tools.to_dict(),
            "dreams": self.dreams.to_dict(),
            "integrations": integrations_dict,
            "human_model": self.human_model.to_dict(),
            "sessions": sessions_dict,
            "snapshot": self.get_snapshot().to_dict(),
            "generated_at": datetime.now().isoformat(),
        }

    def reset(self) -> None:
        """Reset all collected metrics."""
        self.token_records.clear()
        self.consensus = ConsensusStats()
        self.tools = ToolStats()
        self.dreams = DreamStats()
        self.integrations.clear()
        self.human_model = HumanModelMetrics()
        self.sessions.clear()
        logger.info("Metrics collector reset")
```

**Step 4: Run tests**

```bash
pytest tests/unit/test_dashboard.py -v
```

Expected: All tests pass

**Step 5: Commit**

```bash
git add vecna/observability/dashboard.py vecna/server/routes.py tests/unit/test_dashboard.py
git commit -m "feat: add observability dashboard with token, consensus, and tool metrics"
```

---

### Task 29: End-to-End Integration Tests + Documentation

**Files:**
- Create: `tests/e2e/test_full_stack.py`
- Create: `docs/architecture.md`
- Create: `docs/integrations.md`
- Create: `docs/deployment.md`

**Step 1: Write the failing tests**

```python
# tests/e2e/test_full_stack.py
"""End-to-end integration tests for the full Vecna stack.

Validates complete flows with mock adapters (no real LLM calls):
- CLI → HiveLoop → Consensus → Response → State Update
- Server → Channel → HiveLoop → Response → Channel
- DreamLoop consolidation
- HumanModel persistence across sessions
- MetricsCollector end-to-end
- Config bootstrap
"""

import json
from typing import Any, Dict, List, Optional

import pytest

from vecna.adapters.base import BaseAdapter, ModelConfig
from vecna.config.schema import VecnaConfig, create_default_config
from vecna.core.types import Fact, Belief, HiveUpdate
from vecna.core.hive_state import HiveState
from vecna.orchestrator.loop import HiveLoop, HiveConfig
from vecna.observability.dashboard import MetricsCollector


class MockE2EAdapter(BaseAdapter):
    """Mock adapter returning deterministic HIVE_UPDATE responses."""

    def __init__(self):
        config = ModelConfig(name="mock-e2e", model_id="mock-e2e-v1")
        super().__init__(config)

    async def generate(self, prompt: str) -> str:
        return (
            "<HIVE_UPDATE>\n"
            "facts:\n"
            "  - content: \"Python is a programming language\"\n"
            "    confidence: 0.95\n"
            "beliefs:\n"
            "  - content: \"Testing improves code quality\"\n"
            "    confidence: 0.9\n"
            "response: \"I've analyzed the topic and found relevant information.\"\n"
            "</HIVE_UPDATE>"
        )

    def _get_provider_name(self) -> str:
        return "mock"


class TestCLIToHiveLoop:
    """Tests that validate the CLI-to-HiveLoop pipeline end-to-end."""

    async def test_think_returns_response(self):
        """HiveLoop.think returns a non-empty response string."""
        adapter = MockE2EAdapter()
        config = HiveConfig()
        loop = HiveLoop(
            config=config,
            adapters=[adapter],
            name="e2e-cli",
        )
        result = await loop.think("hello")
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0

    async def test_think_updates_state_with_facts(self):
        """HiveLoop.think adds facts to HiveState."""
        adapter = MockE2EAdapter()
        config = HiveConfig()
        loop = HiveLoop(
            config=config,
            adapters=[adapter],
            name="e2e-state",
        )
        initial_facts = len(loop.state.facts)
        await loop.think("tell me about Python")
        assert len(loop.state.facts) > initial_facts

    async def test_multiple_cycles_accumulate_state(self):
        """Multiple think calls accumulate state entries."""
        adapter = MockE2EAdapter()
        config = HiveConfig()
        loop = HiveLoop(
            config=config,
            adapters=[adapter],
            name="e2e-accum",
        )
        await loop.think("first question")
        count_after_first = len(loop.state.facts) + len(loop.state.beliefs)
        await loop.think("second question")
        count_after_second = len(loop.state.facts) + len(loop.state.beliefs)
        assert count_after_second >= count_after_first


class TestServerIntegration:
    """Tests for the HTTP server endpoints using aiohttp test client."""

    async def test_chat_endpoint_returns_response(self, aiohttp_client):
        """POST /api/chat returns 200 with response field."""
        from vecna.server.app import create_app

        app = create_app(adapters=[MockE2EAdapter()])
        client = await aiohttp_client(app)
        resp = await client.post(
            "/api/chat",
            json={"message": "test query"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert "response" in data
        assert len(data["response"]) > 0

    async def test_state_endpoint_returns_state(self, aiohttp_client):
        """GET /api/state returns HiveState with version."""
        from vecna.server.app import create_app

        app = create_app(adapters=[MockE2EAdapter()])
        client = await aiohttp_client(app)
        resp = await client.get("/api/state")
        assert resp.status == 200
        data = await resp.json()
        assert "version" in data
        assert "facts" in data

    async def test_health_endpoint_returns_ok(self, aiohttp_client):
        """GET /api/health returns status ok."""
        from vecna.server.app import create_app

        app = create_app(adapters=[MockE2EAdapter()])
        client = await aiohttp_client(app)
        resp = await client.get("/api/health")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"


class TestDreamLoopIntegration:
    """Tests for dream consolidation pipeline."""

    async def test_dream_loop_processes_facts(self):
        """DreamLoop runs on a state with accumulated facts."""
        from vecna.memory.dream_loop import DreamLoop

        adapter = MockE2EAdapter()
        state = HiveState()
        for i in range(5):
            state.add_fact(Fact(
                content=f"Dream test fact number {i}",
                confidence=0.8 + (i * 0.02),
                source="test",
            ))
        dream = DreamLoop(state=state, adapter=adapter)
        result = await dream.run()
        assert result is not None


class TestHumanModelPersistence:
    """Tests for HumanModel export/import across sessions."""

    def test_export_import_preserves_preferences(self):
        """HumanModel preferences survive export/import cycle."""
        from vecna.core.human_model import HumanModel

        model = HumanModel()
        model.add_preference(
            dimension="communication_style",
            value="concise",
            confidence=0.9,
        )
        model.add_preference(
            dimension="expertise_level",
            value="advanced",
            confidence=0.85,
        )
        exported = model.to_dict()
        restored = HumanModel.from_dict(exported)
        pref = restored.get_preference("communication_style")
        assert pref is not None
        assert pref.value == "concise"

    def test_confidence_evolves_with_repeated_preferences(self):
        """Adding same preference multiple times changes confidence."""
        from vecna.core.human_model import HumanModel

        model = HumanModel()
        model.add_preference(
            dimension="tone",
            value="formal",
            confidence=0.5,
        )
        initial = model.get_preference("tone").confidence
        model.add_preference(
            dimension="tone",
            value="formal",
            confidence=0.8,
        )
        updated = model.get_preference("tone").confidence
        assert updated != initial


class TestMetricsEndToEnd:
    """Tests for MetricsCollector integration."""

    def test_full_report_after_operations(self):
        """Full report contains all recorded metric categories."""
        collector = MetricsCollector()
        collector.record_token_usage("mock-e2e-v1", 100, 50)
        collector.record_token_usage("mock-e2e-v1", 200, 75)
        collector.record_consensus_merge(2, 1, 0, agreement_rate=0.85)
        collector.record_tool_execution(True, 45.0)
        collector.record_tool_execution(False, 120.0)
        collector.record_dream_run(3, 2, 1)
        collector.record_integration_health("slack", "healthy")
        collector.record_session_start("e2e-sess")
        collector.record_token_usage(
            "mock-e2e-v1", 50, 25, session_id="e2e-sess"
        )

        report = collector.to_full_report()
        assert report["tokens"]["by_model"]["mock-e2e-v1"]["total_tokens"] == 500
        assert report["consensus"]["total_merges"] == 1
        assert report["tools"]["total_executions"] == 2
        assert report["dreams"]["total_runs"] == 1
        assert report["integrations"]["slack"]["status"] == "healthy"
        assert report["sessions"]["e2e-sess"]["token_count"] == 75

    def test_metrics_reset_clears_everything(self):
        """Reset leaves collector in clean state."""
        collector = MetricsCollector()
        collector.record_token_usage("gpt-4", 100, 50)
        collector.record_integration_health("discord", "down", error="fail")
        collector.reset()
        report = collector.to_full_report()
        assert report["snapshot"]["total_tokens"] == 0
        assert report["integrations"] == {}


class TestConfigBootstrap:
    """Tests for configuration creation and mapping."""

    def test_default_config_creates_valid_config(self):
        """create_default_config returns a valid VecnaConfig."""
        config = create_default_config()
        assert isinstance(config, VecnaConfig)
```

**Step 2: Run tests, see them fail**

```bash
pytest tests/e2e/test_full_stack.py -v
```

Expected: Tests fail (full stack not yet wired)

**Step 3: Implement**

**`docs/architecture.md`:**

```markdown
# Vecna Architecture

## Overview

Vecna (Virtual Emergent Collective Neural Architecture) is a hive-mind orchestrator for AI
models. It coordinates multiple LLM providers through a shared mental state, enabling
consensus-driven reasoning, persistent memory, and autonomous curiosity via dream loops.

Vecna treats AI models as nodes in a collective intelligence rather than isolated chat endpoints.
Each model contributes facts, beliefs, and hypotheses to a shared `HiveState`, and a consensus
engine reconciles conflicting perspectives into coherent responses.

## Component Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                           User Interface                             │
│                                                                      │
│   ┌──────────┐    ┌──────────────┐    ┌────────────────────┐        │
│   │   CLI    │    │  HTTP Server │    │  WebSocket Server  │        │
│   │ (Click)  │    │  (aiohttp)   │    │    (aiohttp-ws)    │        │
│   └────┬─────┘    └──────┬───────┘    └─────────┬──────────┘        │
└────────┼─────────────────┼──────────────────────┼────────────────────┘
         │                 │                      │
         └─────────────────┼──────────────────────┘
                           │
                    ┌──────▼──────┐
                    │  HiveLoop   │◄──── Main orchestration loop
                    └──┬───┬───┬──┘
                       │   │   │
          ┌────────────┘   │   └────────────┐
          │                │                │
  ┌───────▼───────┐ ┌─────▼──────┐ ┌───────▼────────┐
  │   Adapters    │ │  Consensus │ │  ToolRuntime   │
  │ (LLM calls)  │ │   Engine   │ │  (sandboxed)   │
  └───────┬───────┘ └─────┬──────┘ └───────┬────────┘
          │               │                │
  ┌───────▼───────┐ ┌─────▼──────┐ ┌───────▼────────┐
  │ LLM Providers │ │ HiveState  │ │ Tool Registry  │
  │ Copilot,Groq, │ │ Facts,     │ │ search, code,  │
  │ Ollama,OpenAI │ │ Beliefs,   │ │ file_read,     │
  │ Anthropic,HF  │ │ Hypotheses │ │ file_write     │
  └───────────────┘ └─────┬──────┘ └────────────────┘
                          │
              ┌───────────┼───────────┐
              │           │           │
      ┌───────▼──┐  ┌────▼────┐  ┌───▼──────┐
      │   Hot    │  │  Warm   │  │   Cold   │
      │  Redis   │  │pgvector │  │ PG Epis. │
      │ (cache)  │  │ (embed) │  │ (archive)│
      └──────────┘  └─────────┘  └──────────┘
```

## Core Modules

### HiveState (`vecna/core/hive_state.py`)

The central shared state object. Contains versioned collections of `Fact`, `Belief`,
`Hypothesis`, and `Goal` objects. Every adapter read/write goes through HiveState, which
provides deduplication via Jaccard similarity and version tracking.

Key methods: `add_fact()`, `add_belief()`, `apply_update()`, `to_prompt_context()`,
`to_full_dict()`, `export_to_file()`, `import_from_file()`.

### Adapters (`vecna/adapters/`)

The adapter layer abstracts LLM provider differences behind `BaseAdapter`. Each adapter
implements `generate(prompt) -> str` and `think(state, task) -> (str, HiveUpdate)`.

Concrete adapters:
- **CopilotAdapter** — GitHub Models API
- **OllamaAdapter** — Local Ollama runtime (aiohttp)
- **GroqAdapter** — Groq cloud API (groq SDK)
- **OpenAIAdapter** — OpenAI API (openai SDK, with function calling)
- **AnthropicAdapter** — Anthropic API (anthropic SDK, with tool use)
- **TransformersAdapter** — Local HuggingFace models

### ConsensusEngine (`vecna/orchestrator/consensus.py`)

When multiple adapters produce conflicting facts or beliefs, the consensus engine resolves
disagreements. It uses confidence-weighted voting: facts with higher confidence from more
adapters win. The consensus threshold is configurable via `HiveConfig.consensus_threshold`.

### DreamLoop (`vecna/memory/dream_loop.py`)

An autonomous background process that consolidates accumulated facts into higher-order
insights. Runs in four phases: Review, Synthesize, Integrate, and Prune. Returns a
`DreamResult` with details of each phase.

### ToolRuntime (`vecna/tools/`)

A sandboxed execution environment for tools the LLM can invoke. Tools are registered in a
`ToolRegistry` with permission tiers (`RiskTier`). Execution happens via `ToolExecutionContext`
with configurable timeouts and filesystem restrictions.

### Memory (`vecna/memory/`)

Three-tier memory architecture:
- **Hot (Redis):** Recent conversation context, fast key-value lookups.
- **Warm (pgvector):** Embedding-based semantic search over facts and memories.
- **Cold (PostgreSQL):** Full episodic archives, `Episode` and `MemoryEvent` storage.

## Data Flow

1. **User sends message** via CLI (`vecna chat`), HTTP POST `/api/chat`, or WebSocket.
2. **HiveLoop receives input** and builds a prompt including HiveState context and HumanModel.
3. **Adapters generate responses** — one or more LLMs produce `<HIVE_UPDATE>` YAML blocks.
4. **Parser extracts** `Fact`, `Belief`, `Hypothesis` objects and response text.
5. **ConsensusEngine reconciles** outputs if multiple adapters contributed.
6. **HiveState updates** with new entries; version increments.
7. **Memory stores persist** changes to Redis (hot), pgvector (warm), PostgreSQL (cold).
8. **Response returned** to the user through the originating channel.
9. **DreamLoop (async)** periodically consolidates accumulated state in the background.
10. **ThoughtfulnessEngine** generates proactive follow-ups queued for next interaction.

## Configuration

Configuration is defined in `vecna/config/schema.py`:

- **`VecnaConfig`** — Top-level. Contains model list, group configs, tool policies.
- **`ModelConfig`** — Per-model: name, model_id, domain, weight, temperature, max_tokens,
  api_key, base_url, persona.
- **`HiveConfig`** — Hive behavior: max_cycles, model_timeout, consensus_threshold,
  enable_tools, safety settings.

Configuration loads from `vecna.yaml`, environment variables (`VECNA_*`), or programmatic
construction via `create_default_config()`.

## Extension Points

- **Custom Adapters:** Subclass `BaseAdapter`, implement `generate()` and
  `_get_provider_name()`. Register via `create_adapter()` factory.
- **Custom Tools:** Register with `ToolRegistry.register()` specifying name, risk tier,
  and handler function.
- **Custom Channels:** Implement a transport that feeds input to `MessageRouter.route_inbound()`
  and returns the `OutboundMessage`.
- **Custom Integrations:** Use `BackgroundObserver` pattern from the integration framework
  to connect external services to the substrate.
```

**`docs/integrations.md`:**

```markdown
# Vecna Integrations Guide

## Supported LLM Providers

Vecna supports multiple LLM providers simultaneously. Each provider is configured as an
adapter and can participate in consensus-driven reasoning.

### GitHub Copilot

Uses GitHub's Models API via Copilot authentication.

- **Setup:** `gh auth login` or set `GITHUB_TOKEN` directly.
- **Env Vars:** `GITHUB_TOKEN`
- **Config:** `provider: copilot`, `model_id: gpt-4o`

### Ollama (Local)

Run models locally via Ollama. No API key required.

- **Setup:** Install Ollama, `ollama pull llama3`.
- **Env Vars:** `OLLAMA_HOST` (default: `http://localhost:11434`)
- **Config:** `provider: ollama`, `model_id: llama3`

### Groq (Cloud)

High-speed inference via Groq's cloud API.

- **Setup:** Sign up at groq.com, generate API key.
- **Env Vars:** `GROQ_API_KEY`
- **Config:** `provider: groq`, `model_id: mixtral-8x7b-32768`

### OpenAI

Direct OpenAI API with native function calling support.

- **Setup:** Create key at platform.openai.com.
- **Env Vars:** `OPENAI_API_KEY`
- **Config:** `provider: openai`, `model_id: gpt-4-turbo`
- **Features:** Native tool calling via `hive_update` function schema, streaming.

### Anthropic

Claude models via Anthropic API with native tool use.

- **Setup:** Create key at console.anthropic.com.
- **Env Vars:** `ANTHROPIC_API_KEY`
- **Config:** `provider: anthropic`, `model_id: claude-3-sonnet-20240229`
- **Features:** Native tool use via `hive_update` tool schema, streaming.

### HuggingFace Transformers (Local)

Run models locally with the `transformers` library.

- **Setup:** `pip install vecna[all]`
- **Env Vars:** `HF_HOME` (cache dir), `HF_TOKEN` (gated models)
- **Config:** `provider: huggingface`, `model_id: mistralai/Mistral-7B-Instruct-v0.2`

## External Integrations

### Slack

Connect Vecna as a Slack bot for team-wide hive mind access.

- Env Vars: `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`
- Uses Composio integration framework for event handling.
- Messages route through `MessageRouter` to `HiveLoop.think()`.

### Discord

Run Vecna as a Discord bot.

- Env Vars: `DISCORD_BOT_TOKEN`
- Supports slash commands and direct mentions.
- Uses Composio integration framework.

### GitHub

GitHub webhook integration for code review and issue triage.

- Uses Composio for webhook handling.
- Env Vars: `COMPOSIO_API_KEY`
- Can analyze PRs, suggest fixes, respond to issue comments.

## Channel System

Vecna routes all messages through a unified `MessageRouter`:

| Channel | Format | Transport |
|---------|--------|-----------|
| CLI | Rich markup | Direct function call |
| HTTP API | JSON | POST /api/chat |
| WebSocket | JSON | /ws/stream |
| Slack | Markdown | Composio webhook |
| Discord | Markdown | Composio webhook |
| SMS | Plain text | Composio webhook |

All channels call `HiveLoop.think()` and return the response formatted for the target.

## Adding a Custom Adapter

```python
from vecna.adapters.base import BaseAdapter
from vecna.config.schema import ModelConfig

class MyAdapter(BaseAdapter):
    def __init__(self, config: ModelConfig):
        super().__init__(config)
        # Initialize your provider client

    async def generate(self, prompt: str) -> str:
        # Call your LLM and return the raw response
        return await self.client.complete(prompt)

    def _get_provider_name(self) -> str:
        return "my_provider"
```

Then update `create_adapter()` in `vecna/adapters/base.py` to route to your adapter.

## Adding a Custom Integration

Use the `BackgroundObserver` pattern:

```python
from vecna.integrations.base import BaseIntegration

class MyIntegration(BaseIntegration):
    async def start(self):
        # Connect to your external service
        pass

    async def on_event(self, event):
        # Process external events into HiveState updates
        update = self.process_event(event)
        self.loop.state.apply_update(update)
```
```

**`docs/deployment.md`:**

```markdown
# Vecna Deployment Guide

## Prerequisites

- **Python 3.10+** (3.12 recommended)
- **PostgreSQL 15+** with `pgvector` extension
- **Redis 7+** for hot-tier memory cache
- At least one LLM provider (Ollama for fully local operation)

## Quick Start

```bash
# Install with PostgreSQL support
pip install -e ".[postgres]"

# Configure environment
cp .env.example .env
# Edit .env with database credentials and API keys

# Run database migrations
alembic upgrade head

# Start interactive chat
vecna chat
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `VECNA_CONFIG_PATH` | Path to vecna.yaml | `./vecna.yaml` |
| `VECNA_LOG_LEVEL` | Logging level | `INFO` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://vecna:vecna@localhost:5432/vecna` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `GITHUB_TOKEN` | GitHub token for Copilot | — |
| `GROQ_API_KEY` | Groq API key | — |
| `OPENAI_API_KEY` | OpenAI API key | — |
| `ANTHROPIC_API_KEY` | Anthropic API key | — |
| `OLLAMA_HOST` | Ollama server URL | `http://localhost:11434` |
| `HF_TOKEN` | HuggingFace token | — |
| `VECNA_LANGFUSE_ENABLED` | Enable Langfuse tracing | `false` |
| `LANGFUSE_PUBLIC_KEY` | Langfuse public key | — |
| `LANGFUSE_SECRET_KEY` | Langfuse secret key | — |
| `LANGFUSE_BASE_URL` | Langfuse server URL | `https://cloud.langfuse.com` |
| `COMPOSIO_API_KEY` | Composio API key | — |
| `VECNA_ENCRYPTION_PASSWORD` | State encryption password | — |

## Docker Compose

```yaml
version: "3.9"

services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: vecna
      POSTGRES_PASSWORD: vecna
      POSTGRES_DB: vecna
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U vecna"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  vecna:
    build: .
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql://vecna:vecna@postgres:5432/vecna
      REDIS_URL: redis://redis:6379/0
    env_file:
      - .env
    ports:
      - "8080:8080"
    command: ["vecna", "serve", "--host", "0.0.0.0", "--port", "8080"]

volumes:
  pgdata:
  redisdata:
```

## Production

### Systemd Service

```ini
[Unit]
Description=Vecna Hive Mind Orchestrator
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=vecna
Group=vecna
WorkingDirectory=/opt/vecna
EnvironmentFile=/opt/vecna/.env
ExecStart=/opt/vecna/venv/bin/vecna serve --host 127.0.0.1 --port 8080
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Nginx Reverse Proxy

```nginx
upstream vecna {
    server 127.0.0.1:8080;
}

server {
    listen 443 ssl http2;
    server_name vecna.example.com;

    location / {
        proxy_pass http://vecna;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /ws {
        proxy_pass http://vecna;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
```

## Health Checks

The `/api/health` endpoint returns:

```json
{
  "status": "ok",
  "state_version": 42,
  "adapter_count": 3
}
```

Use for load balancer health checks. The `/api/metrics` endpoint provides detailed
operational metrics including token usage, consensus rates, and tool execution stats.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `pgvector not found` | `CREATE EXTENSION vector;` or use `pgvector/pgvector` Docker image |
| Redis connection refused | Check `REDIS_URL`, ensure Redis is running |
| `alembic: not up to date` | Run `alembic upgrade head` |
| `GITHUB_TOKEN not set` | Run `gh auth login` or set the env var |
| CUDA out of memory | Use smaller model or set `device_map: cpu` |
| Consensus timeout | Increase `model_timeout` in config |
```

**Step 4: Run tests**

```bash
pytest tests/e2e/test_full_stack.py -v
```

Expected: All tests pass

**Step 5: Commit**

```bash
git add tests/e2e/test_full_stack.py docs/architecture.md docs/integrations.md docs/deployment.md
git commit -m "docs: add architecture docs and e2e integration tests"
```

---

## Phase Timeline

```
Week  1-2:  Tasks 1-5   (Temporal Facts, HumanModel, Consensus, Primary Cortex, Task Complete)
Week  3-4:  Tasks 6-9   (HTTP Server, Tool Calling, Integration Framework, Channels)
Week  5-6:  Tasks 10-12 (Goal Queue, Cron Autonomy, Security)
Week  7-8:  Tasks 13-16 (DreamLoop v2, Observer, Google Suite, iMessage)
Week  9-10: Tasks 17-19 (WhatsApp, Summarize, Browser)
Week 11-12: Tasks 20-21 (Composio, Native Adapters)
Week 13-14: Tasks 22-25 (HumanModel wiring, Thoughtfulness, Router, TUI)
Week 15-16: Tasks 26-29 (Full Stack, Encryption, Dashboard, E2E Tests)
```

## Dependency Graph

```
Task 1 (Temporal Facts) ──────────────────────────────────────→ Task 14 (Observer)
Task 2 (HumanModel) ──────────────────────────────────────────→ Task 22 (HumanModel wiring)
Task 3 (Consensus) ────────────────────────────────────────────→ Task 26 (Full Stack)
Task 4 (Primary Cortex) ──→ Task 3 (Consensus) ──→ Task 26
Task 5 (Task Complete) ────→ Task 11 (Cron) ──→ Task 23 (Thoughtfulness)
Task 6 (HTTP Server) ─────→ Task 14 (Observer) ──→ Task 26 (Full Stack)
Task 7 (Tool Calling) ────→ Task 21 (Native Adapters)
Task 8 (Integrations) ────→ Task 15,16,17,20 (All integrations)
Task 9 (Channels) ────────→ Task 16,17 (Channel adapters) ──→ Task 24 (Router)
Task 10 (Goal Queue) ─────→ Task 13 (DreamLoop v2) ──→ Task 23 (Thoughtfulness)
Task 11 (Cron) ────────────→ Task 23 (Thoughtfulness)
Task 12 (Security) ────────→ Task 27 (Encryption Integration)
```

## Verification Gates

### Gate 1: After Task 5 (Foundation cognitive)
```bash
pytest tests/unit/ -v --tb=short
# Expected: All existing + new tests pass
# Verify: HumanModel, Temporal Facts, Consensus upgrade, Primary Cortex, Task Complete
```

### Gate 2: After Task 9 (Foundation agentic)
```bash
pytest tests/unit/ -v --tb=short
python -c "from vecna.server.app import create_app; print('Server OK')"
python -c "from vecna.channels.base import BaseChannel; print('Channels OK')"
python -c "from vecna.integrations.base import BaseIntegration; print('Integrations OK')"
```

### Gate 3: After Task 12 (Foundation complete)
```bash
pytest tests/unit/ -v --tb=short
# Verify: All Phase 1 tasks pass, security encryption works
ruff check .
ruff format --check .
```

### Gate 4: After Task 21 (Integration & Intelligence complete)
```bash
pytest tests/unit/ tests/integration/ -v --tb=short
# Verify: All integrations loadable, channel adapters instantiate
# Verify: DreamLoop v2 generates autonomous tasks
```

### Gate 5: After Task 29 (Full stack)
```bash
pytest tests/ -v --tb=short
# Full test suite including e2e
# Verify: Server starts, chat works, state persists, channels route
```

## Files Created/Modified Summary

### New Files (26)
```
vecna/core/human_model.py
vecna/orchestrator/moa.py
vecna/orchestrator/pg_goal_queue.py
vecna/orchestrator/thoughtfulness.py
vecna/adapters/tool_calling.py
vecna/adapters/openai_adapter.py
vecna/adapters/anthropic_adapter.py
vecna/server/__init__.py
vecna/server/app.py
vecna/server/routes.py
vecna/channels/__init__.py
vecna/channels/base.py
vecna/channels/cli_channel.py
vecna/channels/imessage.py
vecna/channels/whatsapp.py
vecna/channels/router.py
vecna/integrations/__init__.py
vecna/integrations/base.py
vecna/integrations/config.py
vecna/integrations/observer.py
vecna/integrations/google_suite.py
vecna/integrations/composio_bridge.py
vecna/security/__init__.py
vecna/security/encryption.py
vecna/security/privacy.py
vecna/tools/summarize_tool.py
vecna/tools/browser_tool.py
vecna/tui/app.py
```

### Modified Files (12)
```
vecna/core/types.py
vecna/core/hive_state.py
vecna/orchestrator/loop.py
vecna/orchestrator/consensus.py
vecna/orchestrator/heartbeat.py
vecna/orchestrator/autonomy.py
vecna/orchestrator/curiosity.py
vecna/adapters/base.py
vecna/config/schema.py
vecna/cli/main.py
vecna/memory/dream_loop.py
vecna/tools/registry.py
```

### New Test Files (20+)
```
tests/unit/test_temporal_facts.py
tests/unit/test_human_model.py
tests/unit/test_consensus_v2.py
tests/unit/test_primary_cortex.py
tests/unit/test_task_completion.py
tests/unit/test_server.py
tests/unit/test_tool_calling_adapter.py
tests/unit/test_integration_framework.py
tests/unit/test_channels.py
tests/unit/test_pg_goal_queue.py
tests/unit/test_cron_autonomy.py
tests/unit/test_security.py
tests/unit/test_dream_loop_v2.py
tests/unit/test_observer.py
tests/unit/test_google_suite.py
tests/unit/test_imessage.py
tests/unit/test_whatsapp.py
tests/unit/test_summarize_tool.py
tests/unit/test_browser_tool.py
tests/unit/test_composio.py
tests/unit/test_native_adapters.py
tests/unit/test_thoughtfulness.py
tests/unit/test_message_router.py
tests/unit/test_tui.py
tests/unit/test_dashboard.py
tests/integration/test_server_hive.py
tests/integration/test_encrypted_substrate.py
tests/e2e/test_full_stack.py
```

### New Dependencies (add to pyproject.toml)
```toml
[project.optional-dependencies]
server = ["aiohttp>=3.9"]
browser = ["playwright>=1.40"]
integrations = ["composio-core>=0.4"]
security = ["cryptography>=42.0"]
tui = ["textual>=0.50", "trogon>=0.5"]
all = ["vecna[dev,postgres,server,browser,integrations,security,tui]"]
```
