# Environment Variables

> *"Secrets fuel the hive."*

This page documents all environment variables used by VECNA for API keys, connection strings, and runtime configuration.

---

## Quick Reference

### Required (At Least One)

```bash
# Model Provider API Keys (need at least one)
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GROQ_API_KEY="gsk_..."
```

### Optional

```bash
# Database connections
export VECNA_DATABASE_URL="postgresql://user:pass@localhost/vecna"
export VECNA_REDIS_URL="redis://localhost:6379"

# Configuration overrides
export VECNA_VERBOSE="true"
export VECNA_STATE_PATH="~/.vecna/hive_state.json"
```

---

## API Keys

### OpenAI

```bash
export OPENAI_API_KEY="sk-..."
```

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | For OpenAI models | API key from [platform.openai.com](https://platform.openai.com) |
| `OPENAI_ORG_ID` | No | Organization ID for billing |
| `OPENAI_BASE_URL` | No | Custom API endpoint (for proxies) |

**Usage:**
```python
hive = HiveMind()
hive.add_openai()  # Automatically uses OPENAI_API_KEY
```

### Anthropic

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | For Claude models | API key from [console.anthropic.com](https://console.anthropic.com) |
| `ANTHROPIC_BASE_URL` | No | Custom API endpoint |

**Usage:**
```python
hive.add_anthropic()  # Automatically uses ANTHROPIC_API_KEY
```

### Groq

```bash
export GROQ_API_KEY="gsk_..."
```

| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEY` | For Groq models | API key from [console.groq.com](https://console.groq.com) |

**Usage:**
```python
hive.add_groq()  # Automatically uses GROQ_API_KEY
```

### Ollama

```bash
export OLLAMA_HOST="http://localhost:11434"
```

| Variable | Required | Description |
|----------|----------|-------------|
| `OLLAMA_HOST` | No | Ollama server URL (default: `http://localhost:11434`) |

**Usage:**
```python
hive.add_ollama(model="llama3.1")  # Uses OLLAMA_HOST
```

---

## Database Connections

### PostgreSQL

```bash
export VECNA_DATABASE_URL="postgresql://user:password@localhost:5432/vecna"
```

| Variable | Required | Description |
|----------|----------|-------------|
| `VECNA_DATABASE_URL` | For PG memory | Full connection string |
| `VECNA_DB_HOST` | No | Database host (alternative to URL) |
| `VECNA_DB_PORT` | No | Database port (default: 5432) |
| `VECNA_DB_NAME` | No | Database name |
| `VECNA_DB_USER` | No | Database user |
| `VECNA_DB_PASSWORD` | No | Database password |

**Connection String Format:**
```
postgresql://[user]:[password]@[host]:[port]/[database]?[options]
```

**Examples:**
```bash
# Local development
export VECNA_DATABASE_URL="postgresql://localhost/vecna"

# With credentials
export VECNA_DATABASE_URL="postgresql://vecna_user:secret@localhost:5432/vecna"

# With SSL
export VECNA_DATABASE_URL="postgresql://user:pass@host/db?sslmode=require"

# Connection pooling
export VECNA_DATABASE_URL="postgresql://user:pass@host/db?pool_size=20"
```

### Redis

```bash
export VECNA_REDIS_URL="redis://localhost:6379/0"
```

| Variable | Required | Description |
|----------|----------|-------------|
| `VECNA_REDIS_URL` | For hot cache | Redis connection URL |
| `VECNA_REDIS_HOST` | No | Redis host (alternative to URL) |
| `VECNA_REDIS_PORT` | No | Redis port (default: 6379) |
| `VECNA_REDIS_PASSWORD` | No | Redis password |
| `VECNA_REDIS_DB` | No | Redis database number |

**Connection String Format:**
```
redis://[password@]host[:port][/database]
```

**Examples:**
```bash
# Local development
export VECNA_REDIS_URL="redis://localhost:6379"

# With password
export VECNA_REDIS_URL="redis://:mypassword@localhost:6379/0"

# Redis Cluster
export VECNA_REDIS_URL="redis://node1:6379,node2:6379,node3:6379"
```

---

## Configuration Overrides

### HiveConfig Overrides

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `VECNA_MAX_PARALLEL_MODELS` | int | 5 | Max concurrent models |
| `VECNA_USE_ROUTING` | bool | true | Enable domain routing |
| `VECNA_USE_SEMANTIC_MEMORY` | bool | true | Enable vector memory |
| `VECNA_USE_LOCAL_EMBEDDINGS` | bool | false | Use local embeddings |
| `VECNA_AUTO_EXECUTE_CODE` | bool | true | Execute Python blocks |
| `VECNA_COMPRESS_EVERY` | int | 5 | Compression frequency |
| `VECNA_MAX_CYCLES` | int | 20 | Max cycles per session |
| `VECNA_VERBOSE` | bool | true | Enable verbose logging |

**Example:**
```bash
export VECNA_MAX_PARALLEL_MODELS=3
export VECNA_VERBOSE=false
export VECNA_AUTO_EXECUTE_CODE=true
```

### ConsensusConfig Overrides

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `VECNA_MIN_FACT_CONFIDENCE` | float | 0.3 | Min fact confidence |
| `VECNA_MIN_BELIEF_CONFIDENCE` | float | 0.2 | Min belief confidence |
| `VECNA_AGREEMENT_BOOST` | float | 0.15 | Boost per agreement |
| `VECNA_SIMILARITY_THRESHOLD` | float | 0.7 | Clustering threshold |

---

## Paths & Files

| Variable | Default | Description |
|----------|---------|-------------|
| `VECNA_STATE_PATH` | `~/.vecna/hive_state.json` | State file location |
| `VECNA_LOG_PATH` | `~/.vecna/logs` | Log directory |
| `VECNA_EXEC_LOG_PATH` | `~/.vecna/execution_log.jsonl` | Code execution log |
| `VECNA_CONFIG_PATH` | `~/.vecna/config.toml` | Config file location |

**Example:**
```bash
export VECNA_STATE_PATH="/data/vecna/state.json"
export VECNA_LOG_PATH="/var/log/vecna"
```

---

## Logging & Debugging

| Variable | Values | Default | Description |
|----------|--------|---------|-------------|
| `VECNA_LOG_LEVEL` | DEBUG, INFO, WARNING, ERROR | INFO | Log level |
| `VECNA_LOG_FORMAT` | json, text | text | Log format |
| `VECNA_TRACE_MODELS` | true, false | false | Enable model tracing |
| `VECNA_DEBUG` | true, false | false | Enable debug mode |

**Example:**
```bash
export VECNA_LOG_LEVEL=DEBUG
export VECNA_LOG_FORMAT=json
export VECNA_DEBUG=true
```

---

## Docker & Sandbox

| Variable | Default | Description |
|----------|---------|-------------|
| `VECNA_DOCKER_HOST` | unix:///var/run/docker.sock | Docker socket |
| `VECNA_SANDBOX_IMAGE` | python:3.11-slim | Sandbox Docker image |
| `VECNA_SANDBOX_MEMORY_MB` | 512 | Sandbox memory limit |
| `VECNA_SANDBOX_TIMEOUT` | 30 | Sandbox timeout (seconds) |

**Example:**
```bash
export VECNA_DOCKER_HOST="tcp://localhost:2375"
export VECNA_SANDBOX_IMAGE="python:3.12-slim"
export VECNA_SANDBOX_MEMORY_MB=1024
```

---

## Loading Environment Variables

### From `.env` File

VECNA automatically loads from `.env` in the working directory:

```bash
# .env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
VECNA_VERBOSE=true
```

### From Shell

```bash
# Export in shell
export OPENAI_API_KEY="sk-..."

# Or inline
OPENAI_API_KEY="sk-..." vecna
```

### From Python

```python
import os
from dotenv import load_dotenv

# Load from .env file
load_dotenv()

# Or set programmatically
os.environ["OPENAI_API_KEY"] = "sk-..."

from vecna import HiveMind
hive = HiveMind()
```

---

## Environment Profiles

### Development

```bash
# .env.development
OPENAI_API_KEY=sk-dev-...
VECNA_DATABASE_URL=postgresql://localhost/vecna_dev
VECNA_REDIS_URL=redis://localhost:6379/1
VECNA_VERBOSE=true
VECNA_LOG_LEVEL=DEBUG
VECNA_DEBUG=true
```

### Production

```bash
# .env.production
OPENAI_API_KEY=sk-prod-...
ANTHROPIC_API_KEY=sk-ant-prod-...
VECNA_DATABASE_URL=postgresql://prod-host/vecna
VECNA_REDIS_URL=redis://prod-redis:6379/0
VECNA_VERBOSE=false
VECNA_LOG_LEVEL=INFO
VECNA_LOG_FORMAT=json
```

### Testing

```bash
# .env.test
OPENAI_API_KEY=sk-test-...
VECNA_DATABASE_URL=postgresql://localhost/vecna_test
VECNA_USE_SEMANTIC_MEMORY=false
VECNA_AUTO_EXECUTE_CODE=false
VECNA_VERBOSE=false
```

---

## Security Best Practices

!!! danger "Never Commit Secrets"
    
    **Never** commit API keys or credentials to version control.
    
    ```bash
    # .gitignore
    .env
    .env.*
    *.pem
    *.key
    ```

!!! tip "Use Secret Managers"
    
    For production, use secret managers:
    
    - AWS Secrets Manager
    - HashiCorp Vault
    - Google Secret Manager
    - Azure Key Vault
    
    ```python
    import boto3
    
    def get_secret(name):
        client = boto3.client('secretsmanager')
        response = client.get_secret_value(SecretId=name)
        return response['SecretString']
    
    os.environ["OPENAI_API_KEY"] = get_secret("vecna/openai-api-key")
    ```

!!! warning "Rotate Keys Regularly"
    
    - Rotate API keys every 90 days
    - Use separate keys for dev/staging/prod
    - Monitor key usage for anomalies

---

## Validation

VECNA validates environment on startup:

```python
from vecna import validate_environment

# Check all required variables
issues = validate_environment()

for issue in issues:
    print(f"{issue.level}: {issue.message}")

# Output:
# WARNING: OPENAI_API_KEY not set - OpenAI models unavailable
# ERROR: VECNA_DATABASE_URL invalid format
```

---

## Next Steps

- [HiveConfig](hive-config.md) - Python configuration
- [Feature Flags](feature-flags.md) - Enable experimental features
- [Security](../security/secrets.md) - Secret management
