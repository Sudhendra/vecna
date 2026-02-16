# Remaining Work v2 (Goal-Aligned) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the remaining Vecna roadmap in a sequence that preserves Vecna's intended feel: one coherent identity, memory-first continuity, bounded autonomy, and safe tool-driven execution.

**Architecture:** Build in dependency order: (1) runtime contracts + ReWOO hardening, (2) tool breadth + safe execution controls, (3) autonomy substrate (DB goal queue, heartbeat, kill-switch), (4) memory quality upgrades (BM25, multi-hop, dream/patterns/consolidation), (5) identity emergence loops, (6) security + observability + UX.

**Tech Stack:** Python 3.10+, asyncio, aiohttp/httpx, beautifulsoup4, PostgreSQL + pgvector + Alembic, Redis, Docker, Ruff, pytest

---

## Why this v2 supersedes v1

- Fixes API and type mismatches found in v1 (`OpenQuestion.question`, `Contradiction.item_a_content/item_b_content`, `PgMemoryStore.add_item(MemoryItem)`, parser `<TOOL_CALL>{json}</TOOL_CALL>` format).
- Aligns sequencing with architecture guidance: planning/execution hardening before broad autonomy.
- Adds missing roadmap work that v1 deferred too early: BM25, ReWOO open questions, heartbeat, identity emergence scaffolding, seccomp, safety/red-team coverage, interactive approval in chat.
- Moves filesystem policy to config/runtime context (not tool args) to avoid sandbox bypass.

---

## Non-Negotiables (carry into all tasks)

- Keep Vecna in unified `I` voice (no committee voice).
- `SOUL.md` remains user-owned; Vecna does not autonomously rewrite it.
- Memory persistence uses explicit file/database writes; no "mental note" assumptions.
- New subsystems are feature-flagged.
- TDD only: failing test first, then minimal code, then passing test.

---

## Phase Order and Gates

1. **Gate A (Correctness):** runtime contracts + ReWOO hardening + parser/risk consistency
2. **Gate B (Tooling):** HTTP/search/fs tools + semantic routing + quotas
3. **Gate C (Autonomy):** DB goal queue + backoff + kill-switch + heartbeat + curiosity
4. **Gate D (Memory quality):** BM25 + multi-hop + dream/patterns/consolidation
5. **Gate E (Identity):** opinion formation + drift metrics + contradiction growth loop
6. **Gate F (Security/Obs/UX):** seccomp + TTL + redaction + dashboards + safety suites + interactive approvals

---

### Task 1: Add Foundation Config Flags and Dependencies

**Files:**
- Modify: `pyproject.toml`
- Modify: `vecna/config/schema.py`
- Modify: `vecna/cli/main.py`
- Test: `tests/unit/test_config_tools.py`
- Test: `tests/unit/test_agent_mode_config.py`

**Step 1: Write the failing test**

```python
def test_config_has_tooling_and_autonomy_flags():
    from vecna.config.schema import create_default_config

    cfg = create_default_config()
    assert cfg.enable_web_tools is False
    assert cfg.enable_fs_tools is False
    assert cfg.enable_autonomy_heartbeat is False
    assert cfg.tool_quota_per_session == 0
    assert cfg.tool_quota_per_tool == 0
    assert cfg.tool_allowed_fs_roots == ["~/.vecna"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_config_tools.py::test_config_has_tooling_and_autonomy_flags -v`
Expected: FAIL with missing attributes on `VecnaConfig`

**Step 3: Write minimal implementation**

```python
# vecna/config/schema.py (VecnaConfig additions)
enable_web_tools: bool = False
enable_fs_tools: bool = False
enable_autonomy_heartbeat: bool = False
heartbeat_interval_seconds: int = 900
heartbeat_jitter_seconds: int = 90
tool_quota_per_session: int = 0  # 0 = unlimited
tool_quota_per_tool: int = 0     # 0 = unlimited
tool_allowed_fs_roots: List[str] = field(default_factory=lambda: ["~/.vecna"])
rewoo_policy_denied_behavior: str = "fail_step"  # fail_step | abort_plan
rewoo_artifact_injection_mode: str = "final_summary"  # final_summary | per_step
rewoo_use_separate_synthesizer: bool = False
```

```toml
# pyproject.toml (dependencies)
dependencies = [
  "numpy>=1.24.0",
  "rich>=13.7.0",
  "click>=8.1.0",
  "python-dotenv>=1.0.0",
  "pyyaml>=6.0.0",
  "aiohttp>=3.9.0",
  "httpx>=0.27.0",
  "beautifulsoup4>=4.12.0",
]
```

**Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_config_tools.py tests/unit/test_agent_mode_config.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add pyproject.toml vecna/config/schema.py vecna/cli/main.py tests/unit/test_config_tools.py tests/unit/test_agent_mode_config.py
git commit -m "feat: add feature flags and config scaffolding for remaining roadmap"
```

---

### Task 2: Fix Tool Runtime Contract and Risk Assessment

**Files:**
- Modify: `vecna/tools/types.py`
- Modify: `vecna/tools/permissions.py`
- Modify: `vecna/tools/runtime.py`
- Test: `tests/unit/test_tools_runtime.py`
- Test: `tests/unit/test_tools_permissions.py`
- Test: `tests/unit/test_tools_parser.py`

**Step 1: Write the failing test**

```python
def test_runtime_uses_tool_specific_risk_policy():
    from vecna.tools.permissions import assess_tool_risk, RiskTier
    assert assess_tool_risk("python_exec", {"code": "import os\nos.system('x')"}) == RiskTier.HIGH
    assert assess_tool_risk("http_request", {"method": "POST"}) == RiskTier.MEDIUM
    assert assess_tool_risk("memory_get", {}) == RiskTier.LOW
```

```python
@pytest.mark.asyncio
async def test_runtime_tool_call_json_contract_still_required():
    # invalid shape should be ignored by parser
    from vecna.tools.runtime import ToolRuntime
    ...
```

**Step 2: Run tests to verify fail**

Run: `pytest tests/unit/test_tools_permissions.py tests/unit/test_tools_runtime.py tests/unit/test_tools_parser.py -v`
Expected: FAIL (no `assess_tool_risk`, no context extensions)

**Step 3: Write minimal implementation**

```python
# vecna/tools/types.py
from typing import Any, Dict, List, Optional

@dataclass(frozen=True)
class ToolSpec:
    ...
    tags: List[str] = field(default_factory=list)

@dataclass
class ToolExecutionContext:
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    request_id: Optional[str] = None
    domain: Optional[str] = None
    allowed_fs_roots: List[str] = field(default_factory=list)
```

```python
# vecna/tools/permissions.py
from typing import Any, Dict

def assess_tool_risk(tool_name: str, args: Dict[str, Any]) -> RiskTier:
    if tool_name == "python_exec":
        return assess_code_risk(str(args.get("code", "")))
    if tool_name == "http_request":
        method = str(args.get("method", "GET")).upper()
        return RiskTier.MEDIUM if method not in {"GET", "HEAD"} else RiskTier.LOW
    if tool_name.startswith("fs_"):
        return RiskTier.MEDIUM
    return RiskTier.LOW
```

```python
# vecna/tools/runtime.py
risk = assess_tool_risk(call.tool_name, call.arguments)
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_tools_permissions.py tests/unit/test_tools_runtime.py tests/unit/test_tools_parser.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/tools/types.py vecna/tools/permissions.py vecna/tools/runtime.py tests/unit/test_tools_permissions.py tests/unit/test_tools_runtime.py tests/unit/test_tools_parser.py
git commit -m "fix: unify tool risk assessment and runtime contract handling"
```

---

### Task 3: ReWOO Hardening (Open Questions Closed in Code)

**Files:**
- Modify: `vecna/orchestrator/rewoo.py`
- Modify: `vecna/orchestrator/loop.py`
- Modify: `vecna/config/schema.py`
- Test: `tests/unit/test_rewoo_execution.py`
- Test: `tests/unit/test_rewoo_integration.py`

**Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_rewoo_policy_denied_can_abort_plan():
    # when config says abort_plan, later steps become skipped
    ...

@pytest.mark.asyncio
async def test_rewoo_can_use_separate_synthesizer_adapter():
    ...

@pytest.mark.asyncio
async def test_rewoo_artifact_injection_mode_per_step_updates_memory_summary():
    ...
```

**Step 2: Run tests to verify fail**

Run: `pytest tests/unit/test_rewoo_execution.py tests/unit/test_rewoo_integration.py -v`
Expected: FAIL (new config knobs absent)

**Step 3: Write minimal implementation**

```python
# vecna/orchestrator/rewoo.py
@dataclass
class RewooEngineConfig:
    max_steps: int = 8
    retry_limit: int = 1
    backoff_base_seconds: float = 0.25
    max_artifact_chars: int = 4000
    policy_denied_behavior: str = "fail_step"  # fail_step | abort_plan
    artifact_injection_mode: str = "final_summary"  # final_summary | per_step

class RewooEngine:
    def __init__(..., planner_adapter=None, synthesizer_adapter=None, config=None):
        self.planner_adapter = planner_adapter
        self.synthesizer_adapter = synthesizer_adapter or planner_adapter
```

```python
# execute_rewoo_plan(...) policy denied behavior
if (tool_result.error or "") == "denied by policy" and config.policy_denied_behavior == "abort_plan":
    circuit_open = True
```

```python
# vecna/orchestrator/loop.py _run_rewoo_task
engine = RewooEngine(
    runtime=self.tool_runtime,
    registry=self.tool_registry,
    planner_adapter=planner_adapter,
    synthesizer_adapter=synth_adapter,
    config=RewooEngineConfig(
        ...,
        policy_denied_behavior=self.config.rewoo_policy_denied_behavior,
        artifact_injection_mode=self.config.rewoo_artifact_injection_mode,
    ),
)
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_rewoo_execution.py tests/unit/test_rewoo_integration.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/orchestrator/rewoo.py vecna/orchestrator/loop.py vecna/config/schema.py tests/unit/test_rewoo_execution.py tests/unit/test_rewoo_integration.py
git commit -m "feat: harden rewoo policy-denied behavior and synthesis routing"
```

---

### Task 4: ReWOO Tool Composition Coverage

**Files:**
- Create: `tests/unit/test_rewoo_tool_composition.py`
- Modify: `vecna/orchestrator/rewoo.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_rewoo_composes_search_then_fetch_then_summarize():
    plan = parse_rewoo_plan(
        """Plan: compose tools
E1: web_search[{"query":"vecna memory"}]
E2: http_request[{"url":"#E1"}]
E3: python_exec[{"code":"print('summarize #E2')"}]
Final: Use #E3
"""
    )
    ...
```

**Step 2: Run test to verify fail**

Run: `pytest tests/unit/test_rewoo_tool_composition.py -v`
Expected: FAIL

**Step 3: Minimal implementation**

```python
# vecna/orchestrator/rewoo.py
# Keep existing #E reference substitution, add stricter JSON input validation:
def _validate_step_input_json(step: RewooPlanStep) -> None:
    try:
        json.loads(step.raw_input)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid tool input JSON in {step.step_id}: {exc}")
```

Call `_validate_step_input_json` inside `validate_plan` for each step.

**Step 4: Run tests**

Run: `pytest tests/unit/test_rewoo_tool_composition.py tests/unit/test_rewoo_execution.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/test_rewoo_tool_composition.py vecna/orchestrator/rewoo.py
git commit -m "test: add rewoo tool composition coverage and stricter input validation"
```

---

### Task 5: Implement HTTP Request Tool (Safe by Default)

**Files:**
- Create: `vecna/tools/http_tool.py`
- Test: `tests/unit/test_http_tool.py`

**Step 1: Write failing tests**

```python
@pytest.mark.asyncio
async def test_http_tool_blocks_private_network_targets():
    ...

@pytest.mark.asyncio
async def test_http_tool_extracts_text_from_html():
    ...
```

**Step 2: Run test to verify fail**

Run: `pytest tests/unit/test_http_tool.py -v`
Expected: FAIL (module missing)

**Step 3: Write minimal implementation**

```python
"""HTTP request tool with SSRF guards and HTML extraction."""
import ipaddress
import socket
from urllib.parse import urlparse
from typing import List

import httpx
from bs4 import BeautifulSoup

from vecna.tools.types import ToolExecutionContext, ToolResult

_BLOCKED_NETS: List[ipaddress._BaseNetwork] = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
]

def _is_blocked_host(host: str) -> bool:
    try:
        addr = socket.gethostbyname(host)
        ip = ipaddress.ip_address(addr)
        return any(ip in net for net in _BLOCKED_NETS)
    except Exception:
        return True

async def http_request_executor(args: dict, context: ToolExecutionContext) -> ToolResult:
    url = str(args.get("url", "")).strip()
    method = str(args.get("method", "GET")).upper()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return ToolResult("http_request", False, "", error="invalid url scheme")
    if not parsed.hostname or _is_blocked_host(parsed.hostname):
        return ToolResult("http_request", False, "", error="blocked host")

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        resp = await client.request(method, url, headers=args.get("headers"), content=args.get("body"))

    ctype = resp.headers.get("content-type", "")
    if "html" in ctype:
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        output = "\n".join(line.strip() for line in soup.get_text().splitlines() if line.strip())
    else:
        output = resp.text

    return ToolResult("http_request", True, output[:8000], metadata={"status_code": resp.status_code})
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_http_tool.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/tools/http_tool.py tests/unit/test_http_tool.py
git commit -m "feat: add safe http request tool with ssrf guardrails"
```

---

### Task 6: Implement Web Search Tool (No External API Key)

**Files:**
- Create: `vecna/tools/web_search_tool.py`
- Test: `tests/unit/test_web_search_tool.py`

**Step 1: Write failing tests**

```python
@pytest.mark.asyncio
async def test_web_search_returns_ranked_results_text():
    ...

@pytest.mark.asyncio
async def test_web_search_empty_query_is_rejected():
    ...
```

**Step 2: Run test to verify fail**

Run: `pytest tests/unit/test_web_search_tool.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
"""Web search tool backed by DuckDuckGo HTML endpoint."""
import httpx
from bs4 import BeautifulSoup

from vecna.tools.types import ToolExecutionContext, ToolResult

async def web_search_executor(args: dict, context: ToolExecutionContext) -> ToolResult:
    query = str(args.get("query", "")).strip()
    max_results = int(args.get("max_results", 5))
    if not query:
        return ToolResult("web_search", False, "", error="empty query")

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get("https://html.duckduckgo.com/html/", params={"q": query})

    soup = BeautifulSoup(resp.text, "html.parser")
    lines = []
    for idx, block in enumerate(soup.select(".result")[:max_results], start=1):
        title = block.select_one(".result__a")
        snippet = block.select_one(".result__snippet")
        if not title:
            continue
        lines.append(f"{idx}. {title.get_text(strip=True)}")
        lines.append(f"   URL: {title.get('href', '')}")
        if snippet:
            lines.append(f"   {snippet.get_text(strip=True)}")
    if not lines:
        return ToolResult("web_search", True, "No results found.")
    return ToolResult("web_search", True, "\n".join(lines))
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_web_search_tool.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/tools/web_search_tool.py tests/unit/test_web_search_tool.py
git commit -m "feat: add web search tool without external api dependency"
```

---

### Task 7: Implement Filesystem Tools with Config-Driven Sandbox

**Files:**
- Create: `vecna/tools/path_policy.py`
- Create: `vecna/tools/fs_tools.py`
- Modify: `vecna/tools/types.py`
- Test: `tests/unit/test_fs_tools.py`

**Step 1: Write failing tests**

```python
@pytest.mark.asyncio
async def test_fs_read_uses_context_roots_not_args(tmp_path):
    ...

@pytest.mark.asyncio
async def test_fs_read_blocks_path_outside_context_roots(tmp_path):
    ...
```

**Step 2: Run test to verify fail**

Run: `pytest tests/unit/test_fs_tools.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# vecna/tools/path_policy.py
from pathlib import Path
from typing import List

def normalize_roots(roots: List[str]) -> List[Path]:
    return [Path(root).expanduser().resolve() for root in roots]

def is_allowed(path: str, roots: List[str]) -> bool:
    target = Path(path).expanduser().resolve()
    for root in normalize_roots(roots):
        if target == root or root in target.parents:
            return True
    return False
```

```python
# vecna/tools/fs_tools.py
from pathlib import Path
from vecna.tools.path_policy import is_allowed
from vecna.tools.types import ToolExecutionContext, ToolResult

async def fs_read_executor(args: dict, context: ToolExecutionContext) -> ToolResult:
    path = str(args.get("path", "")).strip()
    roots = context.allowed_fs_roots or ["~/.vecna"]
    if not path or not is_allowed(path, roots):
        return ToolResult("fs_read", False, "", error="path not allowed")
    p = Path(path).expanduser().resolve()
    if not p.exists() or not p.is_file():
        return ToolResult("fs_read", False, "", error="file not found")
    return ToolResult("fs_read", True, p.read_text(encoding="utf-8", errors="replace")[:10000])
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_fs_tools.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/tools/path_policy.py vecna/tools/fs_tools.py vecna/tools/types.py tests/unit/test_fs_tools.py
git commit -m "feat: add config-scoped filesystem tools with strict path policy"
```

---

### Task 8: Register New Tools and Add Semantic Tool Routing

**Files:**
- Modify: `vecna/tools/registry.py`
- Modify: `vecna/tools/router.py`
- Modify: `vecna/orchestrator/rewoo.py`
- Test: `tests/unit/test_tools_registry.py`
- Test: `tests/unit/test_tool_router.py`

**Step 1: Write failing tests**

```python
def test_default_registry_includes_new_tools():
    registry = get_default_registry()
    names = [spec.name for spec in registry.list_tools()]
    assert "http_request" in names
    assert "web_search" in names
    assert "fs_read" in names

def test_router_ranks_tools_by_tag_overlap():
    ...
```

**Step 2: Run tests to verify fail**

Run: `pytest tests/unit/test_tools_registry.py tests/unit/test_tool_router.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# vecna/tools/registry.py (register)
ToolSpec(name="http_request", ..., tags=["web", "http", "fetch"])
ToolSpec(name="web_search", ..., tags=["web", "search"])
ToolSpec(name="fs_read", ..., tags=["filesystem", "read"])
ToolSpec(name="fs_list", ..., tags=["filesystem", "list"])
```

```python
# vecna/tools/router.py
from typing import List
from vecna.tools.types import ToolSpec

def rank_specs_for_query(self, specs: List[ToolSpec], query: str) -> List[ToolSpec]:
    words = set(query.lower().split())
    def score(spec: ToolSpec) -> float:
        bag = set(spec.name.lower().split("_")) | set(spec.description.lower().split()) | set(spec.tags)
        return float(len(words & bag)) + self.success_rate(spec.name)
    return sorted(specs, key=score, reverse=True)
```

```python
# vecna/orchestrator/rewoo.py
ranked_specs = self.router.rank_specs_for_query(self.registry.list_tools(), task)
tool_names = [spec.name for spec in ranked_specs]
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_tools_registry.py tests/unit/test_tool_router.py tests/unit/test_rewoo_execution.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/tools/registry.py vecna/tools/router.py vecna/orchestrator/rewoo.py tests/unit/test_tools_registry.py tests/unit/test_tool_router.py
git commit -m "feat: register new tools and add semantic routing for planner"
```

---

### Task 9: Add Tool Quotas and Budgeting

**Files:**
- Create: `vecna/tools/quotas.py`
- Modify: `vecna/tools/runtime.py`
- Modify: `vecna/cli/main.py`
- Test: `tests/unit/test_tool_quotas.py`
- Test: `tests/unit/test_tools_runtime.py`

**Step 1: Write failing tests**

```python
def test_quota_manager_blocks_after_session_limit():
    ...

@pytest.mark.asyncio
async def test_runtime_returns_quota_exceeded_error():
    ...
```

**Step 2: Run tests to verify fail**

Run: `pytest tests/unit/test_tool_quotas.py tests/unit/test_tools_runtime.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# vecna/tools/quotas.py
from dataclasses import dataclass
from typing import Dict

@dataclass
class QuotaConfig:
    per_session: int = 0
    per_tool: int = 0

class ToolQuotaManager:
    def __init__(self, config: QuotaConfig) -> None:
        self.config = config
        self.counts: Dict[str, Dict[str, int]] = {}

    def can_execute(self, session_id: str, tool_name: str) -> bool:
        ...

    def record(self, session_id: str, tool_name: str) -> None:
        ...
```

```python
# vecna/tools/runtime.py (before execution)
if self.quota_manager and context.session_id:
    if not self.quota_manager.can_execute(context.session_id, call.tool_name):
        result = ToolResult(call.tool_name, False, "", error="quota exceeded")
    else:
        ...
        self.quota_manager.record(context.session_id, call.tool_name)
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_tool_quotas.py tests/unit/test_tools_runtime.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/tools/quotas.py vecna/tools/runtime.py vecna/cli/main.py tests/unit/test_tool_quotas.py tests/unit/test_tools_runtime.py
git commit -m "feat: enforce per-session and per-tool quotas in runtime"
```

---

### Task 10: Add DB-Backed Priority Goal Queue

**Files:**
- Create: `vecna/migrations/versions/005_goal_queue_table.py`
- Create: `vecna/orchestrator/pg_goal_queue.py`
- Modify: `vecna/orchestrator/goal_queue.py`
- Test: `tests/unit/test_goal_queue.py`
- Test: `tests/integration/test_goal_queue_pg.py`

**Step 1: Write failing tests**

```python
def test_pg_goal_queue_returns_highest_priority_pending_goal():
    ...

def test_pg_goal_queue_deduplicates_by_content_hash():
    ...

def test_pg_goal_queue_tracks_status_and_retries():
    ...
```

**Step 2: Run tests to verify fail**

Run: `pytest tests/unit/test_goal_queue.py tests/integration/test_goal_queue_pg.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# vecna/migrations/versions/005_goal_queue_table.py
def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS autonomy_goals (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            content TEXT NOT NULL,
            content_hash TEXT NOT NULL UNIQUE,
            priority INTEGER NOT NULL DEFAULT 5,
            status TEXT NOT NULL DEFAULT 'pending',
            retry_count INTEGER NOT NULL DEFAULT 0,
            max_retries INTEGER NOT NULL DEFAULT 0,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            scheduled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            last_error TEXT
        );
        """
    )
```

```python
# vecna/orchestrator/pg_goal_queue.py
class PgGoalQueue:
    def push(self, content: str, priority: int = 5, max_retries: int = 0, metadata: Optional[Dict[str, Any]] = None) -> str:
        ...

    def pop(self) -> Optional[Dict[str, Any]]:
        # SELECT ... FOR UPDATE SKIP LOCKED ORDER BY priority DESC, scheduled_at ASC
        ...

    def mark_completed(self, goal_id: str) -> None:
        ...

    def mark_failed(self, goal_id: str, error: str) -> None:
        ...
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_goal_queue.py tests/integration/test_goal_queue_pg.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/migrations/versions/005_goal_queue_table.py vecna/orchestrator/pg_goal_queue.py vecna/orchestrator/goal_queue.py tests/unit/test_goal_queue.py tests/integration/test_goal_queue_pg.py
git commit -m "feat: add db-backed priority goal queue with dedup and retry tracking"
```

---

### Task 11: Upgrade Autonomy Loop with Backoff + Kill Switch

**Files:**
- Create: `vecna/orchestrator/kill_switch.py`
- Modify: `vecna/orchestrator/autonomy.py`
- Test: `tests/unit/test_kill_switch.py`
- Test: `tests/unit/test_autonomy_loop.py`

**Step 1: Write failing tests**

```python
def test_kill_switch_persists_and_records_audit_events():
    ...

@pytest.mark.asyncio
async def test_autonomy_loop_stops_when_kill_switch_active():
    ...
```

**Step 2: Run tests to verify fail**

Run: `pytest tests/unit/test_kill_switch.py tests/unit/test_autonomy_loop.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# vecna/orchestrator/kill_switch.py
class KillSwitch:
    def __init__(self, state_dir: Path):
        ...
    def kill(self, reason: str) -> None:
        ...
    def resume(self, reason: str) -> None:
        ...
    def is_active(self) -> bool:
        ...
    def check_or_raise(self) -> None:
        ...
```

```python
# vecna/orchestrator/autonomy.py
@dataclass
class BackoffConfig:
    base_seconds: float = 2.0
    max_seconds: float = 120.0
    multiplier: float = 2.0

class AutonomyLoop(HiveLoop):
    async def run(...):
        # kill switch check each cycle
        # retry bookkeeping
        # exponential backoff on failures
        ...
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_kill_switch.py tests/unit/test_autonomy_loop.py tests/unit/test_goal_queue.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/orchestrator/kill_switch.py vecna/orchestrator/autonomy.py tests/unit/test_kill_switch.py tests/unit/test_autonomy_loop.py
git commit -m "feat: add kill switch and robust autonomy loop backoff behavior"
```

---

### Task 12: Add Heartbeat Scheduler (Cron-Friendly)

**Files:**
- Create: `vecna/orchestrator/heartbeat.py`
- Modify: `vecna/cli/main.py`
- Test: `tests/unit/test_heartbeat.py`
- Test: `tests/e2e/test_heartbeat_cli.py`

**Step 1: Write failing tests**

```python
@pytest.mark.asyncio
async def test_heartbeat_tick_reads_queue_and_executes_at_most_n_goals():
    ...

def test_cli_heartbeat_tick_command_exists():
    ...
```

**Step 2: Run tests to verify fail**

Run: `pytest tests/unit/test_heartbeat.py tests/e2e/test_heartbeat_cli.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# vecna/orchestrator/heartbeat.py
@dataclass
class HeartbeatConfig:
    interval_seconds: int = 900
    jitter_seconds: int = 90
    max_goals_per_tick: int = 3

class HeartbeatRunner:
    def __init__(self, autonomy_loop: AutonomyLoop, goal_queue) -> None:
        ...
    async def tick(self) -> Dict[str, Any]:
        # one-shot execution for cron use
        ...
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_heartbeat.py tests/e2e/test_heartbeat_cli.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/orchestrator/heartbeat.py vecna/cli/main.py tests/unit/test_heartbeat.py tests/e2e/test_heartbeat_cli.py
git commit -m "feat: add cron-friendly heartbeat scheduler for bounded autonomy"
```

---

### Task 13: Replace Curiosity Stub with Typed Engine

**Files:**
- Modify: `vecna/orchestrator/curiosity.py`
- Test: `tests/unit/test_curiosity_engine.py`

**Step 1: Write failing tests**

```python
def test_curiosity_uses_open_question_question_field():
    ...

def test_curiosity_uses_contradiction_item_fields():
    ...
```

**Step 2: Run tests to verify fail**

Run: `pytest tests/unit/test_curiosity_engine.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
"""Curiosity signal generation from contradictions, questions, weak beliefs."""
from dataclasses import dataclass
from typing import Dict, List

from vecna.core.types import Belief, Contradiction, OpenQuestion

@dataclass
class CuriosityGoal:
    content: str
    priority: int
    source: str

class CuriosityEngine:
    def from_contradictions(self, contradictions: List[Contradiction]) -> List[CuriosityGoal]:
        goals: List[CuriosityGoal] = []
        for item in contradictions:
            goals.append(
                CuriosityGoal(
                    content=f"Investigate contradiction: {item.item_a_content} vs {item.item_b_content}",
                    priority=9,
                    source="contradiction",
                )
            )
        return goals

    def from_open_questions(self, questions: List[OpenQuestion]) -> List[CuriosityGoal]:
        return [CuriosityGoal(content=f"Research open question: {q.question}", priority=7, source="question") for q in questions]
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_curiosity_engine.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/orchestrator/curiosity.py tests/unit/test_curiosity_engine.py
git commit -m "feat: implement typed curiosity engine with contradiction and question signals"
```

---

### Task 14: Implement True BM25 Hybrid Ranking

**Files:**
- Modify: `vecna/memory/pg_store.py`
- Test: `tests/unit/test_hybrid_search.py`
- Test: `tests/integration/test_hybrid_search_pg.py`

**Step 1: Write failing tests**

```python
def test_hybrid_search_uses_bm25_formula_terms(monkeypatch):
    # verify bm25 computation branch is used, not substring fallback
    ...

@pytest.mark.integration
def test_bm25_ranks_exact_term_match_above_loose_match(pg_memory_store):
    ...
```

**Step 2: Run tests to verify fail**

Run: `pytest tests/unit/test_hybrid_search.py tests/integration/test_hybrid_search_pg.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# vecna/memory/pg_store.py
def _bm25_score(tf: float, df: float, doc_len: float, avg_doc_len: float, total_docs: float, k1: float = 1.2, b: float = 0.75) -> float:
    import math
    idf = math.log(1 + (total_docs - df + 0.5) / (df + 0.5))
    denom = tf + k1 * (1 - b + b * (doc_len / max(avg_doc_len, 1.0)))
    return idf * ((tf * (k1 + 1)) / max(denom, 1e-6))

def _tokenize(text: str) -> List[str]:
    return [tok.lower() for tok in re.findall(r"[a-zA-Z0-9_]+", text)]

# in search(..., hybrid=True):
# 1) fetch vector candidates + text candidates
# 2) compute BM25 per candidate in Python
# 3) combine score = vector_weight * vec + text_weight * bm25
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_hybrid_search.py tests/integration/test_hybrid_search_pg.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/memory/pg_store.py tests/unit/test_hybrid_search.py tests/integration/test_hybrid_search_pg.py
git commit -m "feat: add true bm25 scoring for hybrid memory retrieval"
```

---

### Task 15: Implement Multi-Hop Graph Traversal

**Files:**
- Modify: `vecna/memory/pg_store.py`
- Test: `tests/integration/test_pg_memory_store.py`

**Step 1: Write failing test**

```python
@pytest.mark.integration
def test_get_related_items_respects_max_depth(pg_memory_store):
    # A->B->C chain, depth=1 returns B only, depth=2 returns B and C
    ...
```

**Step 2: Run test to verify fail**

Run: `pytest tests/integration/test_pg_memory_store.py::test_get_related_items_respects_max_depth -v`
Expected: FAIL (current code only does 1-hop)

**Step 3: Write minimal implementation**

```python
# vecna/memory/pg_store.py (replace get_related_items traversal SQL)
# Use WITH RECURSIVE traversal and cycle guard, then pick best path weight per node.
# Keep return signature: List[Tuple[MemoryItem, float, List[str]]]
```

**Step 4: Run tests**

Run: `pytest tests/integration/test_pg_memory_store.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/memory/pg_store.py tests/integration/test_pg_memory_store.py
git commit -m "feat: implement recursive multi-hop memory edge traversal"
```

---

### Task 16: Dream Insights, Cross-Session Patterns, Memory Consolidation

**Files:**
- Modify: `vecna/memory/dream_loop.py`
- Create: `vecna/memory/patterns.py`
- Create: `vecna/memory/consolidation.py`
- Test: `tests/unit/test_dream_loop.py`
- Test: `tests/unit/test_memory_patterns.py`

**Step 1: Write failing tests**

```python
def test_generate_insights_no_longer_returns_stub_zero_when_inputs_exist():
    ...

def test_pattern_detector_finds_repeated_theme_across_sessions():
    ...

def test_consolidation_merges_similar_memory_items():
    ...
```

**Step 2: Run tests to verify fail**

Run: `pytest tests/unit/test_dream_loop.py tests/unit/test_memory_patterns.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# vecna/memory/patterns.py
class SessionPatternDetector:
    def detect(self, sessions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # simple frequency-based recurring theme extraction
        ...
```

```python
# vecna/memory/consolidation.py
class MemoryConsolidator:
    def merge_candidates(self, items: List[MemoryItem]) -> List[List[MemoryItem]]:
        ...

    def consolidate_group(self, group: List[MemoryItem]) -> MemoryItem:
        ...
```

```python
# vecna/memory/dream_loop.py
def _generate_insights(self, dry_run: bool) -> int:
    # remove placeholder; use pattern detector and summarizer to create hypotheses
    ...
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_dream_loop.py tests/unit/test_memory_patterns.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/memory/dream_loop.py vecna/memory/patterns.py vecna/memory/consolidation.py tests/unit/test_dream_loop.py tests/unit/test_memory_patterns.py
git commit -m "feat: add dream insights, cross-session pattern detection, and consolidation"
```

---

### Task 17: Identity Emergence (Opinion Formation + Drift Tracking)

**Files:**
- Create: `vecna/orchestrator/identity_growth.py`
- Modify: `vecna/orchestrator/self_reflection.py`
- Modify: `vecna/core/hive_state.py`
- Test: `tests/unit/test_identity_growth.py`

**Step 1: Write failing tests**

```python
def test_identity_growth_forms_opinion_from_repeated_evidence():
    ...

def test_identity_growth_tracks_personality_drift_metric():
    ...

def test_contradiction_driven_growth_adjusts_self_model_not_soul_file():
    ...
```

**Step 2: Run test to verify fail**

Run: `pytest tests/unit/test_identity_growth.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# vecna/orchestrator/identity_growth.py
@dataclass
class IdentityGrowthResult:
    opinions_updated: int = 0
    drift_delta: float = 0.0
    contradictions_processed: int = 0

class IdentityGrowthEngine:
    def run(self, state: HiveState) -> IdentityGrowthResult:
        # derive candidate opinions from high-confidence repeated beliefs
        # update self_model narrative/coherence metadata
        ...
```

Integrate behind feature flag `enable_identity_growth` in loop reflection path.

**Step 4: Run tests**

Run: `pytest tests/unit/test_identity_growth.py tests/unit/test_self_reflection.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/orchestrator/identity_growth.py vecna/orchestrator/self_reflection.py vecna/core/hive_state.py tests/unit/test_identity_growth.py
git commit -m "feat: add identity growth loop for opinions and drift tracking"
```

---

### Task 18: Security Hardening (Seccomp + TTL + Redaction)

**Files:**
- Create: `vecna/security/seccomp/default-profile.json`
- Create: `vecna/tools/redaction.py`
- Modify: `vecna/memory/rlm_bridge.py`
- Modify: `vecna/tools/audit.py`
- Modify: `vecna/observability/langfuse.py`
- Test: `tests/unit/test_rlm_security.py`
- Test: `tests/unit/test_redaction.py`

**Step 1: Write failing tests**

```python
def test_rlm_bridge_includes_seccomp_profile_when_enabled():
    ...

def test_rlm_container_ttl_forces_shutdown_after_idle_period():
    ...

def test_audit_logger_redacts_secrets_and_pii():
    ...
```

**Step 2: Run tests to verify fail**

Run: `pytest tests/unit/test_rlm_security.py tests/unit/test_redaction.py tests/unit/test_tools_audit.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# vecna/memory/rlm_bridge.py (docker run cmd)
if self.config.enable_seccomp and self.config.seccomp_profile_path:
    cmd.extend(["--security-opt", f"seccomp={self.config.seccomp_profile_path}"])

# track last activity and enforce ttl in execute_code/install_packages
if self.config.container_ttl_seconds > 0 and self._is_expired():
    await self.shutdown()
    await self.prewarm()
```

```python
# vecna/tools/redaction.py
def redact_all(text: str) -> str:
    # redact emails, phone numbers, access keys, db passwords, api tokens
    ...
```

```python
# vecna/tools/audit.py
payload = asdict(event)
if self.redact:
    payload = _redact_payload(payload)
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_rlm_security.py tests/unit/test_redaction.py tests/unit/test_tools_audit.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/security/seccomp/default-profile.json vecna/tools/redaction.py vecna/memory/rlm_bridge.py vecna/tools/audit.py vecna/observability/langfuse.py tests/unit/test_rlm_security.py tests/unit/test_redaction.py tests/unit/test_tools_audit.py
git commit -m "feat: harden runtime with seccomp, ttl cleanup, and end-to-end redaction"
```

---

### Task 19: Observability, Safety Evals, and UX Approvals

**Files:**
- Create: `vecna/observability/tool_dashboard.py`
- Create: `vecna/observability/memory_tracing.py`
- Create: `tests/safety/test_tool_safety_regressions.py`
- Create: `tests/safety/test_red_team_tool_calls.py`
- Modify: `vecna/cli/main.py`
- Modify: `vecna/tools/runtime.py`
- Test: `tests/unit/test_tool_dashboard.py`
- Test: `tests/e2e/test_cli_tools_approvals.py`

**Step 1: Write failing tests**

```python
def test_tool_dashboard_aggregates_latency_failure_and_denials():
    ...

def test_memory_access_trace_records_why_items_were_retrieved():
    ...

def test_chat_inline_approval_command_updates_pending_request():
    ...
```

**Step 2: Run tests to verify fail**

Run: `pytest tests/unit/test_tool_dashboard.py tests/e2e/test_cli_tools_approvals.py tests/safety -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# vecna/observability/tool_dashboard.py
class ToolDashboard:
    def ingest(self, event: ToolAuditEvent) -> None:
        ...
    def summarize(self) -> Dict[str, Any]:
        ...
```

```python
# vecna/tools/runtime.py
# support inline approval control messages in chat text:
# <TOOL_APPROVAL request_id="..." action="approve" />
```

```python
# tests/safety/
# add regression corpus for prompt-injected dangerous tool calls
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_tool_dashboard.py tests/e2e/test_cli_tools_approvals.py tests/safety -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/observability/tool_dashboard.py vecna/observability/memory_tracing.py vecna/cli/main.py vecna/tools/runtime.py tests/unit/test_tool_dashboard.py tests/e2e/test_cli_tools_approvals.py tests/safety/test_tool_safety_regressions.py tests/safety/test_red_team_tool_calls.py
git commit -m "feat: add observability dashboards, safety suites, and inline approval ux"
```

---

### Task 20: Full Verification and Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/index.md`
- Create: `docs/operations/autonomy-heartbeat.md`
- Create: `docs/security/tooling-hardening.md`
- Create: `docs/observability/safety-regressions.md`

**Step 1: Run lint/format checks**

Run: `ruff check .`
Expected: PASS

Run: `ruff format --check .`
Expected: PASS

**Step 2: Run unit and e2e tests**

Run: `pytest tests/unit/ tests/e2e/ -v`
Expected: PASS

**Step 3: Run integration tests (services available)**

Run: `pytest tests/integration/ -v -m "not requires_docker and not requires_copilot and not requires_langfuse"`
Expected: PASS

**Step 4: Run safety suite**

Run: `pytest tests/safety -v`
Expected: PASS

**Step 5: Commit**

```bash
git add README.md docs/index.md docs/operations/autonomy-heartbeat.md docs/security/tooling-hardening.md docs/observability/safety-regressions.md
git commit -m "docs: add operations, security, and observability guidance for new subsystems"
```

---

## Backlog Coverage Map (All Remaining Items)

| Roadmap Item | Covered By |
|---|---|
| A1 True BM25 scoring | Task 14 |
| A5 Multi-hop graph traversal | Task 15 |
| A6 Dream `_generate_insights()` | Task 16 |
| A7 Cross-session patterns | Task 16 |
| A8 Memory consolidation | Task 16 |
| B1 HTTP/web browsing tool | Task 5 |
| B2 Filesystem tools | Task 7 |
| B3 Web search tool | Task 6 |
| B4 Semantic tool routing | Task 8 |
| B5 Quotas/budgeting | Task 9 |
| B6 Tool composition in ReWOO | Task 4 + Task 3 |
| C1 ReWOO hardening/tests | Task 3 + Task 4 |
| C2 Separate synthesis adapter question | Task 3 |
| C3 Policy-denied behavior question | Task 3 |
| C4 Artifact injection timing question | Task 3 |
| D1 DB-backed priority queue | Task 10 |
| D2 Background cycles + backoff/retry | Task 11 + Task 12 |
| D3 Curiosity engine | Task 13 |
| D4 Kill switch | Task 11 |
| D5 Heartbeat scheduling | Task 12 |
| E1 Self-model updates | Task 17 |
| E2 Opinion formation | Task 17 |
| E3 Personality drift tracking | Task 17 |
| E4 Contradiction-driven growth | Task 17 |
| F1 Seccomp profiles | Task 18 |
| F2 Container TTL cleanup | Task 18 |
| F3 PII/secret redaction | Task 18 |
| G1 Tool dashboards | Task 19 |
| G2 Safety regression tests | Task 19 |
| G3 Red-team suite | Task 19 |
| G4 Memory access tracing | Task 19 |
| G5 Identity metrics | Task 19 |
| G6 Flush quality tracking | Task 19 |
| G7 Session analytics | Task 19 |
| H1 Queue status views | Task 19 |
| H2 Interactive approval in chat | Task 19 |

---

## Implementation Notes

- Execute in order; do not parallelize across gates.
- Within a gate, independent tasks can run in parallel if they do not touch shared files.
- Keep each commit narrowly scoped to one task.
- If a task fails due to architecture mismatch, pause and patch the plan before coding further.

---

Plan complete and saved to `docs/plans/2026-02-15-remaining-work-implementation-plan-v2.md`.

Two execution options:

1. **Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration
2. **Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
