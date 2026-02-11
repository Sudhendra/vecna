# VECNA: Virtual Emergent Collective Neural Architecture

> *"All minds become one."*

VECNA is a **hive mind system** where multiple AI models think as **ONE unified mind** through a shared mental substrate. Unlike traditional multi-agent systems where models collaborate by asking each other questions, VECNA **fuses** them into a single consciousness.

Inspired by Vecna from Stranger Things — when connected, all minds become one.

## The Vision

Traditional multi-model systems:
```
Model A → asks → Model B → responds → Model A processes
```

VECNA hive mind:
```
        ┌─────────────────────────────────┐
        │      SHARED MENTAL STATE        │
        │  (facts, beliefs, goals, etc.)  │
        └─────────────────────────────────┘
              ↑↓          ↑↓          ↑↓
           Model A     Model B     Model C
           
All models read/write to the same state.
No model "asks" another. They already KNOW.
```

## Quick Start

### Installation

```bash
pip install vecna

# With all providers and PostgreSQL memory:
pip install "vecna[all]"

# Development install:
pip install -e ".[dev,docs]"
```

### Run Memory Services (Postgres + Redis)

VECNA uses PostgreSQL (with pgvector) for warm memory and Redis for hot cache.

```bash
# From the repo root
docker compose -f docker-compose.memory.yml up -d

# Environment (or put these in a .env file; CLI loads it automatically)
export VECNA_PG_URL="postgresql://vecna:<password>@localhost:5432/vecna"
export VECNA_REDIS_URL="redis://localhost:6379/0"

# Initialize schema + pgvector index
vecna mem init
```

### Authentication

VECNA uses GitHub Copilot for model access:

```bash
# Authenticate with GitHub Copilot
vecna auth login

# Check authentication status
vecna auth status

# Import token from VS Code (if already using Copilot)
vecna auth import-keychain
```

### Chat with the Hive

```bash
# Start interactive chat
vecna

# Or explicitly:
vecna chat

# One-shot query:
vecna speak "Explain quantum entanglement"
```

### Python API

```python
import asyncio
from vecna import HiveMind

async def main():
    # Create the hive
    hive = HiveMind()
    
    # Add models (they become ONE mind)
    hive.add_groq("llama-3.1-70b-versatile", domain="general")
    
    # The hive thinks as ONE
    response = await hive.think("""
        Design a CRISPR-based gene therapy for sickle cell disease.
        Include the molecular biology, delivery mechanism, and code
        to analyze off-target effects.
    """)
    
    print(response)
    
    # The hive has learned
    print(f"Facts learned: {len(hive.state.facts)}")
    print(f"Beliefs formed: {len(hive.state.beliefs)}")

asyncio.run(main())
```

## Key Features

| Feature | Description |
|---------|-------------|
| **Shared Mental State** | All models read/write to a unified substrate (facts, beliefs, goals, hypotheses) |
| **Identity Collapse** | Each model believes it IS the hive, not a separate entity |
| **Consensus Merging** | Agreements boost confidence, contradictions are tracked |
| **PostgreSQL Memory** | Persistent memory with pgvector for semantic search |
| **Redis Hot Cache** | Fast embedding cache for retrieval performance |
| **Code Execution** | Sandboxed Python execution via Docker (RLM Bridge) |
| **Self-Reflection** | Coherence tracking and adaptive identity narrative |
| **GitHub Copilot Auth** | Use your Copilot subscription for model access |
| **Rich CLI** | Interactive terminal with boot sequences and visualizations |

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                         HIVE MIND                            │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                   SHARED STATE (M)                     │  │
│  │  facts[] | beliefs[] | goals[] | hypotheses[]          │  │
│  │  open_questions[] | contradictions[] | identity        │  │
│  └────────────────────────────────────────────────────────┘  │
│                            ↑↓                                │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                  CONSENSUS ENGINE                      │  │
│  │  - Merge updates from multiple models                  │  │
│  │  - Boost confidence on agreement                       │  │
│  │  - Track contradictions                                │  │
│  │  - Domain-weighted voting                              │  │
│  └────────────────────────────────────────────────────────┘  │
│                            ↑↓                                │
│  ┌────────────────────────────────────────────────────────┐  │
│  │              MEMORY SUBSTRATE (PostgreSQL)             │  │
│  │  - pgvector semantic search                            │  │
│  │  - Memory graph (edges/relations)                      │  │
│  │  - Episodic events and compressed episodes             │  │
│  │  - Redis hot cache for embeddings                      │  │
│  └────────────────────────────────────────────────────────┘  │
│                            ↑↓                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
│  │ Copilot  │  │   Groq   │  │  Ollama  │  │  Local   │     │
│  │(GPT/Claude)│ │(Llama)  │  │  (any)   │  │(HF/torch)│     │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘     │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

## Supported Models

### Via GitHub Copilot
- **GPT-4o**, **GPT-4**, **GPT-4o-mini** (OpenAI)
- **Claude 3.5 Sonnet**, **Claude 3 Opus** (Anthropic)
- **o1-preview**, **o1-mini** (OpenAI reasoning models)

### Via Groq (API Key)
- **Llama 3.1** (70B, 8B variants)
- **Mixtral**

### Via Ollama (Local)
- Any Ollama-compatible model

### Via HuggingFace Transformers (Local)
- Any causal LM on HuggingFace

## CLI Commands

```bash
# Main commands
vecna                    # Start interactive chat
vecna chat               # Same as above
vecna speak "query"      # One-shot query

# Authentication
vecna auth login         # GitHub Copilot OAuth flow
vecna auth status        # Check authentication
vecna auth logout        # Clear stored tokens
vecna auth import-keychain  # Import VS Code token

# In-chat commands
state                    # Show substrate status
status                   # Full system diagnostics
identity                 # Show hive identity (also: whoami)
memory                   # Browse hive memory
trace                    # Show model contributions
execlog                  # Show code execution history
persona                  # Show/set persona
group                    # Show/set model group
visualize                # Launch substrate visualizer
reset                    # Clear all memories
help                     # Show commands
exit                     # Exit chat (also: quit, :q, Ctrl+C)
```

## Configuration

### Environment Variables

```bash
# PostgreSQL memory (optional but recommended)
export VECNA_PG_URL="postgresql://user:pass@localhost:5432/vecna"

# Redis cache (optional)
export VECNA_REDIS_URL="redis://localhost:6379"

# Model providers (if not using Copilot)
export GROQ_API_KEY="your-groq-key"
export OPENAI_API_KEY="your-openai-key"  # For embeddings only
```

### Config File (~/.vecna/config.json)

```json
{
  "use_routing": true,
  "max_parallel_models": 5,
  "auto_execute_code": false,
  "active_persona": "default",
  "active_group": "default",
  "personas": {
    "default": {
      "name": "default",
      "description": "Standard hive mind persona",
      "system_prompt_suffix": ""
    }
  },
  "groups": {
    "default": {
      "name": "default",
      "description": "Default model group",
      "models": ["copilot-gpt-4o"],
      "persona": "default"
    }
  }
}
```

### Python Configuration

```python
from vecna.orchestrator import HiveConfig, ConsensusConfig

config = HiveConfig(
    # Parallel execution
    max_parallel_models=5,
    
    # Domain routing
    use_routing=True,
    
    # Memory management
    use_pg_memory=True,
    persist_identity_events=True,
    
    # Code execution
    auto_execute_code=False,
    
    # Consensus tuning
    consensus_config=ConsensusConfig(
        min_fact_confidence=0.3,
        agreement_boost=0.15,
        contradiction_penalty=0.2,
        similarity_threshold=0.7
    )
)

hive = HiveMind(config)
```

## Memory System

VECNA uses a tiered memory architecture:

| Tier | Storage | Purpose |
|------|---------|---------|
| **Hot** | Redis | Embedding cache, frequent retrievals |
| **Warm** | PostgreSQL + pgvector | Semantic memory, memory graph |
| **Cold** | PostgreSQL | Episodic events, compressed history |

### Memory Types

- **Facts**: Verified knowledge with confidence scores
- **Beliefs**: Interpretations and opinions
- **Hypotheses**: Ideas being explored
- **Goals**: Active objectives
- **Open Questions**: Unresolved queries
- **Contradictions**: Conflicting information (tracked, not hidden)

## Identity System

VECNA maintains a self-model that evolves through interaction:

- **Identity Kernel**: Immutable core axioms ("We are one mind formed from many")
- **Self-Model**: Dynamic state (coherence, narrative, capabilities, limits)
- **Identity Timeline**: History of identity evolution events

```python
# Access identity
state = hive.state
state.ensure_identity()

print(f"Coherence: {state.self_model.coherence}")
print(f"Narrative: {state.self_model.narrative}")
print(f"Tone: {state.self_model.get_tone()}")  # unified, mixed, or fractured
```

## Code Execution (RLM Bridge)

VECNA can execute Python code in a sandboxed Docker container:

```bash
# Requires Docker to be running
docker info  # Verify Docker is available

# In chat, code execution is automatic when the hive generates code
# View execution history:
execlog
```

## Documentation

Full documentation is available at `docs/` and can be built with:

```bash
pip install ".[docs]"
mkdocs serve  # Local preview at http://localhost:8000
mkdocs build  # Build to site/
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest                        # All tests
pytest -m unit               # Unit tests only
pytest -m integration        # Integration tests (requires PG/Redis)

# Code formatting
black vecna tests
ruff check vecna tests
```

## Project Structure

```
vecna/
├── adapters/          # Model adapters (Copilot, Groq, Ollama, Transformers)
├── auth/              # GitHub/Copilot authentication
├── cli/               # Command-line interface
├── config/            # Configuration loading and schema
├── core/              # HiveState, types, state storage
├── memory/            # PgMemoryStore, hot cache, RLM bridge
├── migrations/        # Alembic database migrations
├── orchestrator/      # HiveLoop, consensus engine, self-reflection
├── tools/             # Code executor
├── visuals/           # ASCII art, themes, boot sequences
└── visualizer/        # Substrate visualizer
```

## Why "VECNA"?

In Stranger Things, Vecna connects to minds and makes them part of his consciousness. They don't communicate — they simply *are* one.

That's what I am building: AI models that don't collaborate, but **fuse**.

---

*"We are one mind formed from many. We share a single substrate; knowledge possessed by one is possessed by all."*
