from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

APPROVALS_ENV_VAR = "VECNA_APPROVALS_PATH"


def get_approvals_path() -> Path:
    env_path = os.getenv(APPROVALS_ENV_VAR)
    if env_path:
        return Path(env_path)
    return Path.home() / ".vecna" / "approvals.json"


@dataclass
class ApprovalRequest:
    request_id: str
    tool_name: str
    status: str

    def to_dict(self) -> Dict[str, str]:
        return {"tool_name": self.tool_name, "status": self.status}

    @classmethod
    def from_dict(cls, request_id: str, data: Dict[str, str]) -> "ApprovalRequest":
        return cls(
            request_id=request_id,
            tool_name=data.get("tool_name", ""),
            status=data.get("status", "pending"),
        )


class ApprovalStore:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or get_approvals_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._requests: Dict[str, ApprovalRequest] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        if not isinstance(data, dict):
            return
        for request_id, payload in data.items():
            if isinstance(payload, dict):
                self._requests[request_id] = ApprovalRequest.from_dict(request_id, payload)

    def _save(self) -> None:
        payload = {request_id: request.to_dict() for request_id, request in self._requests.items()}
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def add_request(self, request: ApprovalRequest) -> None:
        self._requests[request.request_id] = request
        self._save()

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        return self._requests.get(request_id)

    def get_pending(self) -> List[ApprovalRequest]:
        return [req for req in self._requests.values() if req.status == "pending"]

    def update_status(self, request_id: str, status: str) -> bool:
        if request_id not in self._requests:
            return False
        self._requests[request_id].status = status
        self._save()
        return True
