"""Unit tests for the observability dashboard MetricsCollector.

Tests:
- Token usage recording and per-model aggregation
- Consensus merge recording with agreement rate tracking
- Tool execution recording
- Dream run recording
- Integration health tracking
- HumanModel confidence evolution
- Session-scoped metrics
- Full report generation
- Snapshot and reset
- Metrics endpoint handler
"""

import pytest

from vecna.observability.dashboard import (
    TokenUsage,
    MetricsCollector,
    IntegrationHealth,
    HumanModelMetrics,
    SessionMetrics,
)
from vecna.server.routes import handle_metrics_request


class TestTokenUsage:
    """Tests for TokenUsage dataclass."""

    def test_token_usage_to_dict(self):
        """TokenUsage.to_dict serializes all fields."""
        usage = TokenUsage(
            model="gpt-4",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        d = usage.to_dict()
        assert d["model"] == "gpt-4"
        assert d["prompt_tokens"] == 100
        assert d["completion_tokens"] == 50
        assert d["total_tokens"] == 150
        assert "timestamp" in d

    def test_token_usage_defaults(self):
        """TokenUsage defaults to empty/zero values."""
        usage = TokenUsage()
        assert usage.model == ""
        assert usage.total_tokens == 0


class TestConsensusAgreementRate:
    """Tests for consensus agreement rate tracking."""

    def test_single_merge_with_agreement_rate(self):
        """Recording one merge sets avg_agreement_rate."""
        collector = MetricsCollector()
        collector.record_consensus_merge(
            facts_added=2,
            beliefs_added=1,
            contradictions_found=0,
            agreement_rate=0.85,
        )
        assert collector.consensus.avg_agreement_rate == pytest.approx(0.85)
        assert collector.consensus.total_merges == 1
        assert collector.consensus.facts_added == 2

    def test_multiple_merges_average_agreement_rate(self):
        """Agreement rate is averaged across multiple merges."""
        collector = MetricsCollector()
        collector.record_consensus_merge(
            facts_added=1,
            beliefs_added=0,
            contradictions_found=0,
            agreement_rate=0.80,
        )
        collector.record_consensus_merge(
            facts_added=2,
            beliefs_added=1,
            contradictions_found=1,
            agreement_rate=0.60,
        )
        assert collector.consensus.avg_agreement_rate == pytest.approx(0.70)
        assert collector.consensus.total_merges == 2
        assert collector.consensus.contradictions_found == 1

    def test_merge_without_agreement_rate_defaults_zero(self):
        """When agreement_rate is omitted, it defaults to 0.0."""
        collector = MetricsCollector()
        collector.record_consensus_merge(
            facts_added=1,
            beliefs_added=0,
            contradictions_found=0,
        )
        assert collector.consensus.avg_agreement_rate == pytest.approx(0.0)
        assert collector.consensus.total_merges == 1


class TestIntegrationHealth:
    """Tests for IntegrationHealth dataclass and tracking."""

    def test_integration_health_to_dict(self):
        """IntegrationHealth serializes correctly."""
        health = IntegrationHealth(name="slack", status="healthy")
        d = health.to_dict()
        assert d["name"] == "slack"
        assert d["status"] == "healthy"
        assert d["error_count"] == 0
        assert d["last_error"] is None
        assert "last_check" in d

    def test_record_integration_health_new(self):
        """Recording health for a new integration creates entry."""
        collector = MetricsCollector()
        collector.record_integration_health(
            name="slack",
            status="healthy",
        )
        assert "slack" in collector.integrations
        assert collector.integrations["slack"].status == "healthy"
        assert collector.integrations["slack"].error_count == 0

    def test_record_integration_health_with_error(self):
        """Recording health with error increments error count."""
        collector = MetricsCollector()
        collector.record_integration_health(
            name="discord",
            status="degraded",
            error="Connection timeout",
        )
        assert collector.integrations["discord"].status == "degraded"
        assert collector.integrations["discord"].error_count == 1
        assert collector.integrations["discord"].last_error == "Connection timeout"

    def test_record_integration_health_updates_existing(self):
        """Recording health again updates status and timestamps."""
        collector = MetricsCollector()
        collector.record_integration_health(name="github", status="healthy")
        collector.record_integration_health(
            name="github",
            status="down",
            error="API rate limited",
        )
        assert collector.integrations["github"].status == "down"
        assert collector.integrations["github"].error_count == 1
        assert collector.integrations["github"].last_error == "API rate limited"

    def test_multiple_errors_accumulate(self):
        """Multiple error recordings increment the count."""
        collector = MetricsCollector()
        collector.record_integration_health(name="composio", status="degraded", error="err1")
        collector.record_integration_health(name="composio", status="degraded", error="err2")
        collector.record_integration_health(name="composio", status="down", error="err3")
        assert collector.integrations["composio"].error_count == 3
        assert collector.integrations["composio"].last_error == "err3"


class TestHumanModelMetrics:
    """Tests for HumanModel confidence evolution tracking."""

    def test_empty_human_model_metrics(self):
        """Fresh HumanModelMetrics has no snapshots."""
        hm = HumanModelMetrics()
        assert hm.confidence_snapshots == []
        evolution = hm.get_evolution()
        assert evolution == []

    def test_record_confidence(self):
        """Recording confidence adds a snapshot."""
        hm = HumanModelMetrics()
        hm.record_confidence(
            user_id="user-abc",
            dimension="trust",
            old_value=0.5,
            new_value=0.7,
        )
        assert len(hm.confidence_snapshots) == 1
        snap = hm.confidence_snapshots[0]
        assert snap["user_id"] == "user-abc"
        assert snap["dimension"] == "trust"
        assert snap["old_value"] == 0.5
        assert snap["new_value"] == 0.7
        assert "timestamp" in snap

    def test_get_evolution_returns_chronological_snapshots(self):
        """Evolution returns all snapshots in order."""
        hm = HumanModelMetrics()
        hm.record_confidence("u1", "trust", 0.3, 0.5)
        hm.record_confidence("u1", "trust", 0.5, 0.8)
        hm.record_confidence("u2", "expertise", 0.1, 0.4)
        evolution = hm.get_evolution()
        assert len(evolution) == 3
        assert evolution[0]["old_value"] == 0.3
        assert evolution[1]["new_value"] == 0.8
        assert evolution[2]["dimension"] == "expertise"

    def test_collector_record_human_model_confidence(self):
        """MetricsCollector delegates to HumanModelMetrics."""
        collector = MetricsCollector()
        collector.record_human_model_confidence(
            user_id="u1",
            dimension="friendliness",
            old_value=0.6,
            new_value=0.9,
        )
        assert len(collector.human_model.confidence_snapshots) == 1

    def test_human_model_metrics_to_dict(self):
        """HumanModelMetrics.to_dict includes all snapshots."""
        hm = HumanModelMetrics()
        hm.record_confidence("u1", "trust", 0.5, 0.7)
        d = hm.to_dict()
        assert "confidence_snapshots" in d
        assert len(d["confidence_snapshots"]) == 1
        assert d["total_updates"] == 1


class TestSessionMetrics:
    """Tests for session-scoped metrics."""

    def test_session_metrics_to_dict(self):
        """SessionMetrics serializes correctly."""
        sm = SessionMetrics(session_id="sess-001")
        d = sm.to_dict()
        assert d["session_id"] == "sess-001"
        assert d["token_count"] == 0
        assert d["tool_executions"] == 0
        assert "start_time" in d
        assert d["end_time"] is None

    def test_record_session_start_and_end(self):
        """Starting and ending a session tracks it."""
        collector = MetricsCollector()
        collector.record_session_start("sess-abc")
        assert "sess-abc" in collector.sessions
        assert collector.sessions["sess-abc"].end_time is None

        start_time = collector.sessions["sess-abc"].start_time
        collector.record_session_end("sess-abc")
        end_time = collector.sessions["sess-abc"].end_time
        # Amendment 9: assert end_time > start_time and is recent
        assert end_time is not None
        assert end_time >= start_time

    def test_session_end_nonexistent_is_noop(self):
        """Ending a non-existent session does nothing."""
        collector = MetricsCollector()
        collector.record_session_end("nonexistent")
        assert "nonexistent" not in collector.sessions

    def test_session_token_tracking(self):
        """Token usage within a session is tracked."""
        collector = MetricsCollector()
        collector.record_session_start("sess-1")
        collector.record_token_usage(
            model="gpt-4",
            prompt_tokens=100,
            completion_tokens=50,
            session_id="sess-1",
        )
        assert collector.sessions["sess-1"].token_count == 150

    def test_session_tool_tracking(self):
        """Tool executions within a session are tracked."""
        collector = MetricsCollector()
        collector.record_session_start("sess-2")
        collector.record_tool_execution(
            success=True,
            latency_ms=45.0,
            session_id="sess-2",
        )
        collector.record_tool_execution(
            success=False,
            latency_ms=120.0,
            session_id="sess-2",
        )
        assert collector.sessions["sess-2"].tool_executions == 2
        assert collector.sessions["sess-2"].tool_successes == 1
        assert collector.sessions["sess-2"].tool_failures == 1


class TestFullReport:
    """Tests for the full report generation."""

    def test_full_report_structure(self):
        """to_full_report returns all metric categories."""
        collector = MetricsCollector()
        report = collector.to_full_report()
        assert "tokens" in report
        assert "consensus" in report
        assert "tools" in report
        assert "dreams" in report
        assert "integrations" in report
        assert "human_model" in report
        assert "sessions" in report
        assert "snapshot" in report
        assert "generated_at" in report

    def test_full_report_with_data(self):
        """Full report includes all recorded data."""
        collector = MetricsCollector()
        collector.record_token_usage("gpt-4", 100, 50)
        collector.record_consensus_merge(1, 0, 0, agreement_rate=0.9)
        collector.record_tool_execution(True, 30.0)
        collector.record_dream_run(2, 1, 0)
        collector.record_integration_health("slack", "healthy")
        collector.record_human_model_confidence("u1", "trust", 0.5, 0.7)
        collector.record_session_start("s1")

        report = collector.to_full_report()
        assert report["tokens"]["by_model"]["gpt-4"]["total_tokens"] == 150
        assert report["consensus"]["avg_agreement_rate"] == pytest.approx(0.9)
        assert report["tools"]["total_executions"] == 1
        assert report["dreams"]["total_runs"] == 1
        assert report["integrations"]["slack"]["status"] == "healthy"
        assert len(report["human_model"]["confidence_snapshots"]) == 1
        assert "s1" in report["sessions"]
        assert report["snapshot"]["total_tokens"] == 150


class TestReset:
    """Tests for MetricsCollector reset."""

    def test_reset_clears_all_metrics(self):
        """Reset clears tokens, consensus, tools, dreams, and new fields."""
        collector = MetricsCollector()
        collector.record_token_usage("gpt-4", 100, 50)
        collector.record_consensus_merge(1, 0, 0, agreement_rate=0.9)
        collector.record_tool_execution(True, 30.0)
        collector.record_dream_run(2, 1, 0)
        collector.record_integration_health("slack", "healthy")
        collector.record_human_model_confidence("u1", "trust", 0.5, 0.7)
        collector.record_session_start("s1")

        collector.reset()

        assert collector.token_records == []
        assert collector.consensus.total_merges == 0
        assert collector.tools.total_executions == 0
        assert collector.dreams.total_runs == 0
        assert collector.integrations == {}
        assert collector.human_model.confidence_snapshots == []
        assert collector.sessions == {}


class TestMetricsEndpoint:
    """Tests for the /api/metrics route handler."""

    def test_handle_metrics_request_returns_report(self):
        """handle_metrics_request returns the full report dict."""
        collector = MetricsCollector()
        collector.record_token_usage("gpt-4", 50, 25)

        result = handle_metrics_request(collector)
        assert "tokens" in result
        assert "snapshot" in result
        assert result["tokens"]["by_model"]["gpt-4"]["total_tokens"] == 75

    def test_handle_metrics_request_empty_collector(self):
        """handle_metrics_request works with no data recorded."""
        collector = MetricsCollector()
        result = handle_metrics_request(collector)
        assert result["snapshot"]["total_tokens"] == 0
        assert result["integrations"] == {}
        assert result["sessions"] == {}
