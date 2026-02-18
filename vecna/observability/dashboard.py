"""Observability dashboard metrics collector.

Aggregates operational metrics across the Vecna system:
- Token usage per model per session
- Consensus agreement rates
- Tool execution counts and latencies
- DreamLoop run history
- Integration health tracking
- HumanModel confidence evolution
- Per-session metric breakdowns

This is separate from ToolDashboard (tool_dashboard.py) which
focuses on individual tool audit events. MetricsCollector
provides higher-level system-wide metrics.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import logging

from vecna.core.types import SerializableMixin

logger = logging.getLogger("vecna.observability.dashboard")


@dataclass
class TokenUsage(SerializableMixin):
    """Token usage record for a single LLM call."""

    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ConsensusStats(SerializableMixin):
    """Aggregated consensus statistics."""

    total_merges: int = 0
    facts_added: int = 0
    beliefs_added: int = 0
    contradictions_found: int = 0
    avg_agreement_rate: float = 0.0
    _agreement_sum: float = field(default=0.0, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary, excluding private accumulator fields."""
        result = super().to_dict()
        result.pop("_agreement_sum", None)
        return result


@dataclass
class ToolStats(SerializableMixin):
    """Aggregated tool execution statistics."""

    total_executions: int = 0
    successful: int = 0
    failed: int = 0
    avg_latency_ms: float = 0.0
    _latency_sum: float = field(default=0.0, repr=False)

    def failure_rate(self) -> float:
        """Calculate the failure rate."""
        if self.total_executions == 0:
            return 0.0
        return self.failed / self.total_executions

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary with computed failure_rate."""
        result = super().to_dict()
        result.pop("_latency_sum", None)
        result["failure_rate"] = self.failure_rate()
        return result


@dataclass
class DreamStats(SerializableMixin):
    """Aggregated DreamLoop statistics."""

    total_runs: int = 0
    insights_generated: int = 0
    facts_reinforced: int = 0
    facts_decayed: int = 0


@dataclass
class MetricsSnapshot(SerializableMixin):
    """Point-in-time snapshot of all metrics."""

    total_tokens: int = 0
    consensus_merges: int = 0
    tool_executions: int = 0
    dream_runs: int = 0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class IntegrationHealth(SerializableMixin):
    """Health status for an external integration.

    Tracks the current status of integrations such as Slack,
    Discord, GitHub, or Composio alongside error history.
    """

    name: str = ""
    status: str = "healthy"
    last_check: datetime = field(default_factory=datetime.now)
    error_count: int = 0
    last_error: Optional[str] = None


@dataclass
class HumanModelMetrics(SerializableMixin):
    """Tracks HumanModel confidence evolution over time.

    Records snapshots of confidence changes across dimensions
    (trust, expertise, friendliness, etc.) for each user.
    """

    confidence_snapshots: List[Dict[str, Any]] = field(default_factory=list)

    def record_confidence(
        self,
        user_id: str,
        dimension: str,
        old_value: float,
        new_value: float,
    ) -> None:
        """Record a confidence value change.

        Args:
            user_id: The user whose model changed.
            dimension: The confidence dimension (e.g. trust).
            old_value: Previous confidence value.
            new_value: Updated confidence value.
        """
        self.confidence_snapshots.append(
            {
                "user_id": user_id,
                "dimension": dimension,
                "old_value": old_value,
                "new_value": new_value,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def get_evolution(self) -> List[Dict[str, Any]]:
        """Return all confidence snapshots in chronological order.

        Returns:
            List of confidence snapshot dicts.
        """
        return list(self.confidence_snapshots)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary with total_updates count."""
        return {
            "confidence_snapshots": list(self.confidence_snapshots),
            "total_updates": len(self.confidence_snapshots),
        }


@dataclass
class SessionMetrics(SerializableMixin):
    """Per-session metric breakdown.

    Tracks token usage and tool execution counts scoped
    to a single user session.
    """

    session_id: str = ""
    token_count: int = 0
    tool_executions: int = 0
    tool_successes: int = 0
    tool_failures: int = 0
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary with ISO-formatted times."""
        return {
            "session_id": self.session_id,
            "token_count": self.token_count,
            "tool_executions": self.tool_executions,
            "tool_successes": self.tool_successes,
            "tool_failures": self.tool_failures,
            "start_time": self.start_time.isoformat(),
            "end_time": (self.end_time.isoformat() if self.end_time is not None else None),
        }


class MetricsCollector:
    """Collects and aggregates system-wide metrics.

    Thread-safe for single-writer usage. Records token usage,
    consensus merges, tool executions, dream loop runs,
    integration health, HumanModel confidence, and per-session
    breakdowns.
    """

    def __init__(self) -> None:
        self.token_records: List[TokenUsage] = []
        self.consensus = ConsensusStats()
        self.tools = ToolStats()
        self.dreams = DreamStats()
        self.integrations: Dict[str, IntegrationHealth] = {}
        self.human_model = HumanModelMetrics()
        self.sessions: Dict[str, SessionMetrics] = {}

    def record_token_usage(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        session_id: Optional[str] = None,
    ) -> None:
        """Record token usage for a single LLM call.

        Args:
            model: The model identifier.
            prompt_tokens: Number of prompt tokens.
            completion_tokens: Number of completion tokens.
            session_id: Optional session to attribute to.
        """
        total = prompt_tokens + completion_tokens
        record = TokenUsage(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
        )
        self.token_records.append(record)

        if session_id and session_id in self.sessions:
            self.sessions[session_id].token_count += total

    def record_consensus_merge(
        self,
        facts_added: int,
        beliefs_added: int,
        contradictions_found: int,
        agreement_rate: float = 0.0,
    ) -> None:
        """Record a consensus merge operation.

        Args:
            facts_added: Number of facts added.
            beliefs_added: Number of beliefs added.
            contradictions_found: Number of contradictions.
            agreement_rate: Agreement rate for this merge (0.0-1.0).
        """
        self.consensus.total_merges += 1
        self.consensus.facts_added += facts_added
        self.consensus.beliefs_added += beliefs_added
        self.consensus.contradictions_found += contradictions_found
        self.consensus._agreement_sum += agreement_rate
        self.consensus.avg_agreement_rate = (
            self.consensus._agreement_sum / self.consensus.total_merges
        )

    def record_tool_execution(
        self,
        success: bool,
        latency_ms: float,
        session_id: Optional[str] = None,
    ) -> None:
        """Record a tool execution.

        Args:
            success: Whether the execution succeeded.
            latency_ms: Execution latency in milliseconds.
            session_id: Optional session to attribute to.
        """
        self.tools.total_executions += 1
        if success:
            self.tools.successful += 1
        else:
            self.tools.failed += 1

        self.tools._latency_sum += latency_ms
        self.tools.avg_latency_ms = self.tools._latency_sum / self.tools.total_executions

        if session_id and session_id in self.sessions:
            session = self.sessions[session_id]
            session.tool_executions += 1
            if success:
                session.tool_successes += 1
            else:
                session.tool_failures += 1

    def record_dream_run(
        self,
        insights: int,
        reinforced: int,
        decayed: int,
    ) -> None:
        """Record a DreamLoop run.

        Args:
            insights: Number of insights generated.
            reinforced: Number of facts reinforced.
            decayed: Number of facts decayed.
        """
        self.dreams.total_runs += 1
        self.dreams.insights_generated += insights
        self.dreams.facts_reinforced += reinforced
        self.dreams.facts_decayed += decayed

    def record_integration_health(
        self,
        name: str,
        status: str,
        error: Optional[str] = None,
    ) -> None:
        """Record health status for an integration.

        Creates the integration entry if it doesn't exist,
        otherwise updates status and error tracking.

        Args:
            name: Integration name (e.g. slack, discord).
            status: Current status (healthy/degraded/down).
            error: Optional error message if unhealthy.
        """
        now = datetime.now()
        if name not in self.integrations:
            self.integrations[name] = IntegrationHealth(
                name=name,
                status=status,
                last_check=now,
            )
        else:
            self.integrations[name].status = status
            self.integrations[name].last_check = now

        if error is not None:
            self.integrations[name].error_count += 1
            self.integrations[name].last_error = error

        logger.debug("Integration %s health: %s", name, status)

    def record_human_model_confidence(
        self,
        user_id: str,
        dimension: str,
        old_value: float,
        new_value: float,
    ) -> None:
        """Record a HumanModel confidence change.

        Args:
            user_id: The user whose model changed.
            dimension: The confidence dimension.
            old_value: Previous confidence value.
            new_value: Updated confidence value.
        """
        self.human_model.record_confidence(
            user_id=user_id,
            dimension=dimension,
            old_value=old_value,
            new_value=new_value,
        )

    def record_session_start(self, session_id: str) -> None:
        """Start tracking metrics for a session.

        Args:
            session_id: Unique session identifier.
        """
        self.sessions[session_id] = SessionMetrics(
            session_id=session_id,
        )
        logger.debug("Session started: %s", session_id)

    def record_session_end(self, session_id: str) -> None:
        """Mark a session as ended.

        Does nothing if the session does not exist.

        Args:
            session_id: The session to end.
        """
        if session_id not in self.sessions:
            return
        self.sessions[session_id].end_time = datetime.now()
        logger.debug("Session ended: %s", session_id)

    def get_token_usage_by_model(self) -> Dict[str, Dict[str, int]]:
        """Aggregate token usage per model.

        Returns:
            Dict mapping model name to token totals.
        """
        by_model: Dict[str, Dict[str, int]] = {}
        for record in self.token_records:
            if record.model not in by_model:
                by_model[record.model] = {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "call_count": 0,
                }
            entry = by_model[record.model]
            entry["prompt_tokens"] += record.prompt_tokens
            entry["completion_tokens"] += record.completion_tokens
            entry["total_tokens"] += record.total_tokens
            entry["call_count"] += 1
        return by_model

    def get_snapshot(self) -> MetricsSnapshot:
        """Get a point-in-time snapshot of key metrics.

        Returns:
            A MetricsSnapshot summarizing current state.
        """
        total_tokens = sum(r.total_tokens for r in self.token_records)
        return MetricsSnapshot(
            total_tokens=total_tokens,
            consensus_merges=self.consensus.total_merges,
            tool_executions=self.tools.total_executions,
            dream_runs=self.dreams.total_runs,
        )

    def to_full_report(self) -> Dict[str, Any]:
        """Generate a comprehensive metrics report.

        Combines all metric categories into a single dict
        suitable for JSON serialization and API responses.

        Returns:
            Dict with tokens, consensus, tools, dreams,
            integrations, human_model, sessions, and snapshot.
        """
        integrations_dict: Dict[str, Any] = {}
        for name, health in self.integrations.items():
            integrations_dict[name] = health.to_dict()

        sessions_dict: Dict[str, Any] = {}
        for sid, session in self.sessions.items():
            sessions_dict[sid] = session.to_dict()

        return {
            "tokens": {
                "total_records": len(self.token_records),
                "by_model": self.get_token_usage_by_model(),
            },
            "consensus": self.consensus.to_dict(),
            "tools": self.tools.to_dict(),
            "dreams": self.dreams.to_dict(),
            "integrations": integrations_dict,
            "human_model": self.human_model.to_dict(),
            "sessions": sessions_dict,
            "snapshot": self.get_snapshot().to_dict(),
            "generated_at": datetime.now().isoformat(),
        }

    def reset(self) -> None:
        """Reset all collected metrics."""
        self.token_records.clear()
        self.consensus = ConsensusStats()
        self.tools = ToolStats()
        self.dreams = DreamStats()
        self.integrations.clear()
        self.human_model = HumanModelMetrics()
        self.sessions.clear()
        logger.info("Metrics collector reset")
