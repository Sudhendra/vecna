# Vecna Deployment Guide

## Prerequisites

- **Python 3.10+** (3.12 recommended)
- **PostgreSQL 15+** with `pgvector` extension
- **Redis 7+** for hot-tier memory cache
- At least one LLM provider (Ollama for fully local operation)

## Quick Start

```bash
# Install with PostgreSQL support
pip install -e ".[postgres]"

# Configure environment
cp .env.example .env
# Edit .env with database credentials and API keys

# Run database migrations
alembic upgrade head

# Start interactive chat
vecna chat
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `VECNA_CONFIG_PATH` | Path to vecna.yaml | `./vecna.yaml` |
| `VECNA_LOG_LEVEL` | Logging level | `INFO` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://vecna:vecna@localhost:5432/vecna` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `GITHUB_TOKEN` | GitHub token for Copilot | — |
| `GROQ_API_KEY` | Groq API key | — |
| `OPENAI_API_KEY` | OpenAI API key | — |
| `ANTHROPIC_API_KEY` | Anthropic API key | — |
| `OLLAMA_HOST` | Ollama server URL | `http://localhost:11434` |
| `HF_TOKEN` | HuggingFace token | — |
| `VECNA_LANGFUSE_ENABLED` | Enable Langfuse tracing | `false` |
| `LANGFUSE_PUBLIC_KEY` | Langfuse public key | — |
| `LANGFUSE_SECRET_KEY` | Langfuse secret key | — |
| `LANGFUSE_BASE_URL` | Langfuse server URL | `https://cloud.langfuse.com` |
| `COMPOSIO_API_KEY` | Composio API key | — |
| `VECNA_ENCRYPTION_PASSWORD` | State encryption password | — |

## Docker Compose

```yaml
version: "3.9"

services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: vecna
      POSTGRES_PASSWORD: vecna
      POSTGRES_DB: vecna
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U vecna"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  vecna:
    build: .
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql://vecna:vecna@postgres:5432/vecna
      REDIS_URL: redis://redis:6379/0
    env_file:
      - .env
    ports:
      - "8080:8080"
    command: ["vecna", "serve", "--host", "0.0.0.0", "--port", "8080"]

volumes:
  pgdata:
  redisdata:
```

## Production

### Systemd Service

```ini
[Unit]
Description=Vecna Hive Mind Orchestrator
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=vecna
Group=vecna
WorkingDirectory=/opt/vecna
EnvironmentFile=/opt/vecna/.env
ExecStart=/opt/vecna/venv/bin/vecna serve --host 127.0.0.1 --port 8080
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Nginx Reverse Proxy

```nginx
upstream vecna {
    server 127.0.0.1:8080;
}

server {
    listen 443 ssl http2;
    server_name vecna.example.com;

    location / {
        proxy_pass http://vecna;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /ws {
        proxy_pass http://vecna;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
```

## Health Checks

The `/api/health` endpoint returns:

```json
{
  "status": "ok",
  "state_version": 42,
  "adapter_count": 3
}
```

Use for load balancer health checks. The `/api/metrics` endpoint provides detailed
operational metrics including token usage, consensus rates, and tool execution stats.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `pgvector not found` | `CREATE EXTENSION vector;` or use `pgvector/pgvector` Docker image |
| Redis connection refused | Check `REDIS_URL`, ensure Redis is running |
| `alembic: not up to date` | Run `alembic upgrade head` |
| `GITHUB_TOKEN not set` | Run `gh auth login` or set the env var |
| CUDA out of memory | Use smaller model or set `device_map: cpu` |
| Consensus timeout | Increase `model_timeout` in config |
