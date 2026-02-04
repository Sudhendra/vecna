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
from typing import List, Dict, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
import json
import logging
import os

from vecna.core.hive_state import HiveState
from vecna.core.types import HiveUpdate, Goal
from vecna.adapters.base import BaseAdapter, ModelConfig, create_adapter
from vecna.memory.store import MemoryStore, MemoryCompressor
from vecna.orchestrator.consensus import ConsensusEngine, ConsensusConfig, DomainRouter
from vecna.orchestrator.self_reflection import reflect, get_identity_context_for_prompt
from vecna.tools.code_executor import execute_and_inject


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vecna.hive")


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

    # Use PgStateManager for memory instead of in-memory MemoryStore
    use_pg_memory: bool = True

    # Automatically sync memory to PG after each cycle
    auto_sync_memory: bool = False

    # Persist identity events to PG on significant changes
    persist_identity_events: bool = True


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

        # Tracking
        self.cycle_count = 0
        self.history: List[Dict] = []

    def add_adapter(self, adapter: BaseAdapter) -> None:
        """Add a model adapter to the hive."""
        self.adapters.append(adapter)
        self._rebuild_router()
        logger.info(f"Added adapter: {adapter.name} (domain: {adapter.domain})")

    def add_model(self, config: ModelConfig) -> None:
        """Add a model by config (creates appropriate adapter)."""
        adapter = create_adapter(config)
        self.add_adapter(adapter)

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

        if not self.adapters:
            raise ValueError("No models added to hive. Use add_adapter() or add_model() first.")

        # === LANGFUSE TRACE (using context manager) ===
        with trace_request(
            name="hive.think",
            session_id=str(uuid.uuid4()),
            input=task,
            metadata={
                "active_models": [a.name for a in self.adapters],
                "max_cycles": max_cycles,
                "use_routing": self.config.use_routing,
                "auto_execute_code": self.config.auto_execute_code,
            },
            tags=["vecna", "hive-think"],
        ) as trace_ctx:
            try:
                # Set the task as a goal
                goal = Goal(content=task, priority="high", status="active")
                self.state.add_goal(goal)

                logger.info(f"Hive thinking about: {task[:100]}...")

                final_response = ""
                total_cycles = 0

                for cycle in range(max_cycles):
                    self.cycle_count += 1
                    total_cycles += 1

                    if self.config.verbose:
                        logger.info(f"=== Cycle {self.cycle_count} ===")

                    # Run one cycle
                    responses, updates = await self._run_cycle(task)

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
                            identity_event = reflect(self.state, task)
                            if identity_event and self.state.self_model:
                                span.set_metadata(
                                    {
                                        "coherence": self.state.self_model.coherence,
                                        "tone": self.state.self_model.get_tone().value,
                                        "event_type": identity_event.event_type
                                        if identity_event
                                        else None,
                                    }
                                )
                    else:
                        identity_event = reflect(self.state, task)

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

                    # Combine responses (take the most detailed)
                    if responses:
                        final_response = max(responses, key=len)

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

                    # Compress memory periodically
                    if self.cycle_count % self.config.compress_every == 0:
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
                    if self._is_task_complete(final_response, task):
                        logger.info("Task appears complete.")
                        break

                # Mark goal complete
                for g in self.state.goals:
                    if g.content == task:
                        g.status = "completed"

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

                return final_response

            except Exception as e:
                trace_ctx.set_level("ERROR")
                trace_ctx.set_status_message(str(e))
                raise
            finally:
                flush()

    async def run_session(self, task: str, max_cycles: Optional[int] = None) -> str:
        return await self.think(task, max_cycles=max_cycles)

    async def _run_cycle(self, task: str) -> tuple[List[str], List[HiveUpdate]]:
        """
        Run one cycle of the hive loop.

        All selected models think in parallel, then we collect results.
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

        responses = [r[0] for r in results if r[0]]
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

        return responses, updates

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

    def _is_task_complete(self, response: str, task: str) -> bool:
        """
        Simple heuristic to detect if task is complete.

        In a real system, you'd use more sophisticated methods.
        """
        # For now, just run one cycle for simple tasks
        # Multi-cycle tasks would need explicit continuation signals
        return True

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
            responses, updates = await self._run_cycle(task)
            self.consensus.merge_updates(
                updates,
                self.state,
                model_weights={a.name: a.weight for a in self.adapters},
            )

            # Self-reflection after consensus
            identity_event = reflect(self.state, task)

            # Persist identity event to PG if configured and significant
            if identity_event and self.config.persist_identity_events and self._state_manager:
                try:
                    self._state_manager.persist_identity_event(identity_event)
                except Exception as e:
                    logger.warning(f"Failed to persist identity event: {e}")

            if self.cycle_count % self.config.compress_every == 0:
                await self._compress_memory()

            response = max(responses, key=len) if responses else ""

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
