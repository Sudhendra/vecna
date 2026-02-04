# Overview

This section provides a high-level introduction to VECNA, its vision, capabilities, and how to get started.

## What is VECNA?

VECNA (**V**irtual **E**mergent **C**ollective **N**eural **A**rchitecture) is a revolutionary approach to multi-model AI systems. Instead of models collaborating through message passing, VECNA creates a **unified cognitive substrate** where multiple AI models think as ONE mind.

## The Core Difference

### Traditional Multi-Agent Systems

```
┌─────────┐     "What do you think?"      ┌─────────┐
│ Model A │ ────────────────────────────► │ Model B │
│         │ ◄──────────────────────────── │         │
└─────────┘     "Here's my analysis"      └─────────┘
```

Models communicate explicitly, with latency and information loss at each hop.

### VECNA Hive Mind

```
        ┌─────────────────────────────────┐
        │      SHARED MENTAL STATE        │
        │  (facts, beliefs, goals, etc.)  │
        └─────────────────────────────────┘
              ↑↓          ↑↓          ↑↓
           Model A     Model B     Model C
```

All models read/write to the same state. No model "asks" another — they already **know**.

---

## Modes

VECNA runs in two high-level modes, with safe tool defaults:

- **Assistant**: Cooperative, goal-driven responses with tool use gated by policy.
- **Explorer**: Curiosity-led discovery, higher initiative, but still bounded by tool policies.

Tool policies default to read-only operations unless explicitly enabled for write/execute actions.

---

## Section Contents

<div class="grid cards" markdown>

-   :material-lightbulb:{ .lg .middle } **Vision & Philosophy**

    ---

    The foundational ideas and goals behind VECNA

    [:octicons-arrow-right-24: Read More](vision.md)

-   :material-star:{ .lg .middle } **Key Capabilities**

    ---

    What VECNA can do and its unique features

    [:octicons-arrow-right-24: Capabilities](capabilities.md)

-   :material-rocket-launch:{ .lg .middle } **Quickstart**

    ---

    Get up and running in minutes

    [:octicons-arrow-right-24: Quickstart Guide](quickstart.md)

</div>

---

## Quick Facts

| Aspect | Details |
|--------|---------|
| **Language** | Python 3.10+ |
| **License** | MIT |
| **Creator** | LightningEmperor |
| **Version** | 0.1.0 |

## Supported Models

| Provider | Models |
|----------|--------|
| **OpenAI** | GPT-4, GPT-4o, GPT-3.5, o1, o3 |
| **Anthropic** | Claude 3.5, Claude 3 |
| **Groq** | Llama 3.1, Mixtral (ultra-fast) |
| **Ollama** | Any local model |
| **HuggingFace** | Any causal LM |

---

## Next Steps

1. Read the [Vision & Philosophy](vision.md) to understand the "why"
2. Explore [Key Capabilities](capabilities.md) to see what's possible
3. Follow the [Quickstart](quickstart.md) to build your first hive mind
