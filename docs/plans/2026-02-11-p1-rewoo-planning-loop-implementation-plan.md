# P1 ReWOO Planning Loop Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the current ReWOO parser stub with a real plan-execute-observe loop that can decompose a goal, run tool steps with variable binding, and produce a grounded final answer safely.

**Architecture:** Add a ReWOO orchestrator that (1) asks an adapter to emit a structured plan, (2) validates and compiles the plan, (3) executes each step through ToolRuntime with strict policy gates, (4) records observations back into shared state and trace spans, and (5) synthesizes a final response from execution artifacts. Integrate this path into `HiveLoop` behind an explicit feature flag so rollout can be staged safely.

**Tech Stack:** Python 3.10+, dataclasses, existing `vecna.orchestrator.*`, `vecna.tools.*`, Langfuse tracing (`vecna.observability.langfuse`), pytest + Ruff.

**Execution note:** Commit steps in this plan are optional checkpoints; only perform git commits when explicitly requested.

---

## 1. Problem Framing

Current status:
- `vecna/orchestrator/rewoo.py` only parses `E1: Tool[input]` regex lines and has no planner, no variable interpolation, no execution state, and no error semantics.
- `vecna/orchestrator/autonomy.py` drains a FIFO queue and delegates each goal to `HiveLoop.think` as a one-shot request.
- `vecna/orchestrator/loop.py` currently treats task completion as one cycle (`_is_task_complete` always returns `True`) and tool execution is opportunistic (only if model already emits `<TOOL_CALL>` blocks).

Why this matters:
- P1 autonomy requires deliberate decomposition and multi-step execution, not a single response with optional tool calls.
- Without a plan loop, there is no durable execution trace for partial failures, retries, or explainable outcomes.

### Non-goals (explicit)

- Do not build DB-backed priority goal queue in this work item (that is the next P1 item).
- Do not implement curiosity engine or autonomous wake scheduler here.
- Do not redesign tool permission policy model; reuse existing `ToolPermissionManager` and `ApprovalStore`.
- Do not add new external dependencies.

---

## 2. Current-State Gap Analysis

### Implemented today

- Tool execution engine: `ToolRuntime.execute_calls` in `vecna/tools/runtime.py`.
- Tool parsing: `parse_tool_calls` in `vecna/tools/parser.py`.
- Tool registry and policy: `vecna/tools/registry.py`, `vecna/tools/permissions.py`.
- Basic autonomy queue runner: `AutonomyLoop.run` in `vecna/orchestrator/autonomy.py`.

### Missing for real ReWOO

- Planner contract: no typed ReWOO plan schema and no planner prompt/response parser.
- Execution context: no variable table (`#E1`, `#E2`) and no interpolation rules.
- Step machine: no status model (`pending/running/succeeded/failed/skipped`) for each step.
- Error model: no retry/backoff policy per step and no stop/continue semantics.
- Observability: no dedicated spans for `rewoo.plan`, `rewoo.execute_step`, `rewoo.synthesize`.
- Integration path: `HiveLoop` has no branch that routes complex tasks through a planner/executor loop.

---

## 3. Target Architecture

### 3.0 Reverified "real ReWOO" contract (locked)

Use a strict planner output grammar so this is a real planner/worker loop, not regex-only extraction:

- `Plan: <free-text reasoning summary>`
- `E1: <tool_name>[<input template>]`
- `E2: <tool_name>[<input template with #E1 refs>]`
- ...
- `Final: <final answer template using #E* refs>`

Validation rules:
- Step IDs must be contiguous and monotonic (`E1..En`).
- `<tool_name>` must exist in `ToolRegistry` (`python_exec`, `memory_search`, `memory_get`, and future tools).
- `#E*` references must point to prior steps only.
- `Final:` is required for successful plan execution; if absent or invalid, use deterministic synthesis fallback.

## 3.1 New core dataclasses (in `vecna/orchestrator/rewoo.py`)

- `RewooPlanStep`: `step_id`, `tool_name`, `raw_input`, `depends_on`, `retry_limit`, `timeout_seconds`.
- `RewooPlan`: `goal`, `steps`, `final_prompt_template`.
- `RewooStepResult`: `step_id`, `status`, `tool_result`, `rendered_input`, `attempts`, `error`.
- `RewooExecution`: immutable-ish snapshot of execution (`plan`, `results`, `artifacts`, `started_at`, `ended_at`).

## 3.2 ReWOO engine surface

Add class `RewooEngine` in `vecna/orchestrator/rewoo.py`:
- `async def create_plan(self, task: str, state: HiveState) -> RewooPlan`
- `def validate_plan(self, plan: RewooPlan, registry: ToolRegistry) -> None`
- `def render_step_input(self, raw_input: str, artifacts: Dict[str, str]) -> str`
- `async def execute_plan(...) -> RewooExecution`
- `async def synthesize_answer(...) -> str`
- `async def run(...) -> RewooExecutionResult`

Add `RewooExecutionResult` dataclass containing:
- `answer: str`
- `execution: RewooExecution`
- `used_rewoo: bool`
- `fallback_reason: Optional[str]`

## 3.3 Integration points

- `vecna/orchestrator/loop.py`: branch in `HiveLoop.think` to call `RewooEngine.run` when enabled and eligible.
- `vecna/orchestrator/autonomy.py`: prefer ReWOO path for queued goals when enabled.
- `vecna/config/schema.py` and/or `HiveConfig` in `vecna/orchestrator/loop.py`: add feature flags:
  - `enable_rewoo_planning: bool = False`
  - `rewoo_max_steps: int = 8`
  - `rewoo_retry_limit: int = 1`

---

## 4. Detailed Control/Data Flow

1. `HiveLoop.think(task)` enters and determines eligibility:
   - `enable_rewoo_planning` is true.
   - task complexity heuristic indicates multi-step need (or explicit override).
2. `RewooEngine.create_plan` asks planner adapter for strict text format.
3. Engine parses to `RewooPlan`, validates tool names and references.
4. For each step in order:
   - Render input by resolving references (`#E1`, `#E2`) from `artifacts`.
   - Build synthetic `<TOOL_CALL>` payload and execute via `ToolRuntime.execute_calls`.
   - Capture `ToolResult.output` into `artifacts[step_id]`.
   - Persist step result status and trace metadata.
5. On terminal failure policy, stop loop and prepare fallback synthesis from partial results.
6. `synthesize_answer` composes final answer using task + artifacts + failures.
7. Return answer to caller and append execution summary into session conversation log.

Data contracts:
- Artifact map key format: `E1`, `E2`, etc. (without `#` in storage; `#` only in templates).
- Variable interpolation syntax accepted in step input: `#E<integer>`.
- Final prompt template may reference any prior artifact.

---

## 5. Error Model and Safety Semantics

Step-level failure classes:
- `plan_validation_error`: malformed plan or unknown tools -> immediate fallback to non-ReWOO `HiveLoop` path.
- `policy_denied`: permission manager denies tool -> mark step failed; no retry.
- `approval_required`: mark pending in output and fail step; no auto retry.
- `tool_runtime_error`: executor exception or invalid tool result -> retry up to `rewoo_retry_limit`.
- `interpolation_error`: unresolved `#E*` variable -> fail-fast and stop plan.

Retry/backoff:
- Deterministic linear backoff only (`0.25s * attempt`) to keep behavior testable.
- Max attempts = `1 + retry_limit`.

Circuit-break behavior:
- If two consecutive steps fail, stop remaining steps and synthesize partial answer.
- If planner emits more than `rewoo_max_steps`, reject plan and fallback.

Policy integration:
- All execution must still flow through `ToolRuntime` so `ToolPermissionManager`, `ApprovalStore`, and audit events remain single source of truth.

---

## 6. Persistence Implications (Goal Queue Now vs Later)

Current work item:
- Keep `GoalQueue` JSONL FIFO unchanged in storage schema.
- ReWOO execution state is in-memory per `think()` call and surfaced via logs/traces.

Forward-compatible hooks now:
- Include optional `execution_id` (UUID string) in `RewooExecution` and return object.
- Keep step results serializable to plain dict so they can be persisted by next P1 queue migration without refactor.

Next P1 item impact:
- DB goal queue implementation can attach `rewoo_execution` JSONB blobs and resume semantics.
- No Alembic migration in this item.

---

## 7. Incremental Milestones

M1 Parser and types:
- Replace regex-only parser with typed plan parser and validation helpers.

M2 Execution core:
- Execute validated steps through ToolRuntime with interpolation and retries.

M3 Loop integration:
- Route eligible tasks from `HiveLoop.think` through `RewooEngine`.

M4 Observability and polish:
- Add Langfuse spans/metadata, failure counters, and docs.

M5 Harden and ship:
- Full test matrix green, feature flag default off, rollout checklist complete.

---

## 8. File-by-File Plan (Exact Paths)

### Task 1: Add ReWOO core type contracts

**Files:**
- Modify: `vecna/orchestrator/rewoo.py`
- Test: `tests/unit/test_rewoo_parser.py`

**Step 1: Write failing tests for plan model parsing**

Add tests for:
- valid multi-step plan parses to typed objects,
- unknown lines rejected,
- malformed references rejected.

**Step 2: Run tests to verify failure**

Run: `pytest tests/unit/test_rewoo_parser.py -v`
Expected: FAIL for missing dataclasses/parser behavior.

**Step 3: Implement minimal dataclasses + parser**

Implement `RewooPlanStep`, `RewooPlan`, parser function(s), and validation helpers.

**Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_rewoo_parser.py -v`
Expected: PASS.

**Step 5: Commit**

Run:
```bash
git add vecna/orchestrator/rewoo.py tests/unit/test_rewoo_parser.py
git commit -m "feat: add typed rewoo plan parser"
```

### Task 2: Add interpolation and artifact handling

**Files:**
- Modify: `vecna/orchestrator/rewoo.py`
- Create: `tests/unit/test_rewoo_execution.py`

**Step 1: Write failing tests for `#E*` interpolation**

Cover:
- substitutes known artifacts,
- supports repeated references,
- fails on unknown references.

**Step 2: Run targeted tests**

Run: `pytest tests/unit/test_rewoo_execution.py -k render_step_input -v`
Expected: FAIL.

**Step 3: Implement `render_step_input`**

Use explicit regex with strict error message on unresolved symbols.

**Step 4: Run tests**

Run: `pytest tests/unit/test_rewoo_execution.py -v`
Expected: PASS for interpolation cases.

**Step 5: Commit**

```bash
git add vecna/orchestrator/rewoo.py tests/unit/test_rewoo_execution.py
git commit -m "feat: add rewoo variable interpolation"
```

### Task 3: Execute a plan through ToolRuntime

**Files:**
- Modify: `vecna/orchestrator/rewoo.py`
- Modify: `tests/unit/test_tools_runtime.py`
- Modify: `tests/unit/test_rewoo_execution.py`

**Step 1: Write failing tests for step execution lifecycle**

Cover statuses `succeeded`, `failed`, policy-denied behavior, and result ordering.

**Step 2: Run tests**

Run: `pytest tests/unit/test_rewoo_execution.py tests/unit/test_tools_runtime.py -v`
Expected: FAIL.

**Step 3: Implement `execute_plan`**

Use ToolRuntime as the only execution pathway by emitting synthetic `<TOOL_CALL>` blocks.

**Step 4: Re-run tests**

Run same command.
Expected: PASS.

**Step 5: Commit**

```bash
git add vecna/orchestrator/rewoo.py tests/unit/test_rewoo_execution.py tests/unit/test_tools_runtime.py
git commit -m "feat: execute rewoo plans via tool runtime"
```

### Task 4: Add retry/backoff and circuit-break semantics

**Files:**
- Modify: `vecna/orchestrator/rewoo.py`
- Modify: `tests/unit/test_rewoo_execution.py`

**Step 1: Write failing tests for retry and stop conditions**

Include:
- runtime exception retried,
- denied step not retried,
- two consecutive failures stop remaining steps.

**Step 2: Run tests**

Run: `pytest tests/unit/test_rewoo_execution.py -v`
Expected: FAIL.

**Step 3: Implement retry + breaker policy**

Add deterministic linear backoff and per-failure-class policy.

**Step 4: Run tests**

Run: `pytest tests/unit/test_rewoo_execution.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add vecna/orchestrator/rewoo.py tests/unit/test_rewoo_execution.py
git commit -m "feat: add rewoo retry and circuit break behavior"
```

### Task 5: Add final synthesis path

**Files:**
- Modify: `vecna/orchestrator/rewoo.py`
- Modify: `tests/unit/test_rewoo_execution.py`

**Step 1: Write failing tests for synthesized answer quality contract**

Validate:
- includes successful artifacts,
- includes explicit failure notes,
- returns deterministic fallback when no successful steps.

**Step 2: Run tests**

Run: `pytest tests/unit/test_rewoo_execution.py -v`
Expected: FAIL.

**Step 3: Implement `synthesize_answer`**

Use adapter call if available; fallback to deterministic template summarizer.

**Step 4: Run tests**

Run same command.
Expected: PASS.

**Step 5: Commit**

```bash
git add vecna/orchestrator/rewoo.py tests/unit/test_rewoo_execution.py
git commit -m "feat: synthesize answers from rewoo artifacts"
```

### Task 6: Integrate ReWOO into HiveLoop

**Files:**
- Modify: `vecna/orchestrator/loop.py`
- Modify: `vecna/orchestrator/autonomy.py`
- Create: `tests/unit/test_rewoo_integration.py`

**Step 1: Write failing integration-ish unit tests**

Cover:
- feature flag off uses legacy path,
- feature flag on and eligible task uses ReWOO,
- fallback returns to legacy path on plan validation error.

**Step 2: Run tests**

Run: `pytest tests/unit/test_rewoo_integration.py -v`
Expected: FAIL.

**Step 3: Implement routing branch**

Initialize `RewooEngine` with existing `ToolRuntime`, adapter selection, and state.

**Step 4: Run tests**

Run same command.
Expected: PASS.

**Step 5: Commit**

```bash
git add vecna/orchestrator/loop.py vecna/orchestrator/autonomy.py tests/unit/test_rewoo_integration.py
git commit -m "feat: integrate rewoo execution path in hive loop"
```

### Task 7: Add config knobs and defaults

**Files:**
- Modify: `vecna/orchestrator/loop.py`
- Modify: `vecna/config/schema.py`
- Modify: `tests/unit/test_agent_mode_config.py`
- Modify: `tests/unit/test_config_tools.py`

**Step 1: Write failing tests for config fields/defaults**

**Step 2: Run tests**

Run: `pytest tests/unit/test_agent_mode_config.py tests/unit/test_config_tools.py -k rewoo -v`
Expected: FAIL.

**Step 3: Implement config options**

Add `enable_rewoo_planning`, `rewoo_max_steps`, `rewoo_retry_limit` with conservative defaults.

**Step 4: Run tests**

Run same command.
Expected: PASS.

**Step 5: Commit**

```bash
git add vecna/orchestrator/loop.py vecna/config/schema.py tests/unit/test_config_schema.py
git commit -m "chore: add rewoo planning configuration flags"
```

### Task 8: Add observability spans and metrics metadata

**Files:**
- Modify: `vecna/orchestrator/rewoo.py`
- Modify: `vecna/orchestrator/loop.py`
- Create: `tests/unit/test_rewoo_tracing.py`

**Step 1: Write failing tests for span metadata emission (mock trace contexts)**

**Step 2: Run tests**

Run: `pytest tests/unit/test_rewoo_tracing.py -v`
Expected: FAIL.

**Step 3: Implement spans**

Add spans with names:
- `rewoo.plan`
- `rewoo.execute_step`
- `rewoo.synthesize`

Metadata keys:
- `plan_steps`, `steps_succeeded`, `steps_failed`, `policy_denials`, `duration_ms`.

**Step 4: Run tests**

Run same command.
Expected: PASS.

**Step 5: Commit**

```bash
git add vecna/orchestrator/rewoo.py vecna/orchestrator/loop.py tests/unit/test_rewoo_tracing.py
git commit -m "chore: trace rewoo planning and execution spans"
```

### Task 9: End-to-end behavior tests and docs

**Files:**
- Create: `tests/e2e/test_rewoo_cli_flow.py`
- Modify: `docs/plans/2026-02-07-memory-identity-design.md` (status note only)
- Modify: `docs/overview/vecna-complete-technical-state.md` (status note only)

**Step 1: Write failing E2E test for a simple 2-step plan**

**Step 2: Run E2E test**

Run: `pytest tests/e2e/test_rewoo_cli_flow.py -v -m "not requires_copilot"`
Expected: FAIL.

**Step 3: Implement any glue gaps discovered by E2E**

**Step 4: Re-run E2E + targeted unit tests**

Run:
- `pytest tests/unit/test_rewoo_*.py -v`
- `pytest tests/e2e/test_rewoo_cli_flow.py -v -m "not requires_copilot"`

Expected: PASS.

**Step 5: Commit**

```bash
git add tests/e2e/test_rewoo_cli_flow.py docs/plans/2026-02-07-memory-identity-design.md docs/overview/vecna-complete-technical-state.md
git commit -m "test: cover rewoo cli flow and update status docs"
```

---

## 9. TDD Test Matrix

Unit (`tests/unit/`):
- `test_rewoo_parser.py`: schema parse/validation/reference checks.
- `test_rewoo_execution.py`: interpolation, runtime invocation, retry/breaker, synthesis fallback.
- `test_rewoo_integration.py`: HiveLoop routing and fallback behavior.
- `test_rewoo_tracing.py`: span names and metadata keys.

Integration (`tests/integration/`):
- `test_rewoo_with_pg_memory.py`: ensure retrieved memory context can be consumed in planner prompt and answer synthesis.
- Marker guidance: use `requires_postgres` only where DB required.

E2E (`tests/e2e/`):
- `test_rewoo_cli_flow.py`: CLI task triggers plan path, tool output is reflected in final answer.

Standard verification commands:
- `ruff check .`
- `ruff format --check .`
- `pytest -v -m "not requires_docker and not requires_copilot and not requires_langfuse"`

---

## 10. Performance and Failure Modes

Performance controls:
- cap steps by `rewoo_max_steps`.
- cap per-step retries with small deterministic backoff.
- avoid repeated planner calls; one planning call per task unless explicit replanning is added later.

Known failure modes and handling:
- Planner emits invalid syntax -> fallback to legacy `think` path.
- Tool denied by policy -> mark failure and continue or stop based on breaker.
- Tool output too large -> truncate artifact for synthesis with metadata marker.
- Adapter unavailable during synthesis -> deterministic synthesis fallback.

---

## 11. Acceptance Criteria

- ReWOO path can execute at least 3 sequential tool steps with `#E*` references.
- Policy-denied and approval-required actions are surfaced in final answer and trace metadata.
- Legacy behavior is unchanged when `enable_rewoo_planning=False`.
- New unit/integration/e2e tests pass in CI-safe marker configuration.
- Ruff lint/format checks pass.

---

## 12. Rollout Checklist

- Default feature flag remains off.
- Land behind config gate and document enablement.
- Dogfood with local adapters and mock tools first.
- Enable in non-production environments and observe trace metrics.
- Promote to broader usage after stable success/failure ratio.

---

## 13. Risks and Open Questions

Risks:
- Planner output variability across adapters can increase flaky behavior.
- Tool output shape mismatch may reduce synthesis quality.
- Over-eager eligibility heuristic could route simple tasks into unnecessary planning.

Open questions (to resolve during execution, not blockers for starting):
- Should planner and synthesizer always use same adapter, or allow separate cheaper synthesis adapter?
- Should policy-denied steps always stop execution, or only for critical tools?
- Should step artifacts be injected into `HiveState.memory_summary` immediately or only in final summary?

Design decisions locked for this plan:
- Keep storage unchanged (no queue DB migration in this item).
- Reuse ToolRuntime and policy path as-is.
- Keep deterministic retry/backoff rules for testability.
