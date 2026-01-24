# HiveConfig

> *"Configure the collective consciousness."*

`HiveConfig` is the primary configuration object for VECNA's HiveMind orchestrator. It controls model execution, memory behavior, and system-wide settings.

---

## Overview

```python
from vecna import HiveConfig

config = HiveConfig(
    max_parallel_models=5,
    use_routing=True,
    use_semantic_memory=True,
    auto_execute_code=True,
    verbose=True,
)
```

---

## Complete Reference

### Model Execution

#### `max_parallel_models`

Maximum number of models to query simultaneously.

| Property | Value |
|----------|-------|
| Type | `int` |
| Default | `5` |
| Range | `1` - `10` |

```python
config = HiveConfig(max_parallel_models=3)
```

**Guidance:**
- `1-2`: Low latency, less consensus
- `3-4`: Balanced (recommended)
- `5+`: Maximum consensus, higher latency and cost

#### `use_routing`

Enable domain-based model routing.

| Property | Value |
|----------|-------|
| Type | `bool` |
| Default | `True` |

```python
config = HiveConfig(use_routing=True)
```

When enabled, the DomainRouter selects optimal models based on query type:
- `code` queries → GPT-4, Claude
- `science` queries → GPT-4, Groq
- `creative` queries → Claude, GPT-4

#### `timeout_seconds`

Per-model response timeout.

| Property | Value |
|----------|-------|
| Type | `float` |
| Default | `30.0` |
| Range | `5.0` - `120.0` |

```python
config = HiveConfig(timeout_seconds=45.0)
```

#### `wait_for_all`

Wait for all models to respond before consensus.

| Property | Value |
|----------|-------|
| Type | `bool` |
| Default | `False` |

```python
config = HiveConfig(wait_for_all=True)
```

- `False`: Return as soon as minimum consensus reached
- `True`: Wait for all models (slower but more thorough)

---

### Memory Settings

#### `use_semantic_memory`

Enable vector-based semantic memory.

| Property | Value |
|----------|-------|
| Type | `bool` |
| Default | `True` |

```python
config = HiveConfig(use_semantic_memory=True)
```

When enabled:
- Facts, beliefs, hypotheses are stored with embeddings
- Retrieval uses semantic similarity search
- RLM pattern enriches prompts with relevant context

#### `use_local_embeddings`

Use local embedding model instead of OpenAI.

| Property | Value |
|----------|-------|
| Type | `bool` |
| Default | `False` |

```python
config = HiveConfig(use_local_embeddings=True)
```

- `False`: Use OpenAI `text-embedding-3-small` (1536 dims)
- `True`: Use local `all-MiniLM-L6-v2` (384 dims)

!!! warning "Dimension Mismatch"
    Switching embedding models requires re-embedding all stored memories.

#### `compress_every`

Compress memory every N cycles.

| Property | Value |
|----------|-------|
| Type | `int` |
| Default | `5` |
| Range | `1` - `100` |

```python
config = HiveConfig(compress_every=10)
```

Compression:
- Merges redundant facts
- Summarizes low-value items
- Reduces memory size

#### `max_memory_items`

Maximum items in active memory.

| Property | Value |
|----------|-------|
| Type | `int` |
| Default | `1000` |
| Range | `100` - `10000` |

```python
config = HiveConfig(max_memory_items=500)
```

When exceeded, lowest-confidence items are archived.

---

### Code Execution

#### `auto_execute_code`

Automatically execute Python code blocks in responses.

| Property | Value |
|----------|-------|
| Type | `bool` |
| Default | `True` |

```python
config = HiveConfig(auto_execute_code=True)
```

When enabled:
- Detects ` ```python ` blocks in responses
- Executes in Docker sandbox (RLM bridge)
- Replaces hallucinated output with real output

#### `code_timeout_seconds`

Timeout for code execution.

| Property | Value |
|----------|-------|
| Type | `float` |
| Default | `30.0` |
| Range | `5.0` - `120.0` |

```python
config = HiveConfig(code_timeout_seconds=60.0)
```

#### `sandbox_memory_mb`

Memory limit for code sandbox.

| Property | Value |
|----------|-------|
| Type | `int` |
| Default | `512` |
| Range | `128` - `4096` |

```python
config = HiveConfig(sandbox_memory_mb=1024)
```

---

### Session Settings

#### `max_cycles`

Maximum hive loop cycles per session.

| Property | Value |
|----------|-------|
| Type | `int` |
| Default | `20` |
| Range | `1` - `1000` |

```python
config = HiveConfig(max_cycles=50)
```

Safety limit to prevent runaway sessions.

#### `state_path`

Path to persist hive state.

| Property | Value |
|----------|-------|
| Type | `str` |
| Default | `~/.vecna/hive_state.json` |

```python
config = HiveConfig(state_path="/data/vecna/state.json")
```

#### `auto_save`

Automatically save state after each interaction.

| Property | Value |
|----------|-------|
| Type | `bool` |
| Default | `True` |

```python
config = HiveConfig(auto_save=True)
```

---

### Logging & Debugging

#### `verbose`

Enable verbose logging.

| Property | Value |
|----------|-------|
| Type | `bool` |
| Default | `True` |

```python
config = HiveConfig(verbose=True)
```

When enabled:
- Logs model dispatch and responses
- Shows consensus details
- Displays memory operations

#### `log_level`

Logging level.

| Property | Value |
|----------|-------|
| Type | `str` |
| Default | `"INFO"` |
| Values | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

```python
config = HiveConfig(log_level="DEBUG")
```

#### `trace_models`

Record detailed model contribution traces.

| Property | Value |
|----------|-------|
| Type | `bool` |
| Default | `False` |

```python
config = HiveConfig(trace_models=True)
```

Enables the `trace` command in CLI.

---

## Configuration Presets

### Interactive Chat

Optimized for conversational use:

```python
config = HiveConfig(
    max_parallel_models=3,
    timeout_seconds=30.0,
    wait_for_all=False,
    use_semantic_memory=True,
    auto_execute_code=True,
    verbose=True,
)
```

### Batch Processing

Optimized for quality over latency:

```python
config = HiveConfig(
    max_parallel_models=5,
    timeout_seconds=120.0,
    wait_for_all=True,
    use_semantic_memory=True,
    compress_every=10,
    verbose=False,
)
```

### Low Resource

Minimal resource usage:

```python
config = HiveConfig(
    max_parallel_models=2,
    use_semantic_memory=False,
    use_local_embeddings=True,
    auto_execute_code=False,
    max_memory_items=100,
)
```

### Development

For debugging:

```python
config = HiveConfig(
    max_parallel_models=1,
    verbose=True,
    log_level="DEBUG",
    trace_models=True,
    auto_save=False,
)
```

---

## Programmatic Access

### Reading Configuration

```python
hive = HiveMind(config=config)

# Access current config
print(hive.config.max_parallel_models)
print(hive.config.use_semantic_memory)
```

### Runtime Modification

```python
# Modify at runtime
hive.config.verbose = False
hive.config.max_parallel_models = 2

# Some settings require restart
hive.config.use_local_embeddings = True  # Requires re-init
```

### Export/Import

```python
# Export to dict
config_dict = config.to_dict()

# Import from dict
config = HiveConfig.from_dict(config_dict)

# Export to TOML
config.to_toml("config.toml")

# Import from TOML
config = HiveConfig.from_toml("config.toml")
```

---

## Environment Variable Overrides

All HiveConfig options can be set via environment variables:

| Config Option | Environment Variable |
|---------------|---------------------|
| `max_parallel_models` | `VECNA_MAX_PARALLEL_MODELS` |
| `use_routing` | `VECNA_USE_ROUTING` |
| `use_semantic_memory` | `VECNA_USE_SEMANTIC_MEMORY` |
| `use_local_embeddings` | `VECNA_USE_LOCAL_EMBEDDINGS` |
| `auto_execute_code` | `VECNA_AUTO_EXECUTE_CODE` |
| `verbose` | `VECNA_VERBOSE` |
| `state_path` | `VECNA_STATE_PATH` |

```bash
export VECNA_MAX_PARALLEL_MODELS=3
export VECNA_VERBOSE=false
```

---

## Validation

```python
from vecna import HiveConfig, validate_config

config = HiveConfig(
    max_parallel_models=100,  # Too high
    compress_every=-1,        # Invalid
)

errors, warnings = validate_config(config)
# errors: ["compress_every must be positive"]
# warnings: ["max_parallel_models > 10 may cause high latency"]
```

---

## Best Practices

!!! tip "HiveConfig Tips"
    
    1. **Start with 3 models** - Good balance of consensus and speed
    2. **Enable routing** - Automatically selects best models
    3. **Keep semantic memory on** - Essential for context
    4. **Use presets** - Start from a preset and customize
    5. **Monitor memory usage** - Adjust `max_memory_items` as needed

---

## Next Steps

- [ConsensusConfig](consensus-config.md) - Configure response merging
- [Environment Variables](environment.md) - API keys and secrets
- [Feature Flags](feature-flags.md) - Experimental features
