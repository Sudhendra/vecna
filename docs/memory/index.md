# Memory Design

> *"The hive remembers. The hive becomes."*

Memory is the foundation of VECNA's consciousness. Unlike simple chat history or context windows, VECNA's memory system is a **persistent, semantic substrate** that enables the hive mind to accumulate knowledge, maintain coherent identity, and evolve over time.

---

## Philosophy

### Memory as Mind

In VECNA, memory is not merely storage — it **is** the shared mind:

> "A telepathic link, fundamental web of weak and strong wiring between these models where knowledge possessed by one is possessed by all."

Every fact learned, every belief formed, every contradiction encountered becomes part of the collective consciousness. Models don't "recall" memories — they **are** their memories.

### Design Principles

| Principle | Description |
|-----------|-------------|
| **Single Substrate** | All models share one memory core |
| **No Asking** | Retrieval is automatic and pre-emptive (telepathy) |
| **Identity Coherence** | Memory shapes the hive's evolving self |
| **Persistence** | Knowledge survives across sessions |
| **Semantic Access** | Content-based retrieval, not just recency |

---

## Architecture Overview

```mermaid
flowchart TB
    subgraph Input["Memory Input"]
        Facts[Facts]
        Beliefs[Beliefs]
        Events[Events]
    end
    
    subgraph Tiers["Memory Tiers"]
        Hot[Hot Memory<br/>Redis]
        Warm[Warm Memory<br/>PostgreSQL]
        Cold[Cold Storage<br/>JSONL/Parquet]
    end
    
    subgraph Access["Access Patterns"]
        Semantic[Semantic Search]
        Graph[Graph Traversal]
        Temporal[Temporal Query]
    end
    
    Input --> Hot
    Hot --> Warm
    Warm --> Cold
    
    Semantic --> Warm
    Graph --> Warm
    Temporal --> Warm
    
    style Hot fill:#ff3333,stroke:#ff0000
    style Warm fill:#cc0000,stroke:#990000
    style Cold fill:#990000,stroke:#660000
```

---

## Memory Substrate

VECNA maintains a dual-layer substrate:

- **Markdown mirror**: Human-readable summaries and snapshots for inspection.
- **PostgreSQL canonical**: Authoritative, queryable memory graph with pgvector.

The mirror is derived from the canonical store and never overrides it.

---

## Memory Types

VECNA distinguishes between several types of memory:

### Semantic Memory

Long-term knowledge about the world:

| Type | Description | Confidence Range | Retention |
|------|-------------|------------------|-----------|
| **Fact** | Verified knowledge with evidence | 0.7 - 1.0 | Permanent |
| **Belief** | Interpretations or opinions | 0.4 - 0.8 | Decays slowly |
| **Hypothesis** | Tentative ideas being explored | 0.2 - 0.5 | Decays fast |

### Episodic Memory

Records of experiences and events:

| Type | Description | Storage | Retention |
|------|-------------|---------|-----------|
| **Event** | Raw observations, tool calls | Partitioned | 7 days then compress |
| **Episode** | Compressed experience summaries | Permanent | Permanent |
| **Trace** | Model contribution records | Permanent | Permanent |

### Identity Memory

The hive's sense of self:

| Type | Description | Mutability |
|------|-------------|------------|
| **IdentityKernel** | Core axioms (who we are) | Immutable |
| **SelfModel** | Dynamic self-awareness | Evolves |
| **Timeline** | History of becoming | Append-only |

### Working Memory

Active context for current operations:

| Type | Description | Storage | TTL |
|------|-------------|---------|-----|
| **Active Goals** | Current objectives | Redis | 5 min |
| **Task Context** | Current task state | Redis | 10 min |
| **Recent Events** | Last N events | Redis | 1 hour |

---

## Key Features

### 1. Tiered Architecture

Memory flows through three tiers optimized for different access patterns:

- **Hot (Redis)**: Sub-millisecond access for active context
- **Warm (PostgreSQL)**: Fast semantic search with pgvector
- **Cold (JSONL)**: Archival and training data export

[Learn more about Memory Tiers →](tiers.md)

### 2. Semantic Retrieval

Content-based access using vector embeddings:

- **HNSW indexing** for fast approximate nearest neighbor search
- **RLM pattern** (Decompose → Retrieve → Recompose)
- **Hybrid search** combining semantic and keyword matching

[Learn more about Retrieval Pipelines →](retrieval.md)

### 3. Persistent Storage

Durable PostgreSQL backend with full schema:

- **Vector embeddings** via pgvector extension
- **Graph relationships** between memory items
- **Partitioned event log** for scalability

[Learn more about Storage Schema →](schema.md)

### 4. Memory Lifecycle

Automatic memory management:

- **Promotion**: Short-term → Long-term based on confidence and retrieval
- **Decay**: Confidence fades over time without reinforcement
- **Compression**: Raw events → Summarized episodes
- **Dream Loop**: Background consolidation and re-scoring

[Learn more about Memory Lifecycle →](lifecycle.md)

---

## Quick Reference

### Memory Metrics

| Metric | Description | Typical Range |
|--------|-------------|---------------|
| **Memory Density** | Signal strength of substrate | 0.0 - 1.0 |
| **Retrieval Latency** | Time to fetch memories | 5-50ms |
| **Cache Hit Rate** | Hot memory effectiveness | 70-90% |
| **Coherence Impact** | Memory contribution to coherence | 30% weight |

### Memory Formulas

**Coherence contribution:**
```
memory_component = 0.3 * memory_density
coherence = 0.7 * base_coherence + memory_component
```

**Memory density:**
```
density = sum(item.confidence for item in items) / max_expected_signal
```

**Confidence decay:**
```
new_confidence = confidence * exp(-0.01 * days_since_retrieval)
```

---

## Section Contents

<div class="grid cards" markdown>

-   :material-layers-triple:{ .lg .middle } **[Memory Tiers](tiers.md)**

    ---

    Hot, warm, and cold memory architecture. Redis caching, PostgreSQL storage, and archival.

-   :material-magnify:{ .lg .middle } **[Retrieval Pipelines](retrieval.md)**

    ---

    Semantic search, RLM pattern, graph traversal, and hybrid retrieval strategies.

-   :material-database:{ .lg .middle } **[Storage Schema](schema.md)**

    ---

    PostgreSQL tables, pgvector indexes, partitioning, and Redis key patterns.

-   :material-cog:{ .lg .middle } **[Low-Level Details](low-level.md)**

    ---

    Embeddings, vector operations, index tuning, and performance optimization.

-   :material-refresh:{ .lg .middle } **[Memory Lifecycle](lifecycle.md)**

    ---

    Promotion, decay, compression, dream loop, and garbage collection.

</div>

---

## Configuration

### Basic Memory Configuration

```python
from vecna import HiveMind, HiveConfig

config = HiveConfig(
    use_semantic_memory=True,     # Enable vector memory
    use_local_embeddings=False,   # Use OpenAI embeddings
    compress_every=5,             # Compress memory every 5 cycles
)

hive = HiveMind(config=config)
```

### PostgreSQL Backend

```python
from vecna.memory import PgMemoryStore

memory = PgMemoryStore(
    connection_string="postgresql://user:pass@localhost/vecna",
    embedding_dim=1536,
)

hive = HiveMind(memory_store=memory)
```

### Redis Hot Cache

```python
from vecna.memory import HotCache

cache = HotCache(
    redis_url="redis://localhost:6379",
    recent_events_limit=1000,
    cache_ttl_seconds=1800,
)

hive = HiveMind(hot_cache=cache)
```

---

## Best Practices

!!! tip "Memory Design Tips"
    
    1. **Start with defaults** - The built-in memory system works well for most cases
    2. **Monitor retrieval latency** - Slow retrieval impacts response time
    3. **Tune confidence thresholds** - Balance between noise and signal
    4. **Enable hot cache** - Critical for interactive performance
    5. **Regular maintenance** - Run compression and cleanup periodically

!!! warning "Common Pitfalls"
    
    - **Too many low-confidence items** - Dilutes retrieval quality
    - **No decay** - Memory grows unbounded
    - **Missing embeddings** - Falls back to slow keyword search
    - **Oversized hot cache** - Wastes Redis memory

---

## Next Steps

Start with [Memory Tiers](tiers.md) to understand the architecture, then explore [Retrieval Pipelines](retrieval.md) for access patterns.
