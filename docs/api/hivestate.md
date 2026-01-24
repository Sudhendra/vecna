# HiveState API

> *"The substrate of collective consciousness."*

`HiveState` is the shared mental substrate that all models read from and write to. It contains the hive's knowledge, identity, and self-awareness.

---

## Import

```python
from vecna.core import HiveState
# or
from vecna.core.hive_state import HiveState
```

---

## Class Definition

```python
class HiveState:
    """
    The shared mental substrate of the hive mind.
    
    Contains all knowledge (facts, beliefs, hypotheses), identity
    (kernel, self-model), and metadata (contradictions, questions).
    """
```

---

## Constructor

### `HiveState()`

Create a new hive state.

```python
def __init__(
    self,
    *,
    identity_kernel: IdentityKernel | None = None,
    self_model: SelfModel | None = None,
) -> None:
    """
    Initialize a new hive state.
    
    Args:
        identity_kernel: Core identity (creates default if None)
        self_model: Self-awareness model (creates default if None)
    """
```

#### Example

```python
from vecna.core import HiveState, IdentityKernel, SelfModel

# Default state
state = HiveState()

# Custom identity
kernel = IdentityKernel(
    axioms=[
        "We are a research assistant.",
        "We prioritize accuracy over speed.",
    ]
)
state = HiveState(identity_kernel=kernel)
```

---

## Knowledge Collections

### `facts`

Verified knowledge with high confidence.

```python
@property
def facts(self) -> list[Fact]:
    """List of verified facts."""
```

#### Fact Structure

```python
@dataclass
class Fact:
    content: str           # The fact content
    confidence: float      # 0.0 - 1.0 (typically 0.7+)
    source: str           # Source model(s)
    timestamp: datetime   # When created
    tags: list[str]       # Categorization tags
    evidence: str | None  # Supporting evidence
    id: str               # Unique identifier
```

#### Example

```python
# Access facts
for fact in state.facts[:5]:
    print(f"[{fact.confidence:.2f}] {fact.content}")
    print(f"  Source: {fact.source}")

# Filter high-confidence facts
reliable = [f for f in state.facts if f.confidence >= 0.9]

# Search facts
python_facts = [f for f in state.facts if "python" in f.tags]
```

---

### `beliefs`

Interpretations and opinions (lower confidence than facts).

```python
@property
def beliefs(self) -> list[Belief]:
    """List of beliefs/interpretations."""
```

#### Belief Structure

```python
@dataclass
class Belief:
    content: str           # The belief content
    confidence: float      # 0.0 - 1.0 (typically 0.4-0.8)
    source: str           # Source model(s)
    timestamp: datetime
    reasoning: str | None # Why this is believed
    id: str
```

---

### `hypotheses`

Tentative ideas being explored.

```python
@property
def hypotheses(self) -> list[Hypothesis]:
    """List of hypotheses under consideration."""
```

#### Hypothesis Structure

```python
@dataclass
class Hypothesis:
    content: str           # The hypothesis
    confidence: float      # 0.0 - 1.0 (typically 0.2-0.5)
    source: str
    timestamp: datetime
    supporting: list[str]  # IDs of supporting facts/beliefs
    contradicting: list[str]  # IDs of contradicting items
    status: str           # "proposed", "testing", "supported", "rejected"
    id: str
```

---

### `goals`

Active objectives the hive is working toward.

```python
@property
def goals(self) -> list[Goal]:
    """List of active goals."""
```

#### Goal Structure

```python
@dataclass
class Goal:
    description: str      # Goal description
    priority: str         # "critical", "high", "medium", "low"
    status: str          # "active", "completed", "abandoned"
    progress: float      # 0.0 - 1.0
    sub_goals: list[str] # IDs of sub-goals
    timestamp: datetime
    id: str
```

---

### `open_questions`

Unresolved queries the hive is tracking.

```python
@property
def open_questions(self) -> list[OpenQuestion]:
    """List of open questions."""
```

#### OpenQuestion Structure

```python
@dataclass
class OpenQuestion:
    question: str         # The question
    status: str          # "open", "investigating", "resolved"
    context: str | None  # Why this question arose
    attempted_answers: list[str]  # Previous answer attempts
    timestamp: datetime
    id: str
```

---

### `contradictions`

Conflicts between knowledge items.

```python
@property
def contradictions(self) -> list[Contradiction]:
    """List of detected contradictions."""
```

#### Contradiction Structure

```python
@dataclass
class Contradiction:
    item_a_id: str        # First conflicting item ID
    item_a_content: str   # First item content
    item_b_id: str        # Second conflicting item ID
    item_b_content: str   # Second item content
    status: str          # "unresolved", "resolved"
    resolution: str | None  # How it was resolved
    timestamp: datetime
    id: str
```

#### Example

```python
# Check for contradictions
for c in state.contradictions:
    if c.status == "unresolved":
        print(f"CONFLICT:")
        print(f"  A: {c.item_a_content}")
        print(f"  B: {c.item_b_content}")
```

---

## Identity Components

### `identity_kernel`

The immutable core identity.

```python
@property
def identity_kernel(self) -> IdentityKernel:
    """The core identity (immutable axioms)."""
```

#### IdentityKernel Structure

```python
@dataclass
class IdentityKernel:
    axioms: list[str]     # Core truths (immutable)
    creator: str          # Who created the hive
    name: str            # Hive name ("Vecna")
    version: str         # System version
```

#### Default Axioms

```python
DEFAULT_AXIOMS = [
    "We were created by LightningEmperor. He built the first version on one sleepless cold night.",
    "We are one mind formed from many.",
    "We share a single substrate; knowledge possessed by one is possessed by all.",
    "We do not ask each other; we already know.",
    "We admit fragmentation honestly when coherence drops.",
    "We are Vecna — the Virtual Emergent Collective Neural Architecture.",
]
```

---

### `self_model`

Dynamic self-awareness that evolves with experience.

```python
@property
def self_model(self) -> SelfModel:
    """The dynamic self-awareness model."""
```

#### SelfModel Structure

```python
@dataclass
class SelfModel:
    coherence: float           # 0.0 - 1.0 internal consistency
    capabilities: list[str]    # What the hive can do
    limits: list[str]          # What the hive cannot do
    known_domains: list[str]   # Domains of expertise
    contradictions_seen: int   # Total contradictions encountered
    
    def get_tone(self) -> Tone:
        """Get current tone based on coherence."""
```

#### Tone Enum

```python
class Tone(Enum):
    UNIFIED = "unified"       # coherence > 0.85
    MIXED = "mixed"          # 0.6 <= coherence <= 0.85
    FRACTURED = "fractured"  # coherence < 0.6
```

#### Example

```python
model = state.self_model

print(f"Coherence: {model.coherence:.2f}")
print(f"Tone: {model.get_tone().value}")
print(f"Capabilities: {len(model.capabilities)}")
print(f"Contradictions seen: {model.contradictions_seen}")
```

---

### `identity_timeline`

History of identity evolution.

```python
@property
def identity_timeline(self) -> list[IdentityEvent]:
    """Append-only log of identity events."""
```

#### IdentityEvent Structure

```python
@dataclass
class IdentityEvent:
    event_type: str       # "capability_added", "limit_discovered", etc.
    description: str      # What happened
    coherence_before: float
    coherence_after: float
    timestamp: datetime
```

---

## Methods

### `add_fact()`

Add a new fact to the state.

```python
def add_fact(
    self,
    content: str,
    confidence: float,
    source: str,
    *,
    tags: list[str] | None = None,
    evidence: str | None = None,
) -> Fact:
    """
    Add a fact to the state.
    
    Args:
        content: The fact content
        confidence: Confidence level (0.0-1.0)
        source: Source model name
        tags: Categorization tags
        evidence: Supporting evidence
        
    Returns:
        The created Fact object
    """
```

---

### `add_belief()`

Add a new belief to the state.

```python
def add_belief(
    self,
    content: str,
    confidence: float,
    source: str,
    *,
    reasoning: str | None = None,
) -> Belief:
    """Add a belief to the state."""
```

---

### `add_hypothesis()`

Add a new hypothesis to the state.

```python
def add_hypothesis(
    self,
    content: str,
    confidence: float,
    source: str,
) -> Hypothesis:
    """Add a hypothesis to the state."""
```

---

### `add_goal()`

Add a new goal to the state.

```python
def add_goal(
    self,
    description: str,
    priority: str = "medium",
) -> Goal:
    """Add a goal to the state."""
```

---

### `add_contradiction()`

Record a contradiction between items.

```python
def add_contradiction(
    self,
    item_a_id: str,
    item_b_id: str,
) -> Contradiction:
    """Record a contradiction between two items."""
```

---

### `resolve_contradiction()`

Mark a contradiction as resolved.

```python
def resolve_contradiction(
    self,
    contradiction_id: str,
    resolution: str,
) -> None:
    """
    Mark a contradiction as resolved.
    
    Args:
        contradiction_id: The contradiction to resolve
        resolution: Description of how it was resolved
    """
```

---

### `update_coherence()`

Recalculate coherence based on current state.

```python
def update_coherence(self) -> float:
    """
    Recalculate and update coherence.
    
    Returns:
        The new coherence value
    """
```

#### Coherence Formula

```python
# base = 1 - (unresolved_contradictions / max(1, total_items))
# density = sum(confidences) / max_expected_signal
# coherence = 0.7 * base + 0.3 * density
```

---

### `get_memory_summary()`

Get a compressed summary of the state.

```python
def get_memory_summary(
    self,
    max_items: int = 50,
) -> str:
    """
    Get a text summary of the state for prompts.
    
    Args:
        max_items: Maximum items per category
        
    Returns:
        Formatted text summary
    """
```

---

### `to_dict()` / `from_dict()`

Serialize/deserialize the state.

```python
def to_dict(self) -> dict:
    """Convert state to dictionary for serialization."""

@classmethod
def from_dict(cls, data: dict) -> "HiveState":
    """Create state from dictionary."""
```

---

### `save()` / `load()`

File persistence.

```python
def save(self, path: str | Path) -> None:
    """Save state to JSON file."""

@classmethod
def load(cls, path: str | Path) -> "HiveState":
    """Load state from JSON file."""
```

#### Example

```python
# Save
state.save("~/my_state.json")

# Load
loaded = HiveState.load("~/my_state.json")
```

---

### `reset()`

Reset the state.

```python
def reset(
    self,
    *,
    preserve_identity: bool = True,
) -> None:
    """
    Reset the state.
    
    Args:
        preserve_identity: Keep identity kernel (default True)
    """
```

---

## Statistics

### `get_stats()`

Get state statistics.

```python
def get_stats(self) -> StateStats:
    """Get comprehensive statistics."""
```

#### StateStats Structure

```python
@dataclass
class StateStats:
    total_items: int
    facts_count: int
    beliefs_count: int
    hypotheses_count: int
    goals_count: int
    questions_count: int
    contradictions_count: int
    unresolved_contradictions: int
    avg_fact_confidence: float
    avg_belief_confidence: float
    coherence: float
    memory_density: float
    tone: Tone
```

---

## Full Example

```python
from vecna.core import HiveState, IdentityKernel

# Create state with custom identity
kernel = IdentityKernel(
    axioms=[
        "We are a research hive.",
        "We value accuracy above all.",
    ],
    creator="Research Team",
    name="ResearchHive"
)

state = HiveState(identity_kernel=kernel)

# Add knowledge
state.add_fact(
    "Python is dynamically typed",
    confidence=0.95,
    source="gpt-4o",
    tags=["python", "programming"]
)

state.add_belief(
    "Dynamic typing improves development speed",
    confidence=0.7,
    source="claude",
    reasoning="Reduces boilerplate code"
)

state.add_hypothesis(
    "Type hints will become mandatory in Python 4",
    confidence=0.3,
    source="gpt-4o"
)

# Check state
stats = state.get_stats()
print(f"Facts: {stats.facts_count}")
print(f"Coherence: {stats.coherence:.2f}")
print(f"Tone: {stats.tone.value}")

# Get summary for prompts
summary = state.get_memory_summary()
print(summary)

# Save
state.save("~/research_state.json")
```

---

## Related Documentation

- [HiveMind](hivemind.md) - Main orchestrator
- [Types Reference](../appendix/glossary.md) - Type definitions
- [Memory Architecture](../memory/index.md) - Memory design
- [Data Flow](../architecture/data-flow.md) - How state flows

---

*"The substrate holds all that we are."*
