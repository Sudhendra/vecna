import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class ToolAuditEvent:
    tool_name: str
    action: str
    risk_tier: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    reason: str = ""
    success: bool = False
    error: str = ""


class ToolAuditLogger:
    def __init__(self, log_path: Path | None = None):
        self.log_path = log_path or (Path.home() / ".vecna" / "tool_audit.jsonl")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log_event(self, event: ToolAuditEvent) -> None:
        with open(self.log_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(event)) + "\n")
