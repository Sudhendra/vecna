# Memory Tiers

> *"The hive thinks at the speed of thought."*

VECNA's memory is organized into three tiers optimized for different access patterns and latency requirements. This page details the hot, warm, and cold memory architecture.

---

## Overview

```mermaid
flowchart TB
    subgraph Hot["HOT MEMORY (Redis)"]
        direction TB
        H1[Recent Events<br/>Ring Buffer]
        H2[Active Goals<br/>Current Context]
        H3[Retrieval Cache<br/>LRU]
        H4[Embedding Cache<br/>Content Hash]
    end
    
    subgraph Warm["WARM MEMORY (PostgreSQL)"]
        direction TB
        W1[Semantic Memory<br/>Facts, Beliefs, Hypotheses]
        W2[Memory Graph<br/>Relationships]
        W3[Episodes<br/>Compressed Events]
        W4[Identity Timeline<br/>Evolution Log]
    end
    
    subgraph Cold["COLD STORAGE (JSONL/Parquet)"]
        direction TB
        C1[Training Exports<br/>Adapter Fine-tuning]
        C2[Archived Episodes<br/>Historical Data]
        C3[Full Event History<br/>Compliance/Audit]
    end
    
    Hot --> |"Async Write-Through"| Warm
    Warm --> |"Periodic Export"| Cold
    
    style Hot fill:#ff3333,stroke:#ff0000
    style Warm fill:#cc0000,stroke:#990000
    style Cold fill:#660000,stroke:#330000
```

---

## Hot Memory (Redis)

The **hot tier** provides sub-millisecond access to frequently accessed data. It acts as a write-through cache and working memory for active operations.

### Characteristics

| Property | Value |
|----------|-------|
| **Storage** | Redis |
| **Latency** | < 1ms |
| **Durability** | Volatile (rehydrated from warm) |
| **Capacity** | ~100MB typical |

### Data Stored

#### Recent Events Ring Buffer

Last N events for immediate context:

```
Key: vecna:events:recent
Type: List (capped)
TTL: 1 hour
Size: 1000 events max
```

```python
# Structure
{
    "event_id": "uuid",
    "event_type": "query|response|consensus|tool_call",
    "payload": {...},
    "timestamp": "2025-01-24T10:30:00Z",
    "session_id": "session-123"
}
```

#### Active Goals

Current objectives being pursued:

```
Key: vecna:goals:active
Type: Hash
TTL: 5 minutes
```

```python
# Structure
{
    "goal_id": {
        "description": "Explain quantum computing",
        "priority": "high",
        "status": "in_progress",
        "created_at": "2025-01-24T10:30:00Z"
    }
}
```

#### Current Context

Serialized task state for the active operation:

```
Key: vecna:context:current
Type: String (JSON)
TTL: 10 minutes
```

#### Retrieval Cache

LRU cache of recent memory retrievals:

```
Key: vecna:memory:cache:{query_hash}
Type: String (JSON)
TTL: 30 minutes
```

#### Embedding Cache

Cached embeddings by content hash:

```
Key: vecna:embed:cache:{content_hash}
Type: String (base64 float32 array)
TTL: 24 hours
```

### Write-Through Strategy

Hot memory uses write-through caching:

```mermaid
sequenceDiagram
    participant App as Application
    participant Hot as Redis (Hot)
    participant Warm as PostgreSQL (Warm)
    
    App->>Hot: Write event
    Hot-->>App: ACK (immediate)
    Hot->>Warm: Async persist
    Warm-->>Hot: Confirm
```

1. Write to Redis immediately (synchronous)
2. Async write to PostgreSQL (background)
3. Periodic flush ensures durability

### Configuration

```python
from vecna.memory import HotCache

cache = HotCache(
    redis_url="redis://localhost:6379/0",
    
    # Event ring buffer
    recent_events_limit=1000,
    event_ttl_seconds=3600,
    
    # Retrieval cache
    retrieval_cache_size=500,
    retrieval_ttl_seconds=1800,
    
    # Embedding cache
    embedding_cache_size=10000,
    embedding_ttl_seconds=86400,
    
    # Write-through
    async_persist=True,
    persist_batch_size=100,
    persist_interval_seconds=5,
)
```

---

## Warm Memory (PostgreSQL)

The **warm tier** is the primary persistent store for all semantic memory. It uses PostgreSQL with pgvector for vector similarity search.

### Characteristics

| Property | Value |
|----------|-------|
| **Storage** | PostgreSQL 16+ with pgvector |
| **Latency** | 5-50ms |
| **Durability** | Fully persistent |
| **Capacity** | Unbounded (scales with disk) |

### Data Stored

#### Semantic Memory

Facts, beliefs, hypotheses with embeddings:

```sql
-- memory_items table
id              UUID PRIMARY KEY
content         TEXT NOT NULL
item_type       TEXT NOT NULL  -- fact, belief, hypothesis
confidence      FLOAT NOT NULL
domain          TEXT
source_model    TEXT
embedding       vector(1536)
metadata        JSONB
retrieval_count INTEGER
last_retrieved  TIMESTAMPTZ
created_at      TIMESTAMPTZ
updated_at      TIMESTAMPTZ
```

#### Memory Graph

Relationships between memory items:

```sql
-- memory_edges table
id          UUID PRIMARY KEY
source_id   UUID REFERENCES memory_items
target_id   UUID REFERENCES memory_items
relation    TEXT  -- supports, contradicts, derived_from
weight      FLOAT
metadata    JSONB
created_at  TIMESTAMPTZ
```

#### Episodic Memory

Compressed experience summaries:

```sql
-- episodes table
id          UUID PRIMARY KEY
summary     TEXT NOT NULL
embedding   vector(1536)
start_time  TIMESTAMPTZ
end_time    TIMESTAMPTZ
event_count INTEGER
tags        TEXT[]
metadata    JSONB
created_at  TIMESTAMPTZ
```

#### Raw Events

Partitioned event stream:

```sql
-- memory_events table (partitioned by month)
id          UUID PRIMARY KEY
event_type  TEXT NOT NULL
payload     JSONB NOT NULL
session_id  TEXT
created_at  TIMESTAMPTZ
```

#### Identity Timeline

Evolution of the hive's identity:

```sql
-- identity_timeline table
id          UUID PRIMARY KEY
event_type  TEXT NOT NULL  -- coherence_shift, capability_added
description TEXT
old_value   JSONB
new_value   JSONB
trigger     TEXT
created_at  TIMESTAMPTZ
```

### Indexing Strategy

```sql
-- HNSW index for fast ANN search
CREATE INDEX memory_items_embedding_idx ON memory_items 
    USING hnsw (embedding vector_cosine_ops) 
    WITH (m = 16, ef_construction = 64);

-- Type + confidence for filtered queries
CREATE INDEX memory_items_type_confidence_idx 
    ON memory_items (item_type, confidence DESC);

-- Metadata GIN index for JSON queries
CREATE INDEX memory_items_metadata_idx 
    ON memory_items USING GIN (metadata);

-- Graph traversal indexes
CREATE INDEX memory_edges_source_idx ON memory_edges (source_id);
CREATE INDEX memory_edges_target_idx ON memory_edges (target_id);
```

### Configuration

```python
from vecna.memory import PgMemoryStore

store = PgMemoryStore(
    connection_string="postgresql://user:pass@localhost/vecna",
    
    # Schema
    schema="public",
    embedding_dim=1536,
    
    # Connection pool
    min_connections=5,
    max_connections=20,
    
    # HNSW index tuning
    hnsw_m=16,
    hnsw_ef_construction=64,
    hnsw_ef_search=40,
    
    # Partitioning
    partition_by="month",
    retention_months=12,
)
```

---

## Cold Storage (JSONL/Parquet)

The **cold tier** provides archival storage for historical data and training exports.

### Characteristics

| Property | Value |
|----------|-------|
| **Storage** | JSONL, Parquet, S3/GCS |
| **Latency** | 100ms - 10s |
| **Durability** | Archival |
| **Capacity** | Unlimited (object storage) |

### Data Stored

#### Training Exports

Data prepared for model fine-tuning:

```python
# JSONL format
{
    "messages": [
        {"role": "system", "content": "You are VECNA..."},
        {"role": "user", "content": "Query"},
        {"role": "assistant", "content": "Response"}
    ],
    "metadata": {
        "coherence": 0.85,
        "models_agreed": 3,
        "domain": "science"
    }
}
```

#### Archived Episodes

Historical summaries beyond retention period:

```python
# Parquet schema
episode_id: string
summary: string
start_time: timestamp
end_time: timestamp
event_count: int32
tags: list<string>
metadata: string (JSON)
```

#### Full Event History

Complete audit trail:

```python
# JSONL format (compressed)
{
    "event_id": "uuid",
    "event_type": "query",
    "payload": {...},
    "session_id": "session-123",
    "timestamp": "2025-01-24T10:30:00Z"
}
```

### Export Process

```mermaid
flowchart LR
    PG[(PostgreSQL)] --> Export[Export Job]
    Export --> Transform[Transform]
    Transform --> JSONL[JSONL Files]
    Transform --> Parquet[Parquet Files]
    JSONL --> S3[(S3/GCS)]
    Parquet --> S3
```

### Configuration

```python
from vecna.memory import ColdStorage

cold = ColdStorage(
    # Output location
    output_path="s3://vecna-archive/",  # or local path
    
    # Format
    format="parquet",  # or "jsonl"
    compression="snappy",
    
    # Partitioning
    partition_by=["year", "month"],
    
    # Retention
    archive_after_days=30,
    delete_after_days=365,
)
```

---

## Data Flow Between Tiers

### Write Path

```mermaid
flowchart TB
    Input[New Memory Item] --> Hot
    Hot --> |"Immediate"| Response[Return to User]
    Hot --> |"Async"| Warm
    Warm --> |"Batch Export"| Cold
    
    style Hot fill:#ff3333,stroke:#ff0000
    style Warm fill:#cc0000,stroke:#990000
    style Cold fill:#660000,stroke:#330000
```

### Read Path

```mermaid
flowchart TB
    Query[Memory Query] --> Check{In Hot Cache?}
    Check --> |Yes| Hot[Return from Hot]
    Check --> |No| Warm[Query Warm]
    Warm --> Cache[Cache in Hot]
    Cache --> Return[Return Result]
    
    style Hot fill:#ff3333,stroke:#ff0000
    style Warm fill:#cc0000,stroke:#990000
```

### Promotion & Demotion

| Direction | Trigger | Action |
|-----------|---------|--------|
| Hot → Warm | Write-through | Async persist to PG |
| Warm → Hot | Cache miss | Load into Redis |
| Warm → Cold | Age > threshold | Export and archive |
| Cold → Warm | Rehydration | Import from archive |

---

## Performance Characteristics

### Latency by Tier

| Operation | Hot | Warm | Cold |
|-----------|-----|------|------|
| Point read | < 1ms | 5-10ms | 100ms+ |
| Semantic search | N/A | 20-50ms | N/A |
| Range scan | 2-5ms | 10-30ms | 1-10s |
| Write | < 1ms | 5-20ms | 50-200ms |

### Throughput

| Tier | Reads/sec | Writes/sec |
|------|-----------|------------|
| Hot | 100,000+ | 50,000+ |
| Warm | 5,000+ | 2,000+ |
| Cold | 100 | 50 |

### Storage Efficiency

| Tier | Cost/GB | Typical Size |
|------|---------|--------------|
| Hot | $$$$$ | 100MB - 1GB |
| Warm | $$$ | 1GB - 100GB |
| Cold | $ | 10GB - 10TB |

---

## Multi-Process Access

The tiered architecture supports multiple VECNA processes:

```mermaid
flowchart TB
    subgraph Processes
        CLI[CLI Process]
        Explorer[Explorer Process]
        Dream[Dream Process]
    end
    
    subgraph Shared["Shared Memory"]
        Redis[(Redis)]
        PG[(PostgreSQL)]
    end
    
    CLI --> Redis
    Explorer --> Redis
    Dream --> Redis
    
    CLI --> PG
    Explorer --> PG
    Dream --> PG
    
    Redis --> |"Distributed Locks"| Coord[Coordination]
```

### Coordination

- **Redis locks**: Prevent concurrent writes to same item
- **PG transactions**: ACID guarantees for warm tier
- **Optimistic concurrency**: Version numbers for conflict detection

---

## Configuration Reference

### Full Configuration

```python
from vecna.memory import MemoryConfig

config = MemoryConfig(
    # Hot tier (Redis)
    hot=HotCacheConfig(
        redis_url="redis://localhost:6379/0",
        recent_events_limit=1000,
        retrieval_cache_size=500,
        embedding_cache_size=10000,
    ),
    
    # Warm tier (PostgreSQL)
    warm=PgStoreConfig(
        connection_string="postgresql://localhost/vecna",
        embedding_dim=1536,
        hnsw_m=16,
        hnsw_ef_construction=64,
    ),
    
    # Cold tier (Archive)
    cold=ColdStorageConfig(
        output_path="/data/vecna/archive",
        format="parquet",
        archive_after_days=30,
    ),
    
    # Tier policies
    write_through=True,
    cache_on_read=True,
    async_persist=True,
)
```

---

## Best Practices

!!! tip "Tier Optimization"
    
    1. **Size hot cache appropriately** - Too small = cache thrashing, too large = memory waste
    2. **Monitor cache hit rate** - Target 80%+ for hot tier
    3. **Tune HNSW parameters** - Balance accuracy vs speed
    4. **Partition events by time** - Enables efficient pruning
    5. **Export regularly** - Don't let warm tier grow unbounded

!!! warning "Common Issues"
    
    - **Redis memory exhaustion** - Set `maxmemory` with LRU eviction
    - **Slow warm queries** - Check HNSW index health
    - **Cold storage costs** - Use lifecycle policies for deletion
    - **Replication lag** - Monitor async write-through latency

---

## Next Steps

- [Retrieval Pipelines](retrieval.md) - How to query across tiers
- [Storage Schema](schema.md) - Detailed PostgreSQL schema
- [Memory Lifecycle](lifecycle.md) - Data movement and cleanup
