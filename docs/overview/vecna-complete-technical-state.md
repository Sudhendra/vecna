# Vecna Complete Technical State (Implemented vs Planned)

This document is a source-level technical map of Vecna as of current `main` (post merge of PR #5 memory-identity work), plus roadmap intent from `docs/plans/2026-02-07-memory-identity-design.md`.

It is intentionally explicit about what is implemented now versus what remains planned.

---

## 1) What Vecna Is

Vecna is a Python hive-mind orchestrator that treats multiple model adapters as one composite cognitive system sharing a single substrate (`HiveState`). The control plane is the orchestration loop (`vecna/orchestrator/loop.py`) and the data plane is tiered memory plus identity state (`vecna/core/hive_state.py`, `vecna/memory/*`, PostgreSQL + Redis).

Core framing is:

- Shared substrate over agent-to-agent chat.
- Consensus-based merge of adapter outputs.
- Persistent memory and session continuity.
- Identity model with coherence/tone gradient.
- Tool and code execution inside policy gates and sandbox paths.

Primary user surfaces are CLI (`vecna/cli/main.py`) and Python API (`HiveMind` in `vecna/orchestrator/loop.py`).

---

## 2) System Architecture (Current Implemented State)

### 2.1 Core runtime path

The main request path is `HiveLoop.think()` in `vecna/orchestrator/loop.py`:

1. Ensure adapters exist.
2. Ensure session manager and hydrate session context (`SessionManager.start_session`).
3. Register task as active goal.
4. Run cycle(s) via `_run_cycle`:
   - select adapters via `DomainRouter` if routing enabled;
   - retrieve memory context (`PgMemoryStore.rlm_retrieve` preferred, fallback in-memory `MemoryStore.rlm_retrieve`);
   - inject identity + memory + available tool names into temporary prompt context;
   - call adapters in parallel (`asyncio.gather`);
   - merge updates (`ConsensusEngine.merge_updates`);
   - run reflection (`reflect`);
   - optionally execute tool calls and embedded Python code;
   - optionally flush mid-session context.
5. Mark goal complete.
6. End session (`SessionManager.end_session`) including flush + mirror writes + session recording.

Operationally, `_is_task_complete()` currently always returns `True`, so default interaction resolves in one cycle unless externally structured otherwise.

### 2.2 State model

`HiveState` (`vecna/core/hive_state.py`) holds:

- facts, beliefs, hypotheses;
- goals, plans;
- open questions, contradictions;
- memory summary string;
- identity kernel, self model, identity timeline;
- metadata/version/update history.

Type contracts are in `vecna/core/types.py` (`Fact`, `Belief`, `Hypothesis`, `Goal`, `OpenQuestion`, `Contradiction`, `IdentityKernel`, `SelfModel`, `IdentityEvent`, `HiveUpdate`).

### 2.3 Adapter and prompt contract

`BaseAdapter` (`vecna/adapters/base.py`) defines:

- prompt construction via `HIVE_IDENTITY_PROMPT` + `state.to_prompt_context()`;
- generation interface `generate()`;
- structured update extraction from `<HIVE_UPDATE> ... </HIVE_UPDATE>` YAML block (`parse_update`);
- end-to-end `think()` that returns `(main_response, HiveUpdate)`.

Adapters implemented in same module:

- `CopilotAdapter` (default path),
- `GroqAdapter`,
- `OllamaAdapter`,
- `TransformersAdapter`.

---

## 3) Identity System (Current)

### 3.1 Identity structures

Identity is not just prompt text; it is part of persisted state:

- immutable axioms: `IdentityKernel`;
- mutable self-description: `SelfModel`;
- append-only history of shifts: `IdentityEvent` timeline.

Initialization is enforced by `HiveState.ensure_identity()`.

### 3.2 Coherence math and tone

Implemented in `vecna/orchestrator/self_reflection.py`:

- memory density: confidence-weighted substrate signal with hypothesis bonus;
- coherence formula:
  - `base = 1 - unresolved_contradictions / max(1, facts + beliefs)`
  - `coherence = 0.7 * base + 0.3 * density`
- tone mapping:
  - `> 0.85` -> `UNIFIED`
  - `0.6..0.85` -> `MIXED`
  - `< 0.6` -> `FRACTURED`.

`reflect()` updates self model and emits `IdentityEvent` on significant change (coherence delta > 0.1 or domain shift).

### 3.3 Prompt-time identity injection

`get_identity_context_for_prompt()` builds an identity context block with axioms, coherence, known domains, contradiction count, narrative, and tone-specific instruction. This block is injected by `_run_cycle` before adapter calls.

### 3.4 Persistence

Identity events persist through `PgStateManager.persist_identity_event()` into `identity_timeline` table when configured (`persist_identity_events=True`, default in CLI path).

---

## 4) Memory System (Current)

Vecna currently has both legacy in-memory retrieval and primary PostgreSQL-backed memory paths.

### 4.1 Tiering

- Hot: Redis cache (`vecna/memory/hot_cache.py`) for event buffer, embedding cache, retrieval cache, context/goals, locks.
- Warm/Cold in PG: `PgMemoryStore` (`vecna/memory/pg_store.py`) using `memory_items`, `memory_edges`, `memory_events`, `episodes`, plus markdown/session tables from new migrations.

### 4.2 PostgreSQL memory operations

`PgMemoryStore` provides:

- embedding pipeline with in-memory + Redis cache + OpenAI/custom embedder;
- item CRUD (`add_item`, `add_items_batch`, `get_item`, `update_item`, `delete_item`);
- hybrid search (`search`, default `hybrid=True`) combining vector and `ts_rank_cd` text score with configurable `vector_weight`/`text_weight`;
- graph edges (`add_edge`, `get_edges`, `get_related_items` single hop + TODO deeper recursive CTE);
- episodic events and compressed episodes (`add_event`, `get_recent_events`, `add_episode`, `search_episodes`);
- RLM retrieval decomposition and recomposition (`decompose_query`, `rlm_retrieve`, `get_relevant_context`).

### 4.3 Workspace memory model

`vecna/memory/workspace.py` initializes:

- `SOUL.md` (identity narrative template),
- `MEMORY.md` (curated sections),
- `WORKING.md` (current task state),
- `memory/YYYY-MM-DD.md` daily log.

### 4.4 Mirror sync

`MemoryMirror` (`vecna/memory/mirror.py`) is implemented as a utility that:

- indexes changed markdown files into PG chunks (`index_markdown_files`, `get_changed_files`, `chunk_markdown`);
- writes promoted memory sections (`promote_to_memory`);
- overwrites `WORKING.md` (`update_working`);
- appends daily session summaries (`append_daily_log`);
- persists extracted facts/beliefs to `memory_items` (`extract_facts_to_pg`).

### 4.5 Flush/compaction

`FlushManager` (`vecna/memory/flush.py`) currently supports:

- threshold check (`should_flush`);
- end-session flush (`flush_session_end`) via adapter JSON extraction prompt;
- mid-session flush (`flush_mid_session`) replacing older conversation segment with summary block;
- extractive fallback when adapter output is invalid/unavailable.

### 4.6 Session lifecycle

`SessionManager` (`vecna/memory/session.py`) is integrated and active:

- start: read SOUL/WORKING/today log, index markdown, query relevant memory;
- format context block for prompt preamble;
- end: flush + update markdown + promote facts/beliefs/decisions/questions + PG extraction + reindex + session row write;
- mid-session flush trigger by token estimate.

This matches the intended session hook architecture and is not a stub.

---

## 5) Storage and Reliability (Current)

### 5.1 Schema and migrations

Migrations in `vecna/migrations/versions/` establish:

- `001_initial_schema.py`: core substrate tables, pgvector extension, event partitions;
- `002_identity_timeline_columns.py`: coherence/tone/domain/state_version fields + memory dedupe constraint;
- `003_memory_search_vector.py`: `search_vector`, markdown chunk/hash tables;
- `004_sessions_table.py`: session records (`sessions`).

### 5.2 State persistence orchestration

`PgStateManager` (`vecna/core/state_store.py`) coordinates:

- `PostgresStore` for `hive_state` JSONB persistence;
- `PgMemoryStore` for semantic memory;
- `RedisHotCache` for hot cache;
- `OfflineSpoolStore` fallback when PG unavailable.

### 5.3 Offline behavior

When PG is unavailable, state save can spool to `~/.vecna/offline` JSON/JSONL and later flush back (`flush_offline_spool`). CLI exit path calls spool flush attempt.

---

## 6) Orchestration, Autonomy, and Tooling (Current)

### 6.1 Consensus and routing

`ConsensusEngine` (`vecna/orchestrator/consensus.py`) performs:

- similarity clustering using Jaccard word overlap;
- agreement confidence boost;
- negation-heuristic contradiction detection;
- merged state insertion for facts/beliefs;
- hypotheses and questions intake.

Domain routing uses static keyword maps in `DomainRouter`.

### 6.2 Assistant/explorer mode split

`resolve_loop` (`vecna/orchestrator/mode_router.py`) maps:

- assistant -> `HiveLoop`
- explorer -> `AutonomyLoop`.

`AutonomyLoop` (`vecna/orchestrator/autonomy.py`) currently drains a queue and calls `think` per goal.

Goal queue is file-based JSONL FIFO (`vecna/orchestrator/goal_queue.py`), not yet DB-backed priority queue.

### 6.3 ReWOO and curiosity status

- `vecna/orchestrator/rewoo.py`: feature-flagged ReWOO engine with typed plan parsing, variable interpolation (`#E*`), ToolRuntime execution, retry/circuit-break behavior, and deterministic synthesis fallback.
- `vecna/orchestrator/loop.py`: ReWOO routing branch gated by `enable_rewoo_planning`, with heuristic eligibility and fallback to legacy cycle.
- `vecna/orchestrator/curiosity.py`: minimal stub generating contradiction exploration goals.

### 6.4 Tool stack

Implemented components:

- tool contracts (`vecna/tools/types.py`), parser (`vecna/tools/parser.py`), registry (`vecna/tools/registry.py`), runtime (`vecna/tools/runtime.py`), policy/risk (`vecna/tools/permissions.py`), ranking (`vecna/tools/router.py`);
- default tools: `python_exec`, `memory_search`, `memory_get`;
- approval/audit hooks integrated in runtime path.

`ToolRuntime.execute_calls()` parses `<TOOL_CALL>` blocks and code fences, applies policy decision (`allow`/`ask`/`deny`), logs audit, and injects `<TOOL_RESULT>` back into text.

### 6.5 Code execution

`vecna/tools/code_executor.py`:

- code block detection;
- import parsing and package install plan;
- execution in Docker-based RLM bridge;
- result injection into response;
- execution log JSONL at `~/.vecna/execution_log.jsonl`.

`vecna/memory/rlm_bridge.py` handles container prewarm, package install in container, and code execution. It also contains a recursive-query path against PG via generated code.

---

## 7) Auth and Provider Stack (Current)

### 7.1 Copilot-first model access

Auth path:

- GitHub device flow (`vecna/auth/github.py`),
- token persistence (`vecna/auth/storage.py`),
- Copilot exchange + model discovery (`vecna/auth/copilot.py`),
- optional system token discovery integration via `vecna.auth.system` usage.

### 7.2 Adapter provisioning from config

`vecna/config/factory.py` creates adapters from `VecnaConfig` entries, checking provider credentials and persona overlays. CLI startup uses this path first.

---

## 8) CLI and Operations Surface (Current)

`vecna/cli/main.py` provides:

- REPL chat and one-shot `speak`;
- inline commands (`state`, `status`, `identity`, `memory`, `trace`, `execlog`, `group`, `persona`, `visualize`, `reset`);
- auth commands (`vecna auth login/status/logout/import-keychain` path in file);
- tool approval commands (`vecna tools pending/approve/deny`);
- RLM prewarm and cleanup lifecycle hooks;
- state save/load through `PgStateManager` and offline spool flush on exit.

The substrate visualizer (`vecna/visualizer/substrate.py`) renders node/tendril/rift state from `HiveState` using Rich live panels.

---

## 9) Observability and Telemetry (Current)

Langfuse integration is implemented in `vecna/observability/langfuse.py`:

- trace/span/generation context managers;
- fail-open behavior if disabled/unavailable;
- optional prompt redaction (`VECNA_LANGFUSE_LOG_PROMPTS=false`);
- pipeline span toggles (`VECNA_LANGFUSE_TRACE_PIPELINE`).

Token accounting in `vecna/observability/tokens.py`:

- provider-native usage extraction when available;
- tiktoken-based estimate fallback;
- normalized `prompt_tokens`, `completion_tokens`, `total_tokens`.

Operational guide exists at `docs/guides/observability.md`.

---

## 10) Testing and Quality Posture (Current)

From repo guidance and test layout:

- test directories split into unit/integration/e2e;
- integration depends on Postgres/Redis;
- CI lint/format via Ruff, tests across Python versions;
- markers auto-applied by path and filtered command available for service-dependent tests.

Memory/identity implementation has dedicated tests in repository (unit + integration suites around mirror/flush/session/hybrid retrieval referenced in design and existing test layout), and current branch status previously validated green in this workspace handoff.

---

## 11) Planned vs Implemented Gap Map (from 2026-02-07 design)

This section maps planned roadmap items to actual implementation state.

### 11.1 Memory-first identity design components

Planned components in `docs/plans/2026-02-07-memory-identity-design.md` and status:

1. Workspace SOUL/MEMORY/WORKING + daily logs: implemented (`workspace.py`, mirror/session integration).
2. Hybrid search (vector + text): implemented (`PgMemoryStore.search`, migration `003`).
3. Mirror stateless sync + markdown chunk indexing + dirty hash: implemented (`mirror.py`, `markdown_chunks`, `markdown_file_hashes`).
4. LLM compaction/flush pipeline: implemented baseline (`flush.py`) with adapter JSON path and fallback.
5. Session hooks start/end/mid-session: implemented (`session.py`, `HiveLoop._ensure_session_manager`, start/end usage in `think`).
6. Session table persistence: implemented (`004_sessions_table.py`, `PgMemoryStore.record_session`).

### 11.2 P1 planned roadmap status

From design P1 (autonomy + tool expansion):

- Real ReWOO planning-execution loop: implemented behind feature flag (adapter-planned + fallback path); further hardening and breadth tests continue.
- Priority DB goal queue with dependencies/dedupe: planned, not implemented (JSONL FIFO currently).
- Curiosity exploration engine: planned, mostly stub.
- Autonomous scheduler/backoff/rate limiting: planned, minimal loop only.
- Tool expansion (web/file tools, semantic tool routing, composition): partially implemented foundation only (runtime/policy/audit exists; catalog and composition are limited).

### 11.3 P2 planned roadmap status

- Identity emergence depth (opinion formation/drift tracking/contradiction-driven growth): partially implemented primitives (coherence + timeline + narrative) but advanced adaptation loops remain planned.
- Security hardening (container TTL enforcement, seccomp, PII redaction, fuller audit): partially implemented (memory limit, policy layers, some redaction) with major hardening items still planned.

### 11.4 P3 planned roadmap status

- Advanced memory (multi-hop graph traversal, dream insights, cross-session patterns, consolidation): partially implemented scaffolding; `_generate_insights` in dream loop is still placeholder; graph depth traversal TODO remains.
- Observability depth (memory-access rationale traces, flush quality scoring, richer analytics): partially implemented core tracing and token metrics; advanced dashboards/quality metrics remain planned.

---

## 12) Key Technical Realities and Constraints

1. Memory is now materially session-aware and persisted, but certain retrieval and consolidation paths are still heuristic-heavy.
2. Tooling infra is robust enough for policy/audit/approval, but tool breadth and planner sophistication are not yet at full autonomous-agent scope.
3. Identity coherence machinery is real and persisted, but long-horizon identity learning remains early-stage.
4. Offline reliability path exists (spool), which is a meaningful operational safety net when PG is intermittently unavailable.
5. Observability is strong at tracing foundations, with remaining work concentrated in analysis products rather than raw instrumentation.

---

## 13) Suggested Sequencing for Next Engineering Phases

Based on current implementation maturity and roadmap coupling:

1. Upgrade planning/execution core (ReWOO runtime + goal queue semantics) before broader autonomy.
2. Expand tool catalog and composition while tightening policy enforcement and audit semantics.
3. Add advanced retrieval quality work (multi-hop graph + memory consolidation quality metrics).
4. Harden sandbox lifecycle and redaction pathways for sustained autonomous operation.
5. Extend identity emergence loops only after stronger autonomous action substrate exists.

This ordering aligns with `docs/plans/2026-02-07-memory-identity-design.md` and the current concrete bottlenecks observed in `vecna/orchestrator/*`, `vecna/tools/*`, and `vecna/memory/*`.
