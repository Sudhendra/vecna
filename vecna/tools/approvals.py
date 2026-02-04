from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import tempfile
from typing import Dict, List, Optional

APPROVALS_ENV_VAR = "VECNA_APPROVALS_PATH"
LOGGER = logging.getLogger("vecna.approvals")


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
            LOGGER.warning("Invalid approvals JSON at %s", self.path)
            return
        if not isinstance(data, dict):
            return
        for request_id, payload in data.items():
            if isinstance(payload, dict):
                self._requests[request_id] = ApprovalRequest.from_dict(request_id, payload)

    def _save(self) -> None:
        payload = {request_id: request.to_dict() for request_id, request in self._requests.items()}
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                delete=False,
                dir=self.path.parent,
            ) as tmp_file:
                json.dump(payload, tmp_file, indent=2)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
                tmp_path = tmp_file.name
            os.replace(tmp_path, self.path)
            try:
                dir_flags = os.O_DIRECTORY | os.O_RDONLY
                if hasattr(os, "O_CLOEXEC"):
                    dir_flags |= os.O_CLOEXEC
                dir_fd = os.open(self.path.parent, dir_flags)
            except OSError:
                dir_fd = None
            if dir_fd is not None:
                try:
                    os.fsync(dir_fd)
                except OSError:
                    pass
                finally:
                    os.close(dir_fd)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

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
