# Observability with Langfuse

> *"To understand the hive, one must observe its patterns."*

VECNA integrates with [Langfuse](https://langfuse.com) for comprehensive observability, including token usage tracking, cost monitoring, and latency analysis across all LLM calls.

---

## Overview

Langfuse provides:

- **Token Usage Tracking** - Monitor prompt and completion tokens per request
- **Cost Analysis** - Track spending across models and providers
- **Latency Metrics** - Identify slow operations in the pipeline
- **Trace Visualization** - See the full request lifecycle with nested spans

```
Request (hive.think)
├── memory.retrieval      # Memory lookup span
├── llm.copilot-gpt-4     # LLM generation
├── consensus.merge       # Consensus span
├── identity.reflect      # Identity reflection span
└── code.execute          # Code execution span (if enabled)
```

---

## Setup

### 1. Install Langfuse (Self-Hosted)

```bash
# Clone Langfuse
git clone https://github.com/langfuse/langfuse.git ~/Softwares/langfuse
cd ~/Softwares/langfuse

# Start with Docker Compose
docker compose up -d
```

Langfuse will be available at http://localhost:3000

### 2. Create API Keys

1. Open http://localhost:3000
2. Create an account / sign in
3. Go to **Settings > API Keys**
4. Create a new API key pair (public + secret)

### 3. Configure VECNA

Add to your `.env` file:

```bash
# Langfuse Configuration
LANGFUSE_PUBLIC_KEY=pk-lf-your-public-key
LANGFUSE_SECRET_KEY=sk-lf-your-secret-key
LANGFUSE_BASE_URL=http://localhost:3000

# Enable tracing (auto-enabled by start script if keys present)
VECNA_LANGFUSE_ENABLED=true
```

### 4. Start VECNA

```bash
./start-vecna.sh
```

If Langfuse is running and keys are configured, you'll see:

```
✓ Langfuse ready (http://localhost:3000)
◉ Tracing enabled (tokens & costs tracked)
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LANGFUSE_PUBLIC_KEY` | - | Langfuse project public key |
| `LANGFUSE_SECRET_KEY` | - | Langfuse project secret key |
| `LANGFUSE_BASE_URL` | `https://cloud.langfuse.com` | Langfuse server URL |
| `VECNA_LANGFUSE_ENABLED` | `false` | Enable/disable tracing |
| `VECNA_LANGFUSE_LOG_PROMPTS` | `true` | Log full prompt/response text |
| `VECNA_LANGFUSE_TRACE_PIPELINE` | `true` | Trace memory/consensus/code spans |

### Privacy Controls

To redact prompt/response content (for privacy):

```bash
VECNA_LANGFUSE_LOG_PROMPTS=false
```

This will log only metadata (length, hash) instead of full text.

---

## What Gets Traced

### Request Trace (`hive.think`)

The top-level trace for each user request:

| Field | Description |
|-------|-------------|
| `input` | User's task/prompt |
| `output` | Final response (truncated to 2000 chars) |
| `metadata.active_models` | Models used in the request |
| `metadata.total_cycles` | Number of hive cycles executed |
| `metadata.final_coherence` | Identity coherence score at completion |

### LLM Generation Spans (`llm.*`)

Each model call is traced:

| Field | Description |
|-------|-------------|
| `model` | Model ID (e.g., `gpt-4.1`) |
| `input` | Full prompt sent to model |
| `output` | Model response |
| `usage.input` | Prompt tokens |
| `usage.output` | Completion tokens |
| `metadata.provider` | Provider name (copilot, groq, ollama) |
| `metadata.latency_ms` | Call duration in milliseconds |

### Pipeline Spans

Internal operations (when `VECNA_LANGFUSE_TRACE_PIPELINE=true`):

| Span | Description |
|------|-------------|
| `memory.retrieval` | Memory lookup with RLM facets |
| `consensus.merge` | Consensus engine merge operation |
| `identity.reflect` | Self-reflection and coherence update |
| `code.execute` | RLM code execution in sandbox |

---

## Viewing Traces

### Langfuse Dashboard

1. Open http://localhost:3000
2. Navigate to **Traces**
3. Click any trace to see the full hierarchy

### Useful Filters

- Filter by `tags: vecna` for all VECNA traces
- Filter by `model` to see specific model usage
- Sort by `latency` to find slow requests
- Group by `session_id` for conversation threads

---

## Token Usage & Cost

Langfuse automatically calculates costs based on model pricing. For accurate costs:

1. Go to **Settings > Models**
2. Add pricing for your models (if not auto-detected)

### Example Cost Report

```
Model               Requests    Tokens      Cost
gpt-4.1             42          156,000     $4.68
claude-sonnet       18          82,000      $1.23
llama-3.1-70b       95          420,000     $0.00 (local)
```

---

## Troubleshooting

### Tracing Not Working

Check the startup output:

```
⚠ Langfuse not responding (tracing disabled)
```

**Solutions:**

1. Ensure Langfuse is running:
   ```bash
   cd ~/Softwares/langfuse && docker compose up -d
   ```

2. Check Langfuse is accessible:
   ```bash
   curl http://localhost:3000
   ```

3. Verify keys in `.env`:
   ```bash
   grep LANGFUSE .env
   ```

### "Langfuse keys not set" Warning

Add your API keys to `.env`:

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
```

### Traces Not Appearing

1. Ensure `VECNA_LANGFUSE_ENABLED=true`
2. Check Langfuse logs:
   ```bash
   cd ~/Softwares/langfuse && docker compose logs -f web
   ```
3. Verify the keys match a project in Langfuse

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         VECNA                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                   HiveLoop.think()                   │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │   │
│  │  │   Memory    │  │     LLM     │  │  Consensus  │  │   │
│  │  │  Retrieval  │  │ Generation  │  │    Merge    │  │   │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  │   │
│  │         │                │                │         │   │
│  │         └────────────────┼────────────────┘         │   │
│  │                          │                          │   │
│  │              ┌───────────▼───────────┐              │   │
│  │              │   Langfuse Client     │              │   │
│  │              │   (fail-open)         │              │   │
│  │              └───────────┬───────────┘              │   │
│  └──────────────────────────┼──────────────────────────┘   │
│                             │                              │
└─────────────────────────────┼──────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │    Langfuse     │
                    │  (localhost or  │
                    │     cloud)      │
                    └─────────────────┘
```

### Fail-Open Design

The Langfuse integration is designed to **never block** VECNA operations:

- If Langfuse is down, tracing is silently disabled
- If a trace fails to send, the error is logged but execution continues
- All tracing calls are wrapped in try/catch blocks

---

## Programmatic Usage

You can use the tracing primitives directly:

```python
from vecna.observability.langfuse import (
    trace_request,
    trace_span,
    trace_generation,
)

# Trace a full request
with trace_request("my-operation", input="user query") as trace:
    # Nested span for sub-operations
    with trace_span("preprocessing") as span:
        result = preprocess(data)
        span.set_metadata({"items": len(result)})
    
    # Trace an LLM call
    with trace_generation("llm.gpt-4", model="gpt-4") as gen:
        response = call_llm(prompt)
        gen.set_output(response)
        gen.set_usage(prompt_tokens=100, completion_tokens=50)
    
    trace.set_output(final_result)
```

---

## Best Practices

1. **Enable pipeline tracing** during development to identify bottlenecks
2. **Disable prompt logging** in production if handling sensitive data
3. **Set up alerts** in Langfuse for cost thresholds
4. **Review weekly** to optimize model selection and reduce costs
5. **Use session IDs** to track multi-turn conversations

---

*"The patterns reveal all."*
