"""Unit tests for tool observability helpers."""

import pytest

from vecna.observability.memory_tracing import MemoryAccessTracer
from vecna.observability.tool_dashboard import ToolDashboard
from vecna.tools.audit import ToolAuditEvent


def test_tool_dashboard_aggregates_totals_and_latency_metrics():
    dashboard = ToolDashboard(track_latency=True)

    dashboard.ingest(
        ToolAuditEvent(
            tool_name="python_exec",
            action="allow",
            risk_tier="low",
            success=True,
            payload={"latency_ms": 120},
        )
    )
    dashboard.ingest(
        ToolAuditEvent(
            tool_name="python_exec",
            action="allow",
            risk_tier="low",
            success=False,
            error="boom",
            payload={"latency_ms": 220},
        )
    )
    dashboard.ingest(
        ToolAuditEvent(
            tool_name="http_request",
            action="deny",
            risk_tier="high",
            success=False,
            error="denied by policy",
        )
    )

    summary = dashboard.summarize()

    assert summary["totals"] == {
        "total": 3,
        "success": 1,
        "failure": 2,
        "denials": 1,
    }
    assert summary["tools"]["python_exec"] == {
        "total": 2,
        "success": 1,
        "failure": 1,
        "denials": 0,
        "failure_rate": pytest.approx(0.5),
    }
    assert summary["tools"]["http_request"]["denials"] == 1
    assert summary["latency"]["overall"] == {
        "count": 2,
        "avg_ms": pytest.approx(170.0),
        "min_ms": 120.0,
        "max_ms": 220.0,
    }
    assert summary["latency"]["by_tool"]["python_exec"]["avg_ms"] == pytest.approx(170.0)


def test_tool_dashboard_omits_latency_metrics_when_disabled():
    dashboard = ToolDashboard(track_latency=False)
    dashboard.ingest(
        ToolAuditEvent(
            tool_name="memory_search",
            action="allow",
            risk_tier="low",
            success=True,
            payload={"latency_ms": 15},
        )
    )

    summary = dashboard.summarize()
    assert "latency" not in summary


def test_memory_access_trace_records_why_items_were_retrieved():
    tracer = MemoryAccessTracer()

    entry = tracer.record(
        item_id="fact-123",
        item_type="fact",
        reason="semantic_match",
        query="why is the sky blue",
        score=0.91,
    )

    assert entry.item_id == "fact-123"
    assert entry.reason == "semantic_match"
    assert tracer.events()[0].query == "why is the sky blue"
    assert tracer.events()[0].score == pytest.approx(0.91)
