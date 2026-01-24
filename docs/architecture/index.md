# Architecture

This section provides an in-depth technical overview of VECNA's system architecture, designed for contributors, operators, and advanced users who need to understand the internal workings.

---

## System Overview

VECNA is architected as a **layered system** with clear separation between:

1. **Adapter Layer** — Model provider interfaces
2. **Orchestration Layer** — Hive loop, consensus, routing
3. **State Layer** — HiveState, identity, persistence
4. **Memory Layer** — Semantic memory, caching, retrieval

```
┌─────────────────────────────────────────────────────────────────┐
│                         VECNA HIVE MIND                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│    ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐       │
│    │  GPT-4  │   │ Claude  │   │  Groq   │   │ Ollama  │       │
│    │ Adapter │   │ Adapter │   │ Adapter │   │ Adapter │       │
│    └────┬────┘   └────┬────┘   └────┬────┘   └────┬────┘       │
│         │             │             │             │             │
│         └─────────────┴──────┬──────┴─────────────┘             │
│                              │                                  │
│                     ┌────────▼────────┐                         │
│                     │   HIVE LOOP     │                         │
│                     │  (Orchestrator) │                         │
│                     └────────┬────────┘                         │
│                              │                                  │
│         ┌────────────────────┼────────────────────┐             │
│         │                    │                    │             │
│    ┌────▼────┐         ┌─────▼─────┐        ┌────▼────┐        │
│    │CONSENSUS│         │HIVE STATE │        │  SELF   │        │
│    │ ENGINE  │◄───────►│(Substrate)│◄──────►│REFLECTION│       │
│    └─────────┘         └─────┬─────┘        └─────────┘        │
│                              │                                  │
│         ┌────────────────────┼────────────────────┐             │
│         │                    │                    │             │
│    ┌────▼────┐         ┌─────▼─────┐        ┌────▼────┐        │
│    │ MEMORY  │         │    RLM    │        │  CODE   │        │
│    │  STORE  │         │  BRIDGE   │        │EXECUTOR │        │
│    │(Vector) │         │ (Docker)  │        │(Sandbox)│        │
│    └─────────┘         └───────────┘        └─────────┘        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Section Contents

<div class="grid cards" markdown>

-   :material-sitemap:{ .lg .middle } **System Topology**

    ---

    Component layout and relationships

    [:octicons-arrow-right-24: Topology](topology.md)

-   :material-transfer:{ .lg .middle } **Data Flow & Lifecycles**

    ---

    How data moves through the system

    [:octicons-arrow-right-24: Data Flow](data-flow.md)

-   :material-airplane:{ .lg .middle } **Control vs Data Plane**

    ---

    Separation of concerns in system design

    [:octicons-arrow-right-24: Planes](control-data-plane.md)

-   :material-check-all:{ .lg .middle } **Consistency Model**

    ---

    How VECNA maintains coherent state

    [:octicons-arrow-right-24: Consistency](consistency.md)

-   :material-shield:{ .lg .middle } **Failure Domains & Resilience**

    ---

    Fault isolation and recovery strategies

    [:octicons-arrow-right-24: Resilience](resilience.md)

</div>

---

## Key Design Decisions

### 1. Shared-Nothing Adapters

Each model adapter is stateless and independent. State is managed centrally in HiveState, not in adapters.

**Rationale**: Enables horizontal scaling and provider independence.

### 2. Eventual Consistency

The consensus engine merges model outputs asynchronously. The system is eventually consistent, not strongly consistent.

**Rationale**: Prioritizes availability and performance over strict consistency.

### 3. Immutable Identity Kernel

Core axioms are immutable. Only the SelfModel evolves.

**Rationale**: Ensures stable identity across sessions and model changes.

### 4. Pluggable Storage

State can be stored in JSON, PostgreSQL, or custom backends.

**Rationale**: Supports both quick prototyping and production deployments.

---

## Component Summary

| Component | Module | Responsibility |
|-----------|--------|----------------|
| **HiveMind** | `orchestrator/loop.py` | Main entry point, model management |
| **HiveLoop** | `orchestrator/loop.py` | Think cycle orchestration |
| **ConsensusEngine** | `orchestrator/consensus.py` | Output merging, contradiction detection |
| **DomainRouter** | `orchestrator/consensus.py` | Task-to-expert routing |
| **HiveState** | `core/hive_state.py` | Shared mental substrate |
| **IdentityKernel** | `core/types.py` | Immutable axioms |
| **SelfModel** | `core/types.py` | Dynamic self-awareness |
| **MemoryStore** | `memory/store.py` | Vector-based semantic memory |
| **RLMBridge** | `memory/rlm_bridge.py` | Docker sandbox for code |
| **Adapters** | `adapters/base.py` | Provider-specific interfaces |

---

## Runtime Characteristics

| Metric | Typical Value | Notes |
|--------|---------------|-------|
| Think cycle latency | 500ms - 2s | Depends on model count and provider |
| Memory retrieval | 5-50ms | With pgvector HNSW index |
| Consensus merging | <10ms | CPU-bound clustering |
| State serialization | <50ms | For typical state sizes |

---

## Next Steps

1. [System Topology](topology.md) — Understand component relationships
2. [Data Flow](data-flow.md) — Follow a request through the system
3. [Consistency Model](consistency.md) — Learn about state management
