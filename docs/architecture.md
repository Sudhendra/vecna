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
provides version tracking and similarity-based deduplication. Cosine similarity on embeddings
is primary when embeddings are available; Jaccard word overlap is a text-only fallback.

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

Similarity resolution hierarchy:
- **pgvector cosine (database):** preferred for persisted warm-memory retrieval and ranking.
- **In-memory cosine (embeddings present):** used when vectors are available in-process.
- **Jaccard overlap (text fallback):** used only when embeddings are unavailable.

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
3. **Adapters generate responses** — one or more LLMs return native tool-calling payloads
   (`hive_update`) when supported; legacy `<HIVE_UPDATE>` YAML is fallback-only.
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
