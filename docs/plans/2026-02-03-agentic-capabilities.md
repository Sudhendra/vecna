# Vecna Agentic Capabilities Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build two operating modes (interactive assistant + autonomous exploration) with a durable PG-backed memory substrate and efficient, safe tool use.

**Architecture:** Keep ReAct as the primary loop for dynamic exploration, add a ReWOO fast path for predictable tool chains, and anchor Vecna’s identity in a dual memory substrate (Markdown narrative + PG facts/contradictions/hypotheses). Autonomous exploration runs via a goal queue + curiosity engine with budgets, audits, and strict tool policy gates.

**Tech Stack:** Python, Click, PostgreSQL + pgvector, Redis, OpenAI embeddings (fallback: sentence-transformers), Docker (RLM bridge), pytest.

---

## Decision Summary (record these as non-negotiables)
- Two modes: **Interactive Assistant** (user-facing, secure tool approvals) and **Autonomous Exploration** (self-driven loop with budgeted tool use).
- Vecna’s identity lives in the **memory substrate**. Markdown (daily log + curated MEMORY.md) is human-readable, PG is canonical for structured memory.
- **Search over injection**: retrieve memory via hybrid search and only inject relevant evidence.
- Long-running autonomy is enabled by **goal queue + curiosity engine + dream loop**, not by persistent prompting.
- **Efficiency**: prefer ReWOO batching when tool dependencies are predictable; ReAct for dynamic exploration.
- Safety gates: tool allow/ask/deny policy + audit logging + approval workflow in interactive mode.

## Progress
- [x] Task 1: Add explicit agent modes and autonomy config
- [x] Task 2: Route runtime by mode (assistant vs explorer)
- [x] Task 3: Add CLI approvals for tool requests
- [x] Task 4: Enforce tool policy (allow/ask/deny) in ToolRuntime
- [x] Task 5: Implement MemoryMirror (Markdown <-> PG)
- [x] Task 6: Add memory_search and memory_get tools
- [x] Task 7: Memory flush + session hook
- [x] Task 8: Goal queue + autonomy loop
- [ ] Task 9: Curiosity engine (turn contradictions into goals)
- [ ] Task 10: Add ReWOO planner + solver (fast path)
- [ ] Task 11: Tool routing memory (learn which tool works)
- [ ] Task 12: Add dream loop CLI and scheduling entrypoint
- [ ] Task 13: Document modes, memory, and autonomy

---

### Phase 1: Mode + Config Foundation

### Task 1: Add explicit agent modes and autonomy config

**Files:**
- Modify: `vecna/config/schema.py`
- Modify: `vecna/config/loader.py`
- Test: `tests/unit/test_agent_mode_config.py`

**Step 1: Write the failing test**

```python
from vecna.config.schema import VecnaConfig, AgentMode


def test_default_agent_mode():
    cfg = VecnaConfig()
    assert cfg.agent_mode == AgentMode.assistant


def test_agent_mode_parsing():
    cfg = VecnaConfig(agent_mode=AgentMode.explorer)
    assert cfg.agent_mode == AgentMode.explorer
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_agent_mode_config.py -v`
Expected: FAIL with `AttributeError: type object 'VecnaConfig' has no attribute 'agent_mode'`

**Step 3: Write minimal implementation**

```python
from enum import Enum


class AgentMode(str, Enum):
    assistant = "assistant"
    explorer = "explorer"


@dataclass
class VecnaConfig:
    # ...existing fields...
    agent_mode: AgentMode = AgentMode.assistant
```

Update `vecna/config/loader.py` to preserve `agent_mode` when loading config files.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_agent_mode_config.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/config/schema.py vecna/config/loader.py tests/unit/test_agent_mode_config.py
git commit -m "feat: add agent mode to config"
```

---

### Task 2: Route runtime by mode (assistant vs explorer)

**Files:**
- Create: `vecna/orchestrator/mode_router.py`
- Modify: `vecna/orchestrator/loop.py`
- Test: `tests/unit/test_mode_router.py`

**Step 1: Write the failing test**

```python
from vecna.config.schema import AgentMode
from vecna.orchestrator.mode_router import resolve_loop


class DummyLoop:
    def __init__(self, name):
        self.name = name


def test_resolve_loop_assistant():
    loop = resolve_loop(AgentMode.assistant)
    assert loop.name == "assistant"


def test_resolve_loop_explorer():
    loop = resolve_loop(AgentMode.explorer)
    assert loop.name == "explorer"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_mode_router.py -v`
Expected: FAIL with `ModuleNotFoundError: vecna.orchestrator.mode_router`

**Step 3: Write minimal implementation**

```python
# vecna/orchestrator/mode_router.py
from vecna.config.schema import AgentMode
from vecna.orchestrator.loop import HiveLoop
from vecna.orchestrator.autonomy import AutonomyLoop


def resolve_loop(mode: AgentMode):
    if mode == AgentMode.explorer:
        return AutonomyLoop(name="explorer")
    return HiveLoop(name="assistant")
```

Update `vecna/orchestrator/loop.py` to accept `name` and expose a thin `run_session()` that calls the resolved loop.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_mode_router.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/orchestrator/mode_router.py vecna/orchestrator/loop.py tests/unit/test_mode_router.py
git commit -m "feat: route orchestrator by agent mode"
```

---

### Phase 2: Tool Policy + Approvals (Assistant Mode Safety)

### Task 3: Add CLI approvals for tool requests

**Files:**
- Modify: `vecna/cli/main.py`
- Modify: `vecna/tools/approvals.py`
- Test: `tests/unit/test_cli_tools_approvals.py`

**Step 1: Write the failing test**

```python
from click.testing import CliRunner
from vecna.cli.main import cli


def test_tools_pending_empty():
    runner = CliRunner()
    result = runner.invoke(cli, ["tools", "pending"])
    assert result.exit_code == 0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_cli_tools_approvals.py -v`
Expected: FAIL with "No such command 'tools'"

**Step 3: Write minimal implementation**

```python
# vecna/cli/main.py
@cli.group()
def tools():
    """Tool approval workflows."""


@tools.command("pending")
def tools_pending():
    store = ApprovalStore()
    pending = store.get_pending()
    for req in pending:
        click.echo(f"{req.request_id} {req.tool_name} {req.status}")
```

Add `approve` and `deny` subcommands that call `ApprovalStore.update_status()`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_cli_tools_approvals.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/cli/main.py vecna/tools/approvals.py tests/unit/test_cli_tools_approvals.py
git commit -m "feat: add tool approvals CLI"
```

---

### Task 4: Enforce tool policy (allow/ask/deny) in ToolRuntime

**Files:**
- Modify: `vecna/tools/runtime.py`
- Modify: `vecna/tools/permissions.py`
- Test: `tests/unit/test_tools_policy.py`

**Step 1: Write the failing test**

```python
from vecna.tools.runtime import ToolRuntime
from vecna.tools.registry import ToolRegistry
from vecna.config.schema import ToolPolicyConfig


def test_tool_policy_denies():
    registry = ToolRegistry()
    runtime = ToolRuntime(registry, tool_policy=ToolPolicyConfig(deny=["execute_code"]))
    result = runtime.execute("TOOL_CALL: execute_code {\"code\": \"print(1)\"}")
    assert "denied" in result.lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_tools_policy.py -v`
Expected: FAIL with "policy not enforced"

**Step 3: Write minimal implementation**

```python
# vecna/tools/permissions.py
class ToolPolicy:
    def is_denied(self, name: str) -> bool: ...
    def is_ask(self, name: str) -> bool: ...


# vecna/tools/runtime.py
if policy.is_denied(call.tool_name):
    return f"Tool {call.tool_name} denied by policy"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_tools_policy.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/tools/runtime.py vecna/tools/permissions.py tests/unit/test_tools_policy.py
git commit -m "feat: enforce tool policy in runtime"
```

---

### Phase 3: Memory Substrate Integration (Markdown + PG)

### Task 5: Implement MemoryMirror (Markdown ↔ PG)

**Files:**
- Create: `vecna/memory/mirror.py`
- Modify: `vecna/memory/pg_store.py`
- Test: `tests/unit/test_memory_mirror.py`

**Step 1: Write the failing test**

```python
from vecna.memory.mirror import MemoryMirror


def test_mirror_parses_daily_log(tmp_path):
    daily = tmp_path / "memory" / "2026-02-03.md"
    daily.parent.mkdir()
    daily.write_text("# 2026-02-03\n\n## 10:00 AM - Note\nLearned X")
    mirror = MemoryMirror(base_dir=tmp_path)
    items = mirror.scan_daily()
    assert items and items[0].item_type == "memory_log"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_memory_mirror.py -v`
Expected: FAIL with "ModuleNotFoundError: vecna.memory.mirror"

**Step 3: Write minimal implementation**

```python
# vecna/memory/mirror.py
from dataclasses import dataclass
from pathlib import Path
from vecna.memory.pg_store import MemoryItem


@dataclass
class MemoryMirror:
    base_dir: Path

    def scan_daily(self):
        items = []
        memory_dir = self.base_dir / "memory"
        for path in memory_dir.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            if text.strip():
                items.append(MemoryItem(content=text, item_type="memory_log", domain="self"))
        return items
```

Update `vecna/memory/pg_store.py` to accept `item_type="memory_log"|"curated_memory"`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_memory_mirror.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/memory/mirror.py vecna/memory/pg_store.py tests/unit/test_memory_mirror.py
git commit -m "feat: add memory mirror for markdown logs"
```

---

### Task 6: Add memory_search and memory_get tools

**Files:**
- Create: `vecna/tools/memory_tools.py`
- Modify: `vecna/tools/registry.py`
- Test: `tests/unit/test_memory_tools.py`

**Step 1: Write the failing test**

```python
from vecna.tools.memory_tools import memory_search


def test_memory_search_returns_results(tmp_path):
    results = memory_search("api decision", max_results=3)
    assert isinstance(results, list)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_memory_tools.py -v`
Expected: FAIL with "ModuleNotFoundError: vecna.tools.memory_tools"

**Step 3: Write minimal implementation**

```python
# vecna/tools/memory_tools.py
from vecna.memory.pg_store import PgMemoryStore


def memory_search(query: str, max_results: int = 6, min_score: float = 0.35):
    store = PgMemoryStore()
    items = store.search(query, top_k=max_results)
    return [
        {
            "id": item.id,
            "content": item.content,
            "score": score,
            "item_type": item.item_type,
        }
        for item, score in items
        if score >= min_score
    ]
```

Register the tools in `vecna/tools/registry.py` with clear descriptions.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_memory_tools.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/tools/memory_tools.py vecna/tools/registry.py tests/unit/test_memory_tools.py
git commit -m "feat: add memory search tools"
```

---

### Task 7: Memory flush + session hook

**Files:**
- Create: `vecna/memory/flush.py`
- Modify: `vecna/orchestrator/loop.py`
- Test: `tests/unit/test_memory_flush.py`

**Step 1: Write the failing test**

```python
from vecna.memory.flush import should_flush


def test_should_flush_when_near_limit():
    assert should_flush(current_tokens=9000, limit=10000, soft_threshold=500) is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_memory_flush.py -v`
Expected: FAIL with "ModuleNotFoundError: vecna.memory.flush"

**Step 3: Write minimal implementation**

```python
# vecna/memory/flush.py
def should_flush(current_tokens: int, limit: int, soft_threshold: int) -> bool:
    return (limit - current_tokens) <= soft_threshold
```

Hook into `vecna/orchestrator/loop.py` to trigger a silent memory flush before compaction.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_memory_flush.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/memory/flush.py vecna/orchestrator/loop.py tests/unit/test_memory_flush.py
git commit -m "feat: add memory flush hook"
```

---

### Phase 4: Autonomy Control Plane

### Task 8: Goal queue + autonomy loop

**Files:**
- Create: `vecna/orchestrator/goal_queue.py`
- Create: `vecna/orchestrator/autonomy.py`
- Test: `tests/unit/test_goal_queue.py`

**Step 1: Write the failing test**

```python
from vecna.orchestrator.goal_queue import GoalQueue


def test_goal_queue_push_pop(tmp_path):
    q = GoalQueue(path=tmp_path / "queue.jsonl")
    q.push({"goal": "explore tool usage"})
    item = q.pop()
    assert item["goal"] == "explore tool usage"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_goal_queue.py -v`
Expected: FAIL with "ModuleNotFoundError: vecna.orchestrator.goal_queue"

**Step 3: Write minimal implementation**

```python
# vecna/orchestrator/goal_queue.py
import json
from pathlib import Path


class GoalQueue:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def push(self, item: dict):
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item) + "\n")

    def pop(self):
        if not self.path.exists():
            return None
        lines = self.path.read_text(encoding="utf-8").splitlines()
        if not lines:
            return None
        first = json.loads(lines[0])
        self.path.write_text("\n".join(lines[1:]) + ("\n" if len(lines) > 1 else ""))
        return first
```

Add `AutonomyLoop` in `vecna/orchestrator/autonomy.py` that consumes goals and calls `HiveLoop.think()`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_goal_queue.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/orchestrator/goal_queue.py vecna/orchestrator/autonomy.py tests/unit/test_goal_queue.py
git commit -m "feat: add goal queue and autonomy loop"
```

---

### Task 9: Curiosity engine (turn contradictions into goals)

**Files:**
- Create: `vecna/orchestrator/curiosity.py`
- Modify: `vecna/memory/pg_store.py`
- Test: `tests/unit/test_curiosity_engine.py`

**Step 1: Write the failing test**

```python
from vecna.orchestrator.curiosity import CuriosityEngine


def test_curiosity_creates_goal():
    engine = CuriosityEngine()
    goals = engine.from_contradictions([
        {"content": "X vs Y", "confidence": 0.4}
    ])
    assert goals and "explore" in goals[0]["goal"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_curiosity_engine.py -v`
Expected: FAIL with "ModuleNotFoundError: vecna.orchestrator.curiosity"

**Step 3: Write minimal implementation**

```python
# vecna/orchestrator/curiosity.py
class CuriosityEngine:
    def from_contradictions(self, contradictions):
        goals = []
        for item in contradictions:
            goals.append({"goal": f"explore contradiction: {item['content']}"})
        return goals
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_curiosity_engine.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/orchestrator/curiosity.py tests/unit/test_curiosity_engine.py
git commit -m "feat: add curiosity engine"
```

---

### Phase 5: Exploration Loop (ReAct + ReWOO)

### Task 10: Add ReWOO planner + solver (fast path)

**Files:**
- Create: `vecna/orchestrator/rewoo.py`
- Modify: `vecna/tools/parser.py`
- Test: `tests/unit/test_rewoo_parser.py`

**Step 1: Write the failing test**

```python
from vecna.orchestrator.rewoo import parse_rewoo_plan


def test_parse_rewoo_plan():
    plan = "Plan: need info\nE1: Search[foo]"
    steps = parse_rewoo_plan(plan)
    assert steps[0]["tool"] == "Search"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_rewoo_parser.py -v`
Expected: FAIL with "ModuleNotFoundError: vecna.orchestrator.rewoo"

**Step 3: Write minimal implementation**

```python
# vecna/orchestrator/rewoo.py
import re


def parse_rewoo_plan(text: str):
    steps = []
    for line in text.splitlines():
        match = re.match(r"E\d+:\s*(\w+)\[(.*)\]", line.strip())
        if match:
            steps.append({"tool": match.group(1), "input": match.group(2)})
    return steps
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_rewoo_parser.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/orchestrator/rewoo.py tests/unit/test_rewoo_parser.py
git commit -m "feat: add rewoo plan parser"
```

---

### Task 11: Tool routing memory (learn which tool works)

**Files:**
- Create: `vecna/tools/router.py`
- Modify: `vecna/tools/audit.py`
- Test: `tests/unit/test_tool_router.py`

**Step 1: Write the failing test**

```python
from vecna.tools.router import ToolRouter


def test_router_ranks_tools():
    router = ToolRouter()
    router.record("search", success=True)
    router.record("search", success=True)
    router.record("exec", success=False)
    ranked = router.rank(["exec", "search"])
    assert ranked[0] == "search"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_tool_router.py -v`
Expected: FAIL with "ModuleNotFoundError: vecna.tools.router"

**Step 3: Write minimal implementation**

```python
# vecna/tools/router.py
class ToolRouter:
    def __init__(self):
        self.stats = {}

    def record(self, tool: str, success: bool):
        data = self.stats.setdefault(tool, {"ok": 0, "fail": 0})
        if success:
            data["ok"] += 1
        else:
            data["fail"] += 1

    def rank(self, tools):
        def score(t):
            data = self.stats.get(t, {"ok": 0, "fail": 0})
            return data["ok"] - data["fail"]
        return sorted(tools, key=score, reverse=True)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_tool_router.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/tools/router.py tests/unit/test_tool_router.py
git commit -m "feat: add tool router learning"
```

---

### Phase 6: Memory Consolidation + Ops

### Task 12: Add dream loop CLI and scheduling entrypoint

**Files:**
- Modify: `vecna/cli/main.py`
- Modify: `vecna/memory/dream_loop.py`
- Test: `tests/unit/test_dream_cli.py`

**Step 1: Write the failing test**

```python
from click.testing import CliRunner
from vecna.cli.main import cli


def test_memory_dream_command():
    runner = CliRunner()
    result = runner.invoke(cli, ["memory", "dream", "--dry-run"])
    assert result.exit_code == 0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_dream_cli.py -v`
Expected: FAIL with "No such command 'memory'"

**Step 3: Write minimal implementation**

```python
# vecna/cli/main.py
@cli.group()
def memory():
    """Memory maintenance commands."""


@memory.command("dream")
@click.option("--dry-run", is_flag=True)
def memory_dream(dry_run):
    loop = DreamLoop(pg_store=PgMemoryStore())
    loop.run(dry_run=dry_run)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_dream_cli.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/cli/main.py vecna/memory/dream_loop.py tests/unit/test_dream_cli.py
git commit -m "feat: add dream loop CLI"
```

---

### Phase 7: Docs + Operational Defaults

### Task 13: Document modes, memory, and autonomy

**Files:**
- Modify: `docs/overview/index.md`
- Modify: `docs/memory/index.md`
- Modify: `docs/configuration/index.md`

**Step 1: Write the failing test**

```python
# docs tests are manual; validate with a doc build.
```

**Step 2: Run test to verify it fails**

Run: `mkdocs build`
Expected: FAIL if links are missing

**Step 3: Write minimal implementation**

Add sections:
- **Modes:** assistant vs explorer, tool policy defaults
- **Memory Substrate:** Markdown mirror + PG canonical
- **Autonomy:** goal queue, curiosity engine, dream loop

**Step 4: Run test to verify it passes**

Run: `mkdocs build`
Expected: PASS

**Step 5: Commit**

```bash
git add docs/overview/index.md docs/memory/index.md docs/configuration/index.md
git commit -m "docs: add agentic modes and memory substrate"
```
