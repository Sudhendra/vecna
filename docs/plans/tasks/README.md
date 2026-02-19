# VECNA Task Cards

Split from the master implementation plan (`2026-02-16-vecna-master-implementation-plan.md`)
into individual task files for efficient AI-assisted implementation.

## Why Task Cards?

The master plan is 12,855 lines. Loading it into an AI coding session every time:
- Burns ~30-40k tokens just on the plan (before any work happens)
- Degrades quality — agents lose detail precision in large contexts
- Creates coupling risk — 29 tasks blurring together

Each task card is **200-800 lines** with the exact code, tests, and amendment notes
for that specific task. Token cost drops by ~90-95% per session.

## File Structure

```
docs/plans/tasks/
├── 00-amendments.md                  # Shared preamble (16 binding amendments)
├── 01-temporal-facts-and-...md       # Task 1
├── 02-humanmodel-the-...md           # Task 2
├── ...                               # Tasks 3-28
├── 29-end-to-end-...md              # Task 29
├── PROGRESS.md                       # Completion tracking manifest
├── run-vecna-tasks.sh               # Runner script
└── README.md                         # This file
```

## How to Use

### Option A: Manual (one task at a time)

```bash
# Tell your AI coding tool to implement a specific task
claude -p "Read 00-amendments.md first, then implement this task exactly as specified." < 01-temporal-facts-and-validity-windows.md
```

### Option B: Runner Script (sequential automation)

```bash
# Run Phase 1 (tasks 1-12) overnight
./run-vecna-tasks.sh --phase 1

# Run specific tasks
./run-vecna-tasks.sh 1 2 3

# Resume from task 6
./run-vecna-tasks.sh --from 6

# Dry run (see what would execute)
./run-vecna-tasks.sh --dry-run --phase 1
```

### Option C: Different AI Agent

Edit `AGENT_CMD` in `run-vecna-tasks.sh`:

```bash
AGENT_CMD="claude"                              # Claude Code (default)
AGENT_CMD="codex exec --yolo -"                 # OpenAI Codex
AGENT_CMD="amp"                                 # Amp
AGENT_CMD="opencode run"                        # OpenCode
```

## Execution Order

**16 tasks have ZERO dependencies** and can start immediately.
The full dependency-safe order:

| Group | Tasks | Notes |
|-------|-------|-------|
| 1 (no deps) | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 18, 19, 25, 28, 29 | All independent |
| 2 (light deps) | 11→5, 13→10, 14→1+6, 15→8, 16→8+9, 17→8+9, 20→8, 21→7, 22→2, 24→9, 26→3+6, 27→12 | Each needs 1-2 prior tasks |
| 3 (heavy deps) | 23→5+10+11 | Needs 3 prior tasks |

## Verification Gates

Run after completing each phase:

| Gate | After | Command |
|------|-------|---------|
| 1 | Task 5 | `pytest tests/unit/ -v --tb=short` |
| 2 | Task 9 | Gate 1 + import checks for server, channels, integrations |
| 3 | Task 12 | Gate 2 + `ruff check .` + `ruff format --check .` |
| 4 | Task 21 | `pytest tests/unit/ tests/integration/ -v --tb=short` |
| 5 | Task 29 | `pytest tests/ -v --tb=short` (full suite including e2e) |

## Token Cost Comparison

| Approach | Tokens per session | Sessions | Total |
|----------|-------------------|----------|-------|
| Full plan every time | ~40k + work | 29 | ~2-3M |
| Task cards | ~2-5k + work | 29 | ~300K-800K |
| **Savings** | | | **~60-75%** |
