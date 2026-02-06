import json
import os
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class ApprovalRequest:
    request_id: str
    tool_name: str
    args: dict[str, Any]
    status: str = "pending"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


APPROVALS_ENV_VAR = "VECNA_APPROVALS_PATH"


def get_approvals_path() -> Path:
    env_path = os.getenv(APPROVALS_ENV_VAR)
    if env_path:
        return Path(env_path)
    return Path.home() / ".vecna" / "tool_approvals.jsonl"


class ApprovalStore:
    def __init__(self, path: Path | None = None):
        self.path = path or get_approvals_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def request_approval(self, tool_name: str, args: dict[str, Any]) -> ApprovalRequest:
        request = ApprovalRequest(
            request_id=str(uuid.uuid4()),
            tool_name=tool_name,
            args=args,
        )
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(request)) + "\n")
        return request

    def get_pending(self) -> list[ApprovalRequest]:
        if not self.path.exists():
            return []
        pending: list[ApprovalRequest] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if data.get("status") == "pending":
                pending.append(ApprovalRequest(**data))
        return pending

    def update_status(self, request_id: str, status: str) -> bool:
        if not self.path.exists():
            return False
        updated = False
        entries: list[str] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                entries.append(line)
                continue
            if data.get("request_id") == request_id:
                data["status"] = status
                updated = True
            entries.append(json.dumps(data))
        if not updated:
            return False
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            delete=False,
            dir=self.path.parent,
        ) as handle:
            handle.write("\n".join(entries) + "\n")
            temp_path = Path(handle.name)
        temp_path.replace(self.path)
        return updated
