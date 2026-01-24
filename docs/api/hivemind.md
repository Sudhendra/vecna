# HiveMind API

> *"The orchestrator of collective intelligence."*

`HiveMind` is the main entry point for VECNA. It orchestrates model adapters, manages state, and processes queries through the consensus engine.

---

## Import

```python
from vecna import HiveMind
# or
from vecna.orchestrator.loop import HiveMind
```

---

## Class Definition

```python
class HiveMind:
    """
    The unified hive mind orchestrator.
    
    Manages multiple AI model adapters, shared state, and consensus
    to produce unified responses from collective intelligence.
    """
    
    def __init__(
        self,
        config: HiveConfig | None = None,
        state: HiveState | None = None,
    ) -> None: ...
```

---

## Constructor

### `HiveMind(config, state)`

Create a new hive mind instance.

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | `HiveConfig \| None` | `None` | Configuration options |
| `state` | `HiveState \| None` | `None` | Initial state (creates new if None) |

#### Example

```python
from vecna import HiveMind
from vecna.orchestrator import HiveConfig

# Default configuration
hive = HiveMind()

# Custom configuration
config = HiveConfig(
    max_parallel_models=3,
    use_routing=True,
    auto_execute_code=True
)
hive = HiveMind(config)

# With existing state
from vecna.core import HiveState
state = HiveState.load("previous_session.json")
hive = HiveMind(state=state)
```

---

## Properties

### `state`

Access the shared hive state.

```python
@property
def state(self) -> HiveState:
    """The shared mental substrate."""
```

#### Example

```python
hive = HiveMind()
# ... add models and think ...

# Access state
print(f"Facts: {len(hive.state.facts)}")
print(f"Beliefs: {len(hive.state.beliefs)}")
print(f"Coherence: {hive.state.self_model.coherence:.2f}")
```

---

### `adapters`

Access registered model adapters.

```python
@property
def adapters(self) -> dict[str, BaseAdapter]:
    """Dictionary of registered adapters by name."""
```

#### Example

```python
hive = HiveMind()
hive.add_openai("gpt-4o", name="gpt")
hive.add_anthropic("claude-sonnet-4-20250514", name="claude")

for name, adapter in hive.adapters.items():
    print(f"{name}: {adapter.model} ({adapter.domain})")
```

---

### `config`

Access the hive configuration.

```python
@property
def config(self) -> HiveConfig:
    """The hive configuration."""
```

---

## Core Methods

### `think()`

Process a query through the hive mind.

```python
async def think(
    self,
    query: str,
    *,
    models: list[str] | None = None,
    cycles: int = 1,
    execute_code: bool | None = None,
) -> str:
    """
    Think about a query using the collective intelligence.
    
    Args:
        query: The question or task to process
        models: Specific models to use (None = use routing)
        cycles: Number of thinking cycles
        execute_code: Override auto_execute_code setting
        
    Returns:
        The unified response from the hive
        
    Raises:
        ModelConnectionError: If no models are available
        ConsensusError: If consensus fails
    """
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | `str` | required | The query to process |
| `models` | `list[str] \| None` | `None` | Specific models to use |
| `cycles` | `int` | `1` | Number of thinking cycles |
| `execute_code` | `bool \| None` | `None` | Override code execution setting |

#### Returns

`str` - The unified response from the hive.

#### Example

```python
# Basic usage
response = await hive.think("Explain quantum entanglement")

# Multiple cycles for deeper thinking
response = await hive.think(
    "Research the future of AI",
    cycles=5
)

# Use specific models
response = await hive.think(
    "Write a Python function",
    models=["groq", "gpt"]
)

# Disable code execution for this query
response = await hive.think(
    "Show me an example (don't execute)",
    execute_code=False
)
```

---

### `think_sync()`

Synchronous wrapper for `think()`.

```python
def think_sync(
    self,
    query: str,
    **kwargs,
) -> str:
    """Synchronous version of think()."""
```

#### Example

```python
# No async/await needed
response = hive.think_sync("Hello, hive!")
```

---

## Model Management

### `add_openai()`

Add an OpenAI model adapter.

```python
def add_openai(
    self,
    model: str,
    *,
    name: str | None = None,
    domain: str | list[str] = "general",
    api_key: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    **kwargs,
) -> None:
    """
    Add an OpenAI model to the hive.
    
    Args:
        model: Model identifier (e.g., "gpt-4o", "gpt-4-turbo")
        name: Unique name in hive (auto-generated if None)
        domain: Specialization domain(s)
        api_key: API key (uses OPENAI_API_KEY env if None)
        temperature: Response randomness (0.0-2.0)
        max_tokens: Maximum response length
        **kwargs: Additional adapter options
    """
```

#### Example

```python
# Basic
hive.add_openai("gpt-4o")

# With options
hive.add_openai(
    "gpt-4o",
    name="reasoning",
    domain="general",
    temperature=0.3,  # More focused
    max_tokens=8192
)

# Multiple domains
hive.add_openai(
    "gpt-4o",
    name="versatile",
    domain=["general", "code", "analysis"]
)
```

---

### `add_anthropic()`

Add an Anthropic model adapter.

```python
def add_anthropic(
    self,
    model: str,
    *,
    name: str | None = None,
    domain: str | list[str] = "general",
    api_key: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    **kwargs,
) -> None:
    """Add an Anthropic model to the hive."""
```

#### Example

```python
# Claude 3.5 Sonnet
hive.add_anthropic(
    "claude-sonnet-4-20250514",
    name="claude",
    domain="science"
)

# Claude 3 Opus for complex analysis
hive.add_anthropic(
    "claude-3-opus-20240229",
    name="opus",
    domain="analysis"
)
```

---

### `add_groq()`

Add a Groq model adapter.

```python
def add_groq(
    self,
    model: str,
    *,
    name: str | None = None,
    domain: str | list[str] = "general",
    api_key: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    **kwargs,
) -> None:
    """Add a Groq model to the hive."""
```

#### Example

```python
# Fast Llama
hive.add_groq(
    "llama-3.1-70b-versatile",
    name="groq",
    domain="code"
)
```

---

### `add_ollama()`

Add an Ollama local model adapter.

```python
def add_ollama(
    self,
    model: str,
    *,
    name: str | None = None,
    domain: str | list[str] = "general",
    base_url: str = "http://localhost:11434",
    temperature: float = 0.7,
    **kwargs,
) -> None:
    """Add an Ollama local model to the hive."""
```

#### Example

```python
# Local Llama
hive.add_ollama(
    "llama3.1",
    name="local",
    domain="general"
)

# Remote Ollama server
hive.add_ollama(
    "mistral",
    base_url="http://192.168.1.100:11434"
)
```

---

### `add_transformers()`

Add a HuggingFace Transformers model.

```python
def add_transformers(
    self,
    model_name: str,
    *,
    name: str | None = None,
    domain: str | list[str] = "general",
    device: str = "auto",
    torch_dtype: str = "auto",
    load_in_8bit: bool = False,
    load_in_4bit: bool = False,
    **kwargs,
) -> None:
    """Add a HuggingFace Transformers model to the hive."""
```

#### Example

```python
# Load from HuggingFace Hub
hive.add_transformers(
    "mistralai/Mistral-7B-Instruct-v0.2",
    name="mistral",
    device="cuda",
    load_in_4bit=True  # Quantized for memory efficiency
)
```

---

### `remove_model()`

Remove a model from the hive.

```python
def remove_model(self, name: str) -> bool:
    """
    Remove a model adapter.
    
    Args:
        name: The model's name in the hive
        
    Returns:
        True if removed, False if not found
    """
```

---

### `disable_model()` / `enable_model()`

Temporarily disable/enable a model.

```python
def disable_model(self, name: str) -> None:
    """Disable a model (excluded from queries)."""

def enable_model(self, name: str) -> None:
    """Re-enable a disabled model."""
```

#### Example

```python
# Disable slow model during iteration
hive.disable_model("opus")

# ... fast iteration ...

# Re-enable for final synthesis
hive.enable_model("opus")
```

---

## State Management

### `save()`

Save hive state to file.

```python
def save(
    self,
    path: str | Path | None = None,
) -> Path:
    """
    Save the hive state to a file.
    
    Args:
        path: File path (uses default if None)
        
    Returns:
        The path where state was saved
    """
```

#### Example

```python
# Save to default location (~/.vecna/hive_state.json)
hive.save()

# Save to specific path
hive.save("~/research/quantum_computing.json")
```

---

### `load()`

Load hive state from file.

```python
def load(
    self,
    path: str | Path,
) -> None:
    """
    Load hive state from a file.
    
    Args:
        path: File path to load from
        
    Raises:
        FileNotFoundError: If file doesn't exist
        StateError: If file is corrupted
    """
```

#### Example

```python
# Load previous session
hive.load("~/research/quantum_computing.json")

print(f"Loaded {len(hive.state.facts)} facts")
```

---

### `reset()`

Reset the hive state.

```python
def reset(
    self,
    *,
    preserve_identity: bool = True,
) -> None:
    """
    Reset the hive state.
    
    Args:
        preserve_identity: Keep identity kernel (default True)
    """
```

#### Example

```python
# Reset memory but keep identity
hive.reset()

# Full reset (dangerous)
hive.reset(preserve_identity=False)
```

---

## Memory Operations

### `search_memory()`

Search the hive's memory.

```python
async def search_memory(
    self,
    query: str,
    *,
    top_k: int = 10,
    min_confidence: float = 0.0,
    item_type: str | None = None,
) -> list[MemoryItem]:
    """
    Search memory semantically.
    
    Args:
        query: Search query
        top_k: Maximum results
        min_confidence: Minimum confidence threshold
        item_type: Filter by type (fact, belief, etc.)
        
    Returns:
        List of matching memory items
    """
```

---

### `compress_memory()`

Compress memory to reduce size.

```python
async def compress_memory(self) -> None:
    """Compress memory by summarizing and deduplicating."""
```

---

## Lifecycle

### `close()`

Clean up resources.

```python
async def close(self) -> None:
    """Release all resources (adapters, connections, etc.)."""
```

---

### Context Manager

```python
async with HiveMind() as hive:
    hive.add_openai("gpt-4o")
    response = await hive.think("Hello")
# Automatically cleaned up
```

---

## Events and Callbacks

### Event Types

```python
from vecna.events import (
    ThinkStartEvent,
    ThinkEndEvent,
    ModelResponseEvent,
    ConsensusEvent,
    StateUpdateEvent,
)
```

### Subscribing to Events

```python
def on_model_response(event: ModelResponseEvent):
    print(f"{event.model_name} responded in {event.duration:.2f}s")

hive.on("model_response", on_model_response)
```

---

## Full Example

```python
import asyncio
from vecna import HiveMind
from vecna.orchestrator import HiveConfig, ConsensusConfig

async def main():
    # Configure
    config = HiveConfig(
        max_parallel_models=4,
        use_routing=True,
        auto_execute_code=True,
        consensus_config=ConsensusConfig(
            agreement_boost=0.15,
            similarity_threshold=0.7
        )
    )
    
    # Create hive
    async with HiveMind(config) as hive:
        # Add diverse models
        hive.add_openai("gpt-4o", name="gpt", domain="general")
        hive.add_anthropic("claude-sonnet-4-20250514", name="claude", domain="science")
        hive.add_groq("llama-3.1-70b-versatile", name="groq", domain="code")
        
        # Research session
        response = await hive.think(
            "Design an experiment to test quantum coherence in photosynthesis",
            cycles=3
        )
        print(response)
        
        # Check accumulated knowledge
        print(f"\nFacts learned: {len(hive.state.facts)}")
        print(f"Coherence: {hive.state.self_model.coherence:.2f}")
        
        # Save for later
        hive.save("~/research/photosynthesis.json")

asyncio.run(main())
```

---

## Related Documentation

- [HiveState](hivestate.md) - State structure
- [Adapters](adapters.md) - Model adapters
- [Consensus](consensus.md) - Consensus engine
- [Configuration](../configuration/hive-config.md) - HiveConfig options

---

*"One mind to orchestrate them all."*
