# VECNA — Binding Amendments & Codebase Context

> **REQUIRED READING.** This file contains the 16 binding amendments and current codebase state.
> Read this BEFORE implementing any task. Every rule here applies to every task.

---

## Current Codebase State

### What Works
- Multi-model consensus via Jaccard word overlap (`consensus.py:219-231`)
- HiveState with Facts/Beliefs/Hypotheses/Goals/Contradictions (`types.py`)
- Identity system: IdentityKernel (immutable) + SelfModel (evolving) (`types.py:312-502`)
- PostgreSQL + pgvector + Redis memory tiers (`pg_store.py`, `hot_cache.py`)
- BM25 hybrid search + multi-hop graph traversal (`pg_store.py`)
- ReWOO planning-execution pipeline (`rewoo.py`)
- Tool runtime with risk tiers, quotas, audit logging (`tools/`)
- Docker-based code execution sandbox (`code_executor.py`, `rlm_bridge.py`)
- DreamLoop with 4 phases: compress → reinforce → decay → insight (`dream_loop.py`)
- Copilot/Groq/Ollama/Transformers adapters (`adapters/base.py`)
- Rich CLI with boot sequence, chat REPL, identity views (`cli/main.py`)
- Langfuse observability tracing (`observability/langfuse.py`)
- **524 tests passing** (521 pass, 3 skipped)

### Critical Kill Signals (Must Fix)
| Issue | Location | Impact |
|-------|----------|--------|
| `_is_task_complete()` always returns True | `loop.py` | Agent never autonomously decides when to stop |
| `max(responses, key=len)` for response selection | `loop.py` | Picks longest response, not best |
| Custom `<HIVE_UPDATE>` YAML parsing | `base.py:152-193` | Fragile, models often produce malformed YAML |
| No HTTP server | Entire project | CLI-only, can't be a service or receive webhooks |
| Jaccard-only similarity | `consensus.py:219-231`, `hive_state.py:371-390` | No semantic understanding, word overlap only |
| No HumanModel | Entire project | Can't learn user preferences or adapt |
| No temporal awareness | `types.py` | Facts have timestamps but no validity windows |
| File-based GoalQueue | `goal_queue.py` | JSONL file, not durable, no concurrent access |

---

## Review Amendments (ALL 16 — BINDING)

### Architecture Amendments

**Amendment 1 — Cross-track integration checkpoints.**
Add smoke tests at weeks 4, 8, 12 to verify Track A + Track B compose correctly.
Each checkpoint instantiates the full object graph (HiveLoop → MessageRouter → adapters → tools)
and runs one end-to-end message through the stack. Catches composition bugs before Phase 3.

**Amendment 2 — Audit plan references against current codebase.**
- `vecna/orchestrator/pg_goal_queue.py` already exists — Task 10 must say "Modify:", not "Create:".
- Test count is 523 (not 378). Update "Current Codebase State" section.
- Before implementing any task, verify file existence; use "Modify:" if file exists.

**Amendment 3 — MessageRouter is the single entry point for ALL inbound messages.**
HTTP server routes (`/api/chat`, `/ws/stream`) MUST delegate to `MessageRouter.route_inbound()`,
NOT call `HiveLoop.think()` directly. The router handles session management, channel metadata,
and rate limiting. `HiveLoop.think()` is an internal API only the router calls.

**Amendment 4 — Provider enum as canonical adapter routing key.**
`create_adapter()` in `adapters/base.py` must use `match config.provider` on the `Provider` enum
(not string matching or substring heuristics). Add `OPENAI` and `ANTHROPIC` to `Provider` enum
in Task 18 before creating the adapter classes.

### Code Quality Amendments

**Amendment 5 — Shared tool-call parsing; no duplicate `parse_update()` methods.**
Task 7 defines `parse_tool_call_update()` in `tool_calling.py`. OpenAI adapter (Task 18a)
and Anthropic adapter (Task 18b) MUST import and use this shared function.
Do NOT write a `parse_update()` method in either adapter. Same for `build_hive_update_tool_schema()` —
one definition in `tool_calling.py`, used everywhere.

**Amendment 6 — Field name is `source_model`, not `source`.**
The existing `Fact` dataclass uses `source_model` (types.py:34). All plan code using `source=`
on Fact/Belief/HiveUpdate objects must use `source_model=`. Convention: `source_model` = which
adapter produced it, `source_type` = episodological classification (observation, inference,
told, derived).

**Amendment 7 — `SerializableMixin` for all dataclasses.**
Add `SerializableMixin` to `vecna/core/types.py` with a generic `to_dict()` using
`dataclasses.asdict()` + datetime/enum converter. All dataclasses inherit from it.
Do NOT write individual `to_dict()` methods — the mixin handles it.

**Amendment 8 — Specific exception types at every catch site.**
Never use bare `except Exception as e:`. Every `try/except` must catch the most specific
exception type: `openai.APIError`, `anthropic.APIError`, `json.JSONDecodeError`,
`asyncio.TimeoutError`, `aiohttp.ClientError`, `playwright.async_api.Error`,
`sqlalchemy.exc.SQLAlchemyError`, `redis.RedisError`, `KeyError`, `ValueError`, etc.
Only use `except Exception` at top-level entry points (CLI, HTTP handler) as a last resort.

### Test Amendments

**Amendment 9 — No trivial assertions.**
Tests must NOT use `isinstance(x, SomeClass)`, `x is not None`, or `len(x) > 0` as their
primary assertion. Assert specific values, specific field contents, specific behaviors.
Example: not `assert isinstance(fact, Fact)` but `assert fact.content == "expected"`.

**Amendment 10 — Error path test minimums.**
Every task must include at least 2 error/edge-case tests. Externally-facing components
(HTTP server, channel adapters, native adapters) must have at least 4 error tests covering:
malformed input, authentication failures, timeout/connection errors, and resource exhaustion.

**Amendment 11 — Test through public interface only.**
Tests must NOT access private attributes (`_channels`, `_sessions`, `_human_model`, `_pending`).
Add public accessor methods where needed (`list_channels()`, `get_session_count()`).
Pass dependencies via constructor parameters, not by setting private attributes after construction.

**Amendment 12 — Concurrency tests for shared mutable state.**
Add `asyncio.gather()` stress tests for: HiveState (concurrent `add_fact()`),
MetricsCollector (concurrent `record_*`), MessageRouter (concurrent `route_inbound()`),
PgGoalQueue (concurrent `push()`/`pop()`). Each test runs 50+ concurrent operations
and asserts no data loss or corruption.

### Performance Amendments

**Amendment 13 — Per-adapter timeout and circuit breaker.**
Wrap each adapter's `think()` call in `asyncio.wait_for(timeout=config.adapter_timeout)`.
Add a `CircuitBreaker` dataclass per adapter: after N consecutive failures (default 3),
skip that adapter for exponentially increasing cooldown (30s, 60s, 120s, max 300s).
Log when adapters are skipped. Circuit breaker resets on success.

**Amendment 14 — pgvector for fact deduplication; embeddings for response similarity.**
`add_fact()` must check for similar existing facts via pgvector cosine similarity query
(`ORDER BY embedding <=> $1 LIMIT 5, threshold 0.9`) instead of in-memory Jaccard.
Response-level consensus comparison (3-6 items) uses embedding cosine similarity
instead of Jaccard word overlap. Pairwise is acceptable since n = number of adapters.

**Amendment 15 — Batch DreamLoop database operations.**
Replace per-item UPDATEs in `_reinforce_memories` and `_decay_memories` with batched
`UPDATE ... FROM (VALUES ...) AS data(id, val) WHERE table.id = data.id` statements.
Store `source_event_ids` as a JSONB array (not stringified), use `@>` containment operator
with GIN index. Requires an Alembic migration for the JSONB format change.

**Amendment 16 — Cache `to_prompt_context()` with token budget.**
Add `_context_cache`/`_context_dirty` to HiveState. Any mutation sets dirty flag.
`to_prompt_context()` returns cached string if clean. Add `max_context_tokens` parameter
(default 4000) with relevance-based truncation: recent facts first, high-confidence beliefs
first, skip older/lower-confidence items when budget exceeded.

---

## Tech Stack
Python 3.10+, asyncio, PostgreSQL + pgvector, Redis, Docker (code sandbox), aiohttp (HTTP server), Playwright (browser), Composio (integrations), steipete CLIs (imsg, wacli, gogcli, summarize), MoA (consensus upgrade), Fernet encryption (substrate at rest), Alembic (migrations).

## Implementation Rules
1. Before implementing any task, **verify file existence** — use "Modify:" if file exists (Amendment 2).
2. **Run the task's tests first** to verify they fail, then implement, then verify they pass.
3. **Run full test suite** (`pytest tests/unit/ -v --tb=short`) after each task for regression check.
4. **Commit after each task** with message: `feat: <short description>`.
5. All code must pass `ruff check .` and `ruff format --check .`.
