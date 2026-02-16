# AGENTS.md - Vecna

## What This Is

Vecna (Virtual Emergent Collective Neural Architecture) is a Python hive-mind orchestrator
for AI models. Shared mental state, consensus, memory (PostgreSQL + pgvector + Redis),
adapters for multiple LLM providers (Copilot, Groq, Ollama, local HuggingFace, OpenAI, Anthropic).

Key concepts: Primary Cortex (hierarchy, not democracy), HumanModel (learned user preferences),
DreamLoop (autonomous background processing), Cognitive Substrate (unified mental state).

---

## Engineering Preferences

These are non-negotiable and guide every decision:

- **DRY** — flag repetition aggressively. If logic exists in two places, extract it.
- **Well-tested** — more tests > fewer tests. Every new feature needs tests first (TDD).
- **"Engineered enough"** — not fragile/hacky, not prematurely abstracted. Find the middle.
- **Edge cases matter** — handle more, not fewer. Thoughtfulness > speed.
- **Explicit over clever** — if it needs a comment to explain, simplify it.
- **Errors never pass silently** — specific exceptions, never bare `except:`.

When reviewing or changing code, evaluate: architecture (boundaries, coupling, data flow),
code quality (DRY, error handling, edge cases), tests (coverage, assertions, failure modes),
performance (N+1 queries, memory, caching). For each issue: describe with file references,
present 2-3 options with tradeoffs, recommend one, ask before proceeding.

Do not assume my priorities on timeline or scale.

---

## Build, Test, Lint

```bash
pip install -e ".[dev,postgres]"          # Dev install
pytest                                    # All tests
pytest tests/unit/                        # Unit only
pytest tests/integration/                 # Needs Postgres + Redis
pytest -k "test_add_fact"                 # Single test by keyword
ruff check .                              # Lint (CI-enforced)
ruff format --check .                     # Format (CI-enforced)
alembic upgrade head                      # Apply migrations
```

Ruff is the only CI-enforced tool. Line length: **100 chars**. Target: **Python 3.10+**.
**asyncio_mode = auto** — no `@pytest.mark.asyncio` needed.

Test markers: `unit`, `integration`, `e2e` (auto-applied by path), `requires_postgres`,
`requires_redis`, `requires_docker`, `requires_copilot`, `requires_langfuse`.

---

## TDD Workflow

1. Write failing tests first
2. Implement minimal code to pass
3. Verify: `pytest` passes, `ruff check .` clean, `ruff format --check .` clean
4. Commit: small, focused, per feature/fix

---

## Code Conventions

**Imports:** Module docstring first. Three groups separated by blank lines: stdlib, third-party, local.

**Types:** Use `typing` module style (`List[str]`, `Optional[int]`, not `list[str]`).
All function signatures have type hints. Use `@dataclass` for structured data, not Pydantic.

**Naming:** Files `snake_case.py`, classes `PascalCase`, functions `snake_case`,
constants `UPPER_SNAKE_CASE`, loggers `logging.getLogger("vecna.<module>")`,
tests `class TestThing:` with `test_*` methods.

**Classes:** ABCs for interfaces (`BaseAdapter(ABC)` + `@abstractmethod`),
dataclasses for data (`field(default_factory=...)` for mutables), enums for finite sets.

**Error handling:** Specific exceptions, never bare `except:`. Logging via `logging.getLogger`,
never `print()`. Rich for user-facing CLI output. Core orchestration is async; use `aiohttp`, not `requests`.

**Tests:** Class-based grouping, fixtures in `tests/conftest.py`, mock embedder for CI
(deterministic 1536-dim vectors), no asyncio decorator needed.

---

## Project Layout

```
vecna/
  adapters/     # LLM provider interfaces (base ABC + implementations)
  auth/         # GitHub/Copilot authentication
  channels/     # Channel adapters (CLI, iMessage, WhatsApp, Slack, Discord)
  cli/          # Click CLI
  config/       # Configuration schema, loading, factory
  core/         # HiveState, types, HumanModel
  integrations/ # External services (Google Suite, Composio, Observer)
  memory/       # Hot (Redis), warm (pgvector), cold (PG episodic)
  migrations/   # Alembic DB migrations
  observability/# Langfuse tracing, token counting
  orchestrator/ # Consensus, goals, mode routing, ReWOO, thoughtfulness
  security/     # Encryption at rest, privacy controls
  server/       # HTTP server (aiohttp), API routes, WebSocket
  tools/        # Registry, permissions, sandbox, browser, summarizer
  tui/          # Textual-based TUI
  utils/        # Shared utilities
  visuals/      # ASCII art, boot animations, themes
tests/
  unit/         # Fast, no external services
  integration/  # Needs Postgres/Redis
  e2e/          # Full stack end-to-end
  safety/       # Safety constraint tests
docs/plans/     # Implementation plans — read before feature work
```

---

## Dependency Rules

- Optional deps go in `pyproject.toml` extras (server, browser, integrations, security, tui)
- Core (`vecna/core/`, `vecna/orchestrator/`) must never import from optional extras
- Use `try: import X except ImportError:` for optional deps at module level
- All new modules follow ABC pattern: `BaseX(ABC)` with concrete implementations
- All integrations toggle on/off via config — never hard-fail on missing deps
- steipete CLIs (imsg, wacli, gogcli, summarize) are subprocess calls, not imports

---

## Known Issues (Active)

These are bugs in the current codebase. If you touch these files, fix them:

- `_is_task_complete()` always returns True — `orchestrator/loop.py`
- `max(responses, key=len)` picks longest, not best — `orchestrator/loop.py`
- Custom `<HIVE_UPDATE>` YAML parsing is fragile — `adapters/base.py:152-193`
- Jaccard-only similarity, no semantics — `orchestrator/consensus.py:219-231`
- File-based GoalQueue (JSONL), not durable — `orchestrator/goal_queue.py`

---

## Implementation Plans

Before starting feature work, read the relevant plan:
- **Master plan:** `docs/plans/2026-02-16-vecna-master-implementation-plan.md`

It has exact file paths, test code, and step-by-step implementation for 29 tasks
across three phases (Foundation → Integration → Convergence).

---

## The Zen of Python

A philosophical take on coding principles with python which should be translated directly into your implementation of the code.

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