# AGENTS.md - Vecna Codebase Guide for AI Agents

## Project Overview

Vecna (Virtual Emergent Collective Neural Architecture) is a Python hive-mind orchestrator
for AI models. It manages shared mental state, consensus, memory (PostgreSQL + pgvector + Redis),
and adapters for multiple LLM providers (Copilot, Groq, Ollama, local HuggingFace models).

## Build & Install

```bash
pip install -e ".[dev,postgres]"          # Dev install with all test deps
pip install -e ".[all]"                   # Everything including local models
```

## Lint & Format

```bash
ruff check .                              # Lint (CI-enforced)
ruff format --check .                     # Format check (CI-enforced)
ruff check --fix .                        # Auto-fix lint issues
ruff format .                             # Auto-format
```

Ruff is the primary tool. Black is also configured but CI only runs Ruff.
Line length: **100 characters**. Target: **Python 3.10+**.

## Test Commands

```bash
pytest                                    # Run all tests (verbose, short traceback)
pytest tests/unit/                        # Unit tests only
pytest tests/integration/                 # Integration tests (needs Postgres + Redis)
pytest tests/e2e/                         # End-to-end CLI tests
pytest -m unit                            # Run by marker
pytest -m "not requires_docker"           # Skip Docker-dependent tests

# Single test file
pytest tests/unit/test_hive_state.py

# Single test function
pytest tests/unit/test_hive_state.py::TestFactOperations::test_add_fact

# Single test by keyword
pytest -k "test_add_fact"

# CI command (skips external service tests)
pytest -v -m "not requires_docker and not requires_copilot and not requires_langfuse"
```

**asyncio_mode = auto** -- async test functions are detected automatically, no decorator needed.

### Test Markers

- `unit` -- auto-applied to `tests/unit/` (no external services)
- `integration` -- auto-applied to `tests/integration/`
- `e2e` -- auto-applied to `tests/e2e/`
- `requires_postgres`, `requires_redis`, `requires_docker`, `requires_copilot`, `requires_langfuse`

Tests are auto-marked by path in `tests/conftest.py` via `pytest_collection_modifyitems`.

### Database Migrations

```bash
alembic upgrade head                      # Apply all migrations
```

Migrations live in `vecna/migrations/versions/`.

## Code Style Guidelines

### File Structure

Every Python file starts with a module-level docstring:
```python
"""PostgreSQL Memory Store with pgvector support."""
```

### Import Order (3 groups, separated by blank lines)

1. **Standard library** -- `dataclasses`, `typing`, `datetime`, `enum`, `uuid`, `asyncio`, `logging`, `os`, `json`
2. **Third-party** -- `numpy`, `click`, `rich`, `dotenv`, `yaml`, `aiohttp`
3. **Local project** -- `from vecna.core.types import ...`

```python
"""Module docstring."""
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime
import logging

import numpy as np

from vecna.core.types import HiveUpdate, Goal
from vecna.adapters.base import BaseAdapter
```

### Type Annotations

- Use `typing` module style: `List[str]`, `Dict[str, Any]`, `Optional[int]` (not `list[str]`)
- All function signatures should have type hints
- Use `@dataclass` extensively for structured data (not Pydantic)

### Naming Conventions

- **Files**: `snake_case.py` (e.g., `hive_state.py`, `pg_store.py`, `dream_loop.py`)
- **Classes**: `PascalCase` (e.g., `HiveState`, `ConsensusEngine`, `PgMemoryStore`)
- **Functions/methods**: `snake_case` (e.g., `add_fact`, `should_flush`, `get_identity_context_for_prompt`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `VECNA_BANNER`)
- **Test classes**: `Test*` prefix (e.g., `TestFactOperations`, `TestBeliefOperations`)
- **Test functions**: `test_*` prefix
- **Loggers**: `logging.getLogger("vecna.<module_name>")`

### Class Design

- **ABCs** for interfaces: `BaseAdapter(ABC)` with `@abstractmethod`
- **Dataclasses** for data: `@dataclass` with `field(default_factory=...)` for mutable defaults
- **Enums** for finite sets: `class AgentMode(Enum)`, `class RiskTier(Enum)`

### Error Handling

- Errors should never pass silently (see Zen below)
- Use specific exception types, not bare `except:`
- Logging via `logging.getLogger("vecna.<module>")` -- never `print()` for diagnostics
- Rich library for user-facing console output in CLI

### Async Patterns

- `asyncio_mode = auto` in tests -- async functions auto-detected
- Core orchestration is async (`HiveLoop`, adapters)
- Use `aiohttp` for HTTP, not `requests`

### Project Layout

```
vecna/
  adapters/     # LLM provider interfaces (base ABC + implementations)
  auth/         # GitHub/Copilot authentication
  cli/          # Click CLI + TUI
  config/       # Configuration schema, loading, factory
  core/         # HiveState, types (Fact, Belief, Hypothesis, Goal, HiveUpdate)
  memory/       # Memory tiers: hot (Redis), warm (pgvector), cold (PG episodic)
  migrations/   # Alembic DB migrations
  observability/# Langfuse tracing, token counting
  orchestrator/ # Consensus, curiosity, goals, mode routing, ReWOO, self-reflection
  tools/        # Tool registry, permissions, sandboxed execution, parsing
  utils/        # Shared utilities
  visuals/      # ASCII art, boot animations, themes
  visualizer/   # Substrate visualizer
tests/
  unit/         # Fast, no external services
  integration/  # Needs Postgres/Redis
  e2e/          # CLI end-to-end
```

### Test Style

- Class-based grouping: `class TestFactOperations:` containing related `test_*` methods
- Fixtures defined in `tests/conftest.py` (session and function-scoped)
- Mock embedder provided for CI (deterministic 1536-dim vectors, no API key needed)
- No `@pytest.mark.asyncio` needed -- auto mode is on

## CI Pipeline (.github/workflows/ci.yml)

- **lint** job: Python 3.12, runs `ruff check .` and `ruff format --check .`
- **tests** job: Matrix across Python 3.10, 3.11, 3.12 with Postgres (pgvector) + Redis services
- Tests skip: `requires_docker`, `requires_copilot`, `requires_langfuse`

## The Zen of Python (Applied to Vecna)

```
Beautiful is better than ugly.
Explicit is better than implicit.
Simple is better than complex.
Complex is better than complicated.
Flat is better than nested.
Sparse is better than dense.
Readability counts.
Special cases aren't special enough to break the rules.
Although practicality beats purity.
Errors should never pass silently.
Unless explicitly silenced.
In the face of ambiguity, refuse the temptation to guess.
There should be one-- and preferably only one --obvious way to do it.
Although that way may not be obvious at first unless you're Dutch.
Now is better than never.
Although never is often better than *right* now.
If the implementation is hard to explain, it's a bad idea.
If the implementation is easy to explain, it may be a good idea.
Namespaces are one honking great idea -- let's do more of those!
```

These principles are core to Vecna's design. Prefer explicit dataclasses over magic dicts,
clear module boundaries over monolithic files, and readable code over clever abstractions.
