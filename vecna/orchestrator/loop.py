"""
HiveLoop: The main orchestration loop for the hive mind.

This is where the magic happens — the continuous cycle of:
1. Read shared state
2. All models think in parallel
3. Merge updates via consensus
4. Compress and update state
5. Repeat

The result: a single unified mind emerging from many.
"""

import asyncio
from typing import List, Dict, Optional, Callable, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
import logging
import os

from vecna.config.schema import AgentMode
from vecna.core.hive_state import HiveState
from vecna.core.types import HiveUpdate, Goal
from vecna.adapters.base import BaseAdapter, ModelConfig, create_adapter
from vecna.memory.store import MemoryStore, MemoryCompressor
from vecna.memory.flush import FlushManager, estimate_token_count, should_flush
from vecna.memory.mirror import MemoryMirror
from vecna.memory.session import SessionManager
from vecna.orchestrator.consensus import ConsensusEngine, ConsensusConfig, DomainRouter
from vecna.orchestrator.rewoo import RewooEngine, RewooEngineConfig, RewooExecutionResult
from vecna.orchestrator.self_reflection import reflect, get_identity_context_for_prompt
from vecna.tools.code_executor import execute_and_inject
from vecna.tools.registry import get_default_registry
from vecna.tools.permissions import ToolPermissionManager, ToolPolicy
from vecna.tools.runtime import ToolRuntime, RuntimeConfig
from vecna.tools.quotas import QuotaConfig, ToolQuotaManager
from vecna.tools.types import ToolExecutionContext


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vecna.hive")


# ============================================================
# CIRCUIT BREAKER — Per-adapter fault isolation (Amendment 13)
# ============================================================


@dataclass
class CircuitBreaker:
    """
    Per-adapter circuit breaker with exponential backoff.

    After ``max_failures`` consecutive failures the breaker *opens* and the
    adapter is skipped for an exponentially increasing cooldown period
    (base_cooldown * 2^(failures - max_failures), capped at max_cooldown).

    A single success resets the breaker to closed state.
    """

    adapter_name: str
    failure_count: int = 0
    max_failures: int = 3
    cooldown_until: Optional[datetime] = None
    base_cooldown: float = 30.0  # seconds
    max_cooldown: float = 300.0  # seconds

    def record_failure(self) -> None:
        """Record a failed call. Opens the breaker after max_failures."""
        self.failure_count += 1
        if self.failure_count >= self.max_failures:
            cooldown = min(
                self.base_cooldown * (2 ** (self.failure_count - self.max_failures)),
                self.max_cooldown,
            )
            self.cooldown_until = datetime.now() + timedelta(seconds=cooldown)
            logger.warning(
                "Circuit breaker OPEN for %s — skipping for %.0fs",
                self.adapter_name,
                cooldown,
            )

    def record_success(self) -> None:
        """Record a successful call. Resets the breaker to closed state."""
        self.failure_count = 0
        self.cooldown_until = None

    def is_open(self) -> bool:
        """Return True if the breaker is open (adapter should be skipped)."""
        if self.cooldown_until is None:
            return False
        if datetime.now() >= self.cooldown_until:
            # Half-open: cooldown expired, allow a retry
            self.cooldown_until = None
            return False
        return True


# ============================================================
# RESPONSE SELECTION — Primary Cortex hierarchy
# ============================================================


def select_best_response(
    responses: Dict[str, str],
    primary_name: str,
) -> str:
    """
    Select the best response from multiple model outputs.

    Strategy: the Primary Cortex response wins unless it is absent or
    empty. This replaces the old ``max(responses, key=len)`` approach.

    Args:
        responses: Mapping of adapter name -> response text.
        primary_name: Name of the primary cortex adapter.

    Returns:
        The selected response string (may be empty if all responses are empty).
    """
    if not responses:
        return ""

    # Primary cortex response is the default winner
    if primary_name in responses and responses[primary_name].strip():
        return responses[primary_name]

    # Fallback: pick the most substantial non-empty response
    non_empty = {k: v for k, v in responses.items() if v.strip()}
    if non_empty:
        return max(non_empty.values(), key=len)

    return ""


def is_task_complete(
    response: str,
    task: str,
    cycle: int,
    max_cycles: int,
) -> bool:
    """
    Determine if a task is complete based on the response.

    Replaces the old stub that always returned True.

    Heuristics:
    1. Max cycles reached -> complete (safety valve)
    2. Empty response -> not complete
    3. Response contains clarifying questions -> not complete
    4. Response contains action intent -> not complete (on early cycles)
    5. Substantive response without questions -> complete
    """
    # Safety valve: max cycles
    if cycle >= max_cycles:
        return True

    # Empty response
    if not response or not response.strip():
        return False

    response_lower = response.lower().strip()

    # Clarifying questions (response asks the user something)
    question_indicators = [
        "could you clarify",
        "can you provide",
        "what do you mean",
        "could you be more specific",
        "do you want me to",
        "should i",
        "would you like",
    ]
    if any(indicator in response_lower for indicator in question_indicators):
        return False

    # Action intent on early cycles (still working)
    if cycle < max_cycles - 1:
        action_indicators = [
            "let me search",
            "let me look",
            "i'll check",
            "searching for",
            "looking up",
            "let me find",
            "i need to",
        ]
        if any(indicator in response_lower for indicator in action_indicators):
            return False

    # Substantive response (has content beyond filler)
    words = response.split()
    if len(words) < 3:
        return False

    return True


def _get_identity_event_type(event: object) -> str:
    """Return a stable identity event type for tracing metadata."""
    event_type = getattr(event, "event_type", None)
    if isinstance(event_type, str) and event_type:
        return event_type

    trigger = getattr(event, "trigger", None)
    if isinstance(trigger, str) and trigger:
        return trigger

    return "unknown"


async def run_session(
    task: str,
    mode: Optional[Union[AgentMode, str]] = None,
    max_cycles: Optional[int] = None,
) -> str:
    from vecna.orchestrator.mode_router import resolve_loop

    if mode is None:
        mode_value = AgentMode.assistant
    elif isinstance(mode, AgentMode):
        mode_value = mode
    elif isinstance(mode, str):
        try:
            mode_value = AgentMode(mode)
        except ValueError as exc:
            raise ValueError(f"Invalid agent mode: {mode}") from exc
    else:
        raise TypeError(f"Invalid agent mode type: {type(mode).__name__}")

    loop = resolve_loop(mode_value)
    return await loop.think(task, max_cycles=max_cycles)


@dataclass
class HiveConfig:
    """Configuration for the hive mind."""

    # How many models to run in parallel per cycle
    max_parallel_models: int = 5

    # Whether to run all models or route by domain
    use_routing: bool = True

    # Compress memory every N cycles
    compress_every: int = 5

    # Maximum cycles for a task (safety limit)
    max_cycles: int = 20

    # Whether to use semantic memory
    use_semantic_memory: bool = True

    # Local embeddings (no API) vs OpenAI embeddings
    use_local_embeddings: bool = True

    # Consensus configuration
    consensus_config: ConsensusConfig = field(default_factory=ConsensusConfig)

    # Logging verbosity
    verbose: bool = True

    # Auto-execute Python code blocks in responses via RLM sandbox
    auto_execute_code: bool = True

    # Auto-execute tool calls in responses
    auto_execute_tools: bool = True

    # Tool permission policy
    tool_policy: ToolPolicy = field(default_factory=ToolPolicy)

    # Use PgStateManager for memory instead of in-memory MemoryStore
    use_pg_memory: bool = True

    # Automatically sync memory to PG after each cycle
    auto_sync_memory: bool = False

    # Persist identity events to PG on significant changes
    persist_identity_events: bool = True

    # Enable identity growth updates from repeated beliefs
    enable_identity_growth: bool = False

    # Memory summary token limit
    memory_summary_token_limit: int = 4000

    # Soft threshold for flushing memory
    memory_flush_soft_threshold: int = 500

    # Enable ReWOO planning-execution path
    enable_rewoo_planning: bool = False

    # ReWOO execution settings
    rewoo_max_steps: int = 8
    rewoo_retry_limit: int = 1
    rewoo_backoff_base_seconds: float = 0.25
    rewoo_max_artifact_chars: int = 4000
    rewoo_policy_denied_behavior: str = "fail_step"
    rewoo_artifact_injection_mode: str = "final_summary"
    rewoo_use_separate_synthesizer: bool = False

    # ReWOO eligibility tuning
    rewoo_min_task_words: int = 8
    rewoo_force: bool = False

    # Tooling feature flags and quotas
    enable_web_tools: bool = False
    enable_fs_tools: bool = False
    tool_quota_per_session: int = 0
    tool_quota_per_tool: int = 0
    tool_allowed_fs_roots: List[str] = field(default_factory=lambda: ["~/.vecna"])


class HiveLoop:
    """
    The main orchestration loop for the hive mind.

    This class coordinates all models, manages shared state,
    and creates the emergent "single mind" behavior.
    """

    def __init__(
        self,
        config: Optional[HiveConfig] = None,
        adapters: Optional[List[BaseAdapter]] = None,
        name: str = "assistant",
    ):
        self.config = config or HiveConfig()
        self.adapters: List[BaseAdapter] = adapters or []
        self.name = name

        # Core components
        self.state = HiveState()
        self.state.ensure_identity()  # Initialize identity on creation
        self.consensus = ConsensusEngine(self.config.consensus_config)
        self.router = None  # Initialized when adapters are added

        # Memory - use PgStateManager if configured, else fallback to in-memory
        self.memory = None
        self._state_manager = None

        if self.config.use_pg_memory and os.environ.get("VECNA_PG_URL"):
            try:
                from vecna.core.state_store import PgStateManager

                self._state_manager = PgStateManager(auto_sync_memory=self.config.auto_sync_memory)
                logger.info("Using PgStateManager for memory persistence")
            except Exception as e:
                logger.warning(
                    f"Failed to initialize PgStateManager: {e}, falling back to in-memory"
                )
                self._state_manager = None

        # Fall back to in-memory MemoryStore if PG not available
        if self._state_manager is None and self.config.use_semantic_memory:
            self.memory = MemoryStore(use_local=self.config.use_local_embeddings)

        self.compressor = MemoryCompressor()

        self._session_manager: Optional[SessionManager] = None

        # Tool runtime
        auto_execute_tools = self.config.auto_execute_tools
        tool_policy = self.config.tool_policy
        self.tool_registry = get_default_registry(
            enable_web_tools=self.config.enable_web_tools,
            enable_fs_tools=self.config.enable_fs_tools,
        )
        self.tool_permissions = ToolPermissionManager(tool_policy)
        tool_quota_manager = None
        if self.config.tool_quota_per_session > 0 or self.config.tool_quota_per_tool > 0:
            tool_quota_manager = ToolQuotaManager(
                QuotaConfig(
                    per_session=self.config.tool_quota_per_session,
                    per_tool=self.config.tool_quota_per_tool,
                )
            )
        self.tool_runtime = ToolRuntime(
            registry=self.tool_registry,
            permission_manager=self.tool_permissions,
            quota_manager=tool_quota_manager,
            config=RuntimeConfig(auto_execute_tools=auto_execute_tools),
        )

        # Tracking
        self.cycle_count = 0
        self.history: List[Dict] = []

        # Per-adapter circuit breakers (Amendment 13)
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}

    def add_adapter(self, adapter: BaseAdapter) -> None:
        """Add a model adapter to the hive."""
        self.adapters.append(adapter)
        self._rebuild_router()
        logger.info(f"Added adapter: {adapter.name} (domain: {adapter.domain})")

    def add_model(self, config: ModelConfig) -> None:
        """Add a model by config (creates appropriate adapter)."""
        adapter = create_adapter(config)
        self.add_adapter(adapter)

    # ============================================================
    # PRIMARY CORTEX — Hierarchy, not democracy
    # ============================================================

    def get_primary_cortex(self) -> Optional[BaseAdapter]:
        """
        Get the primary cortex — the highest-weight adapter.

        The Primary Cortex is the most capable model that orchestrates.
        Advisory Lenses are consulted only when the Primary flags uncertainty.
        """
        if not self.adapters:
            return None
        return max(self.adapters, key=lambda a: a.weight)

    def get_advisory_lenses(self) -> List[BaseAdapter]:
        """Get advisory lenses (all adapters except primary cortex)."""
        primary = self.get_primary_cortex()
        if primary is None:
            return []
        return [a for a in self.adapters if a.name != primary.name]

    # ============================================================
    # ADAPTER CALL WITH TIMEOUT + CIRCUIT BREAKER (Amendment 13)
    # ============================================================

    async def _call_adapter_with_timeout(
        self,
        adapter: BaseAdapter,
        task: str,
        timeout: float = 60.0,
    ) -> Optional[tuple]:
        """
        Call adapter.think() with timeout and circuit breaker protection.

        Returns (response_text, HiveUpdate) on success, or None on failure/skip.
        """
        breaker = self._circuit_breakers.get(adapter.name)
        if breaker and breaker.is_open():
            logger.info("Skipping %s — circuit breaker open", adapter.name)
            return None

        try:
            result = await asyncio.wait_for(
                adapter.think(self.state, task),
                timeout=timeout,
            )
            if breaker:
                breaker.record_success()
            return result
        except asyncio.TimeoutError:
            logger.warning("Adapter %s timed out after %.0fs", adapter.name, timeout)
            if breaker:
                breaker.record_failure()
            return None
        except ConnectionError as e:
            logger.error("Adapter %s connection error: %s", adapter.name, e)
            if breaker:
                breaker.record_failure()
            return None
        except RuntimeError as e:
            logger.error("Adapter %s runtime error: %s", adapter.name, e)
            if breaker:
                breaker.record_failure()
            return None

    def _rebuild_router(self) -> None:
        """Rebuild the domain router with current adapters."""
        if self.adapters:
            self.router = DomainRouter(self.adapters)

    async def think(self, task: str, max_cycles: Optional[int] = None) -> str:
        """
        Main entry point: have the hive mind think about a task.

        This runs the full hive loop until the task is complete
        or max_cycles is reached.

        Includes Langfuse tracing for full request observability.
        """
        import uuid
        from vecna.observability.langfuse import (
            trace_request,
            trace_span,
            should_trace_pipeline,
            flush,
        )

        max_cycles = max_cycles or self.config.max_cycles
        auto_execute_tools = self.config.auto_execute_tools

        if not self.adapters:
            raise ValueError("No models added to hive. Use add_adapter() or add_model() first.")

        # === LANGFUSE TRACE (using context manager) ===
        session_id = str(uuid.uuid4())
        with trace_request(
            name="hive.think",
            session_id=session_id,
            input=task,
            metadata={
                "active_models": [a.name for a in self.adapters],
                "max_cycles": max_cycles,
                "use_routing": self.config.use_routing,
                "auto_execute_code": self.config.auto_execute_code,
                "auto_execute_tools": auto_execute_tools,
            },
            tags=["vecna", "hive-think"],
        ) as trace_ctx:
            try:
                await self._ensure_session_manager(task)
                if self._session_manager:
                    context = await self._session_manager.start_session(initial_query=task)
                    session_context = self._session_manager.format_context(context)
                    self.state.memory_summary = (
                        f"{session_context}\n\n{self.state.memory_summary}"
                        if self.state.memory_summary
                        else session_context
                    )
                # Set the task as a goal
                goal = Goal(content=task, priority="high", status="active")
                self.state.add_goal(goal)

                logger.info(f"Hive thinking about: {task[:100]}...")

                if self.config.enable_rewoo_planning and self._is_rewoo_eligible(task):
                    rewoo_result = await self._run_rewoo_task(task=task, session_id=session_id)
                    if rewoo_result.used_rewoo:
                        rewoo_response = rewoo_result.answer
                        self._mark_goal_completed(task)

                        trace_ctx.set_output(rewoo_response[:2000] if rewoo_response else "")
                        trace_ctx.set_metadata(
                            {
                                "total_cycles": 0,
                                "final_coherence": self.state.self_model.coherence
                                if self.state.self_model
                                else None,
                                "rewoo_used": True,
                                "rewoo_fallback_reason": rewoo_result.fallback_reason,
                            }
                        )

                        if self._session_manager:
                            rewoo_summary = self._build_rewoo_session_summary(rewoo_result)
                            await self._session_manager.end_session(
                                [
                                    {"role": "user", "content": task},
                                    {"role": "assistant", "content": rewoo_response},
                                    {"role": "system", "content": rewoo_summary},
                                ]
                            )
                        return rewoo_response

                    if rewoo_result.fallback_reason:
                        logger.info(
                            "ReWOO fallback to legacy loop for task '%s': %s",
                            task[:80],
                            rewoo_result.fallback_reason,
                        )
                elif self.config.enable_rewoo_planning:
                    logger.debug("Task did not meet ReWOO eligibility heuristic")

                final_response = ""
                total_cycles = 0
                conversation_log = [{"role": "user", "content": task}]

                for cycle in range(max_cycles):
                    self.cycle_count += 1
                    total_cycles += 1

                    if self.config.verbose:
                        logger.info(f"=== Cycle {self.cycle_count} ===")

                    # Run one cycle
                    response_map, updates = await self._run_cycle(task)

                    # === CONSENSUS SPAN ===
                    if should_trace_pipeline():
                        with trace_span("consensus.merge") as span:
                            counts = self.consensus.merge_updates(
                                updates,
                                self.state,
                                model_weights={a.name: a.weight for a in self.adapters},
                            )
                            span.set_metadata(
                                {
                                    "facts_added": counts.get("facts_added", 0),
                                    "beliefs_added": counts.get("beliefs_added", 0),
                                    "hypotheses_added": counts.get("hypotheses_added", 0),
                                    "contradictions": counts.get("contradictions_found", 0),
                                }
                            )
                    else:
                        counts = self.consensus.merge_updates(
                            updates,
                            self.state,
                            model_weights={a.name: a.weight for a in self.adapters},
                        )

                    if self.config.verbose:
                        logger.info(f"Consensus: {counts}")

                    # === SELF-REFLECTION ===
                    if should_trace_pipeline():
                        with trace_span("identity.reflect") as span:
                            identity_event = reflect(
                                self.state,
                                task,
                                enable_identity_growth=self.config.enable_identity_growth,
                            )
                            if identity_event and self.state.self_model:
                                span.set_metadata(
                                    {
                                        "coherence": self.state.self_model.coherence,
                                        "tone": self.state.self_model.get_tone().value,
                                        "event_type": _get_identity_event_type(identity_event),
                                    }
                                )
                    else:
                        identity_event = reflect(
                            self.state,
                            task,
                            enable_identity_growth=self.config.enable_identity_growth,
                        )

                    if identity_event and self.config.verbose and self.state.self_model:
                        logger.info(
                            f"Identity: coherence={self.state.self_model.coherence:.2f}, "
                            f"tone={self.state.self_model.get_tone().value}"
                        )

                    # Persist identity event to PG if configured and significant
                    if (
                        identity_event
                        and self.config.persist_identity_events
                        and self._state_manager
                    ):
                        try:
                            self._state_manager.persist_identity_event(identity_event)
                        except Exception as e:
                            logger.warning(f"Failed to persist identity event: {e}")

                    # Combine responses — Primary Cortex hierarchy
                    if response_map:
                        primary = self.get_primary_cortex()
                        primary_name = primary.name if primary else ""
                        final_response = select_best_response(response_map, primary_name)

                        # === TOOL EXECUTION SPAN ===
                        if auto_execute_tools and self.tool_runtime:
                            try:
                                if should_trace_pipeline():
                                    with trace_span("tool.execute") as span:
                                        (
                                            final_response,
                                            tool_results,
                                        ) = await self.tool_runtime.execute_calls(
                                            final_response,
                                            self._build_tool_execution_context(
                                                session_id=session_id
                                            ),
                                        )
                                        span.set_metadata(
                                            {
                                                "tools_executed": len(tool_results)
                                                if tool_results
                                                else 0,
                                                "success": True,
                                            }
                                        )
                                        if tool_results and self.config.verbose:
                                            logger.info(
                                                f"Executed {len(tool_results)} tool call(s)"
                                            )
                                else:
                                    (
                                        final_response,
                                        tool_results,
                                    ) = await self.tool_runtime.execute_calls(
                                        final_response,
                                        self._build_tool_execution_context(session_id=session_id),
                                    )
                                    if tool_results and self.config.verbose:
                                        logger.info(f"Executed {len(tool_results)} tool call(s)")
                            except Exception as e:
                                logger.warning(f"Tool execution failed: {e}")

                        # === CODE EXECUTION SPAN ===
                        if self.config.auto_execute_code:
                            try:
                                if should_trace_pipeline():
                                    with trace_span("code.execute") as span:
                                        final_response, exec_results = await execute_and_inject(
                                            final_response
                                        )
                                        span.set_metadata(
                                            {
                                                "blocks_executed": len(exec_results)
                                                if exec_results
                                                else 0,
                                                "success": True,
                                            }
                                        )
                                        if exec_results and self.config.verbose:
                                            logger.info(
                                                f"Executed {len(exec_results)} code block(s) in RLM sandbox"
                                            )
                                else:
                                    final_response, exec_results = await execute_and_inject(
                                        final_response
                                    )
                                    if exec_results and self.config.verbose:
                                        logger.info(
                                            f"Executed {len(exec_results)} code block(s) in RLM sandbox"
                                        )
                            except Exception as e:
                                logger.warning(f"Code execution failed: {e}")

                        if final_response:
                            conversation_log.append(
                                {"role": "assistant", "content": final_response}
                            )

                        if self._session_manager:
                            await self._session_manager.maybe_flush_mid_session(conversation_log)

                    # Compress memory periodically
                    if self.cycle_count % self.config.compress_every == 0:
                        self._maybe_flush_memory_before_compression()
                        await self._compress_memory()

                    # Record history
                    self.history.append(
                        {
                            "cycle": self.cycle_count,
                            "task": task,
                            "models_used": [u.source_model for u in updates],
                            "counts": counts,
                            "timestamp": datetime.now().isoformat(),
                        }
                    )

                    # Check if task is complete
                    if self._is_task_complete(final_response, task, cycle, max_cycles):
                        logger.info("Task appears complete.")
                        break

                # Mark goal complete
                self._mark_goal_completed(task)

                # Update trace with final output
                trace_ctx.set_output(final_response[:2000] if final_response else "")
                trace_ctx.set_metadata(
                    {
                        "total_cycles": total_cycles,
                        "final_coherence": self.state.self_model.coherence
                        if self.state.self_model
                        else None,
                    }
                )

                if self._session_manager:
                    await self._session_manager.end_session(conversation_log)
                return final_response

            except Exception as e:
                trace_ctx.set_level("ERROR")
                trace_ctx.set_status_message(str(e))
                raise
            finally:
                flush()

    async def run_session(self, task: str, max_cycles: Optional[int] = None) -> str:
        return await self.think(task, max_cycles=max_cycles)

    async def _ensure_session_manager(self, initial_query: Optional[str] = None) -> None:
        if self._session_manager is not None:
            return
        from vecna.config import ensure_default_config
        from vecna.memory.workspace import init_workspace

        vecna_config = ensure_default_config()
        workspace_dir = Path(vecna_config.workspace_dir).expanduser()
        init_workspace(workspace_dir)

        pg_store = self._state_manager._get_memory_store() if self._state_manager else None
        mirror = MemoryMirror(workspace_dir=workspace_dir, pg_store=pg_store, config=vecna_config)
        adapter = self.adapters[0] if self.adapters else None
        flush_mgr = FlushManager(adapter=adapter, mirror=mirror, config=vecna_config)
        self._session_manager = SessionManager(
            mirror=mirror, flush_mgr=flush_mgr, config=vecna_config
        )

    def initialize_session_manager(self) -> None:
        if self._session_manager is None:
            asyncio.run(self._ensure_session_manager())

    async def _run_cycle(self, task: str) -> tuple[Dict[str, str], List[HiveUpdate]]:
        """
        Run one cycle of the hive loop.

        All selected models think in parallel, then we collect results.

        Returns:
            (response_map, updates) where response_map is {adapter_name: response_text}.
        """
        from vecna.observability.langfuse import trace_span, should_trace_pipeline

        # Select models for this task
        if self.config.use_routing and self.router:
            selected = self.router.select_adapters(
                task, max_adapters=self.config.max_parallel_models
            )
        else:
            selected = self.adapters[: self.config.max_parallel_models]

        if self.config.verbose:
            logger.info(f"Models: {[a.name for a in selected]}")

        # Get relevant memory context
        memory_context = ""
        rlm_stats = {}

        # === MEMORY RETRIEVAL SPAN ===
        # Try PgMemoryStore via state manager first
        if self._state_manager:
            try:
                if should_trace_pipeline():
                    with trace_span("memory.retrieval", metadata={"source": "pg"}) as span:
                        pg_memory = self._state_manager._get_memory_store()
                        if pg_memory:
                            memory_context, facets, rlm_stats = pg_memory.rlm_retrieve(
                                task,
                                top_k_per_facet=5,
                                max_items=20,
                                max_chars=4000,
                            )
                            span.set_metadata(
                                {
                                    "num_facets": rlm_stats.get("num_facets", 0),
                                    "total_items_retrieved": rlm_stats.get(
                                        "total_items_retrieved", 0
                                    ),
                                    "cache_hits": rlm_stats.get("cache_hits", 0),
                                }
                            )
                            if (
                                self.config.verbose
                                and rlm_stats.get("total_items_retrieved", 0) > 0
                            ):
                                logger.info(
                                    f"PgRLM: {rlm_stats['num_facets']} facets, "
                                    f"{rlm_stats['total_items_retrieved']} items retrieved"
                                )
                else:
                    pg_memory = self._state_manager._get_memory_store()
                    if pg_memory:
                        memory_context, facets, rlm_stats = pg_memory.rlm_retrieve(
                            task,
                            top_k_per_facet=5,
                            max_items=20,
                            max_chars=4000,
                        )
                        if self.config.verbose and rlm_stats.get("total_items_retrieved", 0) > 0:
                            logger.info(
                                f"PgRLM: {rlm_stats['num_facets']} facets, "
                                f"{rlm_stats['total_items_retrieved']} items retrieved"
                            )
            except Exception as e:
                logger.warning(f"PgMemoryStore retrieval failed: {e}")

        # Fall back to in-memory MemoryStore
        if not memory_context and self.memory and self.memory.items:
            if should_trace_pipeline():
                with trace_span("memory.retrieval", metadata={"source": "memory"}) as span:
                    memory_context, facets, rlm_stats = self.memory.rlm_retrieve(
                        task,
                        top_k_per_facet=5,
                        max_items=20,
                        max_chars=4000,
                    )
                    span.set_metadata(
                        {
                            "num_facets": rlm_stats.get("num_facets", 0),
                            "total_items_retrieved": rlm_stats.get("total_items_retrieved", 0),
                        }
                    )
                    if self.config.verbose and rlm_stats.get("total_items_retrieved", 0) > 0:
                        logger.info(
                            f"RLM: {rlm_stats['num_facets']} facets, "
                            f"{rlm_stats['total_items_retrieved']} items retrieved"
                        )
            else:
                # Use RLM-style decompose → retrieve → recompose
                memory_context, facets, rlm_stats = self.memory.rlm_retrieve(
                    task,
                    top_k_per_facet=5,
                    max_items=20,
                    max_chars=4000,
                )
                if self.config.verbose and rlm_stats.get("total_items_retrieved", 0) > 0:
                    logger.info(
                        f"RLM: {rlm_stats['num_facets']} facets, "
                        f"{rlm_stats['total_items_retrieved']} items retrieved"
                    )

        # Get identity context for models
        identity_context = get_identity_context_for_prompt(self.state)

        # Inject memory and identity into state temporarily
        original_summary = self.state.memory_summary
        augmented_summary = original_summary

        if identity_context:
            augmented_summary = f"{identity_context}\n\n{augmented_summary}"
        if memory_context:
            augmented_summary = f"{augmented_summary}\n\nRELEVANT MEMORIES:\n{memory_context}"
        if self.tool_registry:
            tool_names = [t.name for t in self.tool_registry.list_tools()]
            if tool_names:
                augmented_summary = (
                    f"{augmented_summary}\n\nAVAILABLE TOOLS: {', '.join(tool_names)}"
                )

        self.state.memory_summary = augmented_summary

        # Run all models in parallel
        async def run_model(adapter: BaseAdapter) -> tuple[str, HiveUpdate]:
            try:
                return await adapter.think(self.state, task)
            except Exception as e:
                logger.error(f"Model {adapter.name} failed: {e}")
                return "", HiveUpdate(source_model=adapter.name)

        results = await asyncio.gather(*[run_model(a) for a in selected])

        # Restore original summary
        self.state.memory_summary = original_summary

        # Build adapter_name -> response_text mapping (skip empty responses)
        response_map: Dict[str, str] = {}
        for adapter, result in zip(selected, results):
            if result[0]:
                response_map[adapter.name] = result[0]
        updates = [r[1] for r in results]

        # Update semantic memory with new items
        # Prefer PgMemoryStore via state manager, fall back to in-memory
        if self._state_manager:
            try:
                self._state_manager.sync_memory_from_state(self.state)
            except Exception as e:
                logger.warning(f"Failed to sync memory to PG: {e}")
        elif self.memory:
            self.memory.add_from_state(self.state)

        return response_map, updates

    async def _run_rewoo_task(self, task: str, session_id: str) -> RewooExecutionResult:
        """Run ReWOO plan-execute-synthesize path with structured fallback result."""
        if not self.tool_runtime:
            return RewooExecutionResult(
                answer="",
                execution=None,
                used_rewoo=False,
                fallback_reason="tool runtime unavailable",
            )

        planner_adapter = self.adapters[0] if self.adapters else None
        synthesizer_adapter = None
        if self.config.rewoo_use_separate_synthesizer and len(self.adapters) > 1:
            synthesizer_adapter = self.adapters[1]
        engine = RewooEngine(
            runtime=self.tool_runtime,
            registry=self.tool_registry,
            planner_adapter=planner_adapter,
            synthesizer_adapter=synthesizer_adapter,
            config=RewooEngineConfig(
                max_steps=self.config.rewoo_max_steps,
                retry_limit=self.config.rewoo_retry_limit,
                backoff_base_seconds=self.config.rewoo_backoff_base_seconds,
                max_artifact_chars=self.config.rewoo_max_artifact_chars,
                policy_denied_behavior=self.config.rewoo_policy_denied_behavior,
                artifact_injection_mode=self.config.rewoo_artifact_injection_mode,
            ),
        )
        result = await engine.run(
            task,
            self.state,
            self._build_tool_execution_context(session_id=session_id),
        )
        if (
            result.used_rewoo
            and result.execution is not None
            and self.config.rewoo_artifact_injection_mode == "per_step"
        ):
            self._inject_rewoo_artifacts_into_memory_summary(result)
        return result

    def _inject_rewoo_artifacts_into_memory_summary(self, result: RewooExecutionResult) -> None:
        """Inject successful ReWOO artifacts into memory summary."""
        execution = result.execution
        if execution is None:
            return

        artifact_lines: List[str] = []
        for step_result in execution.results:
            if step_result.status != "succeeded":
                continue
            artifact = execution.artifacts.get(step_result.step_id, "")
            artifact_lines.append(f"[REWOO_ARTIFACT] {step_result.step_id}: {artifact}")

        if not artifact_lines:
            return

        block = "\n".join(artifact_lines)
        if self.state.memory_summary:
            self.state.memory_summary = f"{self.state.memory_summary}\n{block}"
        else:
            self.state.memory_summary = block

    def _is_rewoo_eligible(self, task: str) -> bool:
        """Heuristic gate for routing tasks through ReWOO."""
        if self.config.rewoo_force:
            return True

        lowered = task.strip().lower()
        if not lowered:
            return False

        complexity_signals = [
            " then ",
            " and ",
            " step by step",
            " first ",
            " second ",
            " compare ",
            " research ",
            " investigate ",
        ]
        if any(signal in f" {lowered} " for signal in complexity_signals):
            return True

        return (
            len([word for word in lowered.split(" ") if word]) >= self.config.rewoo_min_task_words
        )

    def _mark_goal_completed(self, task: str) -> None:
        """Mark matching active goals as completed."""
        for goal in self.state.goals:
            if goal.content == task:
                goal.status = "completed"

    def _build_rewoo_session_summary(self, result: RewooExecutionResult) -> str:
        """Build a compact execution summary for session compaction inputs."""
        if result.execution is None:
            return "[REWOO_EXECUTION] no execution details available"

        statuses = [f"{step.step_id}:{step.status}" for step in result.execution.results]
        return (
            "[REWOO_EXECUTION] "
            f"id={result.execution.execution_id}; "
            f"steps={len(result.execution.plan.steps)}; "
            f"succeeded={result.execution.steps_succeeded}; "
            f"failed={result.execution.steps_failed}; "
            f"policy_denials={result.execution.policy_denials}; "
            f"status_flow={', '.join(statuses)}"
        )

    async def _compress_memory(self) -> None:
        """Compress and summarize the hive state."""
        logger.info("Compressing memory...")

        # Generate summary
        summary = await self.compressor.compress(self.state)
        self.state.memory_summary = summary

        # Deduplicate
        removed = self.compressor.deduplicate_facts(self.state)
        if removed > 0:
            logger.info(f"Removed {removed} duplicate facts")

    def _maybe_flush_memory_before_compression(self) -> None:
        if not should_flush(
            current_tokens=estimate_token_count(self.state.memory_summary),
            limit=self.config.memory_summary_token_limit,
            soft_threshold=self.config.memory_flush_soft_threshold,
        ):
            return

        if self._state_manager:
            try:
                self._state_manager.flush_offline_spool()
            except Exception:
                pass

    def _is_task_complete(self, response: str, task: str, cycle: int, max_cycles: int) -> bool:
        """
        Heuristic to detect if task is complete based on response content.

        Delegates to the module-level ``is_task_complete()`` function.

        Args:
            response: The model's response text.
            task: The original task/query.
            cycle: The current cycle index within this task (0-based).
            max_cycles: Maximum number of cycles allowed.
        """
        return is_task_complete(
            response=response,
            task=task,
            cycle=cycle,
            max_cycles=max_cycles,
        )

    async def continuous_think(
        self,
        task: str,
        callback: Optional[Callable[[str, HiveState], None]] = None,
        stop_condition: Optional[Callable[[str, HiveState], bool]] = None,
    ) -> None:
        """
        Continuously think about a task, calling back after each cycle.

        Useful for long-running tasks or interactive sessions.
        """
        goal = Goal(content=task, priority="high", status="active")
        self.state.add_goal(goal)

        while True:
            response_map, updates = await self._run_cycle(task)
            self.consensus.merge_updates(
                updates,
                self.state,
                model_weights={a.name: a.weight for a in self.adapters},
            )

            # Self-reflection after consensus
            identity_event = reflect(
                self.state,
                task,
                enable_identity_growth=self.config.enable_identity_growth,
            )

            # Persist identity event to PG if configured and significant
            if identity_event and self.config.persist_identity_events and self._state_manager:
                try:
                    self._state_manager.persist_identity_event(identity_event)
                except Exception as e:
                    logger.warning(f"Failed to persist identity event: {e}")

            if self.cycle_count % self.config.compress_every == 0:
                self._maybe_flush_memory_before_compression()
                await self._compress_memory()

            response = ""
            if response_map:
                primary = self.get_primary_cortex()
                primary_name = primary.name if primary else ""
                response = select_best_response(response_map, primary_name)

            # Execute any tool calls in the response
            if response and self.config.auto_execute_tools and self.tool_runtime:
                try:
                    response, _ = await self.tool_runtime.execute_calls(
                        response, self._build_tool_execution_context(session_id=None)
                    )
                except Exception as e:
                    logger.warning(f"Tool execution failed: {e}")

            # Execute any Python code blocks in the response via RLM sandbox
            if response and self.config.auto_execute_code:
                try:
                    response, _ = await execute_and_inject(response)
                except Exception as e:
                    logger.warning(f"Code execution failed: {e}")

            if callback:
                callback(response, self.state)

            if stop_condition and stop_condition(response, self.state):
                break

            # Small delay to prevent runaway loops
            await asyncio.sleep(0.1)

    def get_state(self) -> HiveState:
        """Get current hive state."""
        return self.state

    def _build_tool_execution_context(self, session_id: Optional[str]) -> ToolExecutionContext:
        return ToolExecutionContext(
            session_id=session_id,
            allowed_fs_roots=list(self.config.tool_allowed_fs_roots),
        )

    def save_state(self, filepath: Optional[str] = None) -> None:
        """
        Save hive state to PostgreSQL (primary) or file (export/backup).

        Args:
            filepath: Optional. If provided, exports to JSON file (for backup).
                     If None, saves to PostgreSQL via PgStateManager.
        """
        # Primary: save to PostgreSQL via PgStateManager
        if self._state_manager:
            try:
                self._state_manager.save_state(self.state)
                logger.info("State saved to PostgreSQL")
            except Exception as e:
                logger.warning(f"PostgreSQL save failed: {e}")
                # Fall back to file if PG fails and filepath given
                if filepath:
                    self.state.export_to_file(filepath)
                    logger.info(f"State exported to {filepath} (PG unavailable)")
                return

        # If filepath provided, also export to file (backup/debug)
        if filepath:
            self.state.export_to_file(filepath)
            logger.info(f"State exported to {filepath}")
        elif not self._state_manager:
            logger.warning("No filepath provided and PgStateManager not available")

    def load_state(self, filepath: Optional[str] = None) -> None:
        """
        Load hive state from PostgreSQL (primary) or file (import/recovery).

        Args:
            filepath: Optional. If provided, imports from JSON file.
                     If None, loads from PostgreSQL via PgStateManager.
        """
        # If filepath provided, import from file
        if filepath:
            self.state = HiveState.import_from_file(filepath)
            self.state.ensure_identity()
            logger.info(f"State imported from {filepath}")
            return

        # Primary: load from PostgreSQL via PgStateManager
        if self._state_manager:
            try:
                loaded_state = self._state_manager.load_state()
                if loaded_state:
                    self.state = loaded_state
                    self.state.ensure_identity()
                    logger.info("State loaded from PostgreSQL")
                else:
                    logger.info("No existing state in PostgreSQL, using fresh state")
            except Exception as e:
                logger.warning(f"PostgreSQL load failed: {e}")
        else:
            logger.warning("No filepath provided and PgStateManager not available")

    def reset(self) -> None:
        """Reset hive state."""
        self.state = HiveState()
        self.state.ensure_identity()  # Ensure identity on reset
        if self.memory:
            self.memory.clear()
        self.cycle_count = 0
        self.history = []
        logger.info("Hive reset")


class HiveMind:
    """
    High-level API for the hive mind.

    This is the main interface users interact with.
    """

    def __init__(self, config: Optional[HiveConfig] = None):
        self.loop = HiveLoop(config)
        self._setup_complete = False

    def add_copilot(
        self,
        model: str = "gpt-4.1",
        name: Optional[str] = None,
        domain: str = "general",
    ) -> "HiveMind":
        """Add a GitHub Copilot model to the hive."""
        config = ModelConfig(
            name=name or f"copilot-{model}",
            model_id=model,
            domain=domain,
            extra_params={"provider": "copilot"},
        )
        self.loop.add_model(config)
        return self

    def add_ollama(
        self,
        model: str = "llama3.1",
        name: Optional[str] = None,
        domain: str = "general",
        base_url: str = "http://localhost:11434",
    ) -> "HiveMind":
        """Add an Ollama (local) model to the hive."""
        config = ModelConfig(
            name=name or f"ollama-{model}",
            model_id=model,
            domain=domain,
            base_url=base_url,
        )
        self.loop.add_model(config)
        return self

    def add_groq(
        self,
        model: str = "llama-3.1-70b-versatile",
        name: Optional[str] = None,
        domain: str = "general",
        api_key: Optional[str] = None,
    ) -> "HiveMind":
        """Add a Groq model to the hive."""
        config = ModelConfig(
            name=name or f"groq-{model}",
            model_id=model,
            domain=domain,
            api_key=api_key,
            base_url="groq",
        )
        self.loop.add_model(config)
        return self

    async def think(self, task: str) -> str:
        """Have the hive mind think about a task."""
        return await self.loop.think(task)

    def think_sync(self, task: str) -> str:
        """Synchronous version of think()."""
        return asyncio.run(self.think(task))

    @property
    def state(self) -> HiveState:
        """Get current hive state."""
        return self.loop.get_state()

    def save(self, filepath: Optional[str] = None) -> None:
        """
        Save hive state to PostgreSQL (primary) or file (export/backup).

        Args:
            filepath: Optional. If provided, exports to JSON file.
                     If None, saves to PostgreSQL only.
        """
        self.loop.save_state(filepath)

    def load(self, filepath: Optional[str] = None) -> None:
        """
        Load hive state from PostgreSQL (primary) or file (import).

        Args:
            filepath: Optional. If provided, imports from JSON file.
                     If None, loads from PostgreSQL.
        """
        self.loop.load_state(filepath)

    def reset(self) -> None:
        """Reset the hive."""
        self.loop.reset()
