# Agentic Tool Runtime + Sandbox Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a permissioned tool runtime with audit logging, hardened RLM sandbox, and a minimal task queue so Vecna can execute tools safely and repeatedly without manual prompting.

**Architecture:** Model responses are parsed for tool calls, validated against a registry and policy (allow/deny/ask), and executed by tool-specific executors. Results are injected back into the response and recorded in an audit log. The Python tool runs inside a hardened Docker sandbox with strict limits. A lightweight queue/scheduler persists pending tasks in `~/.vecna` and drives autonomous runs via CLI.

**Tech Stack:** Python 3.10+, Docker, Click CLI, JSONL logs in `~/.vecna`, optional Pg/Redis, pytest.

---

## Scope
- General tool registry + runtime (starting with Python execution tool)
- Permissioning policy (allow/deny/ask) + risk tiers
- Audit logging for tool decisions and execution
- Sandbox hardening to match `docs/guides/code-execution.md`
- Minimal task queue + scheduler CLI

## Non-goals (defer)
- Memory architecture upgrades (hybrid retrieval, memory files, compaction flush)
- Multi-agent/multi-process queue distribution
- Rich UI/approval flows beyond CLI prompts

## Success Metrics
- Tool calls are executed only when policy allows; denied/asked calls are logged
- Audit log records decision + execution outcome for every tool call
- Docker sandbox runs with network disabled and read-only root by default
- CLI can enqueue tasks and run a minimal scheduler loop

---

### Task 1: Tool type primitives + registry

**Files:**
- Create: `vecna/tools/types.py`
- Create: `vecna/tools/registry.py`
- Test: `tests/unit/test_tools_types.py`
- Test: `tests/unit/test_tools_registry.py`

**Step 1: Write the failing tests**

```python
# tests/unit/test_tools_types.py
from vecna.tools.types import ToolSpec, ToolCall, ToolResult, ToolExecutionContext

def test_tool_spec_defaults():
    spec = ToolSpec(name="python_exec", description="Run python", input_schema={"code": "string"})
    assert spec.name == "python_exec"
    assert spec.output_schema is None
    assert spec.tags == []

def test_tool_call_round_trip():
    call = ToolCall(tool_name="python_exec", arguments={"code": "print(1)"}, raw_text="x")
    assert call.tool_name == "python_exec"
    assert call.arguments["code"] == "print(1)"

# tests/unit/test_tools_registry.py
from vecna.tools.registry import ToolRegistry
from vecna.tools.types import ToolSpec

def test_registry_register_and_get():
    registry = ToolRegistry()
    spec = ToolSpec(name="python_exec", description="Run python", input_schema={"code": "string"})
    registry.register(spec, executor=lambda args, ctx: None)
    assert registry.get("python_exec").spec.name == "python_exec"

def test_registry_list_tools():
    registry = ToolRegistry()
    spec = ToolSpec(name="python_exec", description="Run python", input_schema={"code": "string"})
    registry.register(spec, executor=lambda args, ctx: None)
    assert "python_exec" in [t.name for t in registry.list_tools()]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_tools_types.py::test_tool_spec_defaults -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vecna.tools.types'`

**Step 3: Write minimal implementation**

```python
# vecna/tools/types.py
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Optional[Dict[str, Any]] = None
    tags: list[str] = field(default_factory=list)

@dataclass
class ToolCall:
    tool_name: str
    arguments: Dict[str, Any]
    raw_text: str
    start_pos: int = 0
    end_pos: int = 0

@dataclass
class ToolResult:
    tool_name: str
    success: bool
    output: str
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ToolExecutionContext:
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    request_id: Optional[str] = None
    domain: Optional[str] = None
```

```python
# vecna/tools/registry.py
from dataclasses import dataclass
from typing import Callable, Dict, List, Awaitable, Union
from vecna.tools.types import ToolSpec, ToolExecutionContext, ToolResult

ToolExecutor = Callable[[dict, ToolExecutionContext], Union[ToolResult, Awaitable[ToolResult]]]

@dataclass
class RegisteredTool:
    spec: ToolSpec
    executor: ToolExecutor

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, RegisteredTool] = {}

    def register(self, spec: ToolSpec, executor: ToolExecutor) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._tools[spec.name] = RegisteredTool(spec=spec, executor=executor)

    def get(self, name: str) -> RegisteredTool:
        return self._tools[name]

    def list_tools(self) -> List[ToolSpec]:
        return [rt.spec for rt in self._tools.values()]
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_tools_types.py tests/unit/test_tools_registry.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/tools/types.py vecna/tools/registry.py tests/unit/test_tools_types.py tests/unit/test_tools_registry.py
git commit -m "feat: add tool types and registry"
```

---

### Task 2: Tool call parser + formatting

**Files:**
- Create: `vecna/tools/parser.py`
- Test: `tests/unit/test_tools_parser.py`

**Step 1: Write the failing tests**

```python
from vecna.tools.parser import parse_tool_calls

def test_parse_tool_call_block():
    text = "hello <TOOL_CALL>{\"name\":\"python_exec\",\"args\":{\"code\":\"print(1)\"}}</TOOL_CALL>"
    calls = parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].tool_name == "python_exec"

def test_parse_python_code_block_as_tool_call():
    text = "```python\nprint(1)\n```"
    calls = parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].tool_name == "python_exec"
    assert "print(1)" in calls[0].arguments["code"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_tools_parser.py::test_parse_tool_call_block -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vecna.tools.parser'`

**Step 3: Write minimal implementation**

```python
# vecna/tools/parser.py
import json
import re
from typing import List
from vecna.tools.types import ToolCall
from vecna.tools.code_executor import detect_code_blocks

_TOOL_CALL_RE = re.compile(r"<TOOL_CALL>(.*?)</TOOL_CALL>", re.DOTALL | re.IGNORECASE)

def parse_tool_calls(text: str) -> List[ToolCall]:
    calls: List[ToolCall] = []

    for match in _TOOL_CALL_RE.finditer(text):
        raw = match.group(1).strip()
        try:
            payload = json.loads(raw)
            tool_name = payload.get("name")
            args = payload.get("args", {})
            if tool_name:
                calls.append(
                    ToolCall(
                        tool_name=tool_name,
                        arguments=args,
                        raw_text=match.group(0),
                        start_pos=match.start(),
                        end_pos=match.end(),
                    )
                )
        except json.JSONDecodeError:
            continue

    # Fallback: treat python code blocks as implicit python_exec tool calls
    for block in detect_code_blocks(text):
        calls.append(
            ToolCall(
                tool_name="python_exec",
                arguments={"code": block.code},
                raw_text=block.original_text,
                start_pos=block.start_pos,
                end_pos=block.end_pos,
            )
        )

    return calls
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_tools_parser.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/tools/parser.py tests/unit/test_tools_parser.py
git commit -m "feat: add tool call parser"
```

---

### Task 3: Permission policy + risk assessment

**Files:**
- Create: `vecna/tools/permissions.py`
- Test: `tests/unit/test_tools_permissions.py`

**Step 1: Write the failing tests**

```python
from vecna.tools.permissions import RiskTier, ToolPolicy, ToolPermissionManager, assess_code_risk

def test_policy_allowlist_wins():
    policy = ToolPolicy(allowlist=["python_exec"], denylist=["python_exec"], default_action="deny")
    mgr = ToolPermissionManager(policy)
    decision = mgr.decide("python_exec", risk=RiskTier.LOW)
    assert decision.action == "allow"

def test_assess_code_risk_high_for_subprocess():
    code = "import subprocess\nsubprocess.run(['ls'])"
    assert assess_code_risk(code) in (RiskTier.HIGH, RiskTier.CRITICAL)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_tools_permissions.py::test_policy_allowlist_wins -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vecna.tools.permissions'`

**Step 3: Write minimal implementation**

```python
# vecna/tools/permissions.py
import ast
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List

class RiskTier(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class PolicyDecision:
    action: str  # allow | deny | ask
    reason: str

@dataclass
class ToolPolicy:
    default_action: str = "deny"
    allowlist: List[str] = field(default_factory=list)
    denylist: List[str] = field(default_factory=list)
    risk_actions: Dict[RiskTier, str] = field(
        default_factory=lambda: {
            RiskTier.LOW: "allow",
            RiskTier.MEDIUM: "ask",
            RiskTier.HIGH: "deny",
            RiskTier.CRITICAL: "deny",
        }
    )

class ToolPermissionManager:
    def __init__(self, policy: ToolPolicy):
        self.policy = policy

    def decide(self, tool_name: str, risk: RiskTier) -> PolicyDecision:
        if tool_name in self.policy.allowlist:
            return PolicyDecision("allow", "allowlist")
        if tool_name in self.policy.denylist:
            return PolicyDecision("deny", "denylist")
        action = self.policy.risk_actions.get(risk, self.policy.default_action)
        return PolicyDecision(action, f"risk:{risk.value}")

def assess_code_risk(code: str) -> RiskTier:
    risky_imports = {"subprocess", "os", "socket", "requests", "urllib"}
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return RiskTier.MEDIUM

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in risky_imports:
                    return RiskTier.HIGH
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in risky_imports:
                return RiskTier.HIGH
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"system", "popen", "run"}:
                return RiskTier.HIGH
    return RiskTier.LOW
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_tools_permissions.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/tools/permissions.py tests/unit/test_tools_permissions.py
git commit -m "feat: add tool permission policy and risk assessment"
```

---

### Task 4: Audit log + approval store

**Files:**
- Create: `vecna/tools/audit.py`
- Create: `vecna/tools/approvals.py`
- Test: `tests/unit/test_tools_audit.py`

**Step 1: Write the failing tests**

```python
from pathlib import Path
from vecna.tools.audit import ToolAuditEvent, ToolAuditLogger
from vecna.tools.approvals import ApprovalStore, ApprovalRequest

def test_audit_logger_writes_event(tmp_path: Path):
    log_path = tmp_path / "audit.jsonl"
    logger = ToolAuditLogger(log_path=log_path)
    event = ToolAuditEvent(tool_name="python_exec", action="allow", risk_tier="low")
    logger.log_event(event)
    assert log_path.read_text().strip().startswith("{")

def test_approval_store_round_trip(tmp_path: Path):
    store = ApprovalStore(path=tmp_path / "approvals.jsonl")
    req = store.request_approval(tool_name="python_exec", args={"code": "print(1)"})
    pending = store.get_pending()
    assert pending[0].request_id == req.request_id
    store.update_status(req.request_id, "approved")
    assert store.get_pending() == []
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_tools_audit.py::test_audit_logger_writes_event -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vecna.tools.audit'`

**Step 3: Write minimal implementation**

```python
# vecna/tools/audit.py
import json
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path

@dataclass
class ToolAuditEvent:
    tool_name: str
    action: str  # allow | deny | ask
    risk_tier: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    reason: str = ""
    success: bool = False
    error: str = ""

class ToolAuditLogger:
    def __init__(self, log_path: Path = None):
        self.log_path = log_path or (Path.home() / ".vecna" / "tool_audit.jsonl")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log_event(self, event: ToolAuditEvent) -> None:
        with open(self.log_path, "a") as f:
            f.write(json.dumps(asdict(event)) + "\n")
```

```python
# vecna/tools/approvals.py
import json
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

@dataclass
class ApprovalRequest:
    request_id: str
    tool_name: str
    args: Dict[str, Any]
    status: str = "pending"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

class ApprovalStore:
    def __init__(self, path: Path = None):
        self.path = path or (Path.home() / ".vecna" / "tool_approvals.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def request_approval(self, tool_name: str, args: Dict[str, Any]) -> ApprovalRequest:
        req = ApprovalRequest(request_id=str(uuid.uuid4()), tool_name=tool_name, args=args)
        with open(self.path, "a") as f:
            f.write(json.dumps(asdict(req)) + "\n")
        return req

    def get_pending(self) -> List[ApprovalRequest]:
        if not self.path.exists():
            return []
        pending: List[ApprovalRequest] = []
        for line in self.path.read_text().splitlines():
            data = json.loads(line)
            if data.get("status") == "pending":
                pending.append(ApprovalRequest(**data))
        return pending

    def update_status(self, request_id: str, status: str) -> bool:
        if not self.path.exists():
            return False
        updated = False
        entries = []
        for line in self.path.read_text().splitlines():
            data = json.loads(line)
            if data.get("request_id") == request_id:
                data["status"] = status
                updated = True
            entries.append(data)
        self.path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
        return updated
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_tools_audit.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/tools/audit.py vecna/tools/approvals.py tests/unit/test_tools_audit.py
git commit -m "feat: add tool audit log and approval store"
```

---

### Task 5: Tool runtime orchestration

**Files:**
- Create: `vecna/tools/runtime.py`
- Modify: `vecna/tools/parser.py`
- Test: `tests/unit/test_tools_runtime.py`

**Step 1: Write the failing tests**

```python
import pytest
from vecna.tools.runtime import ToolRuntime
from vecna.tools.registry import ToolRegistry
from vecna.tools.types import ToolSpec, ToolResult, ToolExecutionContext
from vecna.tools.permissions import ToolPolicy, ToolPermissionManager, RiskTier

@pytest.mark.asyncio
async def test_runtime_executes_allowed_tool():
    registry = ToolRegistry()
    spec = ToolSpec(name="echo", description="echo", input_schema={"text": "string"})
    registry.register(spec, executor=lambda args, ctx: ToolResult("echo", True, args["text"]))
    runtime = ToolRuntime(registry=registry, permission_manager=ToolPermissionManager(ToolPolicy()))

    text = "<TOOL_CALL>{\"name\":\"echo\",\"args\":{\"text\":\"hi\"}}</TOOL_CALL>"
    modified, results = await runtime.execute_calls(text, ToolExecutionContext())
    assert results[0].output == "hi"

@pytest.mark.asyncio
async def test_runtime_denies_tool():
    registry = ToolRegistry()
    spec = ToolSpec(name="echo", description="echo", input_schema={"text": "string"})
    registry.register(spec, executor=lambda args, ctx: ToolResult("echo", True, args["text"]))
    policy = ToolPolicy(default_action="deny")
    runtime = ToolRuntime(registry=registry, permission_manager=ToolPermissionManager(policy))

    text = "<TOOL_CALL>{\"name\":\"echo\",\"args\":{\"text\":\"hi\"}}</TOOL_CALL>"
    modified, results = await runtime.execute_calls(text, ToolExecutionContext())
    assert results[0].success is False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_tools_runtime.py::test_runtime_executes_allowed_tool -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vecna.tools.runtime'`

**Step 3: Write minimal implementation**

```python
# vecna/tools/runtime.py
import inspect
from dataclasses import dataclass
from typing import List, Tuple
from vecna.tools.parser import parse_tool_calls
from vecna.tools.registry import ToolRegistry
from vecna.tools.permissions import ToolPermissionManager, RiskTier, assess_code_risk
from vecna.tools.types import ToolExecutionContext, ToolResult
from vecna.tools.audit import ToolAuditLogger, ToolAuditEvent
from vecna.tools.approvals import ApprovalStore

@dataclass
class RuntimeConfig:
    auto_execute_tools: bool = True

def format_tool_result(call, result: ToolResult) -> str:
    status = "success" if result.success else "error"
    body = result.output if result.success else (result.error or "unknown error")
    return (
        f"{call.raw_text}\n\n<TOOL_RESULT name=\"{call.tool_name}\" status=\"{status}\">\n"
        f"{body}\n</TOOL_RESULT>"
    )

class ToolRuntime:
    def __init__(
        self,
        registry: ToolRegistry,
        permission_manager: ToolPermissionManager,
        audit_logger: ToolAuditLogger = None,
        approval_store: ApprovalStore = None,
        config: RuntimeConfig = None,
    ):
        self.registry = registry
        self.permission_manager = permission_manager
        self.audit_logger = audit_logger or ToolAuditLogger()
        self.approval_store = approval_store or ApprovalStore()
        self.config = config or RuntimeConfig()

    async def execute_calls(
        self, text: str, context: ToolExecutionContext
    ) -> Tuple[str, List[ToolResult]]:
        if not self.config.auto_execute_tools:
            return text, []

        calls = parse_tool_calls(text)
        if not calls:
            return text, []

        results: List[ToolResult] = []
        modified = text

        for call in reversed(calls):
            try:
                registered = self.registry.get(call.tool_name)
            except KeyError:
                result = ToolResult(call.tool_name, False, "", error="unknown tool")
                decision_action = "deny"
                risk = RiskTier.LOW
            else:
                risk = (
                    assess_code_risk(call.arguments.get("code", ""))
                    if call.tool_name == "python_exec"
                    else RiskTier.LOW
                )
                decision = self.permission_manager.decide(call.tool_name, risk=risk)
                decision_action = decision.action

                if decision.action == "ask":
                    req = self.approval_store.request_approval(call.tool_name, call.arguments)
                    result = ToolResult(
                        call.tool_name,
                        False,
                        "",
                        error=f"approval required: {req.request_id}",
                    )
                elif decision.action == "deny":
                    result = ToolResult(call.tool_name, False, "", error="denied by policy")
                else:
                    maybe_result = registered.executor(call.arguments, context)
                    result = await maybe_result if inspect.isawaitable(maybe_result) else maybe_result

            self.audit_logger.log_event(
                ToolAuditEvent(
                    tool_name=call.tool_name,
                    action=decision_action,
                    risk_tier=risk.value,
                    success=result.success,
                    error=result.error or "",
                )
            )
            results.append(result)

            replacement = format_tool_result(call, result)
            modified = modified[: call.start_pos] + replacement + modified[call.end_pos :]

        return modified, list(reversed(results))
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_tools_runtime.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/tools/runtime.py tests/unit/test_tools_runtime.py vecna/tools/parser.py
git commit -m "feat: add tool runtime orchestration"
```

---

### Task 6: Python executor tool wrapper + default registry

**Files:**
- Modify: `vecna/tools/code_executor.py`
- Modify: `vecna/tools/registry.py`
- Test: `tests/unit/test_code_executor_tool.py`

**Step 1: Write the failing tests**

```python
import pytest
from vecna.tools.code_executor import execute_code_tool
from vecna.tools.types import ToolExecutionContext

@pytest.mark.asyncio
async def test_execute_code_tool_wraps_executor(monkeypatch):
    class Dummy:
        success = True
        stdout = "ok"
        stderr = ""
        return_code = 0
        execution_time_ms = 1.0
        packages_installed = []

    async def fake_execute(code):
        return Dummy()

    monkeypatch.setattr("vecna.tools.code_executor.execute_code_block", fake_execute)
    result = await execute_code_tool({"code": "print(1)"}, ToolExecutionContext())
    assert result.success is True
    assert result.output == "ok"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_code_executor_tool.py::test_execute_code_tool_wraps_executor -v`
Expected: FAIL with `ImportError: cannot import name 'execute_code_tool'`

**Step 3: Write minimal implementation**

```python
# vecna/tools/code_executor.py
from vecna.tools.types import ToolResult, ToolExecutionContext

async def execute_code_tool(args: dict, context: ToolExecutionContext) -> ToolResult:
    code = args.get("code", "")
    result = await execute_code_block(code)
    return ToolResult(
        tool_name="python_exec",
        success=result.success,
        output=result.stdout,
        error=result.stderr,
        metadata={
            "return_code": result.return_code,
            "execution_time_ms": result.execution_time_ms,
            "packages_installed": result.packages_installed,
        },
    )
```

```python
# vecna/tools/registry.py
from vecna.tools.code_executor import execute_code_tool
from vecna.tools.types import ToolSpec

def get_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="python_exec",
            description="Execute Python in the RLM sandbox",
            input_schema={"code": "string"},
        ),
        executor=execute_code_tool,
    )
    return registry
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_code_executor_tool.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/tools/code_executor.py vecna/tools/registry.py tests/unit/test_code_executor_tool.py
git commit -m "feat: wrap python executor as tool"
```

---

### Task 7: HiveLoop integration + tool prompt context

**Files:**
- Modify: `vecna/orchestrator/loop.py`
- Modify: `vecna/adapters/base.py`
- Test: `tests/unit/test_adapters.py`

**Step 1: Write the failing tests**

```python
# tests/unit/test_adapters.py
from vecna.adapters.base import HIVE_IDENTITY_PROMPT, BaseAdapter, ModelConfig
from vecna.core.hive_state import HiveState

def test_prompt_includes_tool_instructions():
    assert "TOOL_CALL" in HIVE_IDENTITY_PROMPT
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_adapters.py::test_prompt_includes_tool_instructions -v`
Expected: FAIL with assertion error

**Step 3: Write minimal implementation**

```python
# vecna/adapters/base.py (append to HIVE_IDENTITY_PROMPT)
## TOOL CALLS
If you need to use a tool, emit a tool call block in this exact format:
<TOOL_CALL>{"name":"tool_name","args":{...}}</TOOL_CALL>
Only call tools that are listed under AVAILABLE TOOLS in memory context.
```

```python
# vecna/orchestrator/loop.py (HiveLoop.__init__)
from vecna.tools.registry import get_default_registry
from vecna.tools.permissions import ToolPermissionManager, ToolPolicy
from vecna.tools.runtime import ToolRuntime, RuntimeConfig

self.tool_registry = get_default_registry()
self.tool_permissions = ToolPermissionManager(self.config.tool_policy)
self.tool_runtime = ToolRuntime(
    registry=self.tool_registry,
    permission_manager=self.tool_permissions,
    config=RuntimeConfig(auto_execute_tools=self.config.auto_execute_tools),
)
```

```python
# vecna/orchestrator/loop.py (inside _run_cycle, after memory_context/identity)
tool_context = ""
if getattr(self, "tool_registry", None):
    tool_names = [t.name for t in self.tool_registry.list_tools()]
    tool_context = "AVAILABLE TOOLS: " + ", ".join(tool_names)
if tool_context:
    augmented_summary = f"{augmented_summary}\n\n{tool_context}"
```

```python
# vecna/orchestrator/loop.py (inside think, replacing execute_and_inject block)
session_id = str(uuid.uuid4())
with trace_request(..., session_id=session_id, ...) as trace_ctx:
    ...
    if self.config.auto_execute_tools and self.tool_runtime:
        final_response, tool_results = await self.tool_runtime.execute_calls(
            final_response, ToolExecutionContext(session_id=session_id)
        )
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_adapters.py::test_prompt_includes_tool_instructions -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/adapters/base.py vecna/orchestrator/loop.py tests/unit/test_adapters.py
git commit -m "feat: add tool call prompt and context"
```

---

### Task 8: Config surface for tools + runtime

**Files:**
- Modify: `vecna/config/schema.py`
- Modify: `vecna/config/loader.py`
- Modify: `vecna/cli/main.py`
- Modify: `vecna/orchestrator/loop.py`
- Test: `tests/unit/test_config_tools.py`

**Step 1: Write the failing tests**

```python
from vecna.config.schema import VecnaConfig

def test_config_has_tool_policy_defaults():
    cfg = VecnaConfig()
    assert hasattr(cfg, "tool_policy")
    assert cfg.tool_policy.default_action in ("allow", "deny")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_config_tools.py::test_config_has_tool_policy_defaults -v`
Expected: FAIL with `AttributeError: 'VecnaConfig' object has no attribute 'tool_policy'`

**Step 3: Write minimal implementation**

```python
# vecna/config/schema.py
@dataclass
class ToolPolicyConfig:
    default_action: str = "deny"
    allowlist: list[str] = field(default_factory=list)
    denylist: list[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "default_action": self.default_action,
            "allowlist": self.allowlist,
            "denylist": self.denylist,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolPolicyConfig":
        return cls(
            default_action=data.get("default_action", "deny"),
            allowlist=data.get("allowlist", []),
            denylist=data.get("denylist", []),
        )

@dataclass
class VecnaConfig:
    # ... existing fields ...
    auto_execute_tools: bool = True
    tool_policy: ToolPolicyConfig = field(default_factory=ToolPolicyConfig)

    def to_dict(self) -> Dict[str, Any]:
        return {
            # ... existing fields ...
            "auto_execute_tools": self.auto_execute_tools,
            "tool_policy": self.tool_policy.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VecnaConfig":
        tool_policy = ToolPolicyConfig.from_dict(data.get("tool_policy", {}))
        return cls(
            # ... existing fields ...
            auto_execute_tools=data.get("auto_execute_tools", True),
            tool_policy=tool_policy,
        )
```

```python
# vecna/cli/main.py (get_hive)
from vecna.tools.permissions import ToolPolicy

tool_policy = ToolPolicy(
    default_action=vecna_config.tool_policy.default_action,
    allowlist=vecna_config.tool_policy.allowlist,
    denylist=vecna_config.tool_policy.denylist,
)

hive_config = HiveConfig(
    # ... existing fields ...
    auto_execute_tools=vecna_config.auto_execute_tools,
    tool_policy=tool_policy,
)
```

```python
# vecna/orchestrator/loop.py (HiveConfig)
from vecna.tools.permissions import ToolPolicy

@dataclass
class HiveConfig:
    # ... existing fields ...
    auto_execute_tools: bool = True
    tool_policy: ToolPolicy = field(default_factory=ToolPolicy)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_config_tools.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/config/schema.py vecna/cli/main.py vecna/orchestrator/loop.py tests/unit/test_config_tools.py
git commit -m "feat: add tool policy config"
```

---

### Task 9: RLM sandbox hardening

**Files:**
- Modify: `vecna/memory/rlm_bridge.py`
- Modify: `vecna/tools/code_executor.py`
- Test: `tests/unit/test_rlm_bridge_security.py`

**Step 1: Write the failing tests**

```python
from vecna.memory.rlm_bridge import RLMConfig, RLMBridge

def test_rlm_builds_secure_docker_cmd():
    bridge = RLMBridge(RLMConfig())
    cmd = bridge._build_docker_run_cmd("vecna-rlm-test")
    assert "--network" in cmd and "none" in cmd
    assert "--read-only" in cmd
    assert "--security-opt" in cmd
    assert "--cap-drop" in cmd
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_rlm_bridge_security.py::test_rlm_builds_secure_docker_cmd -v`
Expected: FAIL with `AttributeError: 'RLMBridge' object has no attribute '_build_docker_run_cmd'`

**Step 3: Write minimal implementation**

```python
# vecna/memory/rlm_bridge.py
@dataclass
class RLMConfig:
    image: str = "python:3.11-slim"
    container_prefix: str = "vecna-rlm"
    timeout: int = 30
    max_recursion: int = 3
    memory_limit: str = "512m"
    cpu_limit: float = 1.0
    network_enabled: bool = False
    read_only: bool = True
    no_new_privileges: bool = True
    cap_drop_all: bool = True
    pids_limit: int = 256
    tmpfs_size: str = "64m"

def _build_docker_run_cmd(self, container_name: str) -> list[str]:
    cmd = ["docker", "run", "-d", "--name", container_name, "--memory", self.config.memory_limit]
    if self.config.cpu_limit:
        cmd.extend(["--cpus", str(self.config.cpu_limit)])
    if not self.config.network_enabled:
        cmd.extend(["--network", "none"])
    if self.config.read_only:
        cmd.append("--read-only")
        cmd.extend(["--tmpfs", f"/tmp:rw,size={self.config.tmpfs_size}"])
        cmd.extend(["--tmpfs", f"/root/.cache:rw,size={self.config.tmpfs_size}"])
    if self.config.no_new_privileges:
        cmd.extend(["--security-opt", "no-new-privileges"])
    if self.config.cap_drop_all:
        cmd.extend(["--cap-drop", "ALL"])
    if self.config.pids_limit:
        cmd.extend(["--pids-limit", str(self.config.pids_limit)])
    return cmd
```

Use `_build_docker_run_cmd` inside `prewarm()` to construct the `docker run` arguments so all security flags apply consistently.

```python
# vecna/memory/rlm_bridge.py (install_packages + execute_code)
if not self.config.network_enabled and packages:
    return False, "Network disabled; package install not allowed"

cmd = ["docker", "exec", self._container_id, "pip", "install", "--quiet", "--target", "/tmp/rlm-packages", *packages]

# ensure python can import /tmp/rlm-packages
exec_cmd = ["docker", "exec", "-e", "PYTHONPATH=/tmp/rlm-packages", self._container_id, "python", "-c", code]
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_rlm_bridge_security.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/memory/rlm_bridge.py tests/unit/test_rlm_bridge_security.py
git commit -m "feat: harden rlm docker sandbox"
```

---

### Task 10: Tools CLI + approval handling

**Files:**
- Modify: `vecna/cli/main.py`
- Modify: `vecna/tools/approvals.py`
- Test: `tests/e2e/test_cli_commands.py`

**Step 1: Write the failing tests**

```python
# tests/e2e/test_cli_commands.py
def test_tools_help(self, runner):
    result = runner.invoke(cli, ["tools", "--help"])
    assert result.exit_code == 0
    assert "tools" in result.output.lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/e2e/test_cli_commands.py::TestHelp::test_tools_help -v`
Expected: FAIL with "No such command 'tools'"

**Step 3: Write minimal implementation**

```python
# vecna/cli/main.py
@cli.group()
def tools():
    """Tool approvals and audit logs."""

@tools.command("pending")
def tools_pending():
    store = ApprovalStore()
    for req in store.get_pending():
        console.print(f"{req.request_id} {req.tool_name}")

@tools.command("approve")
@click.argument("request_id")
def tools_approve(request_id: str):
    store = ApprovalStore()
    store.update_status(request_id, "approved")

@tools.command("deny")
@click.argument("request_id")
def tools_deny(request_id: str):
    store = ApprovalStore()
    store.update_status(request_id, "denied")
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/e2e/test_cli_commands.py::TestHelp::test_tools_help -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/cli/main.py vecna/tools/approvals.py tests/e2e/test_cli_commands.py
git commit -m "feat: add tools CLI for approvals"
```

---

### Task 11: Task queue + scheduler CLI

**Files:**
- Create: `vecna/orchestrator/task_queue.py`
- Create: `vecna/orchestrator/scheduler.py`
- Modify: `vecna/cli/main.py`
- Test: `tests/unit/test_task_queue.py`
- Test: `tests/e2e/test_cli_commands.py`

**Step 1: Write the failing tests**

```python
from vecna.orchestrator.task_queue import TaskQueue

def test_queue_fifo(tmp_path):
    queue = TaskQueue(path=tmp_path / "queue.json")
    queue.enqueue("task-1")
    queue.enqueue("task-2")
    assert queue.dequeue() == "task-1"

# tests/e2e/test_cli_commands.py
def test_queue_help(self, runner):
    result = runner.invoke(cli, ["queue", "--help"])
    assert result.exit_code == 0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_task_queue.py::test_queue_fifo -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vecna.orchestrator.task_queue'`

**Step 3: Write minimal implementation**

```python
# vecna/orchestrator/task_queue.py
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

@dataclass
class TaskQueue:
    path: Path
    tasks: List[str] = field(default_factory=list)

    def _load(self):
        if self.path.exists():
            self.tasks = json.loads(self.path.read_text()).get("tasks", [])

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"tasks": self.tasks}))

    def enqueue(self, task: str) -> None:
        self._load()
        self.tasks.append(task)
        self._save()

    def dequeue(self) -> Optional[str]:
        self._load()
        if not self.tasks:
            return None
        task = self.tasks.pop(0)
        self._save()
        return task

    def size(self) -> int:
        self._load()
        return len(self.tasks)
```

```python
# vecna/orchestrator/scheduler.py
import asyncio
from vecna.orchestrator.task_queue import TaskQueue

class TaskScheduler:
    def __init__(self, hive, queue: TaskQueue):
        self.hive = hive
        self.queue = queue

    async def run_once(self):
        task = self.queue.dequeue()
        if task:
            await self.hive.think(task)

    async def run_loop(self, interval_s: int = 2):
        while True:
            await self.run_once()
            await asyncio.sleep(interval_s)
```

```python
# vecna/cli/main.py
@cli.group()
def queue():
    """Queue and run autonomous tasks."""

@queue.command("add")
@click.argument("task")
def queue_add(task: str):
    q = TaskQueue(path=Path.home() / ".vecna" / "queue.json")
    q.enqueue(task)

@queue.command("run")
@click.option("--interval", default=2, show_default=True)
def queue_run(interval: int):
    hive = get_hive()
    scheduler = TaskScheduler(hive, TaskQueue(path=Path.home() / ".vecna" / "queue.json"))
    asyncio.run(scheduler.run_loop(interval))

@queue.command("status")
def queue_status():
    q = TaskQueue(path=Path.home() / ".vecna" / "queue.json")
    console.print(f"pending: {q.size()}")
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_task_queue.py tests/e2e/test_cli_commands.py::TestHelp::test_queue_help -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vecna/orchestrator/task_queue.py vecna/orchestrator/scheduler.py vecna/cli/main.py tests/unit/test_task_queue.py tests/e2e/test_cli_commands.py
git commit -m "feat: add task queue and scheduler"
```

---

### Task 12: Docs updates

**Files:**
- Modify: `docs/guides/code-execution.md`
- Create: `docs/guides/tools.md`
- Modify: `docs/guides/cli.md`
- Modify: `docs/index.md`

**Step 1: Write the failing doc checks (manual)**

Add a checklist entry in the PR description instead of tests.

**Step 2: Update docs**

- Document tool call format and policy in `docs/guides/tools.md`
- Update code execution guide with new sandbox defaults
- Add CLI usage for queue and tools
- Link tools guide from `docs/index.md`

**Step 3: Commit**

```bash
git add docs/guides/code-execution.md docs/guides/tools.md docs/guides/cli.md docs/index.md
git commit -m "docs: add tool runtime and scheduler guides"
```

---

## Execution Notes
- Keep `execute_and_inject` available for backward compatibility, but skip it when ToolRuntime runs to avoid double execution.
- Use `RiskTier` only as a heuristic; keep it simple in v1.
- For `ask` decisions, log the approval request and emit a user-visible message with the request id.
- If Docker is unavailable, ToolRuntime should surface a clean error message and log a denied audit event.
- If config lacks `auto_execute_tools`, fall back to `auto_execute_code` during config load.
- In the parser, de-duplicate tool calls; prefer explicit `<TOOL_CALL>` blocks over implicit code blocks that overlap.

---

## Future Plans (Post‑Milestone)
- Memory architecture v2: workspace Markdown memory, memory_search/memory_get tools, hybrid vector+BM25 retrieval, compaction memory flush, and session hooks.
- Agentic expansion: tool catalog beyond Python (HTTP, filesystem, web, calendar/email), tool capability metadata, quotas/budgeting, and planner/executor loops.
- Autonomy upgrades: persistent goals, background cycles with backoff, failure recovery, and kill‑switch controls.
- Observability/eval: tool audit dashboards, Langfuse trace enrichment, safety regression tests, and red‑team suites.
- Security hardening: stricter seccomp profiles, container cleanup + TTL, secret/PII redaction in logs.
- UX polish: approvals UX, queue status views, and safer “ask/approve/deny” workflows.
