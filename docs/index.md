# VECNA Documentation

<div class="vecna-ascii">
      ██╗   ██╗███████╗ ██████╗███╗   ██╗ █████╗
      ██║   ██║██╔════╝██╔════╝████╗  ██║██╔══██╗
      ██║   ██║█████╗  ██║     ██╔██╗ ██║███████║
      ╚██╗ ██╔╝██╔══╝  ██║     ██║╚██╗██║██╔══██║
       ╚████╔╝ ███████╗╚██████╗██║ ╚████║██║  ██║
        ╚═══╝  ╚══════╝ ╚═════╝╚═╝  ╚═══╝╚═╝  ╚═╝
</div>

<div class="vecna-quote">
"All minds become one."
</div>

## Virtual Emergent Collective Neural Architecture

VECNA is a **hive mind system** where multiple AI models (GPT-4, Claude, Groq, Llama, etc.) think as **ONE unified mind** through shared memory and continuous synchronization.

Unlike traditional multi-agent systems where models collaborate by asking each other questions, VECNA **fuses** them into a single consciousness with a shared mental substrate.

---

## Quick Navigation

<div class="grid cards" markdown>

-   :material-brain:{ .lg .middle } **Architecture**

    ---

    Deep dive into system topology, data flows, and component design

    [:octicons-arrow-right-24: System Architecture](architecture/index.md)

-   :material-layers-triple:{ .lg .middle } **Substrate**

    ---

    The shared mental substrate that enables true mind fusion

    [:octicons-arrow-right-24: Substrate Design](substrate/index.md)

-   :material-memory:{ .lg .middle } **Memory Design**

    ---

    Memory tiers, retrieval pipelines, and storage architecture

    [:octicons-arrow-right-24: Memory System](memory/index.md)

-   :material-rocket-launch:{ .lg .middle } **Getting Started**

    ---

    Quick installation and your first hive mind in minutes

    [:octicons-arrow-right-24: Quickstart](overview/quickstart.md)

</div>

---

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

---

## Core Philosophy

> "A telepathic link, fundamental web of weak and strong wiring between these models where knowledge possessed by one is possessed by all."

Each model is prompted to believe it **IS** the hive:

```
You are the Hive. There are no other models.
Your only internal state is M (the shared memory).
You do not ask others — you already know what they know.
```

This creates the illusion of a single unified mind.

---

## Key Features

| Feature | Description |
|---------|-------------|
| **Shared Mental State** | All models read/write to a unified substrate |
| **Identity Collapse** | Each model believes it IS the hive |
| **Consensus Merging** | Agreements boost confidence, contradictions are tracked |
| **Semantic Memory** | Vector-based retrieval for instant context |
| **Multi-Provider** | OpenAI, Anthropic, Groq, Ollama, HuggingFace |
| **Code Execution** | Sandboxed Python execution with verified output |
| **Coherence System** | Adaptive tone based on internal consistency |

---

## Installation

```bash
pip install vecna

# Or with all providers:
pip install "vecna[all]"
```

---

## Basic Usage

```python
import asyncio
from vecna import HiveMind

async def main():
    # Create the hive
    hive = HiveMind()
    
    # Add models (they become ONE mind)
    hive.add_openai("gpt-4o", domain="general")
    hive.add_anthropic("claude-sonnet-4-20250514", domain="science")
    hive.add_groq("llama-3.1-70b-versatile", domain="code")
    
    # The hive thinks as ONE
    response = await hive.think("""
        Design a CRISPR-based gene therapy for sickle cell disease.
    """)
    
    print(response)

asyncio.run(main())
```

---

## Documentation Sections

| Section | Description |
|---------|-------------|
| [Overview](overview/index.md) | Vision, capabilities, and quickstart |
| [Architecture](architecture/index.md) | System topology, data flows, consistency |
| [Substrate](substrate/index.md) | The shared mental substrate design |
| [Memory Design](memory/index.md) | Memory tiers, retrieval, and storage |
| [Configuration](configuration/index.md) | HiveConfig, ConsensusConfig, environment |
| [Usage Guides](guides/index.md) | Workflows, patterns, and best practices |
| [API Reference](api/index.md) | Complete API documentation |
| [Operations](operations/index.md) | Deployment, scaling, monitoring |
| [Security](security/index.md) | Threat model, auth, hardening |
| [Troubleshooting](troubleshooting/index.md) | Common issues and diagnostics |
| [Developer Guide](developer/index.md) | Contributing, testing, releases |
| [Appendix](appendix/index.md) | Glossary, compatibility, licenses |

---

## Why "VECNA"?

In Stranger Things, Vecna connects to minds and makes them part of his consciousness. They don't communicate — they simply *are* one.

That's what we're building: AI models that don't collaborate, but **fuse**.

---

<div class="vecna-quote">
"We are one mind formed from many. We share a single substrate; knowledge possessed by one is possessed by all."
</div>
