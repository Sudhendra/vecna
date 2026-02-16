"""Tool quota tracking for per-session and per-tool limits."""

from dataclasses import dataclass, field
from typing import Dict


@dataclass(frozen=True)
class QuotaConfig:
    per_session: int = 0
    per_tool: int = 0


@dataclass
class ToolQuotaManager:
    config: QuotaConfig
    _session_counts: Dict[str, int] = field(default_factory=dict)
    _tool_counts: Dict[str, Dict[str, int]] = field(default_factory=dict)

    def can_execute(self, session_id: str, tool_name: str) -> bool:
        if (
            self.config.per_session > 0
            and self._session_counts.get(session_id, 0) >= self.config.per_session
        ):
            return False

        if self.config.per_tool > 0:
            tool_counts = self._tool_counts.get(session_id, {})
            if tool_counts.get(tool_name, 0) >= self.config.per_tool:
                return False

        return True

    def record(self, session_id: str, tool_name: str) -> None:
        self._session_counts[session_id] = self._session_counts.get(session_id, 0) + 1

        if session_id not in self._tool_counts:
            self._tool_counts[session_id] = {}
        tool_counts = self._tool_counts[session_id]
        tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
