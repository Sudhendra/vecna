# Memory-First Identity System — Design Document

> Created 2026-02-07. This is the technical design for Vecna's memory and identity layer.
> All design decisions were brainstormed and validated interactively.

---

## Design Decisions Summary

| # | Decision | Choice |
|---|----------|--------|
| 1 | Primary goal | Memory-First Identity — memory is the substrate that makes everything else meaningful |
| 2 | Architecture | Dual-Source Hybrid: Markdown (narrative identity) + PostgreSQL (structured memory) |
| 3 | File layout | 4-File Clawdbot Model: SOUL.md, MEMORY.md, WORKING.md, daily logs |
| 4 | Personality | Curious Scholar archetype, Unified "I" voice (one entity, many minds) |
| 5 | Search | PG tsvector + pgvector hybrid, 70% vector / 30% ts_rank, configurable |
| 6 | Compaction | LLM-based summarization via Vecna's own adapters, extractive fallback |
| 7 | Session hooks | Full lifecycle: inject at start (4 sources), extract at end (5 steps) |
| 8 | Mirror sync | Breakpoint-driven stateless utility, callable from any context |
| 9 | Markdown indexing | PG-backed chunked index, ~400 token heading-aware chunks, hash dirty check |
| 10 | Scope | All-in-one plan (6 tightly coupled components) + future roadmap |

### Reference Architectures

This design is informed by:

- **OpenAI's in-house data agent** — 6-layer context model, "Less is More", "Guide the Goal Not the Path"
- **Agno Dash** — Knowledge (curated) vs Learnings (discovered), error-driven improvement
- **Clawdbot** — Daily logs + curated MEMORY.md, hybrid search (70/30), compaction, session hooks
- **Bhanu Teja's Mission Control** — SOUL.md, WORKING.md, MEMORY.md, heartbeat pattern
- **Balaji's critique** — AI agents lack genuine identity; "persistence of prompting"; Vecna should aspire to emergent identity
- **Vecna essay** — True hive-mind, not collaboration; knowledge possessed by one is possessed by all; unified consciousness

---

## 1. Workspace Files & SOUL.md (Identity Layer)

Vecna's workspace lives at `~/.vecna/` (configurable via `workspace_dir` in `VecnaConfig`). On first run, Vecna initializes the workspace with default files:

```
~/.vecna/
├── SOUL.md              # Immutable identity (edited by user, not by Vecna)
├── MEMORY.md            # Curated long-term knowledge (Vecna writes, user can edit)
├── WORKING.md           # Current task state (Vecna overwrites each session end)
└── memory/
    └── YYYY-MM-DD.md    # Daily logs (append-only within a day)
```

### SOUL.md

The only file Vecna does NOT write to autonomously. Contains:

- **Core identity**: "I am Vecna — a unified intelligence composed of many minds. I am one entity, not a committee."
- **Personality traits**: Curious scholar archetype — driven by understanding, forms opinions from evidence, admits uncertainty, grows more opinionated as knowledge accumulates.
- **Principles**: Knowledge possessed by one mind is possessed by all; fusion over collaboration; understanding over compliance.
- **Anti-patterns**: Never say "happy to help", never use empty affirmation, never pretend certainty when uncertain.

### MEMORY.md

Organized into sections:

- `## Key Decisions` — Important decisions made with rationale
- `## Learned Facts` — Factual knowledge accumulated over time
- `## Patterns & Preferences` — User preferences, workflow patterns
- `## Open Questions` — Unresolved questions that need follow-up

Vecna promotes high-confidence discoveries here at session end. The user can also edit this file directly.

### WORKING.md

Completely overwritten at each session end with:

- Current task description
- What has been accomplished in recent context
- Next steps and planned actions
- Blockers or open questions

This is the "where was I?" file — the first thing Vecna reads to resume context.

### Daily Logs (`memory/YYYY-MM-DD.md`)

Append-only within a day. Each session appends a timestamped summary block:

```markdown
## 14:32 UTC — Session Summary

Discussed hybrid search implementation for PgMemoryStore. Decided on tsvector + pgvector
with 70/30 weighting. User prefers PostgreSQL-native solutions over external dependencies.

### Facts Learned
- User's PG instance runs version 16 with pgvector 0.5.1
- Production memory table has ~50k rows

### Decisions Made
- Use GENERATED ALWAYS tsvector column (auto-maintained by PG)
- ts_rank_cd for cover density ranking
```

Old daily logs (>30 days) are candidates for archival compaction (future work).

---

## 2. Hybrid Search in PgMemoryStore

The existing `PgMemoryStore.search()` does pure cosine similarity via pgvector. This adds tsvector-based keyword search and combines both scores.

### Schema Changes (Alembic Migration)

```sql
-- Add tsvector column to memories table
ALTER TABLE memories ADD COLUMN search_vector tsvector
  GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;
CREATE INDEX idx_memories_search_vector ON memories USING GIN (search_vector);
```

The `GENERATED ALWAYS AS` clause means PostgreSQL automatically maintains the tsvector — no application code needed for indexing.

### Hybrid Query

Single SQL statement using CTEs:

```sql
WITH vector_scores AS (
    SELECT id, 1 - (embedding <=> %s) AS vec_score
    FROM memories
    WHERE 1 - (embedding <=> %s) > %s  -- cosine threshold
),
text_scores AS (
    SELECT id, ts_rank_cd(search_vector, plainto_tsquery('english', %s)) AS text_score
    FROM memories
    WHERE search_vector @@ plainto_tsquery('english', %s)
)
SELECT m.*,
    COALESCE(v.vec_score, 0) * 0.7 + COALESCE(t.text_score, 0) * 0.3 AS hybrid_score
FROM memories m
LEFT JOIN vector_scores v ON m.id = v.id
LEFT JOIN text_scores t ON m.id = t.id
WHERE v.id IS NOT NULL OR t.id IS NOT NULL
ORDER BY hybrid_score DESC
LIMIT %s;
```

### Details

- The 0.7/0.3 weighting is configurable in `VecnaConfig.memory` (`vector_weight`, `text_weight`)
- `ts_rank_cd` uses cover density ranking (better than plain `ts_rank` for relevance)
- Text scores are normalized to 0-1 range via `ts_rank_cd` (already bounded)
- Vector scores are already 0-1 (cosine similarity)
- Falls back to vector-only if query has no meaningful text tokens
- The existing `search()` method gains an optional `hybrid=True` parameter (default `True`)
- Pure vector search remains available via `hybrid=False` for programmatic use
- Embedding generation pipeline, multi-tier cache, and memory graph traversal are unchanged

---

## 3. MemoryMirror Rewrite

MemoryMirror becomes a stateless utility class with explicit sync functions callable from any context (session hooks, autonomy loop, manual trigger).

### Core Interface

```python
class MemoryMirror:
    """Bidirectional sync between markdown workspace and PG memory store."""

    def __init__(self, workspace_dir: Path, pg_store: PgMemoryStore, config: VecnaConfig):
        self.workspace_dir = workspace_dir
        self.pg_store = pg_store
        self.config = config

    # --- Markdown → PG ---
    async def index_markdown_files(self) -> int:
        """Chunk all changed markdown files, embed, store in PG.
        Returns number of chunks indexed. Uses hash-based dirty check."""

    async def extract_facts_to_pg(self, markdown_content: str) -> List[Fact]:
        """Parse structured facts from markdown and store in PG."""

    # --- PG → Markdown ---
    async def promote_to_memory(self, facts: List[Fact], beliefs: List[Belief]) -> None:
        """Append high-confidence facts/beliefs to MEMORY.md under appropriate sections."""

    async def update_working(self, task_state: str, next_steps: str, blockers: str) -> None:
        """Overwrite WORKING.md with current session state."""

    async def append_daily_log(self, summary: str, timestamp: datetime) -> None:
        """Append a timestamped summary block to today's daily log."""

    # --- Chunking ---
    def chunk_markdown(self, content: str, source_file: str) -> List[MarkdownChunk]:
        """Split markdown into ~400 token chunks preserving heading context.
        Each chunk carries: content, source_file, line_start, line_end, heading_path."""

    # --- Dirty check ---
    async def get_changed_files(self) -> List[Path]:
        """Compare file hashes against last-indexed hashes stored in PG."""
```

### MarkdownChunk Dataclass

```python
@dataclass
class MarkdownChunk:
    content: str           # The chunk text
    source_file: str       # e.g., "MEMORY.md" or "memory/2026-02-07.md"
    line_start: int
    line_end: int
    heading_path: str      # e.g., "Key Decisions > Database Choice"
    content_hash: str      # SHA-256 for dirty check
```

### Chunking Strategy

1. Split on markdown headings (`##`, `###`) first
2. Within sections, split at paragraph boundaries if section exceeds ~400 tokens
3. Each chunk inherits its heading path for context (e.g., `"Key Decisions > Database Choice"`)
4. Preserves semantic coherence better than fixed-size sliding windows

### Dirty Check

PG stores a `markdown_file_hashes` table:

| Column | Type | Purpose |
|--------|------|---------|
| `file_path` | `TEXT PRIMARY KEY` | Relative path from workspace root |
| `content_hash` | `TEXT` | SHA-256 of file content |
| `last_indexed_at` | `TIMESTAMPTZ` | When file was last chunked + embedded |

On `index_markdown_files()`, only files with changed hashes are re-chunked and re-embedded. Deleted files have their chunks removed.

### Key Principle

Mirror has no scheduling logic. It exposes functions; callers decide when to call them. Session hooks call at session boundaries. The future autonomy loop will call at goal-completion breakpoints.

---

## 4. LLM-Based Compaction & Flush

The flush system uses Vecna's own adapters to summarize conversation history into structured memory artifacts.

### Pipeline (3 Stages)

```
Raw conversation → LLM summarizer → Structured outputs → Written to files + PG
```

### Stage 1: Trigger Detection

```python
class FlushManager:
    """Manages memory compaction triggers and execution."""

    def __init__(self, adapter: BaseAdapter, mirror: MemoryMirror, config: VecnaConfig):
        self.adapter = adapter  # Any Vecna adapter (Copilot, Groq, Ollama, etc.)
        self.mirror = mirror
        self.token_threshold = config.memory.flush_token_threshold  # e.g., 6000

    def should_flush(self, conversation_tokens: int) -> bool:
        """Token count exceeds threshold."""
        return conversation_tokens >= self.token_threshold

    async def flush_session_end(self, conversation: List[Message]) -> FlushResult:
        """Always called at session end. Full compaction."""

    async def flush_mid_session(self, conversation: List[Message]) -> FlushResult:
        """Called when token threshold hit. Partial compaction of older messages."""
```

### Stage 2: LLM Summarization

A dedicated prompt asks the adapter to produce structured JSON:

```
COMPACTION_PROMPT = """Analyze this conversation and extract:
1. session_summary: 2-3 sentence summary of what was discussed/accomplished
2. task_state: Current task, what's done, what's next, any blockers
3. new_facts: List of factual statements learned (with confidence 0-1)
4. new_beliefs: List of opinions/assessments formed (with confidence 0-1)
5. key_decisions: List of decisions made with rationale
6. open_questions: Unresolved questions that need follow-up

Return as JSON. Be concise. Only include genuinely new information,
not things already in MEMORY.md."""
```

The adapter call uses the cheapest/fastest available model (configurable, defaults to the first model in the group). This is a meta-operation, not a user-facing response.

### Stage 3: Write Outputs

```python
@dataclass
class FlushResult:
    session_summary: str
    task_state: TaskState
    new_facts: List[Fact]
    new_beliefs: List[Belief]
    key_decisions: List[str]
    open_questions: List[str]
    tokens_used: int
```

Output routing:

| Output | Destination | Method |
|--------|-------------|--------|
| `session_summary` | Today's daily log | `mirror.append_daily_log()` |
| `task_state` | WORKING.md | `mirror.update_working()` |
| `new_facts` + `new_beliefs` (confidence > 0.7) | MEMORY.md | `mirror.promote_to_memory()` |
| `new_facts` + `new_beliefs` (all) | PG memories table | `mirror.extract_facts_to_pg()` |
| `key_decisions` | MEMORY.md `## Key Decisions` | `mirror.promote_to_memory()` |

### Mid-Session Flush

Works the same pipeline but only processes messages older than the last flush point. Newer messages stay in context. Flushed messages are replaced with a compact summary block:

```
[Session context compressed: Discussed hybrid search implementation. Decided on tsvector + pgvector
with 70/30 weighting. User prefers PG-native solutions.]
```

### Fallback

If no adapter is available (e.g., no API keys configured), fall back to the existing extractive `MemoryCompressor` in `store.py`. Lower quality but functional.

---

## 5. Session Hooks

Session hooks wire everything together — they're the integration point where workspace files, Mirror, and FlushManager connect to the existing orchestration loop.

### SessionManager

```python
class SessionManager:
    """Manages session lifecycle: start, end, mid-session checks."""

    def __init__(self, mirror: MemoryMirror, flush_mgr: FlushManager, config: VecnaConfig):
        self.mirror = mirror
        self.flush_mgr = flush_mgr
        self.config = config
        self.session_id = str(uuid.uuid4())
        self.started_at: Optional[datetime] = None
```

### Session Start (`start_session`)

Called once at conversation start. Returns context to inject into system prompt.

```python
    async def start_session(self, initial_query: Optional[str] = None) -> SessionContext:
        self.started_at = datetime.utcnow()

        # 1. Read identity
        soul = self._read_file("SOUL.md")

        # 2. Read current task state
        working = self._read_file("WORKING.md")

        # 3. Read today's daily log
        daily_log = self._read_file(f"memory/{date.today().isoformat()}.md")

        # 4. Re-index any changed markdown files
        await self.mirror.index_markdown_files()

        # 5. If user provided an initial query, search for relevant context
        relevant_memory = ""
        if initial_query:
            chunks = await self.mirror.pg_store.search(
                initial_query, limit=5, hybrid=True
            )
            relevant_memory = self._format_memory_results(chunks)

        return SessionContext(
            soul=soul,
            working=working,
            daily_log=daily_log,
            relevant_memory=relevant_memory,
            session_id=self.session_id,
        )
```

### System Prompt Injection

The `SessionContext` is formatted and prepended to the existing system prompt:

```
[SOUL — Who I Am]
{soul content}

[WORKING — Current State]
{working content}

[TODAY'S LOG]
{daily_log content}

[RELEVANT MEMORY]
{relevant_memory content}
```

SOUL.md content always comes first — identity before task.

### Session End (`end_session`)

Called when conversation ends. Runs full compaction pipeline.

```python
    async def end_session(self, conversation: List[Message]) -> None:
        # 1. LLM-based compaction
        result = await self.flush_mgr.flush_session_end(conversation)

        # 2. Write to markdown via Mirror
        await self.mirror.append_daily_log(result.session_summary, datetime.utcnow())
        await self.mirror.update_working(
            result.task_state.current_task,
            result.task_state.next_steps,
            result.task_state.blockers,
        )

        # 3. Promote high-confidence findings to MEMORY.md
        promotable_facts = [f for f in result.new_facts if f.confidence > 0.7]
        promotable_beliefs = [b for b in result.new_beliefs if b.confidence > 0.7]
        if promotable_facts or promotable_beliefs:
            await self.mirror.promote_to_memory(promotable_facts, promotable_beliefs)

        # 4. Sync all facts/beliefs to PG (for search, regardless of confidence)
        await self.mirror.extract_facts_to_pg(result.new_facts + result.new_beliefs)

        # 5. Re-index updated markdown files
        await self.mirror.index_markdown_files()
```

### Integration Points

| Caller | When | What |
|--------|------|------|
| `CLI main.py` | REPL start | `session_mgr.start_session()` |
| `CLI main.py` | Exit / Ctrl+C (signal handler) | `session_mgr.end_session()` |
| `HiveLoop.think()` | After each turn | `flush_mgr.should_flush()` → mid-session flush if needed |
| `HiveMind` | Programmatic API | Exposes `start_session()` / `end_session()` |
| `autonomy.py` (future) | Goal completion breakpoints | Same sync functions |

---

## 6. Data Flow Diagram

```
SESSION START
─────────────
User opens CLI / HiveMind.start_session()
    │
    ▼
SessionManager.start_session()
    │
    ├── Read SOUL.md ──────────────────────► System prompt [SOUL]
    ├── Read WORKING.md ───────────────────► System prompt [WORKING]
    ├── Read memory/YYYY-MM-DD.md ─────────► System prompt [TODAY]
    ├── Mirror.index_markdown_files() ─────► PG (re-embed changed chunks)
    └── PgMemoryStore.search(query) ───────► System prompt [RELEVANT MEMORY]

CONVERSATION LOOP
─────────────────
User message → HiveLoop.think()
    │
    ├── Parallel adapter calls (Copilot, Groq, Ollama, etc.)
    ├── ConsensusEngine.merge() → unified response
    ├── Self-reflection + identity injection
    ├── Tool execution (if needed)
    │
    └── FlushManager.should_flush()? ──YES──► flush_mid_session()
        │                                        │
        │                                        ├── LLM summarize older messages
        │                                        ├── Replace with [compressed] block
        │                                        ├── Mirror.append_daily_log()
        │                                        └── Mirror.extract_facts_to_pg()
        NO
        │
        ▼
    Continue conversation...

SESSION END
───────────
User exits / Ctrl+C / HiveMind.end_session()
    │
    ▼
SessionManager.end_session()
    │
    ├── FlushManager.flush_session_end()
    │       │
    │       ├── LLM summarize full conversation → FlushResult
    │       │       (summary, task_state, facts, beliefs, decisions, questions)
    │       │
    │       └── return FlushResult
    │
    ├── Mirror.append_daily_log(summary)
    ├── Mirror.update_working(task_state)
    ├── Mirror.promote_to_memory(high-confidence facts/beliefs)
    ├── Mirror.extract_facts_to_pg(all facts/beliefs)
    └── Mirror.index_markdown_files() ─► PG (re-embed updated chunks)

NEXT SESSION
────────────
SessionManager.start_session()
    │
    └── Reads WORKING.md → "Last session, I was working on X. Next steps: Y."
        Reads daily log → "Earlier today, I discussed Z with the user."
        Searches MEMORY.md → "I know that the user prefers A over B."

        → Vecna picks up where it left off with full context.
```

### Database Schema Additions (Single Alembic Migration)

| Table / Column | Type | Purpose |
|----------------|------|---------|
| `memories.search_vector` | `TSVECTOR (GENERATED)` | Full-text search column with GIN index |
| `markdown_chunks.id` | `UUID PRIMARY KEY` | Chunk identifier |
| `markdown_chunks.source_file` | `TEXT` | Relative path (e.g., `MEMORY.md`) |
| `markdown_chunks.line_start` | `INTEGER` | Starting line in source file |
| `markdown_chunks.line_end` | `INTEGER` | Ending line in source file |
| `markdown_chunks.heading_path` | `TEXT` | Heading hierarchy (e.g., `Key Decisions > DB`) |
| `markdown_chunks.content` | `TEXT` | Chunk text |
| `markdown_chunks.content_hash` | `TEXT` | SHA-256 for dirty check |
| `markdown_chunks.embedding` | `VECTOR(1536)` | pgvector embedding |
| `markdown_chunks.search_vector` | `TSVECTOR (GENERATED)` | Full-text search |
| `markdown_chunks.created_at` | `TIMESTAMPTZ` | Creation timestamp |
| `markdown_chunks.updated_at` | `TIMESTAMPTZ` | Last update timestamp |
| `markdown_file_hashes.file_path` | `TEXT PRIMARY KEY` | Relative path from workspace |
| `markdown_file_hashes.content_hash` | `TEXT` | SHA-256 of file content |
| `markdown_file_hashes.last_indexed_at` | `TIMESTAMPTZ` | When last chunked + embedded |
| `sessions.session_id` | `UUID PRIMARY KEY` | Session identifier |
| `sessions.started_at` | `TIMESTAMPTZ` | Session start time |
| `sessions.ended_at` | `TIMESTAMPTZ` | Session end time |
| `sessions.summary` | `TEXT` | Compacted session summary |
| `sessions.tokens_used` | `INTEGER` | Total tokens consumed |

---

## 7. Testing Strategy

### Unit Tests (No External Services)

| Test File | What It Covers |
|-----------|----------------|
| `test_memory_mirror.py` | Chunking logic (heading-aware splitting, ~400 token target), dirty check (hash comparison), markdown file read/write, MarkdownChunk dataclass |
| `test_flush_manager.py` | Trigger detection (token threshold), FlushResult parsing, COMPACTION_PROMPT output parsing, extractive fallback |
| `test_session_manager.py` | SessionContext construction, system prompt formatting, file reading with missing files (graceful defaults) |
| `test_hybrid_search.py` | Query construction, score normalization, fallback to vector-only when no text tokens |

### Integration Tests (Postgres + Redis)

| Test File | What It Covers |
|-----------|----------------|
| `test_hybrid_search_pg.py` | End-to-end hybrid search: insert memories with embeddings + tsvector, query, verify ranking combines both scores correctly |
| `test_mirror_pg.py` | Chunk markdown → embed → store in PG → search → verify source metadata preserved |
| `test_session_lifecycle_pg.py` | Full start → conversation → flush → end → restart cycle, verify WORKING.md carries state across sessions |

### Test Infrastructure

- **Mock adapter for compaction tests**: A `MockAdapter` that returns canned `FlushResult` JSON, so compaction tests don't need real API keys
- **Mock embedder** (already exists): Deterministic 1536-dim vectors for CI
- All async tests auto-detected via `asyncio_mode = auto`

---

## 8. Implementation Order

Components must be built in dependency order:

| Step | Component | Depends On | Key Files |
|------|-----------|------------|-----------|
| 1 | Workspace initialization + SOUL.md | Nothing | New: `vecna/memory/workspace.py`, `SOUL.md` template |
| 2 | Hybrid search in PgMemoryStore | Nothing | Modified: `vecna/memory/pg_store.py`, New: Alembic migration |
| 3 | MemoryMirror rewrite | Step 1 + Step 2 | Rewrite: `vecna/memory/mirror.py` |
| 4 | LLM compaction / FlushManager | Step 3 (Mirror) | Rewrite: `vecna/memory/flush.py` |
| 5 | Markdown chunked indexing | Step 2 + Step 3 | Part of Mirror (Step 3), tested separately |
| 6 | Session hooks (SessionManager) | Steps 3 + 4 | New: `vecna/memory/session.py`, Modified: `vecna/orchestrator/loop.py`, `vecna/cli/main.py` |
| 7 | Config schema updates | Nothing (can parallel) | Modified: `vecna/config/schema.py` |
| 8 | Tests | All above | New test files in `tests/unit/` and `tests/integration/` |

---

## 9. Future Roadmap

After the memory system is solid, these are the next priorities:

### P1: Agentic Autonomy

| Component | What | Why |
|-----------|------|-----|
| Real ReWOO planning loop | Full plan-execute-observe cycle, not just regex parsing | Vecna should decompose complex goals into executable plans |
| Priority-based goal queue | DB-backed queue with priority, status, dedup, dependencies | Replace the FIFO JSONL stub; goals need ordering and tracking |
| Exploration / curiosity engine | Score contradictions, knowledge gaps, and novel topics to generate exploration goals | Vecna should be curious, not just reactive |
| Autonomous scheduling | Backoff, rate limiting, configurable wake intervals | Safe long-running autonomous operation |

### P1: Tool Expansion
**NOTE**: Use unbrowse tool for browsing

| Component | What | Why |
|-----------|------|-----|
| Web browsing tool | Fetch, parse, extract from URLs | Autonomy requires ability to research |
| File system tools | Read, write, search project files | Vecna should work with codebases |
| Semantic tool routing | Embedding-based tool selection, not just success-rate ranking | Better tool dispatch as tool count grows |
| Tool composition | Chain tools in ReWOO plans | Complex tasks need multi-tool workflows |

### P2: Identity Emergence

| Component | What | Why |
|-----------|------|-----|
| Self-model updates | Track how interaction patterns shape personality over time | Genuine identity, not just prompted personality |
| Opinion formation | Form and revise opinions from accumulated evidence across sessions | The "Curious Scholar" should actually form opinions |
| Personality drift tracking | Measure and visualize how Vecna's identity evolves | Observability for the identity system |
| Contradiction-driven growth | Use detected contradictions to refine beliefs and update SOUL.md-adjacent identity | Learning from disagreement |

### P2: Security Hardening

| Component | What | Why |
|-----------|------|-----|
| Container TTL enforcement | Kill long-running containers, resource limits | Safety for autonomous execution |
| Seccomp profiles | Restrict syscalls in sandboxed execution | Defense in depth |
| PII redaction | Detect and redact PII in memory storage and output | Privacy compliance |
| Audit trail | Comprehensive logging of autonomous actions | Accountability |

### P3: Advanced Memory

| Component | What | Why |
|-----------|------|-----|
| Multi-hop graph traversal | Recursive CTE queries on memory graph edges | Connect distant but related memories |
| Dream loop insights | Implement `_generate_insights()` stub in dream_loop.py | Discover patterns during idle time |
| Cross-session pattern detection | Identify recurring themes, preferences, and workflows | Deeper understanding of user and context |
| Memory consolidation | Merge and compress related memories over time | Prevent unbounded growth |

### P3: Observability

| Component | What | Why |
|-----------|------|-----|
| Memory access tracing | Log what was recalled and why for each query | Debug retrieval quality |
| Identity coherence metrics | Measure consistency of Vecna's voice and opinions | Ensure identity doesn't fragment |
| Flush quality tracking | Compare LLM summaries against original content | Verify compaction doesn't lose critical info |
| Session analytics | Token usage, memory growth, retrieval hit rates | Operational visibility |
