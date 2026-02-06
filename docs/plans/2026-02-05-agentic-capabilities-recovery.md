# Agentic Capabilities Recovery Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Resolve the in-progress merge, align tool runtime + policy implementation with tests and docs, and fix CI failures so the agentic-capabilities branch is fully pushed and green.

**Architecture:** Keep the newer async tool runtime (ToolSpec/ToolCall/ToolResult + ToolRuntime) from the plan worktree, wire it into the hive loop, and converge config/CLI/tests to that API. Fix CI by provisioning pgvector + sentence-transformers and running migrations before tests. Resolve all merge conflicts by choosing a single, consistent tool stack (new runtime + policy config) and updating legacy tests.

**Tech Stack:** Python 3.10–3.12, pytest, ruff, Click CLI, PostgreSQL + pgvector, Redis, Alembic, sentence-transformers.

---

## Current State (Must Preserve)

- Branch in merge conflict state on `agentic-capabilities`.
- Conflicts (unresolved):
  - `vecna/adapters/base.py`
  - `vecna/config/schema.py`
  - `vecna/tools/approvals.py`
  - `vecna/tools/audit.py`
  - `vecna/tools/permissions.py`
  - `vecna/tools/registry.py`
  - `vecna/tools/runtime.py`
- Staged/untracked files already present in the merge:
  - Added tests: `tests/unit/test_tools_*.py`, `tests/unit/test_code_executor_tool.py`, `tests/unit/test_config_tools.py`
  - Added tool modules: `vecna/tools/{types,parser,registry,permissions,runtime,approvals,audit}.py`
  - Added plan doc: `docs/plans/2026-01-31-agentic-runtime-design.md`
- CI failures (latest):
  - `ruff format --check` failed on `vecna/orchestrator/consensus.py` (already fixed and pushed earlier).
  - Integration tests fail because:
    - `pgvector` extension missing (`vector type not found in the database`).
    - `sentence-transformers` missing for local embeddings.
  - Redis hot cache integration tests fail because embedding and PG retrieval fail upstream.
- CI workflow already edited in working tree to:
  - use `pgvector/pgvector:pg15`
  - install `.[dev,postgres,local]`
  - run `alembic upgrade head`

---

## Design Decisions (Lock These In Before Implementing)

1) **Tool Runtime API**: adopt async `ToolRuntime.execute_calls()` with `ToolSpec/ToolCall/ToolResult` (from plan worktree), and remove legacy `ToolRuntime.execute()` API.
2) **Tool Registry**: use typed registry with `ToolSpec` and `get_default_registry()`; include `python_exec` plus existing memory tools (`memory_search`, `memory_get`).
3) **Tool Policy Config**: use `ToolPolicyConfig` (default_action/allowlist/denylist/risk_actions) and `ToolPermissionManager` + `RiskTier` from `vecna/tools/permissions.py`.
4) **Approval Store**: keep JSONL approval store (request_approval / get_pending / update_status) and update CLI + tests to match. Retire old approvals JSON format.
5) **Config Defaults**: set `use_routing=True` and add `auto_execute_tools` defaulted from `auto_execute_code` if missing.
6) **CI Fix**: use pgvector image, install local embeddings, run Alembic migrations before tests.

---

## Task 1: Resolve merge conflicts in tool prompt + schema header

**Files:**
- Modify: `vecna/adapters/base.py`
- Modify: `vecna/config/schema.py`

**Step 1: Resolve `vecna/adapters/base.py`**

Keep a single TOOL_CALL instruction block. Recommended final text:

```text
## TOOL CALLS
If you need to use a tool, only call tools listed under AVAILABLE TOOLS.
Use the exact format:
<TOOL_CALL>{"name":"tool_name","args":{...}}</TOOL_CALL>
```

**Step 2: Resolve `vecna/config/schema.py` import block**

Ensure both logger and tool policy imports exist and no conflict markers remain:

```python
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from vecna.tools.permissions import RiskTier, ToolPolicy

logger = logging.getLogger("vecna.config")
```

**Step 3: Verify `schema.py` compiles**

Run: `python -m py_compile vecna/config/schema.py`
Expected: exit 0

**Step 4: Commit merge conflict resolutions (phase 1)**

```bash
git add vecna/adapters/base.py vecna/config/schema.py
git commit -m "fix: resolve schema and prompt conflicts"
```

---

## Task 2: Resolve tool module conflicts and unify API

**Files:**
- Modify: `vecna/tools/approvals.py`
- Modify: `vecna/tools/audit.py`
- Modify: `vecna/tools/permissions.py`
- Modify: `vecna/tools/registry.py`
- Modify: `vecna/tools/runtime.py`
- Modify: `vecna/tools/memory_tools.py`

**Step 1: Replace legacy modules with plan worktree versions**

Keep these newer implementations (JSONL approvals, audit logger, async runtime). Ensure each file has required imports (missing in plan worktree):

- `vecna/tools/approvals.py`: add missing `json`/`asdict` import if needed.
- `vecna/tools/audit.py`: add `import json` if missing.
- `vecna/tools/permissions.py`: ensure `import ast` and dataclass imports exist.
- `vecna/tools/registry.py`: ensure `from dataclasses import dataclass` is present.
- `vecna/tools/parser.py`: add missing `import json`.

**Step 2: Add memory tools to default registry**

Update `get_default_registry()` in `vecna/tools/registry.py` to register:

```python
from vecna.tools.memory_tools import memory_get, memory_search

registry.register(
    ToolSpec(
        name="memory_search",
        description="Search semantic memory for relevant items by query.",
        input_schema={"query": "string", "max_results": "int", "min_score": "float"},
    ),
    executor=lambda args, ctx: ToolResult("memory_search", True, memory_search(**args)),
)
registry.register(
    ToolSpec(
        name="memory_get",
        description="Fetch a specific memory item by id.",
        input_schema={"item_id": "string"},
    ),
    executor=lambda args, ctx: ToolResult("memory_get", True, memory_get(**args)),
)
```

**Step 3: Update `vecna/tools/memory_tools.py` for new registry**

No API changes required, but ensure it still works when called via `ToolRuntime` with dict args.

**Step 4: Commit tool module merge**

```bash
git add vecna/tools/approvals.py vecna/tools/audit.py vecna/tools/permissions.py \
  vecna/tools/registry.py vecna/tools/runtime.py vecna/tools/parser.py
git commit -m "feat: unify tool runtime modules"
```

---

## Task 3: Align config + CLI to tool runtime

**Files:**
- Modify: `vecna/config/schema.py`
- Modify: `vecna/config/loader.py`
- Modify: `vecna/cli/main.py`
- Modify: `vecna/orchestrator/loop.py`

**Step 1: Ensure config includes tool policy and auto_execute_tools**

In `VecnaConfig`:

```python
auto_execute_tools: bool = True
tool_policy: ToolPolicyConfig = field(default_factory=ToolPolicyConfig)
```

Update `to_dict()` and `from_dict()` to include `auto_execute_tools` + `tool_policy` and preserve `agent_mode`.

**Step 2: Loader migration**

In `vecna/config/loader.py` add migration behavior:

```python
if ("auto_execute_tools" not in data or data.get("auto_execute_tools") is None) and "auto_execute_code" in data:
    data = {**data, "auto_execute_tools": data.get("auto_execute_code")}
```

**Step 3: CLI uses tool policy**

In `vecna/cli/main.py`, ensure `get_hive()` builds:

```python
auto_execute_tools = bool(vecna_config.auto_execute_tools if vecna_config.auto_execute_tools is not None else vecna_config.auto_execute_code)
hive_config = HiveConfig(..., auto_execute_tools=auto_execute_tools, tool_policy=vecna_config.tool_policy.to_policy(), ...)
```

**Step 4: Hive loop tool execution**

Confirm `vecna/orchestrator/loop.py`:

- creates `ToolRuntime` with `ToolPermissionManager` and registry.
- injects available tool names into memory summary.
- executes tool calls before code execution.

Consider whether code execution should still run when tool runtime is enabled (currently `elif`). Decide and update tests if changed.

**Step 5: Commit config/CLI integration**

```bash
git add vecna/config/schema.py vecna/config/loader.py vecna/cli/main.py vecna/orchestrator/loop.py
git commit -m "feat: wire tool policy into config and runtime"
```

---

## Task 4: Update tests to match new tool stack

**Files:**
- Modify: `tests/unit/test_tools_policy.py`
- Modify: `tests/unit/test_memory_tools.py`
- Modify: `tests/unit/test_cli_tools_approvals.py`
- Add/keep: `tests/unit/test_tools_types.py`, `tests/unit/test_tools_registry.py`, `tests/unit/test_tools_parser.py`, `tests/unit/test_tools_permissions.py`, `tests/unit/test_tools_runtime.py`, `tests/unit/test_tools_audit.py`, `tests/unit/test_code_executor_tool.py`, `tests/unit/test_config_tools.py`

**Step 1: Update `test_tools_policy.py`**

Replace legacy `ToolRuntime`/`ToolPolicyConfig(deny/ask/allow)` tests with new `ToolPermissionManager` + `ToolPolicy` + `RiskTier`.

**Step 2: Update `test_memory_tools.py`**

Change expectations to use `get_default_registry().list_tools()` instead of `registry.tools`.

**Step 3: Update CLI approvals tests**

Convert `ApprovalStore` tests to JSONL behavior (request_approval + get_pending + update_status). Remove expectations around JSON dict format.

**Step 4: Add missing imports in new tests**

Ensure tests import required classes (many plan tests currently omit imports). Each test file should import the module under test explicitly.

**Step 5: Run targeted tests**

```bash
pytest tests/unit/test_tools_types.py tests/unit/test_tools_registry.py tests/unit/test_tools_parser.py -v
pytest tests/unit/test_tools_permissions.py tests/unit/test_tools_runtime.py -v
pytest tests/unit/test_tools_audit.py tests/unit/test_code_executor_tool.py -v
pytest tests/unit/test_cli_tools_approvals.py tests/unit/test_tools_policy.py -v
```

Expected: all PASS.

**Step 6: Commit test updates**

```bash
git add tests/unit/test_tools_*.py tests/unit/test_code_executor_tool.py tests/unit/test_config_tools.py tests/unit/test_cli_tools_approvals.py tests/unit/test_memory_tools.py
git commit -m "test: align tool runtime and approvals"
```

---

## Task 5: Fix CI environment for pgvector + embeddings

**Files:**
- Modify: `.github/workflows/ci.yml`

**Step 1: Use pgvector image**

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg15
```

**Step 2: Install local embeddings**

```yaml
pip install -e ".[dev,postgres,local]"
```

**Step 3: Run migrations**

```yaml
- name: Install database schema
  run: alembic upgrade head
```

**Step 4: Commit CI fixes**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: provision pgvector and local embeddings"
```

---

## Task 6: Resolve remaining merge state + formatting

**Files:**
- Resolve any remaining `UU`/`AA` files
- Run formatters

**Step 1: Ensure no conflict markers**

```bash
git diff --name-only --diff-filter=U
```

Expected: no output.

**Step 2: Format**

```bash
ruff format .
ruff check .
```

**Step 3: Commit formatting if needed**

```bash
git add -A
git commit -m "chore: format and finalize merge"
```

---

## Task 7: Full verification and push

**Step 1: Run full test command used in CI**

```bash
pytest -v -m "not requires_docker and not requires_copilot and not requires_langfuse"
```

Expected: PASS.

**Step 2: Push**

```bash
git push
```

---

## Task 8: Post‑merge checklist

- Confirm PR checks are green (`gh pr status` + `gh run list`).
- Verify plan completion coverage:
  - Agent modes and routing
  - Tool approvals, policy, audit, runtime
  - Memory mirror/search/flush
  - Goal queue + curiosity + ReWOO
  - Dream loop CLI
  - Docs updated

---

## Execution Options

Plan complete and saved to `docs/plans/2026-02-05-agentic-capabilities-recovery.md`. Two execution options:

1. Subagent-Driven (this session) – I dispatch fresh subagent per task, review between tasks, fast iteration
2. Parallel Session (separate) – Open new session with executing-plans, batch execution with checkpoints

Which approach?
