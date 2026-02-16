"""Audit logging for tool approvals and execution decisions."""

import json
from typing import Any, Dict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from vecna.tools.redaction import redact_all


@dataclass
class ToolAuditEvent:
    tool_name: str
    action: str
    risk_tier: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    reason: str = ""
    success: bool = False
    error: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)


class ToolAuditLogger:
    def __init__(self, log_path: Path | None = None, redact: bool = False):
        self.log_path = log_path or (Path.home() / ".vecna" / "tool_audit.jsonl")
        self.redact = redact
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log_event(self, event: ToolAuditEvent) -> None:
        serialized = asdict(event)
        if self.redact:
            serialized = redact_all(serialized)

        with open(self.log_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(serialized) + "\n")
