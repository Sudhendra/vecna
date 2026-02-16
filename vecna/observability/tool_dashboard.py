"""Aggregate tool audit events into dashboard-friendly metrics."""

from dataclasses import dataclass, field
from typing import Any, Dict, List

from vecna.tools.audit import ToolAuditEvent


@dataclass
class _ToolSummary:
    total: int = 0
    success: int = 0
    failure: int = 0
    denials: int = 0
    latencies_ms: List[float] = field(default_factory=list)


def _build_latency_summary(latencies_ms: List[float]) -> Dict[str, float | int]:
    if not latencies_ms:
        return {"count": 0, "avg_ms": 0.0, "min_ms": 0.0, "max_ms": 0.0}

    total = sum(latencies_ms)
    return {
        "count": len(latencies_ms),
        "avg_ms": total / len(latencies_ms),
        "min_ms": min(latencies_ms),
        "max_ms": max(latencies_ms),
    }


class ToolDashboard:
    """Aggregate and summarize tool audit events."""

    def __init__(self, track_latency: bool = False) -> None:
        self.track_latency = track_latency
        self._overall = _ToolSummary()
        self._by_tool: Dict[str, _ToolSummary] = {}

    def ingest(self, event: ToolAuditEvent) -> None:
        """Ingest a single audit event."""
        aggregate = self._by_tool.setdefault(event.tool_name, _ToolSummary())
        self._increment(aggregate, event)
        self._increment(self._overall, event)

        if self.track_latency:
            latency = event.payload.get("latency_ms") if isinstance(event.payload, dict) else None
            if isinstance(latency, int | float):
                latency_value = float(latency)
                aggregate.latencies_ms.append(latency_value)
                self._overall.latencies_ms.append(latency_value)

    def summarize(self) -> Dict[str, Any]:
        """Return aggregate dashboard metrics."""
        response: Dict[str, Any] = {
            "totals": {
                "total": self._overall.total,
                "success": self._overall.success,
                "failure": self._overall.failure,
                "denials": self._overall.denials,
            },
            "tools": {
                tool_name: {
                    "total": tool.total,
                    "success": tool.success,
                    "failure": tool.failure,
                    "denials": tool.denials,
                    "failure_rate": (tool.failure / tool.total) if tool.total else 0.0,
                }
                for tool_name, tool in self._by_tool.items()
            },
        }

        if self.track_latency:
            response["latency"] = {
                "overall": _build_latency_summary(self._overall.latencies_ms),
                "by_tool": {
                    tool_name: _build_latency_summary(tool.latencies_ms)
                    for tool_name, tool in self._by_tool.items()
                },
            }

        return response

    def _increment(self, aggregate: _ToolSummary, event: ToolAuditEvent) -> None:
        aggregate.total += 1
        if event.action == "deny":
            aggregate.denials += 1
            aggregate.failure += 1
            return

        if event.success:
            aggregate.success += 1
        else:
            aggregate.failure += 1
