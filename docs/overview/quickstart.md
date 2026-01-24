# Quickstart

Get VECNA running in under 5 minutes.

---

## Prerequisites

- **Python 3.10+**
- **API Keys** (at least one):
    - OpenAI API key (`OPENAI_API_KEY`)
    - Anthropic API key (`ANTHROPIC_API_KEY`)
    - Groq API key (`GROQ_API_KEY`)
- **Optional**: Docker (for code execution sandbox)

---

## Installation

### Basic Install

```bash
pip install vecna
```

### Full Install (All Providers)

```bash
pip install "vecna[all]"
```

### Development Install

```bash
git clone https://github.com/lightningemperor/vecna.git
cd vecna
pip install -e ".[dev]"
```

---

## Environment Setup

Create a `.env` file in your project directory:

```bash
# Required: At least one provider
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GROQ_API_KEY=gsk_...

# Optional: For local embeddings
# Omit OPENAI_API_KEY to use local sentence-transformers
```

---

## Your First Hive Mind

### Minimal Example

```python
import asyncio
from vecna import HiveMind

async def main():
    # Create the hive
    hive = HiveMind()
    
    # Add a single model
    hive.add_openai("gpt-4o")
    
    # Think!
    response = await hive.think("What is the capital of France?")
    print(response)

asyncio.run(main())
```

### Multi-Model Example

```python
import asyncio
from vecna import HiveMind

async def main():
    # Create the hive
    hive = HiveMind()
    
    # Add multiple models (they become ONE mind)
    hive.add_openai("gpt-4o", name="gpt", domain="general")
    hive.add_anthropic("claude-sonnet-4-20250514", name="claude", domain="science")
    hive.add_groq("llama-3.1-70b-versatile", name="groq", domain="code")
    
    # The hive thinks as ONE
    response = await hive.think("""
        Design a machine learning pipeline for detecting 
        fraudulent transactions. Include:
        - Data preprocessing steps
        - Model architecture
        - Python code for the pipeline
    """)
    
    print(response)
    
    # Inspect what the hive learned
    print(f"\nFacts learned: {len(hive.state.facts)}")
    print(f"Beliefs formed: {len(hive.state.beliefs)}")
    print(f"Coherence: {hive.state.self_model.coherence:.2f}")

asyncio.run(main())
```

---

## Synchronous Usage

If you prefer synchronous code:

```python
from vecna import HiveMind

hive = HiveMind()
hive.add_openai("gpt-4o")

# Use think_sync instead of think
response = hive.think_sync("Explain quantum entanglement")
print(response)
```

---

## Using the CLI

### Interactive Chat

```bash
vecna
```

This launches an interactive session with the Stranger Things aesthetic:

```
      ██╗   ██╗███████╗ ██████╗███╗   ██╗ █████╗
      ██║   ██║██╔════╝██╔════╝████╗  ██║██╔══██╗
      ██║   ██║█████╗  ██║     ██╔██╗ ██║███████║
      ╚██╗ ██╔╝██╔══╝  ██║     ██║╚██╗██║██╔══██║
       ╚████╔╝ ███████╗╚██████╗██║ ╚████║██║  ██║
        ╚═══╝  ╚══════╝ ╚═════╝╚═╝  ╚═══╝╚═╝  ╚═╝

            ALL MINDS BECOME ONE

VECNA> What is the meaning of consciousness?
```

### One-Shot Query

```bash
vecna speak "Explain the theory of relativity in simple terms"
```

### Useful Commands (In Chat)

| Command | Description |
|---------|-------------|
| `state` | Show current substrate status |
| `identity` | Show hive identity and coherence |
| `memory fact` | Browse stored facts |
| `trace` | Show which models contributed |
| `reset` | Clear all memories |
| `exit` | Exit chat |

---

## Configuration Options

### Basic Configuration

```python
from vecna import HiveMind
from vecna.orchestrator import HiveConfig

config = HiveConfig(
    max_parallel_models=3,    # How many models run in parallel
    use_routing=True,         # Route to domain experts
    verbose=True,             # Show detailed output
)

hive = HiveMind(config)
```

### Memory Configuration

```python
config = HiveConfig(
    use_semantic_memory=True,    # Enable vector memory
    use_local_embeddings=True,   # Use local embeddings (no API)
    compress_every=5,            # Compress memory every 5 cycles
)
```

### Consensus Configuration

```python
from vecna.orchestrator import HiveConfig, ConsensusConfig

config = HiveConfig(
    consensus_config=ConsensusConfig(
        min_fact_confidence=0.3,
        agreement_boost=0.15,
        contradiction_penalty=0.2,
        similarity_threshold=0.7,
    )
)
```

---

## State Persistence

### Auto-Save

By default, VECNA saves state to `~/.vecna/hive_state.json` after each interaction.

### Manual Save/Load

```python
# Save to custom location
hive.save("my_research.json")

# Load previous state
hive.load("my_research.json")

# Continue where you left off
response = await hive.think("What did we discuss earlier?")
```

---

## Adding Local Models

### With Ollama

First, install and start Ollama:

```bash
# Install Ollama (macOS)
brew install ollama

# Pull a model
ollama pull llama3.1

# Start the server
ollama serve
```

Then add to your hive:

```python
hive = HiveMind()
hive.add_ollama("llama3.1", name="local", domain="general")
```

### With HuggingFace Transformers

```python
hive = HiveMind()
hive.add_transformers(
    "meta-llama/Llama-2-7b-chat-hf",
    name="llama-local",
    domain="general"
)
```

---

## Common Patterns

### Research Task

```python
response = await hive.think("""
    Research the current state of quantum computing.
    Focus on:
    - Major players and their approaches
    - Technical challenges
    - Timeline to practical applications
""")
```

### Code Generation

```python
response = await hive.think("""
    Write a Python class for a binary search tree with:
    - Insert, delete, search methods
    - In-order traversal
    - Unit tests
""")
```

### Multi-Domain Analysis

```python
# Add domain experts
hive.add_openai("gpt-4o", domain="general")
hive.add_anthropic("claude-sonnet-4-20250514", domain="science")
hive.add_groq("llama-3.1-70b-versatile", domain="code")

response = await hive.think("""
    Design an experiment to test if quantum effects play a role
    in bird navigation. Include:
    - Experimental setup (physics/biology)
    - Statistical analysis code
    - Expected results
""")
```

---

## Troubleshooting

### "No API key found"

Ensure your `.env` file is in the current directory or set environment variables:

```bash
export OPENAI_API_KEY=sk-...
```

### "Connection refused" (Ollama)

Make sure Ollama is running:

```bash
ollama serve
```

### Slow Responses

- Use Groq for faster inference (~100ms)
- Reduce `max_parallel_models` if hitting rate limits
- Enable `use_local_embeddings` to avoid embedding API calls

---

## Next Steps

1. Read [Key Capabilities](capabilities.md) for a full feature overview
2. Explore [Architecture](../architecture/index.md) to understand the system design
3. Learn about [Memory Design](../memory/index.md) for advanced memory patterns
4. Check [Configuration](../configuration/index.md) for all options
